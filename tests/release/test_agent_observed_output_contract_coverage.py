import hashlib
import importlib
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.semantic_output_validation import (
    registered_semantic_profiles,
    semantic_profile_for,
    semantic_profile_is_implemented,
    semantic_profile_supports_media_type,
)


FORMAT_MEDIA_TYPES = {
    "alphafold3-output": "application/zip", "artifact-directory": "application/zip",
    "bed": "text/tab-separated-values", "broadpeak": "text/tab-separated-values",
    "cellbender-h5": "application/x-hdf5", "count-matrix": "text/tab-separated-values",
    "csv": "text/csv", "fasta": "text/x-fasta", "h5ad": "application/x-hdf5",
    "h5mu": "application/x-hdf5", "html": "text/html", "inline-json": "application/json",
    "json": "application/json", "matrix-market": "text/plain", "metascape-result": "application/zip",
    "mmcif": "chemical/x-mmcif", "mofa-hdf5": "application/x-hdf5",
    "monocle-object-directory": "application/zip", "narrowpeak": "text/tab-separated-values",
    "newick": "text/x-newick", "normalized-json": "application/json",
    "paf": "text/tab-separated-values", "pdb": "chemical/x-pdb", "pdf": "application/pdf",
    "publication-figure-set": "application/zip", "rds": "application/octet-stream",
    "scvi-model-directory": "application/zip", "seurat-rds": "application/octet-stream",
    "spatialdata-zarr": "application/zip", "svg": "image/svg+xml",
    "tab-separated-values": "text/tab-separated-values", "tabular": "text/tab-separated-values",
    "tiff": "image/tiff", "tskit-trees": "application/octet-stream", "vcf": "text/x-vcf",
    "yaml": "application/yaml",
}


class AgentObservedOutputContractCoverageTests(unittest.TestCase):
    def test_every_agent_workflow_has_port_complete_gate_bound_result_contracts(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        agent_modules = tuple(item for item in registry.all() if item.access == "agent_generated")
        self.assertEqual(len(agent_modules), 54)
        for manifest in agent_modules:
            with self.subTest(module=manifest.id):
                contracts = {item.port: item for item in manifest.observed_output_contracts}
                self.assertEqual(set(contracts), {item.name for item in manifest.output_artifacts})
                blocking = {item.id for item in manifest.quality_gates if item.blocks_interpretation}
                for contract in contracts.values():
                    port = next(item for item in manifest.output_artifacts if item.name == contract.port)
                    self.assertTrue(blocking <= set(contract.required_postflight_gate_ids))
                    self.assertTrue(any(item.minimum > 0 for item in contract.payloads))
                    self.assertFalse(contract.content_schema.get("additionalProperties", True))
                    self.assertTrue(contract.container_reload_validator)
                    self.assertTrue(contract.semantic_validator)
                    module_name, _ = contract.semantic_validator.split(":", 1)
                    source = Path(importlib.import_module(module_name).__file__)
                    self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), contract.semantic_validator_sha256)
                    self.assertEqual(
                        {item.gate_id for item in contract.gate_evaluators},
                        set(contract.required_postflight_gate_ids),
                    )
                    self.assertEqual(contract.semantic_profile, semantic_profile_for(port.artifact_type))
                    self.assertTrue(semantic_profile_is_implemented(contract.semantic_profile))
                    for format_contract in port.formats:
                        self.assertTrue(
                            semantic_profile_supports_media_type(
                                contract.semantic_profile, FORMAT_MEDIA_TYPES[format_contract.name]
                            ),
                            (manifest.id, port.name, format_contract.name),
                        )
                    self.assertTrue(all(item.metric_key == "semantic_violation_count" for item in contract.gate_evaluators))
                    self.assertTrue(all(item.metric_type == "integer" for item in contract.gate_evaluators))
                    self.assertTrue(all(item.operator == "equals" and item.threshold == 0 for item in contract.gate_evaluators))
                    self.assertIn("semantic-metadata", {item.role for item in contract.payloads if item.minimum > 0})
                    source_data = next(item for item in contract.payloads if item.role == "source-data")
                    self.assertIn("application/json", source_data.media_types)

        used_profiles = {
            contract.semantic_profile
            for manifest in agent_modules
            for contract in manifest.observed_output_contracts
        }
        self.assertEqual(used_profiles, set(registered_semantic_profiles()))
        self.assertLess(len(used_profiles), sum(len(item.observed_output_contracts) for item in agent_modules))


if __name__ == "__main__":
    unittest.main()
