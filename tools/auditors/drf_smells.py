import ast
from pathlib import Path
from typing import List

from tools.auditors.base import Auditor, Finding, Severity


LIST_VIEW_BASES = {'ListAPIView', 'ListCreateAPIView'}


class DrfSmellsAuditor(Auditor):
    name = 'drf_smells'

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
            if isinstance(node, ast.ClassDef):
                if self._is_list_view(node):
                    finding = self._check_list_view(path, node)
                    if finding:
                        findings.append(finding)
                if self._is_serializer(node):
                    findings.extend(self._check_serializer(path, node))
        return findings

    def _is_list_view(self, node: ast.ClassDef) -> bool:
        for base in node.bases:
            name = self._base_name(base)
            if name in LIST_VIEW_BASES:
                return True
        return False

    def _is_serializer(self, node: ast.ClassDef) -> bool:
        for base in node.bases:
            name = self._base_name(base)
            if name and name.endswith('Serializer'):
                return True
        return False

    def _base_name(self, node: ast.AST):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def _check_list_view(self, path: Path, node: ast.ClassDef):
        queryset_node = None
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == 'queryset':
                        queryset_node = stmt.value
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if stmt.name == 'get_queryset':
                    queryset_node = stmt
        if queryset_node is None:
            return None
        if self._has_prefetch(queryset_node):
            return None
        if not self._references_objects(queryset_node):
            return None
        return Finding(
            file=str(path),
            line=node.lineno,
            severity=Severity.ERROR,
            code='drf.list_view_no_prefetch',
            message=(
                f'List view {node.name} defines a queryset without '
                'select_related/prefetch_related. Add the appropriate '
                'prefetch for the serializer fields it exposes.'
            ),
            auditor=self.name,
        )

    def _has_prefetch(self, node: ast.AST) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr in ('select_related', 'prefetch_related'):
                    return True
        return False

    def _references_objects(self, node: ast.AST) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute) and child.attr == 'objects':
                return True
        return False

    def _check_serializer(self, path: Path, node: ast.ClassDef) -> List[Finding]:
        findings: List[Finding] = []
        for stmt in node.body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not stmt.name.startswith('get_'):
                continue
            for child in ast.walk(stmt):
                if isinstance(child, ast.Attribute) and child.attr in ('objects', 'filter'):
                    findings.append(
                        Finding(
                            file=str(path),
                            line=stmt.lineno,
                            severity=Severity.WARN,
                            code='drf.serializer_method_query',
                            message=(
                                f'SerializerMethodField "{stmt.name}" runs a DB query. '
                                'Pre-fetch the data in the view or denormalize.'
                            ),
                            auditor=self.name,
                        )
                    )
                    break
        return findings
