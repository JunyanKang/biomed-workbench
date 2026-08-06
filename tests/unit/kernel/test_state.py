import copy
import json
import unittest
from pathlib import Path

from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import ProjectState, _migrate_v1_adjudication, apply_event
from biomed_workbench.kernel.hypotheses import revise_hypothesis
from tests.unit.kernel.test_artifacts import artifact
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_evidence import evidence_record
from tests.unit.kernel.test_hypotheses import hypothesis


def research_plan(**overrides):
    node = PlanNode(
        id="node-cell-state-analysis",
        module_id="single-cell-qc",
        input_bindings={"single_cell_counts": "artifact-counts-01"},
        dependencies=(),
        branch_id="branch-omics",
        target_hypothesis_ids=("hypothesis-lineage-shift-v1",),
        expected_evidence_types=("cell-state-association",),
        expected_output_artifact_types=("quality_report",),
        planned_output_artifact_ids={"cell_quality": "artifact-planned-cell-quality"},
        compatibility_row_candidates=("python-3.14.3-inline-json-1",),
        status="pending",
        attempt=0,
    )
    values = {
        "id": "plan-lineage-analysis-v1",
        "objective": "Test the lineage-shift hypothesis with quality-controlled molecular evidence.",
        "nodes": (node,),
        "required_output_artifact_types": ("quality_report",),
        "plan_type": "single",
        "revision": 1,
        "parent_plan_id": None,
        "rationale": ("The available count matrix directly supports the selected validation module.",),
    }
    values.update(overrides)
    return ResearchDAG.create(**values)


def populated_state():
    state = ProjectState.create(project_context())
    state = apply_event(
        state,
        "artifact_registered",
        {"artifact": artifact(source_artifact_ids=()).to_dict()},
        rationale="Register the declared count matrix before planning.",
        affected_artifact_ids=("artifact-counts-01",),
    )
    state = apply_event(
        state,
        "hypothesis_added",
        {"hypothesis": hypothesis().to_dict()},
        rationale="Register a falsifiable lineage hypothesis before testing it.",
        affected_hypothesis_ids=("hypothesis-lineage-shift-v1",),
    )
    return state


