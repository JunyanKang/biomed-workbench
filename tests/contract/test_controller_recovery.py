import unittest

from biomed_workbench.orchestration.controller import ControllerPolicy, ResearchController
from tests.unit.orchestration.test_controller import completed_execution, serial_fixture


class ControllerRecoveryContractTests(unittest.TestCase):
    def test_completed_state_round_trip_does_not_repeat_module_execution(self):
        temporary, registry, state, plan = serial_fixture()
        self.addCleanup(temporary.cleanup)
        calls = []

        def executor(current_state, _plan, node, active_registry, **_kwargs):
            calls.append(node.id)
            return completed_execution(current_state, node, active_registry)

        controller = ResearchController(
            registry,
            environment_provider=lambda _manifest: None,
            node_executor=executor,
            policy=ControllerPolicy(
                require_approved_admission=False,
                require_scientific_review=False,
                require_evidence_map_for_publication=False,
            ),
        )
        first = controller.advance(state, plan)
        first_calls = tuple(calls)
        second = controller.resume(first.state.to_dict())

        self.assertEqual(tuple(calls), first_calls)
        self.assertEqual(second.stop_reason, "already_complete")
        self.assertEqual(second.state.state_digest, first.state.state_digest)


if __name__ == "__main__":
    unittest.main()
