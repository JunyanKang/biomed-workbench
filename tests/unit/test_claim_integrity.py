import unittest

from biomed_workbench.capabilities.claim_integrity import audit_claim_evidence_integrity


_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64


def declared(**overrides):
    value = {
        "id": "claim-1",
        "text": "Perturbing regulator X causally reduces outcome Y.",
        "claim_strength": "causal",
        "intended_evidence_types": ["literature", "experiment"],
        "citation_ids": ["citation-1"],
        "experiment_ids": ["experiment-1"],
        "analysis_artifact_ids": [],
        "minimum_independent_supports": 2,
        "negative_constraints": [{"id": "constraint-1", "description": "Do not claim complete rescue."}],
        "partial_support_policy": "forbidden",
    }
    value.update(overrides)
    return value


def emitted(**overrides):
    value = {
        "id": "emitted-1",
        "declared_claim_id": "claim-1",
        "text": "Perturbing regulator X causally reduces outcome Y.",
        "claim_strength": "causal",
        "citation_ids": ["citation-1"],
        "experiment_ids": ["experiment-1"],
        "analysis_artifact_ids": [],
    }
    value.update(overrides)
    return value


def citation(**overrides):
    value = {
        "id": "citation-1",
        "identity_status": "verified_match",
        "source_acquired": True,
        "metadata_verified_against_original": True,
        "claim_content_reviewed": True,
        "retrieval_status": "completed",
        "verification_method": "original_source_review",
        "study_design": "observational-cohort",
        "independent_group": "published-cohort-1",
    }
    value.update(overrides)
    return value


def experiment(**overrides):
    value = {
        "id": "experiment-1",
        "study_design": "controlled-perturbation",
        "independent_group": "local-perturbation-1",
        "planned_units": [
            {"id": "unit-1", "planned": "Measure outcome Y after perturbation.", "executed": True, "skip_reason": None, "result_pointer": "artifact-result-1"}
        ],
        "negative_results": [],
        "known_limitations": [{"id": "limitation-1", "description": "One biological system was tested."}],
        "results_reviewed": True,
        "reproducibility_record": {"input_digest": _DIGEST_A, "parameter_digest": _DIGEST_B, "software_recorded": True, "randomization_recorded": True},
    }
    value.update(overrides)
    return value


def assessment(kind, evidence_id, **overrides):
    value = {
        "emitted_claim_id": "emitted-1",
        "evidence_kind": kind,
        "evidence_id": evidence_id,
        "relation": "supports",
        "adjudication_status": "completed",
        "review_method": "original_source_review" if kind == "citation" else "deterministic_result_check",
        "independent_from_writer": True,
        "rationale": "The reviewed source or result directly addresses the bounded claim.",
    }
    value.update(overrides)
    return value


def constraint(**overrides):
    value = {
        "emitted_claim_id": "emitted-1",
        "constraint_id": "constraint-1",
        "verdict": "not_violated",
        "review_method": "manual_review",
        "independent_from_writer": True,
        "rationale": "The emitted claim does not assert complete rescue.",
    }
    value.update(overrides)
    return value


def provenance(**overrides):
    value = {
        "audit_id": "claim-audit-1",
        "audit_version": "1.0.0",
        "review_owner": "independent evidence reviewer",
        "reviewed_at": "2026-07-13",
        "rules_independent_from_writer": True,
        "leakage_reviewed": True,
    }
    value.update(overrides)
    return value


def run(**overrides):
    payload = {
        "declared_claims": [declared()],
        "emitted_claims": [emitted()],
        "citations": [citation()],
        "experiments": [experiment()],
        "analysis_artifacts": [],
        "evidence_assessments": [assessment("citation", "citation-1"), assessment("experiment", "experiment-1")],
        "constraint_assessments": [constraint()],
        "audit_provenance": provenance(),
    }
    payload.update(overrides)
    return audit_claim_evidence_integrity(**payload)


