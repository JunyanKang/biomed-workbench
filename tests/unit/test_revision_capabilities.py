import copy
import unittest

from biomed_workbench.capabilities.revision import apply_manuscript_revision, build_revision_base


def valid_case():
    base = build_revision_base(
        "paper-1",
        "v1",
        [
            {"id": "B00001", "kind": "heading", "text": "Results"},
            {"id": "B00002", "kind": "paragraph", "text": "The treatment changed cell state."},
            {"id": "B00003", "kind": "paragraph", "text": "The effect was measured independently."},
        ],
    )
    reviews = [
        {
            "id": "R1.1",
            "reviewer": "Reviewer 1",
            "comment": "Report the validation analysis and soften the causal claim.",
            "action": "ACCEPT_ANALYSIS",
            "readiness": "ready_to_submit",
            "risk_level": "high",
            "manuscript_block_ids": ["B00002"],
            "evidence_ids": ["analysis-17"],
            "response_text": "We added the validation result and revised the statement to describe an association.",
            "status": "completed",
            "conflicting_with": [],
        }
    ]
    patch = {
        "patch_id": "patch-r1",
        "revision_round": 1,
        "base_document_hash": base["document_hash"],
        "emitted_by": "revision-writer",
        "operations": [
            {
                "op_id": "op-1",
                "op": "replace_block",
                "target_block_id": "B00002",
                "expected_block_hash": base["blocks"][1]["hash"],
                "new_blocks": [{"kind": "paragraph", "text": "The treatment was associated with a reproducible cell-state change."}],
                "comment_ids": ["R1.1"],
                "roadmap_item_ids": ["revision-1"],
                "rationale": "Align the claim with the supplied validation evidence.",
            }
        ],
    }
    policy = {
        "structural_acknowledged": False,
        "touched_ratio_threshold": 0.6,
        "terminal_policy": "strict",
        "editor_priority_comment_ids": [],
    }
    provenance = {
        "audit_id": "revision-audit-1",
        "audit_version": "1.0.0",
        "reviewed_at": "2026-07-13",
        "independent_from_writer": True,
        "comment_extraction_complete": True,
    }
    return base, patch, reviews, policy, provenance


