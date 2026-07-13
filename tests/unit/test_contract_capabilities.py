import unittest

from biomed_workbench.capabilities.contracts import audit_research_contract


def _provenance(**overrides):
    value = {
        "contract_id": "manuscript-release-contract",
        "contract_version": "1.0.0",
        "owner": "research quality lead",
        "reviewed_at": "2026-07-13",
        "intended_use": "Pre-submission cross-artifact validation",
        "rules_independent_from_artifacts": True,
        "reviewed_for_completeness": True,
    }
    value.update(overrides)
    return value


class ResearchContractAuditTests(unittest.TestCase):
    def test_audits_structured_and_scoped_text_contracts(self):
        result = audit_research_contract(
            artifacts=[
                {
                    "id": "rubric",
                    "role": "Canonical reviewer rubric",
                    "media_type": "application/json",
                    "content": {
                        "version": "1.0",
                        "dimensions": [
                            {"id": "rigor", "weight": 60},
                            {"id": "clarity", "weight": 40},
                        ],
                        "mode": "strict",
                        "strict_policy": {"minimum_score": 80},
                    },
                },
                {
                    "id": "submission",
                    "role": "Submission instructions",
                    "media_type": "text/markdown",
                    "content": "# Submission\nRequired citation audit.\nFirst validate evidence. Then emit.\n# Appendix\nforbidden decoy\n",
                },
            ],
            rules=[
                {"id": "dimension-ids-unique", "kind": "json_unique_by", "severity": "major", "artifact_ids": ["rubric"], "parameters": {"path": "#/dimensions", "field": "id"}},
                {"id": "weights-sum", "kind": "numeric_sum", "severity": "major", "artifact_ids": ["rubric"], "parameters": {"path": "#/dimensions", "field": "weight", "expected": 100, "tolerance": 0}},
                {"id": "strict-fields", "kind": "json_conditional_required", "severity": "major", "artifact_ids": ["rubric"], "parameters": {"if_path": "#/mode", "equals": "strict", "required_paths": ["#/strict_policy/minimum_score"]}},
                {"id": "submission-token", "kind": "text_contains", "severity": "major", "artifact_ids": ["submission"], "parameters": {"tokens": ["Required citation audit"], "heading": "Submission", "normalization": "whitespace"}},
                {"id": "submission-order", "kind": "text_ordered", "severity": "major", "artifact_ids": ["submission"], "parameters": {"tokens": ["validate evidence", "emit"], "heading": "Submission", "normalization": "casefold_whitespace"}},
                {"id": "submission-no-forbidden", "kind": "text_absent", "severity": "major", "artifact_ids": ["submission"], "parameters": {"tokens": ["forbidden decoy"], "heading": "Submission", "normalization": "exact"}},
            ],
            contract_provenance=_provenance(),
        )

        self.assertEqual(result["overall_status"], "passed")
        self.assertFalse(result["semantic_validity_assessed"])
        self.assertEqual(result["rule_count"], 6)
        self.assertEqual(result["failed_major_rule_ids"], [])

    def test_scoped_text_does_not_accept_decoys_outside_the_section(self):
        result = audit_research_contract(
            artifacts=[{"id": "protocol", "role": "Protocol", "media_type": "text/markdown", "content": "# Live rule\nNo gate here.\n# Example\nMANDATORY GATE\n"}],
            rules=[{"id": "live-gate", "kind": "text_contains", "severity": "major", "artifact_ids": ["protocol"], "parameters": {"tokens": ["MANDATORY GATE"], "heading": "Live rule", "normalization": "exact"}}],
            contract_provenance=_provenance(),
        )

        self.assertEqual(result["overall_status"], "blocked")
        self.assertEqual(result["failed_major_rule_ids"], ["live-gate"])

    def test_detects_mirror_closed_set_and_cross_artifact_drift(self):
        result = audit_research_contract(
            artifacts=[
                {"id": "canonical", "role": "Canonical policy", "media_type": "text/plain", "content": "Evidence first"},
                {"id": "mirror", "role": "Policy mirror", "media_type": "text/plain", "content": "Evidence later"},
                {"id": "a", "role": "Registry", "media_type": "application/json", "content": {"version": "2", "labels": ["pass", "fail", "extra"]}},
                {"id": "b", "role": "Release metadata", "media_type": "application/json", "content": {"version": "1"}},
            ],
            rules=[
                {"id": "policy-mirror", "kind": "text_mirror", "severity": "major", "artifact_ids": ["canonical", "mirror"], "parameters": {"normalization": "whitespace"}},
                {"id": "label-roster", "kind": "json_closed_set", "severity": "major", "artifact_ids": ["a"], "parameters": {"path": "#/labels", "values": ["pass", "fail"]}},
                {"id": "release-version", "kind": "json_equal", "severity": "major", "artifact_ids": ["a", "b"], "parameters": {"paths": ["#/version", "#/version"]}},
            ],
            contract_provenance=_provenance(),
        )

        self.assertEqual(result["overall_status"], "blocked")
        self.assertEqual(result["failed_major_rule_ids"], ["policy-mirror", "label-roster", "release-version"])

    def test_warning_failure_requires_review_without_blocking(self):
        result = audit_research_contract(
            artifacts=[{"id": "report", "role": "Report", "media_type": "application/json", "content": {}}],
            rules=[{"id": "optional-note", "kind": "json_path_exists", "severity": "warning", "artifact_ids": ["report"], "parameters": {"path": "#/note"}}],
            contract_provenance=_provenance(),
        )

        self.assertEqual(result["overall_status"], "review_required")
        self.assertEqual(result["failed_warning_rule_ids"], ["optional-note"])

    def test_validates_record_shape_references_and_acyclic_lineage(self):
        artifacts = [{
            "id": "timeline",
            "role": "Evidence timeline",
            "media_type": "application/json",
            "content": {"events": [
                {"id": "e1", "date": "2024", "supersedes": None},
                {"id": "e2", "date": "2025", "supersedes": "e1"},
            ]},
        }]
        rules = [
            {"id": "event-shape", "kind": "json_records_shape", "severity": "major", "artifact_ids": ["timeline"], "parameters": {"path": "#/events", "required_fields": ["id", "date", "supersedes"], "forbidden_fields": ["unverified_claim"]}},
            {"id": "event-links", "kind": "json_reference_integrity", "severity": "major", "artifact_ids": ["timeline"], "parameters": {"path": "#/events", "id_field": "id", "reference_fields": ["supersedes"]}},
            {"id": "event-lineage", "kind": "json_acyclic_relation", "severity": "major", "artifact_ids": ["timeline"], "parameters": {"path": "#/events", "id_field": "id", "edge_field": "supersedes"}},
        ]

        passed = audit_research_contract(artifacts, rules, _provenance())
        self.assertEqual(passed["overall_status"], "passed")

        cyclic = [{**artifacts[0], "content": {"events": [
            {"id": "e1", "date": "2024", "supersedes": "e2"},
            {"id": "e2", "date": "2025", "supersedes": "e1", "unverified_claim": True},
        ]}}]
        failed = audit_research_contract(cyclic, rules, _provenance())
        self.assertEqual(failed["overall_status"], "blocked")
        self.assertEqual(failed["rule_results"][0]["observed"]["violation_count"], 1)
        self.assertEqual(failed["rule_results"][2]["observed"]["cycle_node_ids"], ["e1", "e2"])

    def test_contract_provenance_blocks_circular_or_unreviewed_rules(self):
        result = audit_research_contract(
            artifacts=[{"id": "report", "role": "Report", "media_type": "application/json", "content": {"ready": True}}],
            rules=[{"id": "ready-present", "kind": "json_path_exists", "severity": "major", "artifact_ids": ["report"], "parameters": {"path": "#/ready"}}],
            contract_provenance=_provenance(rules_independent_from_artifacts=False, reviewed_for_completeness=False),
        )

        self.assertEqual(result["provenance_gate_ids"], ["rules_not_independent", "contract_completeness_not_reviewed"])
        self.assertEqual(result["overall_status"], "blocked")

    def test_rejects_unknown_rules_bad_pointers_and_ambiguous_headings(self):
        artifact = [{"id": "report", "role": "Report", "media_type": "application/json", "content": {}}]
        with self.assertRaises(ValueError):
            audit_research_contract(artifact, [{"id": "unknown-rule", "kind": "execute_code", "severity": "major", "artifact_ids": ["report"], "parameters": {}}], _provenance())
        with self.assertRaises(ValueError):
            audit_research_contract(artifact, [{"id": "bad-pointer", "kind": "json_path_exists", "severity": "major", "artifact_ids": ["report"], "parameters": {"path": "not-a-pointer"}}], _provenance())

        result = audit_research_contract(
            [{"id": "doc", "role": "Document", "media_type": "text/markdown", "content": "# Gate\none\n# Gate\ntwo\n"}],
            [{"id": "unique-heading", "kind": "text_contains", "severity": "major", "artifact_ids": ["doc"], "parameters": {"tokens": ["one"], "heading": "Gate", "normalization": "exact"}}],
            _provenance(),
        )
        self.assertEqual(result["rule_results"][0]["message"], "heading_ambiguous")
        self.assertEqual(result["overall_status"], "blocked")


if __name__ == "__main__":
    unittest.main()
