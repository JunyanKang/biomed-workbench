import threading
import time
import unittest

from biomed_workbench.kernel.artifacts import ScientificArtifact
from biomed_workbench.kernel.evidence import EvidenceRecord
from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import apply_event
from biomed_workbench.orchestration.controller import ControllerPolicy, ResearchController
from biomed_workbench.orchestration.execution import NodeExecution
from biomed_workbench.orchestration.graph import build_capability_graph
from biomed_workbench.orchestration.planner import PlanningRequest, plan_research
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.orchestration.test_planner import inline_artifact, module_payload, state_with, workflow_registry


def execution_artifact(state, node, registry):
    manifest = registry.get(node.module_id)
    port = manifest.output_artifacts[0]
    artifact_id = node.planned_output_artifact_ids[port.name]
    source_ids = tuple(node.input_bindings.values())
    denominators = {artifact.denominator for artifact in state.artifacts if artifact.id in source_ids}
    return ScientificArtifact.create(
        id=artifact_id,
        artifact_type=port.artifact_type,
        schema_version="1.0",
        format_name="inline-json",
        format_version="1",
        compression="none",
        orientation="request-object",
        indexes=(),
        producing_module_id=manifest.id,
        producing_module_version=manifest.version,
        source_artifact_ids=source_ids,
        scientific_scope={"species": "human", "sample_id": "s1"},
        experimental_unit=state.context.experimental_unit,
        denominator=next(iter(denominators)),
        processing_level="derived",
        quality_status="passed",
        coordinate_system=None,
        genome_build=None,
        annotation_release=None,
        identifier_namespace=None,
        producer_tool_versions={},
        content={"module": manifest.id, "sample_id": "s1"},
    )


def completed_execution(state, node, registry):
    artifact = execution_artifact(state, node, registry)
    return NodeExecution(
        node_id=node.id,
        module_id=node.module_id,
        module_version=registry.get(node.module_id).version,
        status="completed",
        compatibility_row_id=registry.get(node.module_id).compatibility_matrix[0].id,
        input_artifact_ids=tuple(node.input_bindings.values()),
        output_artifact_ids=(artifact.id,),
        artifacts=(artifact,),
        quality_findings=(),
        compatibility_finding_codes=(),
        provenance={"module_id": node.module_id, "module_version": "1.0.0", "compatibility_row_id": registry.get(node.module_id).compatibility_matrix[0].id},
        safe_error_class=None,
    )


def serial_fixture():
    temporary, registry = workflow_registry(
        (
            module_payload("normalize-matrix", "count_matrix", "normalized_matrix"),
            module_payload("test-contrast", "normalized_matrix", "contrast_result"),
        )
    )
    state = state_with(inline_artifact("artifact-counts", "count_matrix"))
    request = PlanningRequest("request-contrast", "contrast_result", (hypothesis().id,), ("cell-state-association",))
    plan = plan_research(state, registry, build_capability_graph(registry), (request,))
    return temporary, registry, state, plan


