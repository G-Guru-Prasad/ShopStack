import ast
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from tools.auditors.base import Auditor, Finding, Severity


MUTATING_CLIENT_METHODS = {'post', 'patch', 'put', 'delete'}
MUTATING_ORM_METHODS = {'save', 'create', 'delete', 'bulk_create'}
DB_READ_HINTS = {'get', 'filter', 'count', 'exists', 'first', 'refresh_from_db', 'all'}
TENANT_BASE_NAMES = {
    'ListAPIView', 'RetrieveAPIView', 'CreateAPIView',
    'UpdateAPIView', 'DestroyAPIView',
    'ListCreateAPIView', 'RetrieveUpdateAPIView',
    'RetrieveUpdateDestroyAPIView', 'APIView',
}


class TestCoverageAuditor(Auditor):
    name = 'test_coverage'

    def __init__(self, coverage_file: Optional[str] = None, repo_root: Optional[Path] = None):
        self.coverage_file = coverage_file
        self.repo_root = repo_root or Path.cwd()

    def check(self, files, ast_cache):
        findings: List[Finding] = []
        source_files = [
            p for p in files
            if p.suffix == '.py'
            and 'migrations' not in p.parts
            and not self._is_test_file(p)
        ]
        test_files = [p for p in files if self._is_test_file(p)]

        missing_lines = self._collect_missing_lines(source_files)
        for path, lines in missing_lines.items():
            for line in sorted(lines):
                findings.append(
                    Finding(
                        file=str(path),
                        line=line,
                        severity=Severity.ERROR,
                        code='test.uncovered_lines',
                        message=(
                            'Line not covered by the test suite. Add or extend a test.'
                        ),
                        auditor=self.name,
                    )
                )

        for path in test_files:
            tree = ast_cache.get(path)
            if tree is None:
                continue
            findings.extend(self._check_integrity_asserts(path, tree))

        findings.extend(self._check_tenant_isolation(source_files, test_files, ast_cache))
        return findings

    def _is_test_file(self, path: Path) -> bool:
        name = path.name
        if name == 'tests.py' or name.startswith('test_') or name.startswith('tests_'):
            return True
        return 'tests' in path.parts

    def _collect_missing_lines(self, source_files: List[Path]) -> Dict[Path, Set[int]]:
        if not source_files:
            return {}
        try:
            from coverage import Coverage
        except ImportError:
            return {}

        coverage_path = self._resolve_coverage_file()
        if coverage_path is None:
            return {}
        cov = Coverage(data_file=str(coverage_path))
        try:
            cov.load()
        except Exception:
            return {}

        result: Dict[Path, Set[int]] = {}
        data = cov.get_data()
        measured_files = {Path(p).resolve() for p in data.measured_files()}
        for source in source_files:
            src_resolved = source.resolve()
            if src_resolved not in measured_files:
                continue
            try:
                _, _, missing, _ = cov.analysis2(str(src_resolved))[:4]
            except Exception:
                try:
                    analysis = cov.analysis2(str(src_resolved))
                    missing = analysis[3]
                except Exception:
                    continue
            if missing:
                result[source] = set(missing)
        return result

    def _resolve_coverage_file(self) -> Optional[Path]:
        if self.coverage_file:
            path = Path(self.coverage_file)
            if path.exists():
                return path
            return None
        candidates = [
            self.repo_root / '.coverage',
            self.repo_root / 'shopstack' / '.coverage',
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return self._run_coverage()

    def _run_coverage(self) -> Optional[Path]:
        rcfile = self.repo_root / 'shopstack' / '.coveragerc'
        if not rcfile.exists():
            return None
        manage = self.repo_root / 'shopstack' / 'manage.py'
        if not manage.exists():
            return None
        env = os.environ.copy()
        try:
            subprocess.run(
                [
                    'coverage', 'run',
                    f'--rcfile={rcfile}',
                    'manage.py', 'test', '--keepdb', '--verbosity=0',
                ],
                cwd=manage.parent,
                env=env,
                check=False,
                capture_output=True,
                timeout=600,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        candidate = manage.parent / '.coverage'
        if candidate.exists():
            return candidate
        return None

    def _check_integrity_asserts(self, path: Path, tree: ast.AST) -> List[Finding]:
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith('test_'):
                continue
            mutating = self._has_mutating_call(node)
            if not mutating:
                continue
            if self._has_db_read(node):
                continue
            findings.append(
                Finding(
                    file=str(path),
                    line=node.lineno,
                    severity=Severity.ERROR,
                    code='test.missing_integrity_assert',
                    message=(
                        f'Test {node.name} mutates state but never reads it back. '
                        'Add an assertion that re-queries the DB or refresh_from_db().'
                    ),
                    auditor=self.name,
                )
            )
        return findings

    def _has_mutating_call(self, node) -> bool:
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if not isinstance(child.func, ast.Attribute):
                continue
            attr = child.func.attr
            if attr in MUTATING_ORM_METHODS:
                return True
            if attr in MUTATING_CLIENT_METHODS:
                owner = self._owner_chain(child.func.value)
                if owner and 'client' in owner:
                    return True
        return False

    def _has_db_read(self, node) -> bool:
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if not isinstance(child.func, ast.Attribute):
                continue
            if child.func.attr in DB_READ_HINTS:
                return True
        return False

    def _owner_chain(self, node) -> str:
        parts: List[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return '.'.join(reversed(parts))

    def _check_tenant_isolation(
        self,
        source_files: List[Path],
        test_files: List[Path],
        ast_cache,
    ) -> List[Finding]:
        findings: List[Finding] = []
        new_views = self._collect_views(source_files, ast_cache)
        if not new_views:
            return findings
        test_signal = self._tests_have_tenant_switch(test_files, ast_cache)
        if test_signal:
            return findings
        for path, view_name, line in new_views:
            findings.append(
                Finding(
                    file=str(path),
                    line=line,
                    severity=Severity.ERROR,
                    code='test.missing_tenant_isolation',
                    message=(
                        f'View {view_name} touches a TenantBaseModel-style model but '
                        'no changed test switches tenant_id via ThreadVaribales to '
                        'assert cross-tenant isolation.'
                    ),
                    auditor=self.name,
                )
            )
        return findings

    def _collect_views(self, files: List[Path], ast_cache) -> List[Tuple[Path, str, int]]:
        result: List[Tuple[Path, str, int]] = []
        for path in files:
            name = path.name
            if name not in ('views.py',) and not name.startswith('views_'):
                continue
            tree = ast_cache.get(path)
            if tree is None:
                continue
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                if any(
                    (isinstance(b, ast.Name) and b.id in TENANT_BASE_NAMES)
                    or (isinstance(b, ast.Attribute) and b.attr in TENANT_BASE_NAMES)
                    for b in node.bases
                ):
                    result.append((path, node.name, node.lineno))
        return result

    def _tests_have_tenant_switch(self, test_files: List[Path], ast_cache) -> bool:
        for path in test_files:
            tree = ast_cache.get(path)
            if tree is None:
                continue
            source = path.read_text() if path.exists() else ''
            if 'ThreadVaribales' in source and 'tenant_id' in source:
                return True
        return False