class ProjectStateTests(unittest.TestCase):
    def test_previous_release_v1_state_migrates_to_v2_with_exact_receipt_bindings(self):
        fixture = Path(__file__).parents[2] / "fixtures" / "project_state_v1_gate_adjudications.json"
        legacy = json.loads(fixture.read_text(encoding="utf-8"))

        state = ProjectState.from_dict(legacy)

        self.assertEqual(state.schema_version, 2)
        self.assertEqual(state.revision, legacy["revision"])
        self.assertEqual(len(state.gate_adjudications), 3)
        self.assertTrue(all(item.adjudication_mode == "manual" for item in state.gate_adjudications))
        self.assertTrue(all(item.observed_value and item.criterion and item.finding for item in state.gate_adjudications))
        self.assertEqual(len(state.state_migrations), 1)
        self.assertEqual(state.state_migrations[0].source_state_digest, legacy["state_digest"])
        self.assertEqual(state.state_migrations[0].source_revision, legacy["revision"])
        self.assertEqual(ProjectState.from_dict(state.to_dict()), state)

    def test_v1_migration_rejects_tampering_and_unrecoverable_gate_bindings(self):
        fixture = Path(__file__).parents[2] / "fixtures" / "project_state_v1_gate_adjudications.json"
        legacy = json.loads(fixture.read_text(encoding="utf-8"))
        tampered = copy.deepcopy(legacy)
        tampered["gate_adjudications"][0]["gate_result_digest"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "state digest is invalid"):
            ProjectState.from_dict(tampered)
        with self.assertRaisesRegex(ValueError, "cannot recover an exact observed binding"):
            _migrate_v1_adjudication(legacy["gate_adjudications"][0], {})

    def test_events_are_append_only_digest_linked_and_update_ledgers(self):
        state = populated_state()
        prior_digest = state.state_digest
        evidence = evidence_record(artifact_id="artifact-counts-01")

        state = apply_event(
            state,
            "evidence_added",
            {"evidence": evidence.to_dict()},
            rationale="Link the observed contrast to the active hypothesis.",
            trigger_finding_ids=("finding-contrast-direction",),
            affected_artifact_ids=("artifact-counts-01",),
            affected_hypothesis_ids=("hypothesis-lineage-shift-v1",),
        )

        self.assertEqual(state.revision, 3)
        self.assertEqual(tuple(event.sequence for event in state.decisions), (1, 2, 3))
        self.assertEqual(state.decisions[-1].prior_state_digest, prior_digest)
        self.assertEqual(state.decisions[-1].resulting_state_digest, state.state_digest)
        self.assertEqual(state.hypotheses[0].supporting_evidence_ids, ("evidence-cell-state-01",))
        self.assertEqual(state.evidence[0].relation, "supports")

    def test_plan_creation_validates_artifact_hypothesis_and_activates_plan(self):
        state = populated_state()
        plan = research_plan()

        state = apply_event(
            state,
            "plan_created",
            {"plan": plan.to_dict(), "activate": True},
            rationale="Create the first executable capability DAG.",
            affected_artifact_ids=("artifact-counts-01",),
            affected_hypothesis_ids=("hypothesis-lineage-shift-v1",),
            replacement_action_ids=("node-cell-state-analysis",),
        )

        self.assertEqual(state.active_plan_id, plan.id)
        self.assertEqual(state.plans, (plan,))

    def test_pending_node_cannot_jump_directly_to_completed(self):
        state = populated_state()
        plan = research_plan()
        state = apply_event(
            state,
            "plan_created",
            {"plan": plan.to_dict(), "activate": True},
            rationale="Register a pending node before exercising its transition contract.",
        )
        with self.assertRaisesRegex(ValueError, "transition"):
            apply_event(
                state,
                "node_status_changed",
                {"plan_id": plan.id, "node_id": plan.nodes[0].id, "status": "completed", "attempt": 0},
                rationale="A pending node must never become completed without observed execution and review.",
            )

    def test_refuted_hypothesis_remains_when_a_revised_hypothesis_is_added(self):
        state = ProjectState.create(project_context())
        original = hypothesis(status="refuted")
        state = apply_event(state, "hypothesis_added", {"hypothesis": original.to_dict()}, rationale="Preserve the refuted initial mechanism.")
        revised = revise_hypothesis(
            original,
            new_id="hypothesis-survival-shift-v2",
            statement="The perturbation changes apparent neuronal abundance through selective survival rather than fate transition.",
            expected_direction="change",
            status="active",
        )

        state = apply_event(
            state,
            "hypothesis_revised",
            {"hypothesis": revised.to_dict()},
            rationale="Test the survival alternative without erasing the refuted fate mechanism.",
            affected_hypothesis_ids=(original.id, revised.id),
        )

        self.assertEqual(tuple(item.status for item in state.hypotheses), ("refuted", "active"))
        self.assertEqual(state.hypotheses[1].parent_hypothesis_id, original.id)

    def test_unknown_references_unknown_events_and_sensitive_payloads_fail_closed(self):
        state = ProjectState.create(project_context())
        invalid = (
            lambda: apply_event(state, "invented_event", {}, rationale="Unknown events must fail closed."),
            lambda: apply_event(state, "artifact_registered", {"artifact": artifact(source_artifact_ids=("missing-artifact",)).to_dict()}, rationale="Unknown sources are invalid."),
            lambda: apply_event(state, "hypothesis_added", {"hypothesis": hypothesis().to_dict(), "NCBI_API_KEY": "private"}, rationale="Secrets are invalid."),
            lambda: apply_event(state, "hypothesis_added", {"hypothesis": hypothesis().to_dict(), "path": "/Users/researcher/state.json"}, rationale="Paths are invalid."),
        )
        for factory in invalid:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()
        self.assertEqual(state.revision, 0)
        self.assertEqual(state.decisions, ())


if __name__ == "__main__":
    unittest.main()
