import unittest

from biomed_workbench.catalog import (
    BUILTIN_MODULE_ROOT,
    CapabilityResolutionError,
    all_capabilities,
    capability_to_dict,
    load_module_capabilities,
    resolve,
    resolve_entrypoint,
)
from biomed_workbench.modules.registry import ModuleRegistry
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
            input_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            requirements=(),
            access="offline",
            mutability="read_only",
        )
        with self.assertRaises(CapabilityResolutionError):
            resolve_entrypoint(capability)

    def test_catalog_ids_are_unique_and_sorted(self):
        ids = [capability.id for capability in all_capabilities()]
        self.assertEqual(ids, sorted(set(ids)))

    def test_runtime_catalog_is_a_projection_of_builtin_modules(self):
        registry = ModuleRegistry.discover(BUILTIN_MODULE_ROOT)
        capabilities = {capability.id: capability for capability in all_capabilities()}

        self.assertEqual(set(capabilities), {module.id for module in registry.all()})
        for module in registry.all():
            capability = capabilities[module.id]
            self.assertEqual(capability.entrypoint, module.entrypoint)
            self.assertEqual(capability.input_schema, module.input_schema)
            self.assertEqual(capability.kind, module.execution.kind)

    def test_custom_module_root_loads_without_domain_specifications(self):
        capabilities = load_module_capabilities(BUILTIN_MODULE_ROOT)

        self.assertEqual(len(capabilities), 56)
        self.assertEqual([item.id for item in capabilities], sorted(item.id for item in capabilities))


if __name__ == "__main__":
    unittest.main()