class ResearchControllerTests(unittest.TestCase):
    def test_serial_nodes_materialize_artifacts_in_dependency_order_and_update_state(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)
        order = []

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            order.append(node.module_id)
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(registry, environment_provider=lambda _manifest: None, node_executor=executor).advance(state, plan)

        self.assertEqual(order, ["normalize-matrix", "test-contrast"])
        self.assertEqual(result.stop_reason, "plan_completed")
        self.assertEqual(len(result.executions), 2)
        self.assertTrue({execution.output_artifact_ids[0] for execution in result.executions} <= {artifact.id for artifact in result.state.artifacts})
        self.assertEqual({node.status for node in result.active_plan.nodes}, {"completed"})
        self.assertGreater(result.state.revision, state.revision)

    def test_independent_ready_nodes_execute_in_parallel_but_merge_deterministically(self):
        temporary, registry = workflow_registry(
            (
                module_payload("normalize-matrix", "count_matrix", "normalized_matrix"),
                module_payload("measure-image", "image_collection", "image_measurements"),
            )
        )
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"), inline_artifact("artifact-images", "image_collection"))
        plan = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (
                PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",)),
                PlanningRequest("request-image", "image_measurements", (hypothesis().id,), ("regulatory-association",)),
            ),
        )
        threads = set()

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            threads.add(threading.current_thread().name)
            time.sleep(0.05)
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(max_plan_revisions=2, max_node_attempts=1, parallel_workers=2, stop_on_fatal=True),
        ).advance(state, plan)

        self.assertGreaterEqual(len(threads), 2)
        self.assertEqual(tuple(execution.node_id for execution in result.executions), tuple(sorted(execution.node_id for execution in result.executions)))
        self.assertEqual(result.stop_reason, "plan_completed")

    def test_blocked_downstream_preserves_completed_upstream_and_stops_branch(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            if node.module_id == "test-contrast":
                return NodeExecution(
                    node.id,
                    node.module_id,
                    "1.0.0",
                    "blocked",
                    None,
                    tuple(node.input_bindings.values()),
                    (),
                    (),
                    (),
                    ("UNVALIDATED_DEPENDENCY_VERSION",),
                    {},
                    "CompatibilityError",
                )
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(registry, environment_provider=lambda _manifest: None, node_executor=executor).advance(state, plan)

        self.assertEqual(result.stop_reason, "blocked")
        self.assertIn("normalized_matrix", {artifact.artifact_type for artifact in result.state.artifacts})
        self.assertEqual({node.module_id: node.status for node in result.active_plan.nodes}["test-contrast"], "blocked")

    def test_evidence_mapper_changes_hypothesis_status_and_state_replays(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)

        def mapper(execution, node, current_state):
            if node.module_id != "test-contrast":
                return ()
            return (
                EvidenceRecord(
                    id="evidence-controller-contrast",
                    hypothesis_id=hypothesis().id,
                    artifact_id=execution.output_artifact_ids[0],
                    relation="supports",
                    evidence_type="cell-state-association",
                    independent_group="controller-cohort",
                    study_design="paired-perturbation",
                    experimental_unit=current_state.context.experimental_unit,
                    effect={"estimate": -0.5},
                    uncertainty={"interval": [-0.8, -0.2]},
                    quality_status="passed",
                    limitations=(),
                    rationale="The completed contrast matches one prespecified expected observation.",
                ),
            )

        controller = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=lambda current_state, _plan, node, active_registry, **_kwargs: completed_execution(current_state, node, active_registry),
            evidence_mapper=mapper,
        )
        result = controller.advance(state, plan)
        resumed = controller.resume(result.state.to_dict())

        self.assertEqual(result.assessments[0].new_status, "inconclusive")
        self.assertEqual(result.state.hypotheses[0].status, "inconclusive")
        self.assertEqual(resumed.state.state_digest, result.state.state_digest)
        self.assertEqual(resumed.stop_reason, "already_complete")

    def test_transient_failure_retries_within_bound_and_then_completes(self):
        temporary, registry = workflow_registry((module_payload("normalize-matrix", "count_matrix", "normalized_matrix"),))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"))
        plan = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",)),),
        )
        attempts = []

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            attempts.append(node.attempt)
            if len(attempts) == 1:
                return NodeExecution(node.id, node.module_id, "1.0.0", "failed", None, tuple(node.input_bindings.values()), (), (), (), (), {}, "TransientError")
            return completed_execution(current_state, node, active_registry)

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(max_plan_revisions=1, max_node_attempts=2, parallel_workers=1, stop_on_fatal=True),
        ).advance(state, plan)

        self.assertEqual(attempts, [1, 2])
        self.assertEqual(result.stop_reason, "plan_completed")

    def test_blocked_primary_is_replaced_by_revision_with_declared_alternative(self):
        primary = module_payload("primary-normalizer", "count_matrix", "normalized_matrix", alternatives=("alternative-normalizer",))
        alternative = module_payload("alternative-normalizer", "count_matrix", "normalized_matrix")
        temporary, registry = workflow_registry((primary, alternative))
        self.addCleanup(temporary.cleanup)
        state = state_with(inline_artifact("artifact-counts", "count_matrix"))
        initial = plan_research(
            state,
            registry,
            build_capability_graph(registry),
            (PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",)),),
            compatible_module_ids=("primary-normalizer",),
        )

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            if node.module_id == "primary-normalizer":
                return NodeExecution(
                    node_id=node.id,
                    module_id=node.module_id,
                    module_version="1.0.0",
                    status="blocked",
                    compatibility_row_id=None,
                    input_artifact_ids=tuple(node.input_bindings.values()),
                    output_artifact_ids=(),
                    artifacts=(),
                    quality_findings=(),
                    compatibility_finding_codes=("UNVALIDATED_DEPENDENCY_VERSION",),
                    provenance={},
                    safe_error_class="CompatibilityError",
                )
            return completed_execution(current_state, node, active_registry)

        def replanner(current_state, parent, _executions, _findings):
            old = parent.nodes[0]
            replacement = PlanNode(
                **{
                    **old.__dict__,
                    "id": "node-alternative-normalizer",
                    "module_id": "alternative-normalizer",
                    "planned_output_artifact_ids": {"profile": "artifact-planned-alternative"},
                    "compatibility_row_candidates": (registry.get("alternative-normalizer").compatibility_matrix[0].id,),
                    "status": "pending",
                    "attempt": 0,
                }
            )
            return ResearchDAG.create(
                id="plan-alternative-revision",
                objective=parent.objective,
                nodes=(replacement,),
                required_output_artifact_types=parent.required_output_artifact_types,
                plan_type="single",
                revision=parent.revision + 1,
                parent_plan_id=parent.id,
                rationale=("The primary module was blocked, so use its declared compatible alternative.",),
            )

        result = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            replanner=replanner,
            policy=ControllerPolicy(max_plan_revisions=2, max_node_attempts=1, parallel_workers=1, stop_on_fatal=True),
        ).advance(state, initial)

        self.assertEqual(result.stop_reason, "plan_completed")
        self.assertEqual(result.active_plan.parent_plan_id, initial.id)
        self.assertEqual(result.active_plan.revision, 2)
        self.assertEqual(tuple(execution.module_id for execution in result.executions), ("primary-normalizer", "alternative-normalizer"))
        self.assertEqual(len(result.state.plans), 2)


if __name__ == "__main__":
    unittest.main()
