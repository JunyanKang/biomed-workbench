import hashlib
import copy
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore
from biomed_workbench.kernel.execution_receipts import ExecutionHandoff
from biomed_workbench.kernel.identity import digest_value
from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import ProjectState, apply_event
from biomed_workbench.orchestration.controller import ResearchController
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.contract import observed_output_contract_digest
from biomed_workbench.orchestration.execution_ingest import ingest_execution_bundle
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.kernel.test_scientific_dependency import decision, review
from tests.unit.orchestration.test_planner import inline_artifact, state_with


class ExecutionIngestTests(unittest.TestCase):
    def _prepared_case(self, *, contract_digest=None):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        manifest = registry.get("functional-enrichment")
        state = state_with(
            inline_artifact("artifact-genes", "gene_list_or_ranking"),
            inline_artifact("artifact-universe", "measured_gene_universe"),
        )
        node = PlanNode(
            id="node-functional-enrichment",
            module_id=manifest.id,
            input_bindings={"gene_evidence": "artifact-genes", "tested_universe": "artifact-universe"},
            dependencies=(), branch_id="branch-enrichment", target_hypothesis_ids=(hypothesis().id,),
            expected_evidence_types=("functional-enrichment",),
            expected_output_artifact_types=("functional_enrichment_evidence",),
            planned_output_artifact_ids={"functional_enrichment_evidence": "artifact-enrichment-result"},
            compatibility_row_candidates=(manifest.compatibility_matrix[0].id,),
            status="awaiting_observed_execution", attempt=1,
        )
        plan = ResearchDAG.create(
            id="plan-functional-enrichment", objective="Test the registered gene set against its measured universe.",
            nodes=(node,), required_output_artifact_types=("functional_enrichment_evidence",),
            plan_type="single", revision=1, parent_plan_id=None,
            rationale=("Exercise adversarial observed-result admission.",),
        )
        state = apply_event(state, "plan_created", {"plan": plan.to_dict(), "activate": True}, rationale="Register the test plan.")
        handoff = ExecutionHandoff.create(
            plan_node_id=node.id, module_id=manifest.id, module_version=manifest.version,
            request_digest=digest_value({"genes": ["TP53"], "universe": ["TP53", "BRCA1"]}),
            compatibility_row_id=manifest.compatibility_matrix[0].id,
            observed_output_contract_digest=contract_digest or observed_output_contract_digest(manifest),
            planned_output_artifact_ids=node.planned_output_artifact_ids,
            protocol={"result_kind": "execution_handoff", "execution_state": "prepared-not-run"},
        )
        state = apply_event(state, "execution_handoff_recorded", {"handoff": handoff.to_dict()}, rationale="Record the exact handoff.")
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        table = root / "enrichment.tsv"
        table.write_text("term\tp_value\nDNA repair\t0.01\n", encoding="utf-8")
        payload_digest = hashlib.sha256(table.read_bytes()).hexdigest()
        bundle = {
            "handoff_id": handoff.id, "process_exit_code": 0,
            "runtime_versions": {"R": "4.3.3", "clusterProfiler": "4.10.1"},
            "postflight_results": [{
                "gate_id": gate.id, "status": "passed", "observed_metric": f"{gate.id}=passed",
                "threshold": "predeclared manifest gate must pass", "evidence_payload_sha256": payload_digest,
            } for gate in manifest.quality_gates],
            "outputs": [{
                "port": "functional_enrichment_evidence",
                "content": {
                    "artifact_type": "functional_enrichment_evidence", "format": "tab-separated-values",
                    "processing_level": "tested", "result_summary": "A reloadable enrichment result was produced.",
                    "record_count": 1,
                    "provenance": {"workflow": "clusterProfiler", "workflow_version": "4.10.1",
                                   "parameters_digest": handoff.request_digest,
                                   "compatibility_row_id": handoff.compatibility_row_id},
                },
                "payload_files": [{"role": "primary", "path": str(table), "media_type": "text/tab-separated-values"}],
            }],
        }
        return registry, state, root, bundle

    def test_handoff_observation_reloads_outputs_and_enters_scientific_review(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        manifest = registry.get("functional-enrichment")
        state = state_with(
            inline_artifact("artifact-genes", "gene_list_or_ranking"),
            inline_artifact("artifact-universe", "measured_gene_universe"),
        )
        node = PlanNode(
            id="node-functional-enrichment",
            module_id=manifest.id,
            input_bindings={"gene_evidence": "artifact-genes", "tested_universe": "artifact-universe"},
            dependencies=(),
            branch_id="branch-enrichment",
            target_hypothesis_ids=(hypothesis().id,),
            expected_evidence_types=("functional-enrichment",),
            expected_output_artifact_types=("functional_enrichment_evidence",),
            planned_output_artifact_ids={"functional_enrichment_evidence": "artifact-enrichment-result"},
            compatibility_row_candidates=(manifest.compatibility_matrix[0].id,),
            status="awaiting_observed_execution",
            attempt=1,
        )
        plan = ResearchDAG.create(
            id="plan-functional-enrichment",
            objective="Test the registered gene set against its measured universe.",
            nodes=(node,),
            required_output_artifact_types=("functional_enrichment_evidence",),
            plan_type="single",
            revision=1,
            parent_plan_id=None,
            rationale=("Exercise the exact agent execution receipt re-entry path.",),
        )
        state = apply_event(state, "plan_created", {"plan": plan.to_dict(), "activate": True}, rationale="Register the test plan.")
        handoff = ExecutionHandoff.create(
            plan_node_id=node.id,
            module_id=manifest.id,
            module_version=manifest.version,
            request_digest=digest_value({"genes": ["TP53"], "universe": ["TP53", "BRCA1"]}),
            compatibility_row_id=manifest.compatibility_matrix[0].id,
            observed_output_contract_digest=observed_output_contract_digest(manifest),
            planned_output_artifact_ids=node.planned_output_artifact_ids,
            protocol={"result_kind": "execution_handoff", "execution_state": "prepared-not-run"},
        )
        state = apply_event(state, "execution_handoff_recorded", {"handoff": handoff.to_dict()}, rationale="Record the exact handoff.")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            table = root / "enrichment.tsv"
            table.write_text("term\tp_value\nDNA repair\t0.01\n", encoding="utf-8")
            payload_digest = hashlib.sha256(table.read_bytes()).hexdigest()
            bundle = {
                "handoff_id": handoff.id,
                "process_exit_code": 0,
                "runtime_versions": {"R": "4.3.3", "clusterProfiler": "4.10.1"},
                "postflight_results": [{
                    "gate_id": gate.id,
                    "status": "passed",
                    "observed_metric": f"{gate.id}=passed on reloaded output",
                    "threshold": "predeclared manifest gate must pass",
                    "evidence_payload_sha256": payload_digest,
                } for gate in manifest.quality_gates],
                "outputs": [{
                    "port": "functional_enrichment_evidence",
                    "content": {
                        "artifact_type": "functional_enrichment_evidence",
                        "format": "tab-separated-values",
                        "processing_level": "tested",
                        "result_summary": "One tested gene produced a reloadable enrichment result.",
                        "record_count": 1,
                        "provenance": {
                            "workflow": "clusterProfiler",
                            "workflow_version": "4.10.1",
                            "parameters_digest": handoff.request_digest,
                            "compatibility_row_id": handoff.compatibility_row_id,
                        },
                    },
                    "payload_files": [{"role": "primary", "path": str(table), "media_type": "text/tab-separated-values"}],
                }],
            }
            state = ingest_execution_bundle(
                state,
                bundle,
                registry=registry,
                artifact_store=ProjectArtifactStore(root / "objects"),
            )

        self.assertEqual(state.plans[-1].nodes[0].status, "awaiting_review")
        self.assertEqual(len(state.observed_executions), 1)
        self.assertEqual(len(state.artifact_reloads), 1)
        self.assertEqual(len(state.execution_reviews), 1)
        self.assertEqual(state.artifact_reloads[0].artifact_id, "artifact-enrichment-result")

    def test_observed_result_contract_rejects_adversarial_bundles(self):
        mutations = {
            "arbitrary content": lambda value: value["outputs"][0].update(content={"arbitrary_unvalidated_field": True}),
            "missing required field": lambda value: value["outputs"][0]["content"].pop("record_count"),
            "wrong payload role": lambda value: value["outputs"][0]["payload_files"][0].update(role="table"),
            "wrong payload media": lambda value: value["outputs"][0]["payload_files"][0].update(media_type="text/plain"),
            "missing postflight gate": lambda value: value["postflight_results"].pop(),
            "mismatched gate evidence": lambda value: value["postflight_results"][0].update(evidence_payload_sha256="0" * 64),
            "unobserved workflow version": lambda value: value["outputs"][0]["content"]["provenance"].update(workflow_version="99.0.0"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                registry, state, root, bundle = self._prepared_case()
                invalid = copy.deepcopy(bundle)
                mutate(invalid)
                with self.assertRaises((ValueError, TypeError)):
                    ingest_execution_bundle(
                        state, invalid, registry=registry,
                        artifact_store=ProjectArtifactStore(root / "objects"),
                    )

    def test_reload_validator_rejects_plain_text_disguised_as_a_result_table(self):
        registry, state, root, bundle = self._prepared_case()
        Path(bundle["outputs"][0]["payload_files"][0]["path"]).write_text(
            "ordinary text without a scientific table contract\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "too few columns"):
            ingest_execution_bundle(
                state,
                bundle,
                registry=registry,
                artifact_store=ProjectArtifactStore(root / "objects"),
            )

    def test_handoff_rejects_observed_contract_digest_drift(self):
        registry, state, root, bundle = self._prepared_case(contract_digest="f" * 64)
        with self.assertRaisesRegex(ValueError, "contract changed"):
            ingest_execution_bundle(state, bundle, registry=registry, artifact_store=ProjectArtifactStore(root / "objects"))

    def test_ingest_review_retain_and_resume_completes_handoff_node(self):
        registry, state, root, bundle = self._prepared_case()
        state = ingest_execution_bundle(
            state, bundle, registry=registry, artifact_store=ProjectArtifactStore(root / "objects")
        )
        state = ProjectState.from_dict(state.to_dict())
        artifact_id = "artifact-enrichment-result"
        artifact_review = review(
            id="review-artifact-enrichment-result",
            artifact_id=artifact_id,
            results_zh="富集结果及其主表已经按登记契约重新读取，身份、格式和门控证据完整。",
            results_en="The enrichment result and primary table were reloaded under the registered contract with complete identity, format, and gate evidence.",
        )
        state = apply_event(
            state, "artifact_review_recorded", {"review": artifact_review.to_dict()},
            rationale="Record the bilingual scientific review of the reloaded workflow output.",
        )
        retained = decision(
            id="decision-artifact-enrichment-result",
            review_id=artifact_review.id,
            artifact_id=artifact_id,
            next_plan_node_ids=(),
        )
        state = apply_event(
            state, "scientific_decision_recorded", {"decision": retained.to_dict()},
            rationale="Retain the reviewed workflow output as active evidence.",
        )
        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            artifact_store=ProjectArtifactStore(root / "objects"),
        ).resume(state.to_dict())
        self.assertEqual(result.stop_reason, "plan_completed")
        self.assertEqual(result.active_plan.nodes[0].status, "completed")


if __name__ == "__main__":
    unittest.main()
