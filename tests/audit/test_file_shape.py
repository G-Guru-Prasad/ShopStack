import unittest

from tools.auditors.file_shape import FileShapeAuditor
from tests.audit._helpers import codes, fixture_files, run_auditor


class FileShapeTests(unittest.TestCase):
    def test_file_too_large_warn(self):
        source = '\n'.join([f'x{i} = {i}' for i in range(450)])
        with fixture_files({'shopstack/stackapp/x.py': source}) as (_, paths, cache):
            findings = run_auditor(FileShapeAuditor(), paths, cache)
            self.assertIn('shape.file_too_large', codes(findings))

    def test_function_too_long_warn(self):
        body = '\n'.join([f'    a{i} = {i}' for i in range(60)])
        source = f'def f():\n{body}\n'
        with fixture_files({'shopstack/stackapp/x.py': source}) as (_, paths, cache):
            findings = run_auditor(FileShapeAuditor(), paths, cache)
            self.assertIn('shape.function_too_long', codes(findings))

    def test_nesting_too_deep_warn(self):
        source = (
            'def f(x):\n'
            '    if x:\n'
            '        for i in range(10):\n'
            '            if i:\n'
            '                with open("/tmp") as fp:\n'
            '                    if fp:\n'
            '                        return 1\n'
        )
        with fixture_files({'shopstack/stackapp/x.py': source}) as (_, paths, cache):
            findings = run_auditor(FileShapeAuditor(), paths, cache)
            self.assertIn('shape.nesting_too_deep', codes(findings))

    def test_mixed_concerns_models_imports_rest(self):
        source = 'from rest_framework import serializers\n'
        with fixture_files({'shopstack/stackapp/models.py': source}) as (_, paths, cache):
            findings = run_auditor(FileShapeAuditor(), paths, cache)
            self.assertIn('shape.mixed_concerns', codes(findings))

    def test_short_file_clean(self):
        source = 'x = 1\n'
        with fixture_files({'shopstack/stackapp/x.py': source}) as (_, paths, cache):
            findings = run_auditor(FileShapeAuditor(), paths, cache)
            self.assertEqual(findings, [])


if __name__ == '__main__':
    unittest.main()
