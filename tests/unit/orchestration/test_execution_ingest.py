import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore
from biomed_workbench.kernel.execution_receipts import ExecutionHandoff
from biomed_workbench.kernel.identity import digest_value
from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import apply_event
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.orchestration.execution_ingest import ingest_execution_bundle
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.orchestration.test_planner import inline_artifact, state_with


class ExecutionIngestTests(unittest.TestCase):
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
            planned_output_artifact_ids=node.planned_output_artifact_ids,
            protocol={"result_kind": "execution_handoff", "execution_state": "prepared-not-run"},
        )
        state = apply_event(state, "execution_handoff_recorded", {"handoff": handoff.to_dict()}, rationale="Record the exact handoff.")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            table = root / "enrichment.tsv"
            table.write_text("term\tp_value\nDNA repair\t0.01\n", encoding="utf-8")
            bundle = {
                "handoff_id": handoff.id,
                "process_exit_code": 0,
                "runtime_versions": {"R": "4.3.3", "clusterProfiler": "4.10.1"},
                "postflight_finding_ids": [],
                "outputs": [{
                    "port": "functional_enrichment_evidence",
                    "content": {"tested_gene_count": 1, "tested_universe_count": 2},
                    "payload_files": [{"role": "table", "path": str(table), "media_type": "text/tab-separated-values"}],
                    "quality_status": "passed",
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


if __name__ == "__main__":
    unittest.main()
