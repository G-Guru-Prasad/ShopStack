import ast
from pathlib import Path
from typing import List, Set

from tools.auditors.base import Auditor, Finding, Severity


LOOP_INVARIANT_CALLS = {'re.compile'}


def _qualified_name(node: ast.AST) -> str:
    parts: List[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return '.'.join(reversed(parts))


class PythonPerfAuditor(Auditor):
    name = 'python_perf'

    def check(self, files, ast_cache):
        findings: List[Finding] = []
        for path in files:
            tree = ast_cache.get(path)
            if tree is None:
                continue
            findings.extend(self._check_file(path, tree))
        return findings

    def _check_file(self, path: Path, tree: ast.AST) -> List[Finding]:
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.For):
                findings.extend(self._check_loop(path, node))
        return findings

    def _check_loop(self, path: Path, loop: ast.For) -> List[Finding]:
        findings: List[Finding] = []
        loop_vars = self._loop_vars(loop)
        invariant_findings = self._work_in_loop(path, loop)
        findings.extend(invariant_findings)
        list_build = self._list_build(path, loop)
        if list_build:
            findings.append(list_build)
        findings.extend(self._membership(path, loop, loop_vars))
        return findings

    def _loop_vars(self, loop: ast.For) -> Set[str]:
        result: Set[str] = set()

        def _collect(target):
            if isinstance(target, ast.Name):
                result.add(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    _collect(elt)
        _collect(loop.target)
        return result

    def _work_in_loop(self, path: Path, loop: ast.For) -> List[Finding]:
        findings: List[Finding] = []
        for stmt in loop.body:
            for child in ast.walk(stmt):
                if not isinstance(child, ast.Call):
                    continue
                qname = _qualified_name(child.func)
                if qname in LOOP_INVARIANT_CALLS and self._call_is_invariant(child, loop):
                    findings.append(
                        Finding(
                            file=str(path),
                            line=child.lineno,
                            severity=Severity.WARN,
                            code='perf.work_in_loop',
                            message=(
                                f'{qname}(...) is loop-invariant. '
                                'Move it outside the loop.'
                            ),
                            auditor=self.name,
                        )
                    )
        return findings

    def _call_is_invariant(self, call: ast.Call, loop: ast.For) -> bool:
        loop_vars = self._loop_vars(loop)
        for child in ast.walk(call):
            if isinstance(child, ast.Name) and child.id in loop_vars:
                return False
        return True

    def _list_build(self, path: Path, loop: ast.For):
        if len(loop.body) != 1:
            return None
        stmt = loop.body[0]
        if not isinstance(stmt, ast.Expr):
            return None
        call = stmt.value
        if not isinstance(call, ast.Call):
            return None
        if not isinstance(call.func, ast.Attribute) or call.func.attr != 'append':
            return None
        return Finding(
            file=str(path),
            line=loop.lineno,
            severity=Severity.WARN,
            code='perf.list_build_loop',
            message=(
                'List built with .append inside a for-loop. '
                'A list comprehension is clearer and faster.'
            ),
            auditor=self.name,
        )

    def _membership(self, path: Path, loop: ast.For, loop_vars: Set[str]) -> List[Finding]:
        findings: List[Finding] = []
        for stmt in loop.body:
            for child in ast.walk(stmt):
                if not isinstance(child, ast.Compare):
                    continue
                for op, comparator in zip(child.ops, child.comparators):
                    if not isinstance(op, ast.In):
                        continue
                    if not isinstance(comparator, (ast.Name, ast.Attribute)):
                        continue
                    container_name = (
                        comparator.id if isinstance(comparator, ast.Name) else None
                    )
                    if container_name and container_name in loop_vars:
                        continue
                    findings.append(
                        Finding(
                            file=str(path),
                            line=child.lineno,
                            severity=Severity.WARN,
                            code='perf.list_membership_in_loop',
                            message=(
                                'Membership test against a sequence inside a loop. '
                                'If the container is loop-invariant, convert to a set.'
                            ),
                            auditor=self.name,
                        )
                    )
        return findings
