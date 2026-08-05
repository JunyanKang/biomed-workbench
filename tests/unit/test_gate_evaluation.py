import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.semantic_output_validation import evaluate_structured_gate


class GateEvaluationTests(unittest.TestCase):
    def _case(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(temporary) / "primary.json"
        path.write_text(
            json.dumps({
                "schema_version": 1,
                "analysis_mode": "observed",
                "records": [{"sample_id": "s1", "metric": "mapped_reads", "value": 100, "unit": "reads"}],
            }),
            encoding="utf-8",
        )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        payloads = ({
            "role": "primary", "path": str(path), "media_type": "application/json", "sha256": digest,
        },)
        semantic = {
            "family_admission_status": "passed",
            "profile": "bulk-assay-summary-v1",
            "family_admission": True,
            "evidence_payload_digests": {"primary": digest},
        }
        return payloads, semantic

    def test_family_admission_only_proves_a_system_reload_gate(self):
        payloads, semantic = self._case()
        result = evaluate_structured_gate(
            payloads=payloads,
            gate_id="bulk-ribosome-profiling-execution-reload",
            evaluator_type="system-provenance",
            evidence_payload_role="primary",
            metric_key="family_admission",
            metric_type="boolean",
            operator="equals",
            threshold=True,
            semantic_result=semantic,
        )
        self.assertEqual(result["status"], "passed")

    def test_minimal_ribosome_payload_does_not_pass_assay_or_claim_gates(self):
        payloads, semantic = self._case()
        for gate_id, evaluator_type in (
            ("bulk-ribosome-profiling-assay-contract", "provenance-design"),
            ("bulk-ribosome-profiling-claim-boundary", "claim-boundary"),
        ):
            with self.subTest(gate_id=gate_id):
                result = evaluate_structured_gate(
                    payloads=payloads,
                    gate_id=gate_id,
                    evaluator_type=evaluator_type,
                    evidence_payload_role="primary",
                    metric_key="scientific_review",
                    metric_type="string",
                    operator="equals",
                    threshold="accepted",
                    semantic_result=semantic,
                )
                self.assertEqual(result["status"], "requires_review")

    def test_minimal_single_cell_container_cannot_pass_integration_design_gates(self):
        payloads, semantic = self._case()
        semantic["profile"] = "single-cell-object-v1"
        for gate_id in (
            "integration-input-and-design-semantics",
            "integration-identifiability",
            "integration-no-label-leakage",
            "integration-batch-mixing",
            "integration-biological-conservation",
            "integration-selection-sensitivity",
        ):
            result = evaluate_structured_gate(
                payloads=payloads,
                gate_id=gate_id,
                evaluator_type="provenance-design",
                evidence_payload_role="primary",
                metric_key="scientific_review",
                metric_type="string",
                operator="equals",
                threshold="accepted",
                semantic_result=semantic,
            )
            self.assertEqual(result["status"], "requires_review")

    def test_high_risk_structure_spatial_trajectory_and_figure_claims_need_their_own_review(self):
        payloads, semantic = self._case()
        cases = (
            ("complex-result-accounting", "tool-native"),
            ("complex-score-semantics", "claim-boundary"),
            ("velocity-confidence", "tool-native"),
            ("spatial-sample-isolated-graph", "provenance-design"),
            ("domain-label-blind-benchmark", "provenance-design"),
            ("final-size-vector-raster-contract", "payload-derived"),
        )
        for gate_id, evaluator_type in cases:
            with self.subTest(gate_id=gate_id):
                result = evaluate_structured_gate(
                    payloads=payloads,
                    gate_id=gate_id,
                    evaluator_type=evaluator_type,
                    evidence_payload_role="primary",
                    metric_key="scientific_review",
                    metric_type="string",
                    operator="equals",
                    threshold="accepted",
                    semantic_result=semantic,
                )
                self.assertEqual(result["status"], "requires_review")

    def test_declared_evidence_role_digest_mismatch_is_rejected(self):
        payloads, semantic = self._case()
        semantic["evidence_payload_digests"] = {"primary": "f" * 64}
        with self.assertRaisesRegex(ValueError, "differs from the family-admitted payload"):
            evaluate_structured_gate(
                payloads=payloads,
                gate_id="integration-input-and-design-semantics",
                evaluator_type="provenance-design",
                evidence_payload_role="primary",
                metric_key="scientific_review",
                metric_type="string",
                operator="equals",
                threshold="accepted",
                semantic_result=semantic,
            )


if __name__ == "__main__":
    unittest.main()
