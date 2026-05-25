import ast
from pathlib import Path
from typing import List

from tools.auditors.base import Auditor, Finding, Severity


MAX_FILE_LINES = 1000
MAX_FUNCTION_LINES = 60
MAX_NESTING = 6


class FileShapeAuditor(Auditor):
    name = 'file_shape'

    def check(self, files, ast_cache):
        findings: List[Finding] = []
        for path in files:
            tree = ast_cache.get(path)
            if tree is None:
                continue
            try:
                source = path.read_text()
            except OSError:
                continue
            findings.extend(self._check_file(path, tree, source))
        return findings

    def _check_file(self, path: Path, tree: ast.AST, source: str) -> List[Finding]:
        findings: List[Finding] = []
        lines = source.splitlines()
        if len(lines) > MAX_FILE_LINES:
            findings.append(
                Finding(
                    file=str(path),
                    line=1,
                    severity=Severity.WARN,
                    code='shape.file_too_large',
                    message=(
                        f'File has {len(lines)} lines (> {MAX_FILE_LINES}). '
                        'Split by responsibility.'
                    ),
                    auditor=self.name,
                )
            )
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = self._function_length(node)
                if length > MAX_FUNCTION_LINES:
                    findings.append(
                        Finding(
                            file=str(path),
                            line=node.lineno,
                            severity=Severity.WARN,
                            code='shape.function_too_long',
                            message=(
                                f'Function {node.name} is {length} lines '
                                f'(> {MAX_FUNCTION_LINES}). Extract sub-functions.'
                            ),
                            auditor=self.name,
                        )
                    )
                depth = self._max_depth(node)
                if depth > MAX_NESTING:
                    findings.append(
                        Finding(
                            file=str(path),
                            line=node.lineno,
                            severity=Severity.WARN,
                            code='shape.nesting_too_deep',
                            message=(
                                f'Function {node.name} nests {depth} levels deep '
                                f'(> {MAX_NESTING}). Flatten with early returns.'
                            ),
                            auditor=self.name,
                        )
                    )
        findings.extend(self._check_mixed_concerns(path, tree))
        return findings

    def _function_length(self, node) -> int:
        end = getattr(node, 'end_lineno', None) or node.lineno
        return max(end - node.lineno + 1, 1)

    def _max_depth(self, node, current=0):
        if not hasattr(node, 'body'):
            return current
        if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)):
            current += 1
        max_depth = current
        for child in getattr(node, 'body', []) or []:
            child_depth = self._max_depth(child, current)
            if child_depth > max_depth:
                max_depth = child_depth
        for child in getattr(node, 'orelse', []) or []:
            child_depth = self._max_depth(child, current)
            if child_depth > max_depth:
                max_depth = child_depth
        for child in getattr(node, 'finalbody', []) or []:
            child_depth = self._max_depth(child, current)
            if child_depth > max_depth:
                max_depth = child_depth
        return max_depth

    def _check_mixed_concerns(self, path: Path, tree: ast.AST) -> List[Finding]:
        findings: List[Finding] = []
        name = path.name
        imports_rest = False
        has_model_class = False
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = (
                    node.module if isinstance(node, ast.ImportFrom)
                    else (node.names[0].name if node.names else '')
                )
                if module and 'rest_framework' in module:
                    imports_rest = True
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = (
                        base.attr if isinstance(base, ast.Attribute)
                        else (base.id if isinstance(base, ast.Name) else '')
                    )
                    if base_name == 'Model':
                        has_model_class = True
        if name == 'models.py' and imports_rest:
            findings.append(
                Finding(
                    file=str(path),
                    line=1,
                    severity=Severity.WARN,
                    code='shape.mixed_concerns',
                    message='models.py imports rest_framework. Move DRF code to views/serializers.',
                    auditor=self.name,
                )
            )
        if name == 'views.py' and has_model_class:
            findings.append(
                Finding(
                    file=str(path),
                    line=1,
                    severity=Severity.WARN,
                    code='shape.mixed_concerns',
                    message='views.py defines a models.Model subclass. Move it to models.py.',
                    auditor=self.name,
                )
            )
        return findings
