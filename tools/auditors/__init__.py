from tools.auditors.base import Auditor, Finding, Severity
from tools.auditors.drf_smells import DrfSmellsAuditor
from tools.auditors.file_shape import FileShapeAuditor
from tools.auditors.orm_smells import OrmSmellsAuditor
from tools.auditors.python_perf import PythonPerfAuditor
from tools.auditors.shopstack_patterns import ShopstackPatternsAuditor
from tools.auditors.tenant_smells import TenantSmellsAuditor
from tools.auditors.test_coverage import TestCoverageAuditor


CHEAP_AUDITORS = [
    OrmSmellsAuditor,
    TenantSmellsAuditor,
    PythonPerfAuditor,
    DrfSmellsAuditor,
    FileShapeAuditor,
    ShopstackPatternsAuditor,
]


__all__ = [
    'Auditor',
    'Finding',
    'Severity',
    'CHEAP_AUDITORS',
    'TestCoverageAuditor',
    'DrfSmellsAuditor',
    'FileShapeAuditor',
    'OrmSmellsAuditor',
    'PythonPerfAuditor',
    'ShopstackPatternsAuditor',
    'TenantSmellsAuditor',
]
