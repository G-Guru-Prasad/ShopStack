import unittest

from tools.auditors.orm_smells import OrmSmellsAuditor
from tests.audit._helpers import codes, fixture_files, run_auditor


class OrmSmellsTests(unittest.TestCase):
    def test_n_plus_one_in_for_loop_flagged(self):
        source = (
            'def f(ids):\n'
            '    for pid in ids:\n'
            '        Product.objects.get(id=pid)\n'
        )
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(OrmSmellsAuditor(), paths, cache)
            self.assertIn('orm.n_plus_one', codes(findings))

    def test_query_outside_loop_not_flagged(self):
        source = (
            'def f():\n'
            '    items = Product.objects.all()\n'
            '    for item in items:\n'
            '        pass\n'
        )
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(OrmSmellsAuditor(), paths, cache)
            self.assertNotIn('orm.n_plus_one', codes(findings))

    def test_unbounded_list_warn(self):
        source = (
            'def f():\n'
            '    return list(Product.objects.all())\n'
        )
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(OrmSmellsAuditor(), paths, cache)
            self.assertIn('orm.unbounded_list', codes(findings))

    def test_count_then_query_warn(self):
        source = (
            'def f():\n'
            '    qs = Product.objects.filter(active=True)\n'
            '    n = qs.count()\n'
            '    return qs.filter(price__gt=0)\n'
        )
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(OrmSmellsAuditor(), paths, cache)
            self.assertIn('orm.count_then_query', codes(findings))


if __name__ == '__main__':
    unittest.main()
