import unittest

from tools.auditors.tenant_smells import TenantSmellsAuditor
from tests.audit._helpers import codes, fixture_files, run_auditor


class TenantSmellsTests(unittest.TestCase):
    def test_default_manager_bypass_flagged(self):
        source = 'def f():\n    return Product._default_manager.all()\n'
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(TenantSmellsAuditor(), paths, cache)
            self.assertIn('tenant.bypass_manager', codes(findings))

    def test_raw_sql_without_tenant_flagged(self):
        source = "def f():\n    return Product.objects.raw('SELECT * FROM product')\n"
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(TenantSmellsAuditor(), paths, cache)
            self.assertIn('tenant.raw_sql_no_tenant', codes(findings))

    def test_raw_sql_with_tenant_id_clean(self):
        source = (
            "def f():\n"
            "    return Product.objects.raw('SELECT * FROM product WHERE tenant_id = %s', [t])\n"
        )
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(TenantSmellsAuditor(), paths, cache)
            self.assertNotIn('tenant.raw_sql_no_tenant', codes(findings))

    def test_request_user_in_view_flagged(self):
        source = 'def f(request):\n    return request.user.id\n'
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(TenantSmellsAuditor(), paths, cache)
            self.assertIn('tenant.uses_request_user', codes(findings))

    def test_request_user_in_non_view_clean(self):
        source = 'def f(request):\n    return request.user.id\n'
        with fixture_files({'shopstack/stackapp/utils.py': source}) as (_, paths, cache):
            findings = run_auditor(TenantSmellsAuditor(), paths, cache)
            self.assertNotIn('tenant.uses_request_user', codes(findings))


if __name__ == '__main__':
    unittest.main()
