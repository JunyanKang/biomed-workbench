import hashlib
import importlib
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.semantic_output_validation import (
    evaluate_structured_gate,
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
                assigned = {
                    gate_id
                    for contract in contracts.values()
                    for gate_id in contract.required_postflight_gate_ids
                }
                self.assertTrue(blocking <= assigned)
                self.assertEqual(
                    sum(len(contract.required_postflight_gate_ids) for contract in contracts.values()),
                    len(assigned),
                )
                self.assertEqual({item.protocol_version for item in contracts.values()}, {"2.1.0"})
                for contract in contracts.values():
                    port = next(item for item in manifest.output_artifacts if item.name == contract.port)
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
                    self.assertTrue(all(item.evidence_payload_role == "primary" for item in contract.gate_evaluators))
                    self.assertTrue(all(item.evaluator_type in {
                        "payload-derived", "tool-native", "provenance-design", "system-provenance", "claim-boundary"
                    } for item in contract.gate_evaluators))
                    self.assertFalse(any(item.metric_key == "semantic_violation_count" for item in contract.gate_evaluators))
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

    def test_family_admission_cannot_promote_any_non_system_manifest_gate(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        digest = "a" * 64
        payloads = ({
            "role": "primary", "path": "content-addressed-object", "media_type": "application/json", "sha256": digest,
        },)
        for manifest in (item for item in registry.all() if item.access == "agent_generated"):
            for contract in manifest.observed_output_contracts:
                semantic_result = {
                    "family_admission_status": "passed",
                    "profile": contract.semantic_profile,
                    "family_admission": True,
                    "evidence_payload_digests": {"primary": digest},
                }
                for evaluator in contract.gate_evaluators:
                    with self.subTest(module=manifest.id, port=contract.port, gate=evaluator.gate_id):
                        result = evaluate_structured_gate(
                            payloads=payloads,
                            gate_id=evaluator.gate_id,
                            evaluator_type=evaluator.evaluator_type,
                            evidence_payload_role=evaluator.evidence_payload_role,
                            metric_key=evaluator.metric_key,
                            metric_type=evaluator.metric_type,
                            operator=evaluator.operator,
                            threshold=evaluator.threshold,
                            semantic_result=semantic_result,
                        )
                        self.assertEqual(result["status"], "requires_review")

    def test_no_manifest_gate_is_inferred_as_system_provenance_from_its_name(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        system_gates = [
            (manifest.id, contract.port, evaluator.gate_id)
            for manifest in registry.all() if manifest.access == "agent_generated"
            for contract in manifest.observed_output_contracts
            for evaluator in contract.gate_evaluators
            if evaluator.evaluator_type == "system-provenance"
        ]
        self.assertEqual(system_gates, [])

    def test_high_risk_gates_are_bound_to_the_output_that_can_support_review(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        expected = {
            ("protein-complex-docking", "structure-publication-figures"): "structure_figure_bundle",
            ("single-cell-batch-integration", "integration-batch-mixing"): "integration_benchmark",
            ("single-cell-batch-integration", "integration-selection-sensitivity"): "integration_decision",
            ("single-cell-trajectory-velocity", "velocity-confidence"): "trajectory_velocity_validation",
            ("docking-pose-review", "docking-preparation-parameters"): "validated_docking_config",
            ("docking-pose-review", "docking-review-geometry"): "docking_review_report",
        }
        for (module_id, gate_id), port in expected.items():
            manifest = registry.get(module_id)
            observed = next(
                contract.port
                for contract in manifest.observed_output_contracts
                if gate_id in contract.required_postflight_gate_ids
            )
            self.assertEqual(observed, port)


if __name__ == "__main__":
    unittest.main()
