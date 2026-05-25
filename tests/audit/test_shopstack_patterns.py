import unittest

from tools.auditors.shopstack_patterns import ShopstackPatternsAuditor
from tests.audit._helpers import codes, fixture_files, run_auditor


class ShopstackPatternsTests(unittest.TestCase):
    def test_model_without_tenant_base_flagged(self):
        source = (
            'from django.db import models\n'
            'class Widget(models.Model):\n'
            '    name = models.CharField(max_length=50)\n'
        )
        with fixture_files({'shopstack/stackapp/models.py': source}) as (_, paths, cache):
            findings = run_auditor(ShopstackPatternsAuditor(), paths, cache)
            self.assertIn('shopstack.missing_tenant_base_model', codes(findings))

    def test_model_inheriting_tenant_base_clean(self):
        source = (
            'class Widget(TenantBaseModel):\n'
            '    name = "x"\n'
        )
        with fixture_files({'shopstack/stackapp/models.py': source}) as (_, paths, cache):
            findings = run_auditor(ShopstackPatternsAuditor(), paths, cache)
            self.assertNotIn('shopstack.missing_tenant_base_model', codes(findings))

    def test_multi_write_without_atomic_flagged(self):
        source = (
            'def place_order():\n'
            '    order.save()\n'
            '    item.save()\n'
        )
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(ShopstackPatternsAuditor(), paths, cache)
            self.assertIn('shopstack.missing_atomic', codes(findings))

    def test_multi_write_with_atomic_clean(self):
        source = (
            'def place_order():\n'
            '    with transaction.atomic():\n'
            '        order.save()\n'
            '        item.save()\n'
        )
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(ShopstackPatternsAuditor(), paths, cache)
            self.assertNotIn('shopstack.missing_atomic', codes(findings))

    def test_single_write_not_flagged(self):
        source = 'def f():\n    order.save()\n'
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(ShopstackPatternsAuditor(), paths, cache)
            self.assertNotIn('shopstack.missing_atomic', codes(findings))


if __name__ == '__main__':
    unittest.main()
