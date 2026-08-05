import unittest
from types import SimpleNamespace

from biomed_workbench.kernel.execution_chain import (
    gate_adjudication_bundle_digest,
    validate_gate_adjudication_chain,
)
from biomed_workbench.kernel.scientific_dependency import ScientificGateAdjudication


class GateAdjudicationPolicyTests(unittest.TestCase):
    def _state(self, *, adjudication_status, decision_action):
        gate_id = "gate-not-evaluable"
        evidence_digest = "a" * 64
        result_digest = "b" * 64
        observed = SimpleNamespace(
            id="observed-receipt-one",
            source_kind="handoff",
            handoff_id="handoff-one",
            postflight_results={
                gate_id: {
                    "status": "not_evaluable",
                    "evaluations": ({
                        "port": "result-port",
                        "evaluator_type": "tool-native",
                        "evidence_payload_sha256": evidence_digest,
                    },),
                }
            },
            postflight_result_digests={gate_id: result_digest},
        )
        adjudication = ScientificGateAdjudication(
            id="adjudication-gate-not-evaluable",
            artifact_id="artifact-result",
            observed_execution_receipt_id=observed.id,
            gate_id=gate_id,
            port="result-port",
            evaluator_type="tool-native",
            gate_result_digest=result_digest,
            evidence_payload_sha256=evidence_digest,
            status=adjudication_status,
            reviewer_identity="independent-scientific-reviewer",
            rationale_zh="当前证据不足以直接计算该门禁，因此独立记录审议结论和保留范围。",
            rationale_en="The evidence cannot directly compute this gate, so the adjudication and retained scope are recorded independently.",
            limitations_zh=("该门禁当前不可直接评定，所有下游解释必须保留此限制。",),
            limitations_en=("This gate is not directly evaluable and every downstream interpretation must retain that limitation.",),
            source_urls=("https://www.nature.com/articles/s41592-019-0686-2",),
        )
        state = SimpleNamespace(
            artifact_reloads=(SimpleNamespace(
                artifact_id="artifact-result", observed_execution_receipt_id=observed.id,
            ),),
            observed_executions=(observed,),
            execution_handoffs=(SimpleNamespace(
                id="handoff-one", planned_output_artifact_ids={"result-port": "artifact-result"},
            ),),
            gate_adjudications=(adjudication,),
            artifact_reviews=(SimpleNamespace(
                artifact_id="artifact-result", gate_adjudication_ids=(adjudication.id,),
            ),),
            scientific_decisions=(),
        )
        digest = gate_adjudication_bundle_digest(state, "artifact-result")
        state.scientific_decisions = (SimpleNamespace(
            artifact_id="artifact-result", gate_adjudication_digest=digest, action=decision_action,
        ),)
        return state

    def test_not_evaluable_gate_rejects_unqualified_acceptance(self):
        state = self._state(adjudication_status="accepted", decision_action="retain-as-evidence")
        with self.assertRaisesRegex(ValueError, "accepted-with-caveat"):
            validate_gate_adjudication_chain(state, "artifact-result")

    def test_not_evaluable_gate_requires_caveated_adjudication_and_decision(self):
        state = self._state(adjudication_status="accepted-with-caveat", decision_action="retain-as-evidence")
        with self.assertRaisesRegex(ValueError, "caveated retain decision"):
            validate_gate_adjudication_chain(state, "artifact-result")
        state = self._state(adjudication_status="accepted-with-caveat", decision_action="retain-with-caveat")
        self.assertEqual(
            validate_gate_adjudication_chain(state, "artifact-result"),
            ("adjudication-gate-not-evaluable",),
        )


if __name__ == "__main__":
    unittest.main()
