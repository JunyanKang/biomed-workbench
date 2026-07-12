import unittest

from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import apply_event
from tests.unit.kernel.test_state import populated_state


def node(node_id, module_id, *, dependencies=(), input_artifact="artifact-counts-01", output_artifact="artifact-planned-output"):
    return PlanNode(
        id=node_id,
        module_id=module_id,
        input_bindings={"records": input_artifact},
        dependencies=dependencies,
        branch_id="branch-test",
        target_hypothesis_ids=("hypothesis-lineage-shift-v1",),
        expected_evidence_types=("cell-state-association",),
        expected_output_artifact_types=("quality_report",),
        planned_output_artifact_ids={"profile": output_artifact},
        compatibility_row_candidates=("python-3.14.3-inline-json-1",),
        status="pending",
        attempt=0,
    )


class DagValidityContractTests(unittest.TestCase):
    def test_dependent_binding_must_come_from_declared_dependency_output(self):
        first = node("node-first", "data-profile", output_artifact="artifact-planned-first")
        second = node(
            "node-second",
            "manuscript-audit",
            dependencies=(first.id,),
            input_artifact="artifact-planned-first",
            output_artifact="artifact-planned-second",
        )
        plan = ResearchDAG.create(
            id="plan-valid-chain",
            objective="Execute a validated dependency chain for the declared research objective.",
            nodes=(first, second),
            required_output_artifact_types=("quality_report",),
            plan_type="serial",
            revision=1,
            parent_plan_id=None,
            rationale=("The second node consumes the first node's declared output artifact.",),
        )

        state = apply_event(populated_state(), "plan_created", {"plan": plan.to_dict(), "activate": True}, rationale="Register a valid dependent DAG.")

        self.assertEqual(state.active_plan_id, plan.id)

    def test_unknown_planned_binding_and_cycles_are_rejected(self):
        first = node("node-first", "data-profile", dependencies=("node-second",), input_artifact="artifact-planned-second", output_artifact="artifact-planned-first")
        second = node("node-second", "manuscript-audit", dependencies=("node-first",), input_artifact="artifact-planned-first", output_artifact="artifact-planned-second")
        with self.assertRaisesRegex(ValueError, "cycle"):
            ResearchDAG.create(
                id="plan-cycle",
                objective="Reject a dependency cycle before any scientific module can execute.",
                nodes=(first, second),
                required_output_artifact_types=("quality_report",),
                plan_type="serial",
                revision=1,
                parent_plan_id=None,
                rationale=("Cycles cannot produce an executable scientific dependency order.",),
            )

        invalid = node("node-invalid", "data-profile", input_artifact="artifact-never-produced")
        plan = ResearchDAG.create(
            id="plan-invalid-binding",
            objective="Reject a planned input binding without an available or dependency-produced artifact.",
            nodes=(invalid,),
            required_output_artifact_types=("quality_report",),
            plan_type="single",
            revision=1,
            parent_plan_id=None,
            rationale=("Every planned input must have an explicit artifact lineage.",),
        )
        with self.assertRaisesRegex(ValueError, "unknown artifacts"):
            apply_event(populated_state(), "plan_created", {"plan": plan.to_dict(), "activate": True}, rationale="Reject unknown planned lineage.")


if __name__ == "__main__":
    unittest.main()
