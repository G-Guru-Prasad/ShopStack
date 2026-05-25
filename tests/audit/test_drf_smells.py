import unittest

from tools.auditors.drf_smells import DrfSmellsAuditor
from tests.audit._helpers import codes, fixture_files, run_auditor


class DrfSmellsTests(unittest.TestCase):
    def test_list_view_without_prefetch_flagged(self):
        source = (
            'class ProductListView(ListAPIView):\n'
            '    queryset = Product.objects.all()\n'
            '    serializer_class = ProductSerializer\n'
        )
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(DrfSmellsAuditor(), paths, cache)
            self.assertIn('drf.list_view_no_prefetch', codes(findings))

    def test_list_view_with_prefetch_clean(self):
        source = (
            'class ProductListView(ListAPIView):\n'
            '    queryset = Product.objects.select_related("category").all()\n'
        )
        with fixture_files({'shopstack/stackapp/views.py': source}) as (_, paths, cache):
            findings = run_auditor(DrfSmellsAuditor(), paths, cache)
            self.assertNotIn('drf.list_view_no_prefetch', codes(findings))

    def test_serializer_method_query_warn(self):
        source = (
            'class ProductSerializer(ModelSerializer):\n'
            '    def get_extra(self, obj):\n'
            '        return Tag.objects.filter(product=obj).count()\n'
        )
        with fixture_files({'shopstack/stackapp/serializers.py': source}) as (_, paths, cache):
            findings = run_auditor(DrfSmellsAuditor(), paths, cache)
            self.assertIn('drf.serializer_method_query', codes(findings))


if __name__ == '__main__':
    unittest.main()
