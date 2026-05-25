#!/usr/bin/env python3
"""ShopStack codebase auditor CLI.

Runs deterministic checks (ORM smells, tenant safety, ShopStack
patterns, test discipline, etc.) on the diff or whole repo. Emits
terminal + markdown reports. Exits non-zero on ERROR findings.
"""
import argparse
import ast
import fnmatch
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from tools import suppressions as suppressions_mod
from tools.auditors import CHEAP_AUDITORS, TestCoverageAuditor
from tools.auditors.base import Finding, Severity
from tools.reporters import markdown as markdown_reporter
from tools.reporters import terminal as terminal_reporter


EXCLUDE_PATTERNS = [
    '*/migrations/*',
    '*/tests.py',
    '*/test_*.py',
    '*/tests_*.py',
    '*/__init__.py',
    '*/wsgi.py',
    '*/asgi.py',
    '*/settings.py',
    'manage.py',
    '*/manage.py',
]


def _excluded(path: Path) -> bool:
    rel = str(path)
    for pattern in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, f'**/{pattern}'):
            return True
    name = path.name
    if name in ('manage.py',):
        return True
    return False


def _run_git(args: List[str]) -> str:
    result = subprocess.run(
        ['git', *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _git_changed_files(since: Optional[str]) -> List[Path]:
    paths: set = set()
    if since:
        out = _run_git(['diff', '--name-only', '--diff-filter=AM', f'{since}...HEAD'])
        for line in out.splitlines():
            line = line.strip()
            if line:
                paths.add(line)
        return sorted(REPO_ROOT / p for p in paths if p.endswith('.py'))

    out = _run_git(['diff', '--name-only', '--diff-filter=AM', 'HEAD'])
    for line in out.splitlines():
        line = line.strip()
        if line:
            paths.add(line)
    out = _run_git(['diff', '--name-only', '--diff-filter=AM', '--cached'])
    for line in out.splitlines():
        line = line.strip()
        if line:
            paths.add(line)
    out = _run_git(['ls-files', '--others', '--exclude-standard'])
    for line in out.splitlines():
        line = line.strip()
        if line:
            paths.add(line)
    return sorted(REPO_ROOT / p for p in paths if p.endswith('.py'))


def _all_python_files() -> List[Path]:
    root = REPO_ROOT / 'shopstack'
    return sorted(root.rglob('*.py'))


def discover_files(args: argparse.Namespace) -> List[Path]:
    if args.all:
        candidates = _all_python_files()
    else:
        candidates = _git_changed_files(args.since)
    result: List[Path] = []
    for path in candidates:
        if not path.exists():
            continue
        if _excluded(path):
            continue
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            continue
        rel_str = str(rel)
        if not rel_str.startswith('shopstack/') and not rel_str.startswith('tools/'):
            continue
        if rel_str.startswith('tools/'):
            continue
        result.append(path)
    return result


def parse_files(files: List[Path]) -> (Dict[Path, ast.AST], Dict[Path, str]):
    ast_cache: Dict[Path, ast.AST] = {}
    sources: Dict[Path, str] = {}
    for path in files:
        try:
            text = path.read_text()
        except OSError:
            continue
        sources[path] = text
        try:
            ast_cache[path] = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
    return ast_cache, sources


def _to_rel(finding: Finding) -> Finding:
    path = Path(finding.file)
    try:
        rel = path.resolve().relative_to(REPO_ROOT)
    except (ValueError, OSError):
        rel = path
    return Finding(
        file=str(rel),
        line=finding.line,
        severity=finding.severity,
        code=finding.code,
        message=finding.message,
        auditor=finding.auditor,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='ShopStack codebase auditor')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--diff', action='store_true', help='staged+unstaged vs HEAD (default)')
    mode.add_argument('--all', action='store_true', help='whole shopstack/ tree')
    parser.add_argument('--since', help='diff vs git ref (e.g. origin/main)')
    parser.add_argument(
        '--format',
        choices=['terminal', 'markdown', 'both'],
        default='both',
    )
    parser.add_argument('--report-dir', default='reports')
    parser.add_argument('--no-block', action='store_true', help='exit 0 even with ERRORs')
    parser.add_argument(
        '--no-fail-fast',
        action='store_true',
        help='run coverage auditor even if earlier auditors raised ERROR',
    )
    parser.add_argument(
        '--coverage-file',
        help='path to an existing .coverage file to consume (CI mode)',
    )
    parser.add_argument(
        '--skip-coverage',
        action='store_true',
        help='skip the test_coverage auditor entirely',
    )
    args = parser.parse_args(argv)

    if args.all:
        mode_label = 'all'
    elif args.since:
        mode_label = f'since:{args.since}'
    else:
        mode_label = 'diff'

    files = discover_files(args)
    ast_cache, sources = parse_files(files)
    context, sup_findings = suppressions_mod.build_context(sources)

    findings: List[Finding] = list(sup_findings)

    for auditor_cls in CHEAP_AUDITORS:
        auditor = auditor_cls()
        try:
            findings.extend(auditor.check(files, ast_cache))
        except Exception as exc:
            findings.append(
                Finding(
                    file=str(REPO_ROOT),
                    line=0,
                    severity=Severity.ERROR,
                    code='audit.internal_error',
                    message=f'{auditor.name} crashed: {exc!r}',
                    auditor=auditor.name,
                )
            )

    has_error_so_far = any(f.severity is Severity.ERROR for f in findings)

    if not args.skip_coverage and (args.no_fail_fast or not has_error_so_far):
        coverage_auditor = TestCoverageAuditor(
            coverage_file=args.coverage_file,
            repo_root=REPO_ROOT,
        )
        try:
            findings.extend(coverage_auditor.check(files, ast_cache))
        except Exception as exc:
            findings.append(
                Finding(
                    file=str(REPO_ROOT),
                    line=0,
                    severity=Severity.ERROR,
                    code='audit.internal_error',
                    message=f'test_coverage crashed: {exc!r}',
                    auditor='test_coverage',
                )
            )

    findings = [_to_rel(f) for f in findings]

    kept: List[Finding] = []
    for finding in findings:
        if suppressions_mod.is_suppressed(context, finding):
            continue
        kept.append(finding)
    kept.extend(suppressions_mod.stale_findings(context))

    kept.sort(key=lambda f: (f.severity.value, f.file, f.line, f.code))

    timestamp = datetime.now()
    sup_used_count = len(context.used)

    if args.format in ('terminal', 'both'):
        terminal_report = terminal_reporter.render(
            kept, sup_used_count, mode_label,
        )
        sys.stdout.write(terminal_report)

    if args.format in ('markdown', 'both'):
        md = markdown_reporter.render(kept, context, mode_label, timestamp)
        report_dir = (REPO_ROOT / args.report_dir).resolve()
        path = markdown_reporter.write(md, report_dir, timestamp)
        sys.stdout.write(f'\nMarkdown report: {path.relative_to(REPO_ROOT)}\n')

    has_error = any(f.severity is Severity.ERROR for f in kept)
    if has_error and not args.no_block:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
