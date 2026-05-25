import ast
from pathlib import Path
from typing import List

from tools.auditors.base import Auditor, Finding, Severity


MUTATING_METHODS = {'save', 'create', 'delete', 'bulk_create', 'update'}
ALLOWED_NON_TENANT_MODELS = {
    'Tenant', 'TenantBaseModel',
    'AbstractUser', 'AbstractBaseUser', 'PermissionsMixin',
}


class ShopstackPatternsAuditor(Auditor):
    name = 'shopstack_patterns'

    def check(self, files, ast_cache):
        findings: List[Finding] = []
        for path in files:
            tree = ast_cache.get(path)
            if tree is None:
                continue
            findings.extend(self._check_models(path, tree))
            findings.extend(self._check_atomic(path, tree))
        return findings

    def _check_models(self, path: Path, tree: ast.AST) -> List[Finding]:
        findings: List[Finding] = []
        if path.name != 'models.py':
            return findings
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = self._base_names(node)
            if not base_names:
                continue
            if node.name in ALLOWED_NON_TENANT_MODELS:
                continue
            if self._inherits_tenant_base(base_names):
                continue
            if self._inherits_only_meta(base_names):
                continue
            if self._is_model_subclass(base_names):
                findings.append(
                    Finding(
                        file=str(path),
                        line=node.lineno,
                        severity=Severity.ERROR,
                        code='shopstack.missing_tenant_base_model',
                        message=(
                            f'Model {node.name} does not inherit TenantBaseModel. '
                            'Tenant scoping will not be enforced.'
                        ),
                        auditor=self.name,
                    )
                )
        return findings

    def _base_names(self, node: ast.ClassDef) -> List[str]:
        names: List[str] = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                names.append(base.id)
            elif isinstance(base, ast.Attribute):
                names.append(base.attr)
        return names

    def _inherits_tenant_base(self, base_names: List[str]) -> bool:
        return 'TenantBaseModel' in base_names

    def _inherits_only_meta(self, base_names: List[str]) -> bool:
        if not base_names:
            return False
        return all(n in ('object', 'ABC') for n in base_names)

    def _is_model_subclass(self, base_names: List[str]) -> bool:
        return 'Model' in base_names

    def _check_atomic(self, path: Path, tree: ast.AST) -> List[Finding]:
        findings: List[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if self._is_test_method(node):
                continue
            mutations = self._count_mutations(node)
            if mutations < 2:
                continue
            if self._wrapped_in_atomic(node):
                continue
            findings.append(
                Finding(
                    file=str(path),
                    line=node.lineno,
                    severity=Severity.ERROR,
                    code='shopstack.missing_atomic',
                    message=(
                        f'Function {node.name} performs {mutations} mutating ORM calls '
                        'without transaction.atomic(). Wrap multi-write flows in a transaction.'
                    ),
                    auditor=self.name,
                )
            )
        return findings

    def _is_test_method(self, node) -> bool:
        return node.name.startswith('test_') or node.name.startswith('setUp')

    def _count_mutations(self, node) -> int:
        count = 0
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if not isinstance(child.func, ast.Attribute):
                continue
            if child.func.attr in MUTATING_METHODS:
                count += 1
        return count

    def _wrapped_in_atomic(self, node) -> bool:
        for decorator in node.decorator_list:
            name = self._decorator_name(decorator)
            if name and 'atomic' in name:
                return True
        for child in ast.walk(node):
            if isinstance(child, ast.With):
                for item in child.items:
                    ctx = item.context_expr
                    name = self._call_name(ctx)
                    if name and 'atomic' in name:
                        return True
        return False

    def _decorator_name(self, node):
        if isinstance(node, ast.Call):
            return self._call_name(node)
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Name):
            return node.id
        return None

    def _call_name(self, node):
        if isinstance(node, ast.Call):
            return self._decorator_name(node.func)
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Name):
            return node.id
        return None
