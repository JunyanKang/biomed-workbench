import unittest

from biomed_workbench.assistant import ResearchAssistant
from biomed_workbench.orchestration.controller import ResearchController
from biomed_workbench.orchestration.planner import PlanningRequest
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.orchestration.test_controller import completed_execution
from tests.unit.orchestration.test_planner import inline_artifact, module_payload, workflow_registry


class StatefulAssistantEndToEndTests(unittest.TestCase):
    def test_one_entry_initializes_plans_executes_and_resumes_project_state(self):
        temporary, registry = workflow_registry(
            (
                module_payload("normalize-matrix", "count_matrix", "normalized_matrix"),
                module_payload("test-contrast", "normalized_matrix", "contrast_result"),
            )
        )
        self.addCleanup(temporary.cleanup)
        controller = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=lambda state, _plan, node, active_registry, **_kwargs: completed_execution(state, node, active_registry),
        )
        assistant = ResearchAssistant(registry=registry, controller=controller)

        result = assistant.start(
            project_context(),
            artifacts=(inline_artifact("artifact-counts", "count_matrix"),),
            hypotheses=(hypothesis(),),
            requests=(PlanningRequest("request-contrast", "contrast_result", (hypothesis().id,), ("cell-state-association",)),),
        )
        resumed = assistant.continue_project(result.state.to_dict())

        self.assertEqual(result.active_plan.plan_type, "serial")
        self.assertEqual(result.stop_reason, "plan_completed")
        self.assertIn("contrast_result", {artifact.artifact_type for artifact in result.state.artifacts})
        self.assertEqual(resumed.stop_reason, "already_complete")
        self.assertEqual(resumed.state.state_digest, result.state.state_digest)

    def test_stateful_entry_rejects_missing_hypothesis_or_artifact_contracts(self):
        temporary, registry = workflow_registry((module_payload("normalize-matrix", "count_matrix", "normalized_matrix"),))
        self.addCleanup(temporary.cleanup)
        assistant = ResearchAssistant(
            registry=registry,
            controller=ResearchController(registry, environment_provider=lambda _manifest: None, node_executor=lambda *_args, **_kwargs: None),
        )
        request = PlanningRequest("request-normalized", "normalized_matrix", (hypothesis().id,), ("cell-state-association",))

        with self.assertRaises(ValueError):
            assistant.start(project_context(), artifacts=(), hypotheses=(hypothesis(),), requests=(request,))
        with self.assertRaises(ValueError):
            assistant.start(project_context(), artifacts=(inline_artifact("artifact-counts", "count_matrix"),), hypotheses=(), requests=(request,))


if __name__ == "__main__":
    unittest.main()
