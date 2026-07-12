import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.evidence import EvidenceRecord
from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import ProjectState
from biomed_workbench.orchestration.controller import ControllerPolicy, ResearchController
from biomed_workbench.orchestration.execution import NodeExecution
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.orchestration.test_controller import completed_execution
from tests.unit.orchestration.test_planner import inline_artifact, module_payload, state_with, workflow_registry


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "research-cycles"


def plan_node(node_id, module_id, input_id, output_id, *, dependency=(), target=True):
    return PlanNode(
        id=node_id,
        module_id=module_id,
        input_bindings={"records": input_id},
        dependencies=dependency,
        branch_id=f"branch-{node_id}",
        target_hypothesis_ids=("hypothesis-lineage-shift-v1",) if target else (),
        expected_evidence_types=("cycle-evidence",) if target else (),
        expected_output_artifact_types=("cycle_result",),
        planned_output_artifact_ids={"profile": output_id},
        compatibility_row_candidates=("python-3.14.3-inline-json-1",),
        status="pending",
        attempt=0,
    )


def child_plan(fixture, parent):
    domain = fixture["domain"].replace("_", "-")
    alternative = plan_node("node-alternative", f"alternative-{domain}", "artifact-cycle-input", "artifact-alternative-output")
    nodes = [alternative]
    if fixture["revised_plan_type"] in {"serial", "mixed"}:
        nodes.append(plan_node("node-downstream", f"downstream-{domain}", "artifact-alternative-output", "artifact-downstream-output", dependency=(alternative.id,)))
    if fixture["revised_plan_type"] in {"parallel", "mixed"}:
        nodes.append(plan_node("node-orthogonal", f"orthogonal-{domain}", "artifact-cycle-input", "artifact-orthogonal-output"))
    return ResearchDAG.create(
        id=f"plan-{domain}-revision",
        objective=parent.objective,
        nodes=tuple(nodes),
        required_output_artifact_types=("cycle_result",),
        plan_type=fixture["revised_plan_type"],
        revision=2,
        parent_plan_id=parent.id,
        rationale=("Replace the blocked primary module and add the required downstream or orthogonal evidence branches.",),
    )


def run_scenario(fixture):
    domain = fixture["domain"].replace("_", "-")
    blocked_id = f"blocked-{domain}"
    alternative_id = f"alternative-{domain}"
    payloads = [module_payload(blocked_id, "raw_table", "cycle_result", alternatives=(alternative_id,)), module_payload(alternative_id, "raw_table", "cycle_result")]
    if fixture["revised_plan_type"] in {"serial", "mixed"}:
        payloads.append(module_payload(f"downstream-{domain}", "cycle_result", "cycle_result"))
    if fixture["revised_plan_type"] in {"parallel", "mixed"}:
        payloads.append(module_payload(f"orthogonal-{domain}", "raw_table", "cycle_result"))
    for payload in payloads:
        payload["domains"] = [fixture["domain"]]
    temporary, registry = workflow_registry(tuple(payloads))
    required = tuple(fixture["required_evidence_types"])
    active = hypothesis(required_evidence_types=required, missing_evidence_types=required, minimum_independent_evidence_groups=max(1, fixture["evidence_relations"].count("supports")))
    state = state_with(inline_artifact("artifact-cycle-input", "raw_table"))
    if state.hypotheses[0] != active:
        base = ProjectState.create(state.context)
        from biomed_workbench.kernel.state import apply_event

        base = apply_event(base, "hypothesis_added", {"hypothesis": active.to_dict()}, rationale="Register the scenario hypothesis.")
        state = apply_event(base, "artifact_registered", {"artifact": inline_artifact("artifact-cycle-input", "raw_table").to_dict()}, rationale="Register the scenario input artifact.")
    parent_node = plan_node("node-blocked-primary", blocked_id, "artifact-cycle-input", "artifact-blocked-output")
    parent = ResearchDAG.create(
        id=f"plan-{domain}-initial",
        objective=state.context.objective,
        nodes=(parent_node,),
        required_output_artifact_types=("cycle_result",),
        plan_type="single",
        revision=1,
        parent_plan_id=None,
        rationale=("Attempt the primary validated module before selecting an alternative.",),
    )
    child_nodes = child_plan(fixture, parent).nodes
    if fixture["revised_plan_type"] == "single":
        evidence_modules = [child_nodes[0].module_id]
    elif fixture["revised_plan_type"] == "serial":
        evidence_modules = [child_nodes[-1].module_id]
    elif fixture["revised_plan_type"] == "parallel":
        evidence_modules = [node.module_id for node in child_nodes]
    else:
        evidence_modules = [node.module_id for node in child_nodes if node.module_id != alternative_id]
    relation_map = {module_id: relation for module_id, relation in zip(evidence_modules, fixture["evidence_relations"])}
    type_map = {module_id: evidence_type for module_id, evidence_type in zip(evidence_modules, required)}

    def executor(current_state, _plan, node, active_registry, **_kwargs):
        if node.module_id == blocked_id:
            return NodeExecution(node.id, node.module_id, "1.0.0", "blocked", None, tuple(node.input_bindings.values()), (), (), (), (fixture["failed_gate_code"],), {}, "CompatibilityError")
        return completed_execution(current_state, node, active_registry)

    def mapper(execution, node, current_state):
        if node.module_id not in relation_map:
            return ()
        return (
            EvidenceRecord(
                id=f"evidence-{node.id}",
                hypothesis_id=active.id,
                artifact_id=execution.output_artifact_ids[0],
                relation=relation_map[node.module_id],
                evidence_type=type_map[node.module_id],
                independent_group=f"group-{node.id}",
                study_design=current_state.context.study_design,
                experimental_unit=current_state.context.experimental_unit,
                effect={"direction": "declared"},
                uncertainty={"status": "bounded"},
                quality_status="passed",
                limitations=(),
                rationale="The controlled scenario output has a declared directional relation to the hypothesis.",
            ),
        )

    controller = ResearchController(
        registry,
        environment_provider=lambda _manifest: None,
        node_executor=executor,
        evidence_mapper=mapper,
        replanner=lambda _state, current, _executions, _findings: child_plan(fixture, current),
        policy=ControllerPolicy(max_plan_revisions=2, max_node_attempts=1, parallel_workers=3, stop_on_fatal=True),
    )
    result = controller.advance(state, parent)
    replayed = ProjectState.from_dict(result.state.to_dict())
    temporary.cleanup()
    return result, replayed


class ResearchCycleScenarioTests(unittest.TestCase):
    def test_every_scenario_executes_gate_revision_hypothesis_transition_and_replay(self):
        for path in sorted(FIXTURES.glob("*.json")):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(scenario=fixture["id"]):
                result, replayed = run_scenario(fixture)
                self.assertEqual(result.stop_reason, "plan_completed")
                self.assertEqual(result.active_plan.plan_type, fixture["revised_plan_type"])
                self.assertEqual(result.active_plan.revision, 2)
                self.assertEqual(result.active_plan.parent_plan_id, result.state.plans[0].id)
                self.assertIn(fixture["failed_gate_code"], result.executions[0].compatibility_finding_codes)
                self.assertEqual(result.assessments[0].new_status, fixture["hypothesis_transition"][1])
                self.assertTrue(result.state.evidence)
                self.assertEqual(replayed.state_digest, result.state.state_digest)
                self.assertEqual(result.state.state_digest, fixture["expected_replay_digest"])


if __name__ == "__main__":
    unittest.main()
