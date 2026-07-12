import unittest
import time
from dataclasses import replace

from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import ProjectState, apply_event
from biomed_workbench.modules.compatibility import EnvironmentSnapshot
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.contract import ExecutionContract
from biomed_workbench.orchestration.execution import execute_node
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.orchestration.test_planner import inline_artifact


def execution_state(*, quality="passed", rows=None):
    state = ProjectState.create(project_context())
    state = apply_event(state, "hypothesis_added", {"hypothesis": hypothesis().to_dict()}, rationale="Register the execution hypothesis.")
    value = inline_artifact("artifact-table", "scientific_table", quality_status=quality)
    payload = value.to_dict()
    payload["content"] = {"rows": rows if rows is not None else [{"sample_id": "s1", "value": 1.0}, {"sample_id": "s2", "value": None}]}
    from biomed_workbench.kernel.artifacts import ScientificArtifact

    value = ScientificArtifact.create(**{key: item for key, item in payload.items() if key != "content_digest"})
    return apply_event(state, "artifact_registered", {"artifact": value.to_dict()}, rationale="Register the execution input table.")


def execution_node():
    return PlanNode(
        id="node-data-profile",
        module_id="data-profile",
        input_bindings={"records": "artifact-table"},
        dependencies=(),
        branch_id="branch-quality",
        target_hypothesis_ids=(hypothesis().id,),
        expected_evidence_types=("cell-state-association",),
        expected_output_artifact_types=("quality_report",),
        planned_output_artifact_ids={"profile": "artifact-planned-profile"},
        compatibility_row_candidates=("python-3.14.3-inline-json-1",),
        status="ready",
        attempt=0,
    )


def execution_plan(node=None):
    node = node or execution_node()
    return ResearchDAG.create(
        id="plan-execution",
        objective="Profile the registered scientific table under strict compatibility and quality gates.",
        nodes=(node,),
        required_output_artifact_types=("quality_report",),
        plan_type="single",
        revision=1,
        parent_plan_id=None,
        rationale=("The table contract matches the validated data-profile module input.",),
    )


def environment(version="3.14.3"):
    return EnvironmentSnapshot(tools={}, dependencies={"python": version}, platform="macos-arm64")


def slow_profile(**_inputs):
    time.sleep(2)
    return {"row_count": 0, "column_count": 0, "column_order": [], "columns": {}}


class NodeExecutionTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModuleRegistry.discover(BUILTIN_ROOT)

    def test_compatible_node_executes_and_emits_versioned_typed_artifact(self):
        state = execution_state()
        node = execution_node()

        result = execute_node(state, execution_plan(node), node, self.registry, environment_provider=lambda _manifest: environment())

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.compatibility_row_id, "python-3.14.3-inline-json-1")
        self.assertEqual(result.output_artifact_ids, ("artifact-planned-profile",))
        self.assertEqual(result.artifacts[0].artifact_type, "quality_report")
        self.assertEqual(result.artifacts[0].producing_module_id, "data-profile")
        self.assertEqual(result.artifacts[0].producer_tool_versions, {})
        self.assertEqual(result.provenance["dependencies"]["python"], "3.14.3")
        self.assertRegex(result.provenance["parameters_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(result.provenance["output_digest"], r"^[0-9a-f]{64}$")

    def test_unknown_dependency_version_blocks_before_entrypoint(self):
        state = execution_state()
        node = execution_node()
        calls = []

        result = execute_node(
            state,
            execution_plan(node),
            node,
            self.registry,
            environment_provider=lambda _manifest: environment("3.15.0"),
            entrypoint_resolver=lambda _module_id: calls.append("resolved"),
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.safe_error_class, "CompatibilityError")
        self.assertEqual(calls, [])
        self.assertIn("UNVALIDATED_DEPENDENCY_VERSION", result.compatibility_finding_codes)

    def test_major_quality_and_invalid_schema_block_without_execution(self):
        cases = (
            (execution_state(quality="major"), "QualityGateError"),
            (execution_state(rows="not-an-array"), "InputValidationError"),
        )
        for state, error_class in cases:
            calls = []
            node = execution_node()
            result = execute_node(
                state,
                execution_plan(node),
                node,
                self.registry,
                environment_provider=lambda _manifest: environment(),
                entrypoint_resolver=lambda _module_id: calls.append("resolved"),
            )
            with self.subTest(error_class=error_class):
                self.assertEqual(result.status, "blocked")
                self.assertEqual(result.safe_error_class, error_class)
                self.assertEqual(calls, [])

    def test_declared_timeout_terminates_entrypoint_process(self):
        manifest = self.registry.get("data-profile")
        bounded = replace(manifest, execution=ExecutionContract(kind="python", timeout_seconds=1, max_output_bytes=manifest.execution.max_output_bytes))
        registry = ModuleRegistry((bounded,), "bounded-fixture")
        node = execution_node()
        started = time.monotonic()

        result = execute_node(
            execution_state(),
            execution_plan(node),
            node,
            registry,
            environment_provider=lambda _manifest: environment(),
            entrypoint_resolver=lambda _module_id: slow_profile,
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.safe_error_class, "TimeoutError")
        self.assertLess(time.monotonic() - started, 1.8)


if __name__ == "__main__":
    unittest.main()
