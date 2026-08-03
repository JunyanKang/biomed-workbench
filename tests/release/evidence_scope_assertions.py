from biomed_workbench.modules.evidence_scope import evidence_scope_is_current
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


def assert_evidence_scope_current(testcase, report):
    """Assert stable scientific execution scope while preserving historical raw manifest identity."""
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    testcase.assertTrue(evidence_scope_is_current(report, registry))
    testcase.assertRegex(report["module"]["manifest_sha256"], r"^[0-9a-f]{64}$")
