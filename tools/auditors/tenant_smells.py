import ast
from pathlib import Path
from typing import List

from tools.auditors.base import Auditor, Finding, Severity


BYPASS_ATTRS = {'_default_manager', '_base_manager'}
RAW_SQL_ATTRS = {'raw'}


class TenantSmellsAuditor(Auditor):
    name = 'tenant_smells'

    def check(self, files, ast_cache):
        findings: List[Finding] = []
        for path in files:
            tree = ast_cache.get(path)
            if tree is None:
                continue
            if self._is_management_command(path):
                continue
            findings.extend(self._check_bypass(path, tree))
            findings.extend(self._check_raw_sql(path, tree))
            findings.extend(self._check_request_user(path, tree))
        return findings

    def _is_management_command(self, path: Path) -> bool:
        parts = path.parts
        return 'management' in parts and 'commands' in parts

    def _check_bypass(self, path: Path, tree: ast.AST) -> List[Finding]:
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr in BYPASS_ATTRS:
                findings.append(
                    Finding(
                        file=str(path),
                        line=node.lineno,
                        severity=Severity.ERROR,
                        code='tenant.bypass_manager',
                        message=(
                            f'Use of {node.attr} bypasses TenantBasedManager. '
                            'Use .objects instead, or scope tenant explicitly.'
                        ),
                        auditor=self.name,
                    )
                )
        return findings

    def _check_raw_sql(self, path: Path, tree: ast.AST) -> List[Finding]:
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == 'raw' and node.args:
                    sql = self._sql_text(node.args[0])
                    if sql is not None and 'tenant_id' not in sql.lower():
                        findings.append(
                            Finding(
                                file=str(path),
                                line=node.lineno,
                                severity=Severity.ERROR,
                                code='tenant.raw_sql_no_tenant',
                                message=(
                                    'Model.objects.raw(...) without tenant_id in the SQL. '
                                    'Add a WHERE tenant_id = %s clause.'
                                ),
                                auditor=self.name,
                            )
                        )
                if node.func.attr == 'cursor':
                    parent = self._cursor_owner(node)
                    if parent and parent == 'connection':
                        findings.append(
                            Finding(
                                file=str(path),
                                line=node.lineno,
                                severity=Severity.ERROR,
                                code='tenant.raw_sql_no_tenant',
                                message=(
                                    'connection.cursor() raw SQL escapes the tenant manager. '
                                    'Verify and embed tenant_id in the query.'
                                ),
                                auditor=self.name,
                            )
                        )
        return findings

    def _cursor_owner(self, call: ast.Call):
        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
            return call.func.value.id
        return None

    def _sql_text(self, node: ast.AST):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
            return ' '.join(parts)
        return None

    def _check_request_user(self, path: Path, tree: ast.AST) -> List[Finding]:
        findings: List[Finding] = []
        if not self._looks_like_view_module(path):
            return findings
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr not in ('id', 'pk'):
                continue
            target = node.value
            if (
                isinstance(target, ast.Attribute)
                and target.attr == 'user'
                and isinstance(target.value, ast.Name)
                and target.value.id == 'request'
            ):
                findings.append(
                    Finding(
                        file=str(path),
                        line=node.lineno,
                        severity=Severity.ERROR,
                        code='tenant.uses_request_user',
                        message=(
                            'request.user.id used for tenant/user context. '
                            'Use ThreadVaribales().get_val("user_id") instead.'
                        ),
                        auditor=self.name,
                    )
                )
        return findings

    def _looks_like_view_module(self, path: Path) -> bool:
        name = path.name
        return name in ('views.py',) or name.startswith('views_')