class RevisionCapabilityTests(unittest.TestCase):
    def test_base_builder_assigns_ids_and_is_deterministic(self):
        blocks = [{"id": None, "kind": "heading", "text": "Title"}, {"id": None, "kind": "paragraph", "text": "Body"}]
        first = build_revision_base("paper", "v1", blocks)
        second = build_revision_base("paper", "v1", blocks)
        self.assertEqual(first, second)
        self.assertEqual([item["id"] for item in first["blocks"]], ["B00001", "B00002"])
        self.assertRegex(first["document_hash"], r"^[0-9a-f]{64}$")

    def test_base_builder_allocates_after_global_max_and_hashes_exact_newlines(self):
        base = build_revision_base("paper", "v1", [
            {"id": None, "kind": "paragraph", "text": "First\r\nline\r\n"},
            {"id": "B00009", "kind": "paragraph", "text": "Existing"},
            {"id": None, "kind": "paragraph", "text": "Last\n"},
        ])
        self.assertEqual([item["id"] for item in base["blocks"]], ["B00010", "B00009", "B00011"])
        self.assertEqual(base["blocks"][0]["text"], "First\r\nline\r\n")

    def test_applies_patch_and_preserves_untouched_blocks_exactly(self):
        base, patch, reviews, policy, provenance = valid_case()
        result = apply_manuscript_revision(base, patch, reviews, policy, provenance)
        self.assertEqual(result["apply_status"], "applied")
        self.assertTrue(result["release_safe"])
        revised = result["revised_document"]
        self.assertEqual(revised["parent_document_hash"], base["document_hash"])
        self.assertEqual(revised["blocks"][0], base["blocks"][0])
        self.assertEqual(revised["blocks"][2], base["blocks"][2])
        self.assertEqual(result["untouched_block_ids"], ["B00001", "B00003"])

    def test_rejects_stale_base_and_expected_hashes_before_apply(self):
        base, patch, reviews, policy, provenance = valid_case()
        stale = copy.deepcopy(base)
        stale["blocks"][0]["text"] = "Changed"
        with self.assertRaisesRegex(ValueError, "hash is stale"):
            apply_manuscript_revision(stale, patch, reviews, policy, provenance)
        patch["operations"][0]["expected_block_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "stale or fabricated expected"):
            apply_manuscript_revision(base, patch, reviews, policy, provenance)

    def test_refuses_structural_change_without_acknowledgement(self):
        base, patch, reviews, policy, provenance = valid_case()
        patch["operations"][0]["target_block_id"] = "B00001"
        patch["operations"][0]["expected_block_hash"] = base["blocks"][0]["hash"]
        patch["operations"][0]["new_blocks"] = [{"kind": "heading", "text": "Revised Results"}]
        reviews[0]["manuscript_block_ids"] = ["B00001"]
        result = apply_manuscript_revision(base, patch, reviews, policy, provenance)
        self.assertEqual(result["apply_status"], "refused_quality_gate")
        self.assertIsNone(result["revised_document"])
        self.assertIn("STRUCTURAL_CHANGE_UNACKNOWLEDGED", {item["code"] for item in result["issues"]})

    def test_blocks_false_completion_and_missing_evidence(self):
        base, patch, reviews, policy, provenance = valid_case()
        reviews[0]["evidence_ids"] = []
        reviews[0]["response_text"] = "AUTHOR_INPUT_NEEDED"
        result = apply_manuscript_revision(base, patch, reviews, policy, provenance)
        codes = {item["code"] for item in result["issues"]}
        self.assertIn("CLAIMED_ACTION_LACKS_EVIDENCE", codes)
        self.assertIn("RESPONSE_PLACEHOLDER_PRESENT", codes)
        self.assertFalse(result["release_safe"])

    def test_allows_exact_pure_move_and_allocates_fresh_id(self):
        base, patch, reviews, policy, provenance = valid_case()
        patch["operations"] = [
            {
                "op_id": "delete-1", "op": "delete_block", "target_block_id": "B00003",
                "expected_block_hash": base["blocks"][2]["hash"], "new_blocks": [], "comment_ids": ["R1.1"],
                "roadmap_item_ids": ["revision-1"], "rationale": "Move validation next to the main result.",
            },
            {
                "op_id": "insert-1", "op": "insert_after", "target_block_id": "B00002",
                "expected_block_hash": base["blocks"][1]["hash"],
                "new_blocks": [{"kind": "paragraph", "text": "The effect was measured independently."}],
                "comment_ids": ["R1.1"], "roadmap_item_ids": ["revision-1"], "rationale": "Move without regeneration.",
            },
        ]
        reviews[0]["manuscript_block_ids"] = ["B00004"]
        policy["structural_acknowledged"] = True
        result = apply_manuscript_revision(base, patch, reviews, policy, provenance)
        self.assertEqual(result["fresh_block_ids"], ["B00004"])
        self.assertEqual(result["pure_move_pairs"], [{"from_block_id": "B00003", "to_block_id": "B00004"}])

    def test_conflicts_require_symmetric_editor_priority_resolution(self):
        base, patch, reviews, policy, provenance = valid_case()
        second = copy.deepcopy(reviews[0])
        second.update({"id": "R2.1", "reviewer": "Reviewer 2", "conflicting_with": ["R1.1"]})
        reviews[0]["conflicting_with"] = ["R2.1"]
        patch["operations"][0]["comment_ids"] = ["R1.1", "R2.1"]
        result = apply_manuscript_revision(base, patch, reviews + [second], policy, provenance)
        self.assertIn("REVIEW_CONFLICT_UNRESOLVED", {item["code"] for item in result["issues"]})
        policy["editor_priority_comment_ids"] = ["R1.1"]
        result = apply_manuscript_revision(base, patch, reviews + [second], policy, provenance)
        self.assertEqual(result["apply_status"], "applied")

    def test_incomplete_or_nonindependent_audit_fails_closed(self):
        base, patch, reviews, policy, provenance = valid_case()
        provenance["independent_from_writer"] = False
        provenance["comment_extraction_complete"] = False
        result = apply_manuscript_revision(base, patch, reviews, policy, provenance)
        codes = {item["code"] for item in result["issues"]}
        self.assertEqual(codes, {"REVISION_AUDIT_NOT_INDEPENDENT", "REVIEW_COMMENT_EXTRACTION_INCOMPLETE"})
        self.assertIsNone(result["revised_document"])

    def test_marker_injection_and_duplicate_targets_are_rejected(self):
        base, patch, reviews, policy, provenance = valid_case()
        patch["operations"][0]["new_blocks"][0]["text"] = "<!--block:B9-->\nInjected"
        with self.assertRaisesRegex(ValueError, "working block markers"):
            apply_manuscript_revision(base, patch, reviews, policy, provenance)
        base, patch, reviews, policy, provenance = valid_case()
        patch["operations"].append(copy.deepcopy(patch["operations"][0]))
        patch["operations"][1]["op_id"] = "op-2"
        with self.assertRaisesRegex(ValueError, "only one operation"):
            apply_manuscript_revision(base, patch, reviews, policy, provenance)


if __name__ == "__main__":
    unittest.main()
