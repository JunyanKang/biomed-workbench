import unittest

from biomed_workbench.catalog import (
    CapabilityResolutionError,
    all_capabilities,
    capability_to_dict,
    resolve,
    resolve_entrypoint,
)
from biomed_workbench.models import Capability


class CatalogTests(unittest.TestCase):
    def test_ncbi_operations_are_real_registered_capabilities(self):
        expected = {"ncbi-info", "ncbi-search", "ncbi-summary", "ncbi-fetch", "ncbi-link", "ncbi-search-summary"}
        capabilities = {capability.id: capability for capability in all_capabilities()}

        self.assertTrue(expected <= set(capabilities))
        for capability_id in expected:
            capability = resolve(capability_id)
            self.assertTrue(callable(resolve_entrypoint(capability)))
            self.assertEqual(capability.workflow, "evidence")

        runtime = resolve("runtime-status")
        self.assertTrue(callable(resolve_entrypoint(runtime)))
        self.assertEqual(runtime.workflow, "runtime")

    def test_catalog_serialization_has_no_source_or_bridge_fields(self):
        payload = capability_to_dict(resolve("ncbi-search"))

        self.assertNotIn("source", payload)
        self.assertNotIn("source_path", payload)
        self.assertNotIn("run_policy", payload)
        self.assertNotIn("adapter", str(payload).lower())

    def test_unresolvable_entrypoint_is_rejected(self):
        capability = Capability(
            id="broken",
            workflow="evidence",
            kind="python",
            title="Broken",
            description="A deliberately broken resolution fixture.",
            entrypoint="missing.module:call",
            input_schema={},
            requirements=(),
            access="offline",
            mutability="read_only",
        )
        with self.assertRaises(CapabilityResolutionError):
            resolve_entrypoint(capability)

    def test_catalog_ids_are_unique_and_sorted(self):
        ids = [capability.id for capability in all_capabilities()]
        self.assertEqual(ids, sorted(set(ids)))


if __name__ == "__main__":
    unittest.main()
