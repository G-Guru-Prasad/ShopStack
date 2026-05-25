import unittest

from tools.auditors.python_perf import PythonPerfAuditor
from tests.audit._helpers import codes, fixture_files, run_auditor


class PythonPerfTests(unittest.TestCase):
    def test_loop_invariant_re_compile_flagged(self):
        source = (
            'import re\n'
            'def f(items):\n'
            '    for it in items:\n'
            '        re.compile("foo").match(it)\n'
        )
        with fixture_files({'shopstack/stackapp/x.py': source}) as (_, paths, cache):
            findings = run_auditor(PythonPerfAuditor(), paths, cache)
            self.assertIn('perf.work_in_loop', codes(findings))

    def test_list_build_loop_flagged(self):
        source = (
            'def f(items):\n'
            '    out = []\n'
            '    for it in items:\n'
            '        out.append(it * 2)\n'
            '    return out\n'
        )
        with fixture_files({'shopstack/stackapp/x.py': source}) as (_, paths, cache):
            findings = run_auditor(PythonPerfAuditor(), paths, cache)
            self.assertIn('perf.list_build_loop', codes(findings))

    def test_list_membership_in_loop_flagged(self):
        source = (
            'def f(items, banned):\n'
            '    for it in items:\n'
            '        if it in banned:\n'
            '            pass\n'
        )
        with fixture_files({'shopstack/stackapp/x.py': source}) as (_, paths, cache):
            findings = run_auditor(PythonPerfAuditor(), paths, cache)
            self.assertIn('perf.list_membership_in_loop', codes(findings))

    def test_clean_loop_no_warnings(self):
        source = (
            'def f(items):\n'
            '    out = [it for it in items]\n'
            '    return out\n'
        )
        with fixture_files({'shopstack/stackapp/x.py': source}) as (_, paths, cache):
            findings = run_auditor(PythonPerfAuditor(), paths, cache)
            self.assertEqual(findings, [])


if __name__ == '__main__':
    unittest.main()
