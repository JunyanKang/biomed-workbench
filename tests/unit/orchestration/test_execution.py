import unittest
import time
from dataclasses import replace
import json
import tempfile
from pathlib import Path

from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import ProjectState, apply_event
from biomed_workbench.kernel.artifact_store import ProjectArtifactStore
from biomed_workbench.kernel.artifacts import ScientificArtifact
from biomed_workbench.kernel.environment_identity import capture_analysis_environment
from biomed_workbench.kernel.execution_receipts import ObservedExecutionReceipt
from biomed_workbench.kernel.identity import digest_value
from biomed_workbench.modules.compatibility import EnvironmentSnapshot
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.contract import ExecutionContract, observed_output_contract_digest, parse_manifest
from biomed_workbench.orchestration.execution import execute_node
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.orchestration.test_planner import inline_artifact
from tests.unit.modules.test_scientific_command import executable
from tests.unit.test_module_contract import closed_schema, command_manifest_payload


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
        self.assertTrue(result.provenance["tested_version_baseline"]["dependencies"]["python"])
        self.assertEqual(result.provenance["compatibility_policy"]["dependencies"]["python"], (">=3.14,<3.15",))
        self.assertRegex(result.provenance["parameters_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(result.provenance["output_digest"], r"^[0-9a-f]{64}$")

    def test_compatible_runtime_patch_is_recorded_without_claiming_tested_baseline(self):
        state = execution_state()
        node = execution_node()

        result = execute_node(state, execution_plan(node), node, self.registry, environment_provider=lambda _manifest: environment("3.14.9"))

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.provenance["dependencies"]["python"], "3.14.9")
        self.assertFalse(result.provenance["tested_version_baseline"]["dependencies"]["python"])

    def test_repeat_execution_reuses_exact_environment_and_blocks_content_drift(self):
        state = execution_state()
        node = execution_node()
        plan = execution_plan(node)
        state = apply_event(
            state,
            "plan_created",
            {"plan": plan.to_dict(), "activate": True},
            rationale="Register a plan before testing repeat-environment identity.",
        )
        current = capture_analysis_environment()
        snapshot = EnvironmentSnapshot(
            tools={}, dependencies={"python": "3.14.3"}, platform="macos-arm64",
            analysis_environment=current,
        )
        first = execute_node(
            state, plan, node, self.registry,
            environment_provider=lambda _manifest: snapshot,
        )
        manifest = self.registry.get(node.module_id)
        receipt = ObservedExecutionReceipt.create(
            plan_node_id=node.id,
            module_id=manifest.id,
            module_version=manifest.version,
            compatibility_row_id=str(first.compatibility_row_id),
            observed_output_contract_digest=observed_output_contract_digest(manifest),
            parameters_digest=str(first.provenance["parameters_digest"]),
            runtime_versions={"python": "3.14.3"},
            output_artifact_digests={artifact.id: artifact.content_digest for artifact in first.artifacts},
            postflight_result_digests={},
            postflight_results={},
            process_exit_code=0,
            source_kind="direct",
            execution_request_digest=digest_value(first.to_dict()),
            execution_environment=first.provenance["analysis_environment"],
        )
        state = apply_event(
            state,
            "execution_observed",
            {"receipt": receipt.to_dict()},
            rationale="Record the first environment-bound execution.",
        )

        reused = execute_node(
            state, plan, node, self.registry,
            environment_provider=lambda _manifest: snapshot,
        )
        self.assertEqual(reused.status, "completed")
        self.assertEqual(reused.provenance["analysis_environment_reuse_status"], "reused-exact")

        drifted = capture_analysis_environment(container_image_digest="a" * 64)
        blocked = execute_node(
            state,
            plan,
            node,
            self.registry,
            environment_provider=lambda _manifest: EnvironmentSnapshot(
                tools={}, dependencies={"python": "3.14.3"}, platform="macos-arm64",
                analysis_environment=drifted,
            ),
        )
        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(blocked.safe_error_class, "EnvironmentDriftError")
        self.assertIn("ANALYSIS_ENVIRONMENT_DRIFT", blocked.compatibility_finding_codes)

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

    def test_command_node_resolves_payload_roles_and_emits_payload_backed_artifact(self):
        body = """
import argparse, json
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
json.dump({'label': args.label, 'text': open(args.input).read().upper()}, open(args.output, 'w'))
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            source = root / "reads.txt"
            source.write_text("acgt", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(source, role="records", media_type="text/plain")
            manifest_payload = command_manifest_payload()
            manifest_payload["input_schema"] = closed_schema({"label": {"type": "string"}}, ["label"])
            manifest_payload["output_schema"] = closed_schema(
                {"payload_roles": {"type": "array", "items": {"type": "string"}}},
                ["payload_roles"],
            )
            manifest_payload["input_artifacts"][0]["required_metadata"] = []
            manifest = parse_manifest(manifest_payload)
            registry = ModuleRegistry((manifest,), "command-fixture")
            state = ProjectState.create(project_context())
            state = apply_event(state, "hypothesis_added", {"hypothesis": hypothesis().to_dict()}, rationale="Register command execution hypothesis.")
            artifact = ScientificArtifact.create(
                id="artifact-command-input",
                artifact_type="feature_matrix",
                schema_version="1.0",
                format_name="inline-json",
                format_version="1",
                compression="none",
                orientation="records",
                indexes=(),
                producing_module_id=None,
                producing_module_version=None,
                source_artifact_ids=(),
                scientific_scope={"species": "human"},
                experimental_unit="independent-organoid-line",
                denominator="four-independent-lines",
                processing_level="raw",
                quality_status="passed",
                coordinate_system=None,
                genome_build=None,
                annotation_release=None,
                identifier_namespace=None,
                producer_tool_versions={},
                content={"label": "treated"},
                payloads=(payload,),
            )
            state = apply_event(state, "artifact_registered", {"artifact": artifact.to_dict()}, rationale="Register command input payload.")
            node = PlanNode(
                id="node-command-fixture",
                module_id=manifest.id,
                input_bindings={"records": artifact.id},
                dependencies=(),
                branch_id="branch-command",
                target_hypothesis_ids=(hypothesis().id,),
                expected_evidence_types=("fixture-evidence",),
                expected_output_artifact_types=("quality_report",),
                planned_output_artifact_ids={"profile": "artifact-command-profile"},
                compatibility_row_candidates=(manifest.compatibility_matrix[0].id,),
                status="ready",
                attempt=0,
            )
            plan = ResearchDAG.create(
                id="plan-command-execution",
                objective="Execute one exact version-gated payload command.",
                nodes=(node,),
                required_output_artifact_types=("quality_report",),
                plan_type="single",
                revision=1,
                parent_plan_id=None,
                rationale=("The payload and command contract are exactly compatible.",),
            )

            result = execute_node(
                state,
                plan,
                node,
                registry,
                environment_provider=lambda _manifest: EnvironmentSnapshot(
                    tools={"fixture-tool": "2.4.1"},
                    dependencies={"python": "3.14.3"},
                    platform="macos-arm64",
                ),
                artifact_store=store,
                command_executable_resolver=lambda _name: tool,
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.artifacts[0].payloads[0].role, "profile")
            output = json.loads(store.resolve(result.artifacts[0].payloads[0]).read_text(encoding="utf-8"))
            self.assertEqual(output, {"label": "treated", "text": "ACGT"})
            self.assertNotIn(str(root), json.dumps(result.to_dict(), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