class ClaimEvidenceIntegrityTests(unittest.TestCase):
    def test_passes_independent_original_source_and_experiment_support(self):
        result = run()

        self.assertEqual(result["overall_status"], "passed")
        self.assertEqual(result["claim_results"][0]["claim_state"], "supported")
        self.assertEqual(result["claim_results"][0]["emission_gate"], "passed")
        self.assertEqual(result["claim_results"][0]["independent_support_groups"], ["local-perturbation-1", "published-cohort-1"])

    def test_resolver_match_or_unresolved_identity_never_substitutes_for_content_review(self):
        result = run(
            citations=[citation(identity_status="unresolved", source_acquired=False, metadata_verified_against_original=False, claim_content_reviewed=False, retrieval_status="not_found", verification_method="resolver_only")]
        )

        codes = {item["code"] for item in result["claim_results"][0]["issues"]}
        self.assertTrue({"UNRESOLVED_CITATION_CANNOT_SUPPORT", "UNREAD_SOURCE_CANNOT_SUPPORT"} <= codes)
        self.assertEqual(result["claim_results"][0]["claim_state"], "weakened")
        self.assertEqual(result["overall_status"], "blocked")

    def test_all_skipped_experiment_cannot_support_a_claim(self):
        skipped = experiment(
            planned_units=[{"id": "unit-1", "planned": "Measure outcome Y.", "executed": False, "skip_reason": "Instrument unavailable.", "result_pointer": None}],
            results_reviewed=False,
        )
        result = run(experiments=[skipped])

        codes = {item["code"] for item in result["claim_results"][0]["issues"]}
        self.assertIn("UNEXECUTED_EXPERIMENT_CANNOT_SUPPORT", codes)
        self.assertEqual(result["overall_status"], "blocked")

    def test_missing_skip_reason_and_result_pointer_are_structural_blockers(self):
        malformed_science = experiment(planned_units=[
            {"id": "unit-1", "planned": "Primary endpoint.", "executed": False, "skip_reason": None, "result_pointer": None},
            {"id": "unit-2", "planned": "Secondary endpoint.", "executed": True, "skip_reason": None, "result_pointer": None},
        ])
        result = run(experiments=[malformed_science])

        codes = {item["code"] for item in result["global_issues"]}
        self.assertTrue({"UNEXECUTED_UNIT_MISSING_REASON", "EXECUTED_UNIT_MISSING_RESULT"} <= codes)
        self.assertEqual(result["overall_status"], "blocked")

    def test_refutation_and_negative_constraint_violation_override_support(self):
        result = run(
            evidence_assessments=[
                assessment("citation", "citation-1", relation="refutes", rationale="The original article reports the opposite direction."),
                assessment("experiment", "experiment-1"),
            ],
            constraint_assessments=[constraint(verdict="violated", rationale="The emitted text asserts complete rescue.")],
        )

        claim_result = result["claim_results"][0]
        self.assertEqual(claim_result["claim_state"], "refuted")
        self.assertEqual(claim_result["violated_constraint_ids"], ["constraint-1"])
        self.assertEqual(claim_result["emission_gate"], "blocked")

    def test_tool_failure_remains_unresolved_not_negative_evidence(self):
        failed = assessment(
            "citation",
            "citation-1",
            relation="not_assessed",
            adjudication_status="tool_failure",
            review_method="not_reviewed",
            independent_from_writer=False,
            rationale="The source retrieval service was unavailable.",
        )
        result = run(evidence_assessments=[failed, assessment("experiment", "experiment-1")])

        claim_result = result["claim_results"][0]
        self.assertEqual(claim_result["claim_state"], "weakened")
        self.assertEqual(claim_result["refuting_ids"], [])
        self.assertIn("EVIDENCE_AUDIT_TOOL_FAILURE", {item["code"] for item in claim_result["issues"]})

    def test_claim_drift_and_causal_escalation_block_emission(self):
        result = run(emitted_claims=[emitted(declared_claim_id=None, citation_ids=[], experiment_ids=[])], evidence_assessments=[], constraint_assessments=[])

        codes = {item["code"] for item in result["claim_results"][0]["issues"]}
        self.assertIn("EMITTED_CLAIM_UNDECLARED", codes)
        self.assertEqual(result["declared_not_emitted_ids"], ["claim-1"])
        self.assertEqual(result["overall_status"], "blocked")

        escalated = run(
            declared_claims=[declared(claim_strength="association")],
            emitted_claims=[emitted(claim_strength="causal")],
        )
        self.assertIn("CLAIM_STRENGTH_ESCALATION", {item["code"] for item in escalated["claim_results"][0]["issues"]})

    def test_declared_evidence_omission_is_visible_drift(self):
        result = run(
            declared_claims=[declared(claim_strength="association")],
            emitted_claims=[emitted(claim_strength="association", citation_ids=[], experiment_ids=[], analysis_artifact_ids=[])],
            evidence_assessments=[],
        )

        codes = {item["code"] for item in result["claim_results"][0]["issues"]}
        self.assertTrue({"DECLARED_CITATION_NOT_BOUND", "DECLARED_EXPERIMENT_NOT_BOUND"} <= codes)
        self.assertEqual(result["claim_results"][0]["emission_gate"], "review_required")

    def test_circular_or_leakage_unreviewed_audit_is_blocked(self):
        result = run(audit_provenance=provenance(rules_independent_from_writer=False, leakage_reviewed=False))

        self.assertEqual(result["provenance_gate_ids"], ["audit_rules_not_independent", "audit_leakage_not_reviewed"])
        self.assertEqual(result["overall_status"], "blocked")

    def test_reviewed_analysis_artifact_can_supply_omics_evidence(self):
        result = run(
            declared_claims=[declared(intended_evidence_types=["omics", "experiment"], citation_ids=[], analysis_artifact_ids=["omics-1"], minimum_independent_supports=2)],
            emitted_claims=[emitted(citation_ids=[], analysis_artifact_ids=["omics-1"])],
            citations=[],
            analysis_artifacts=[{"id": "omics-1", "evidence_type": "omics", "study_design": "observational-cohort", "independent_group": "omics-cohort-1", "result_reviewed": True, "provenance_complete": True, "quality_status": "passed"}],
            evidence_assessments=[assessment("artifact", "omics-1", review_method="deterministic_result_check"), assessment("experiment", "experiment-1")],
        )

        self.assertEqual(result["analysis_artifact_count"], 1)
        self.assertEqual(result["claim_results"][0]["claim_state"], "supported")
        self.assertEqual(result["overall_status"], "passed")

    def test_unreviewed_or_provenance_incomplete_analysis_cannot_support(self):
        result = run(
            declared_claims=[declared(intended_evidence_types=["omics"], citation_ids=[], experiment_ids=[], analysis_artifact_ids=["omics-1"], minimum_independent_supports=1)],
            emitted_claims=[emitted(citation_ids=[], experiment_ids=[], analysis_artifact_ids=["omics-1"])],
            citations=[],
            experiments=[],
            analysis_artifacts=[{"id": "omics-1", "evidence_type": "omics", "study_design": "observational-cohort", "independent_group": "omics-cohort-1", "result_reviewed": False, "provenance_complete": False, "quality_status": "major"}],
            evidence_assessments=[assessment("artifact", "omics-1", review_method="deterministic_result_check")],
        )

        codes = {item["code"] for item in result["claim_results"][0]["issues"]}
        self.assertTrue({"UNREVIEWED_ANALYSIS_CANNOT_SUPPORT", "INCOMPLETE_ANALYSIS_PROVENANCE", "BLOCKED_ANALYSIS_CANNOT_SUPPORT"} <= codes)
        self.assertEqual(result["overall_status"], "blocked")

    def test_incoherent_tool_failure_and_not_reviewed_direction_fail_closed(self):
        with self.assertRaises(ValueError):
            run(evidence_assessments=[assessment("citation", "citation-1", adjudication_status="tool_failure"), assessment("experiment", "experiment-1")])
        with self.assertRaises(ValueError):
            run(constraint_assessments=[constraint(review_method="not_reviewed", verdict="not_violated")])


if __name__ == "__main__":
    unittest.main()
