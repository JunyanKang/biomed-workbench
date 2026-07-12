import copy
import unittest

from biomed_workbench.kernel.decisions import DecisionEvent
from biomed_workbench.kernel.state import ProjectState, apply_event, replay
from tests.unit.kernel.test_state import populated_state, research_plan


class StateReplayContractTests(unittest.TestCase):
    def test_canonical_round_trip_and_event_replay_reproduce_exact_state_digest(self):
        state = populated_state()
        plan = research_plan()
        state = apply_event(
            state,
            "plan_created",
            {"plan": plan.to_dict(), "activate": True},
            rationale="Create a replayable analysis plan.",
            replacement_action_ids=("node-cell-state-analysis",),
        )

        restored = ProjectState.from_dict(state.to_dict())
        replayed = replay(state.context, state.decisions)

        self.assertEqual(restored, state)
        self.assertEqual(replayed, state)
        self.assertEqual(restored.state_digest, state.state_digest)

    def test_payload_or_digest_tampering_is_detected(self):
        state = populated_state()
        serialized = state.to_dict()
        payload_tampered = copy.deepcopy(serialized)
        payload_tampered["decisions"][0]["payload"]["artifact"]["content"]["cell_count"] = 1
        digest_tampered = copy.deepcopy(serialized)
        digest_tampered["state_digest"] = "0" * 64

        for value in (payload_tampered, digest_tampered):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ProjectState.from_dict(value)

    def test_nonmonotonic_or_broken_event_chain_is_rejected(self):
        state = populated_state()
        events = [event.to_dict() for event in state.decisions]
        events[1]["sequence"] = 1
        with self.assertRaises(ValueError):
            replay(state.context, tuple(DecisionEvent.from_dict(item) for item in events))

        events = [event.to_dict() for event in state.decisions]
        events[1]["prior_state_digest"] = "f" * 64
        with self.assertRaises(ValueError):
            replay(state.context, tuple(DecisionEvent.from_dict(item) for item in events))


if __name__ == "__main__":
    unittest.main()
