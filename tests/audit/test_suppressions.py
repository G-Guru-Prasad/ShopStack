import unittest
from pathlib import Path

from tools import suppressions
from tools.auditors.base import Finding, Severity


class SuppressionsTests(unittest.TestCase):
    def _ctx(self, file_str: str, source: str):
        ctx, findings = suppressions.build_context({Path(file_str): source})
        return ctx, findings

    def _finding(self, file_str: str, line: int, code: str) -> Finding:
        return Finding(
            file=file_str,
            line=line,
            severity=Severity.ERROR,
            code=code,
            message='x',
            auditor='test',
        )

    def test_inline_suppression_with_reason(self):
        source = 'x = 1  # audit: ignore orm.n_plus_one -- legacy code\n'
        ctx, no_reason = self._ctx('a.py', source)
        self.assertEqual(no_reason, [])
        finding = self._finding('a.py', 1, 'orm.n_plus_one')
        self.assertTrue(suppressions.is_suppressed(ctx, finding))

    def test_inline_suppression_without_reason_emits_error(self):
        source = 'x = 1  # audit: ignore orm.n_plus_one\n'
        ctx, no_reason = self._ctx('a.py', source)
        self.assertEqual(len(no_reason), 1)
        self.assertEqual(no_reason[0].code, 'audit.suppression_no_reason')

    def test_function_scope_suppression(self):
        source = (
            '# audit: ignore-function all -- function-wide skip needed for legacy\n'
            'def f():\n'
            '    a = 1\n'
            '    b = 2\n'
        )
        ctx, _ = self._ctx('a.py', source)
        finding = self._finding('a.py', 3, 'orm.n_plus_one')
        self.assertTrue(suppressions.is_suppressed(ctx, finding))

    def test_file_scope_suppression(self):
        source = '# audit: ignore-file all -- generated file\nx = 1\n'
        ctx, _ = self._ctx('a.py', source)
        finding = self._finding('a.py', 1, 'orm.n_plus_one')
        self.assertTrue(suppressions.is_suppressed(ctx, finding))

    def test_stale_suppression_flagged(self):
        source = 'x = 1  # audit: ignore orm.n_plus_one -- no match expected\n'
        ctx, _ = self._ctx('a.py', source)
        stale = suppressions.stale_findings(ctx)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0].code, 'audit.stale_suppression')


if __name__ == '__main__':
    unittest.main()
