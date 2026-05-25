import ast
from pathlib import Path
from typing import Dict, List

from tools.auditors.base import Auditor, Finding, Severity


QUERYSET_METHODS = {'all', 'filter', 'get', 'exclude', 'order_by'}
RELATED_QS_METHODS = {'select_related', 'prefetch_related'}


def _is_objects_chain(node: ast.AST) -> bool:
    current = node
    while isinstance(current, ast.Attribute):
        if isinstance(current.value, ast.Attribute) and current.value.attr == 'objects':
            return True
        current = current.value
    return False


def _walk_calls_in_loop(loop_body: List[ast.stmt]):
    for node in loop_body:
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                yield child


class OrmSmellsAuditor(Auditor):
    name = 'orm_smells'

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
                findings.extend(self._check_for_loop(path, node))
            if isinstance(node, ast.Call):
                finding = self._check_unbounded_list(path, node)
                if finding:
                    findings.append(finding)
        findings.extend(self._check_count_then_query(path, tree))
        return findings

    def _check_for_loop(self, path: Path, loop: ast.For) -> List[Finding]:
        findings: List[Finding] = []
        for call in _walk_calls_in_loop(loop.body):
            if not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr not in QUERYSET_METHODS:
                continue
            if _is_objects_chain(call.func):
                findings.append(
                    Finding(
                        file=str(path),
                        line=call.lineno,
                        severity=Severity.ERROR,
                        code='orm.n_plus_one',
                        message=(
                            f'ORM call .{call.func.attr}(...) inside a for-loop. '
                            'Pull the queryset outside the loop or batch the query.'
                        ),
                        auditor=self.name,
                    )
                )
        loop_var_name = self._loop_var(loop)
        if loop_var_name:
            iter_call = loop.iter
            uses_prefetch = self._iter_has_prefetch(iter_call)
            if not uses_prefetch:
                for child in ast.walk(ast.Module(body=loop.body, type_ignores=[])):
                    if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                        if child.value.id != loop_var_name:
                            continue
                        if isinstance(child.ctx, ast.Load) and self._looks_like_related(child):
                            findings.append(
                                Finding(
                                    file=str(path),
                                    line=child.lineno,
                                    severity=Severity.ERROR,
                                    code='orm.related_access_no_prefetch',
                                    message=(
                                        f'Related attribute "{child.attr}" accessed on '
                                        f'loop variable "{loop_var_name}" without '
                                        'select_related/prefetch_related on the queryset.'
                                    ),
                                    auditor=self.name,
                                )
                            )
                            break
        return findings

    def _loop_var(self, loop: ast.For):
        if isinstance(loop.target, ast.Name):
            return loop.target.id
        return None

    def _iter_has_prefetch(self, node: ast.AST) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr in RELATED_QS_METHODS:
                    return True
        return False

    def _looks_like_related(self, attr: ast.Attribute) -> bool:
        name = attr.attr
        if name.startswith('_'):
            return False
        if name in ('pk', 'id', 'tenant_id'):
            return False
        if name.endswith('_set'):
            return True
        if name.endswith('_id'):
            return False
        return False

    def _check_unbounded_list(self, path: Path, call: ast.Call):
        if not isinstance(call.func, ast.Name) or call.func.id != 'list':
            return None
        if not call.args:
            return None
        inner = call.args[0]
        if not isinstance(inner, ast.Call) or not isinstance(inner.func, ast.Attribute):
            return None
        if inner.func.attr != 'all':
            return None
        if not _is_objects_chain(inner.func):
            return None
        return Finding(
            file=str(path),
            line=call.lineno,
            severity=Severity.WARN,
            code='orm.unbounded_list',
            message='list(Model.objects.all()) materializes the entire table. Paginate or filter.',
            auditor=self.name,
        )

    def _check_count_then_query(self, path: Path, tree: ast.AST) -> List[Finding]:
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            seen_counts: Dict[str, int] = {}
            for child in ast.walk(node):
                if isinstance(child, ast.Assign) and isinstance(child.value, ast.Call):
                    call = child.value
                    if isinstance(call.func, ast.Attribute) and call.func.attr == 'count':
                        if isinstance(call.func.value, ast.Name):
                            seen_counts[call.func.value.id] = call.lineno
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                    name_node = child.func.value
                    if isinstance(name_node, ast.Name) and name_node.id in seen_counts:
                        if child.func.attr in QUERYSET_METHODS:
                            findings.append(
                                Finding(
                                    file=str(path),
                                    line=child.lineno,
                                    severity=Severity.WARN,
                                    code='orm.count_then_query',
                                    message=(
                                        f'.count() on "{name_node.id}" followed by another '
                                        'query on the same name. Consider .exists() or caching.'
                                    ),
                                    auditor=self.name,
                                )
                            )
        return findings
