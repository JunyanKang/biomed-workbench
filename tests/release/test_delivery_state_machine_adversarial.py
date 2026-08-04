import unittest

from biomed_workbench.kernel.execution_chain import validate_validated_delivery_state
from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import apply_event
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.orchestration.test_planner import inline_artifact, state_with


def _node(identifier, status, output_id):
    return PlanNode(
        id=identifier,
        module_id="fixture-analysis",
        input_bindings={"input_data": "artifact-input"},
        dependencies=(),
        branch_id=f"branch-{identifier}",
        target_hypothesis_ids=(hypothesis().id,),
        expected_evidence_types=("quality-evidence",),
        expected_output_artifact_types=("shared_result",),
        planned_output_artifact_ids={"profile": output_id},
        compatibility_row_candidates=("fixture-row",),
        status=status,
        attempt=1 if status != "pending" else 0,
    )


class DeliveryStateMachineAdversarialTests(unittest.TestCase):
    def _state(self, statuses):
        state = state_with(inline_artifact("artifact-input", "feature_matrix"))
        nodes = tuple(
            _node(f"node-{index}", status, f"artifact-output-{index}")
            for index, status in enumerate(statuses, start=1)
        )
        plan = ResearchDAG.create(
            id="plan-adversarial-delivery",
            objective="Require every planned branch and exact leaf output before delivery.",
            nodes=nodes,
            required_output_artifact_types=("shared_result",),
            plan_type="parallel" if len(nodes) > 1 else "single",
            revision=1,
            parent_plan_id=None,
            rationale=("Exercise negative delivery states that type-only coverage must never hide.",),
        )
        return apply_event(
            state, "plan_created", {"plan": plan.to_dict(), "activate": True},
            rationale="Register an adversarial delivery plan.",
        )

    def test_nonterminal_active_plan_states_never_form_validated_delivery(self):
        for statuses in (
            ("completed", "pending"),
            ("completed", "awaiting_review"),
            ("completed", "failed"),
        ):
            with self.subTest(statuses=statuses), self.assertRaisesRegex(ValueError, "every active plan node"):
                validate_validated_delivery_state(self._state(statuses))

    def test_same_artifact_type_cannot_hide_an_unfinished_parallel_branch(self):
        state = self._state(("completed", "pending"))
        self.assertEqual(
            {artifact_type for node in state.plans[-1].nodes for artifact_type in node.expected_output_artifact_types},
            {"shared_result"},
        )
        with self.assertRaisesRegex(ValueError, "every active plan node"):
            validate_validated_delivery_state(state)

    def test_completed_status_without_receipts_and_retained_identities_is_insufficient(self):
        with self.assertRaisesRegex(ValueError, "observed execution|retained leaf"):
            validate_validated_delivery_state(self._state(("completed", "completed")))


if __name__ == "__main__":
    unittest.main()
