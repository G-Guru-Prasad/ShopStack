import unittest

from tools.auditors.test_coverage import TestCoverageAuditor
from tests.audit._helpers import codes, fixture_files, run_auditor


class TestCoverageAuditorTests(unittest.TestCase):
    def test_missing_integrity_assert_flagged(self):
        source = (
            'class T:\n'
            '    def test_create(self):\n'
            '        self.client.post("/api/cart/items/", {"x": 1})\n'
        )
        files = {'shopstack/stackapp/tests/test_cart.py': source}
        with fixture_files(files) as (_, paths, cache):
            findings = run_auditor(TestCoverageAuditor(), paths, cache)
            self.assertIn('test.missing_integrity_assert', codes(findings))

    def test_mutating_test_with_db_read_clean(self):
        source = (
            'class T:\n'
            '    def test_create(self):\n'
            '        self.client.post("/api/cart/items/", {"x": 1})\n'
            '        self.assertEqual(CartItem.objects.count(), 1)\n'
        )
        files = {'shopstack/stackapp/tests/test_cart.py': source}
        with fixture_files(files) as (_, paths, cache):
            findings = run_auditor(TestCoverageAuditor(), paths, cache)
            self.assertNotIn('test.missing_integrity_assert', codes(findings))

    def test_tenant_isolation_missing_flagged(self):
        view_src = (
            'class WidgetListView(ListAPIView):\n'
            '    queryset = Widget.objects.all()\n'
        )
        test_src = (
            'class T:\n'
            '    def test_list(self):\n'
            '        self.client.get("/api/widgets/")\n'
        )
        files = {
            'shopstack/stackapp/views.py': view_src,
            'shopstack/stackapp/tests/test_widget.py': test_src,
        }
        with fixture_files(files) as (_, paths, cache):
            findings = run_auditor(TestCoverageAuditor(), paths, cache)
            self.assertIn('test.missing_tenant_isolation', codes(findings))

    def test_tenant_isolation_present_clean(self):
        view_src = (
            'class WidgetListView(ListAPIView):\n'
            '    queryset = Widget.objects.all()\n'
        )
        test_src = (
            'class T:\n'
            '    def test_cross_tenant(self):\n'
            '        ThreadVaribales().set_val("tenant_id", "other")\n'
            '        self.client.get("/api/widgets/")\n'
        )
        files = {
            'shopstack/stackapp/views.py': view_src,
            'shopstack/stackapp/tests/test_widget.py': test_src,
        }
        with fixture_files(files) as (_, paths, cache):
            findings = run_auditor(TestCoverageAuditor(), paths, cache)
            self.assertNotIn('test.missing_tenant_isolation', codes(findings))


if __name__ == '__main__':
    unittest.main()
