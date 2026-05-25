import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

from tools.auditors.base import Finding, Severity


INLINE_RE = re.compile(r'#\s*audit:\s*ignore\s+([\w.,*-]+)(.*)$')
FUNC_RE = re.compile(r'#\s*audit:\s*ignore-function\s+([\w.,*-]+)(.*)$')
FILE_RE = re.compile(r'#\s*audit:\s*ignore-file\s+([\w.,*-]+)(.*)$')
REASON_RE = re.compile(r'--\s*(\S.*\S|\S)')


@dataclass
class Suppression:
    file: str
    line: int
    scope: str
    codes: Set[str]
    reason: str
    raw: str


@dataclass
class SuppressionContext:
    by_file: Dict[str, List[Suppression]]
    used: Set[int]


def _parse_codes(raw: str) -> Set[str]:
    return {c.strip() for c in raw.split(',') if c.strip()}


def _extract_reason(tail: str) -> str:
    match = REASON_RE.search(tail)
    if not match:
        return ''
    return match.group(1).strip()


def _function_scope_end(lines: List[str], def_line: int) -> int:
    if def_line >= len(lines):
        return def_line
    base_indent = len(lines[def_line]) - len(lines[def_line].lstrip())
    end = def_line
    for idx in range(def_line + 1, len(lines)):
        stripped = lines[idx].strip()
        if not stripped or stripped.startswith('#'):
            continue
        indent = len(lines[idx]) - len(lines[idx].lstrip())
        if indent <= base_indent:
            break
        end = idx
    return end


def parse_suppressions(file_path: Path, source: str) -> Tuple[List[Suppression], List[Finding]]:
    lines = source.splitlines()
    suppressions: List[Suppression] = []
    findings: List[Finding] = []
    file_str = str(file_path)

    for idx, raw_line in enumerate(lines):
        line_no = idx + 1
        stripped = raw_line.strip()

        file_match = FILE_RE.search(stripped)
        func_match = FUNC_RE.search(stripped)
        inline_match = INLINE_RE.search(stripped)

        if file_match:
            codes_raw, tail = file_match.group(1), file_match.group(2)
            reason = _extract_reason(tail)
            sup = Suppression(
                file=file_str,
                line=line_no,
                scope='file',
                codes=_parse_codes(codes_raw),
                reason=reason,
                raw=stripped,
            )
            suppressions.append(sup)
            if not reason:
                findings.append(_no_reason_finding(file_str, line_no, stripped))
            continue

        if func_match:
            codes_raw, tail = func_match.group(1), func_match.group(2)
            reason = _extract_reason(tail)
            anchor = _find_function_def_line(lines, idx)
            scope_end = _function_scope_end(lines, anchor)
            sup = Suppression(
                file=file_str,
                line=anchor + 1,
                scope='function',
                codes=_parse_codes(codes_raw),
                reason=reason,
                raw=stripped,
            )
            sup.__dict__['_range'] = (anchor + 1, scope_end + 1)
            suppressions.append(sup)
            if not reason:
                findings.append(_no_reason_finding(file_str, line_no, stripped))
            continue

        if inline_match:
            codes_raw, tail = inline_match.group(1), inline_match.group(2)
            reason = _extract_reason(tail)
            target_line = line_no if raw_line.lstrip().startswith('#') is False else line_no + 1
            sup = Suppression(
                file=file_str,
                line=target_line,
                scope='inline',
                codes=_parse_codes(codes_raw),
                reason=reason,
                raw=stripped,
            )
            suppressions.append(sup)
            if not reason:
                findings.append(_no_reason_finding(file_str, line_no, stripped))

    return suppressions, findings


def _find_function_def_line(lines: List[str], comment_idx: int) -> int:
    for idx in range(comment_idx + 1, len(lines)):
        stripped = lines[idx].strip()
        if stripped.startswith('def ') or stripped.startswith('async def '):
            return idx
        if stripped.startswith('@'):
            continue
        if stripped == '' or stripped.startswith('#'):
            continue
        return idx
    return comment_idx


def _no_reason_finding(file_str: str, line_no: int, raw: str) -> Finding:
    return Finding(
        file=file_str,
        line=line_no,
        severity=Severity.ERROR,
        code='audit.suppression_no_reason',
        message=(
            'Audit suppression missing mandatory reason. Use '
            '"# audit: ignore <code> -- <reason>".'
        ),
        auditor='suppressions',
    )


def build_context(
    file_sources: Dict[Path, str],
) -> Tuple[SuppressionContext, List[Finding]]:
    by_file: Dict[str, List[Suppression]] = {}
    findings: List[Finding] = []
    for path, source in file_sources.items():
        suppressions, no_reason = parse_suppressions(path, source)
        by_file[str(path)] = suppressions
        findings.extend(no_reason)
    return SuppressionContext(by_file=by_file, used=set()), findings


def is_suppressed(
    context: SuppressionContext,
    finding: Finding,
) -> bool:
    if finding.code == 'audit.suppression_no_reason':
        return False
    suppressions = context.by_file.get(finding.file, [])
    for sup in suppressions:
        if not sup.reason:
            continue
        if 'all' not in sup.codes and finding.code not in sup.codes:
            continue
        if sup.scope == 'file':
            context.used.add(id(sup))
            return True
        if sup.scope == 'function':
            start, end = sup.__dict__.get('_range', (sup.line, sup.line))
            if start <= finding.line <= end:
                context.used.add(id(sup))
                return True
        if sup.scope == 'inline':
            if finding.line == sup.line:
                context.used.add(id(sup))
                return True
    return False


def stale_findings(context: SuppressionContext) -> List[Finding]:
    findings: List[Finding] = []
    for file_str, suppressions in context.by_file.items():
        for sup in suppressions:
            if not sup.reason:
                continue
            if id(sup) in context.used:
                continue
            findings.append(
                Finding(
                    file=file_str,
                    line=sup.line,
                    severity=Severity.WARN,
                    code='audit.stale_suppression',
                    message=(
                        f'Suppression "{sup.raw}" matched no finding. '
                        'Remove it or fix the underlying issue.'
                    ),
                    auditor='suppressions',
                )
            )
    return findings
