from __future__ import annotations

import json
from pathlib import Path
import unittest

from biomed_workbench.router import route
from biomed_workbench.scientific_semantics import parse_scientific_semantics


ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(
    (ROOT / "tests" / "fixtures" / "scientific_routing" / "real_project_cases.json").read_text(encoding="utf-8")
)


class ScientificSemanticRoutingTests(unittest.TestCase):
    def test_real_project_semantics_and_boundaries(self) -> None:
        for case in CASES:
            with self.subTest(case=case["id"]):
                result = route(case["objective"], per_workflow=10)
                concepts = result["scientific_semantics"]["concepts"]
                for axis, expected in case["required_concepts"].items():
                    self.assertTrue(set(expected) <= set(concepts[axis]), (axis, concepts[axis]))
                self.assertTrue(set(case.get("required_modules", ())) <= set(result["selected_module_ids"]))
                self.assertFalse(set(case.get("forbidden_modules", ())) & set(result["selected_module_ids"]))
                messages = [
                    *result["scientific_semantics"]["design_requirements"],
                    *result["scientific_semantics"]["eligibility_warnings"],
                ]
                fragment = case.get("required_requirement_fragment") or case.get("required_warning_fragment")
                if fragment:
                    self.assertTrue(any(fragment in message for message in messages), messages)

    def test_secondary_transcription_is_not_secondary_structure(self) -> None:
        result = route(
            "Distinguish direct BANP binding from secondary transcriptional effects in RNA-seq and CUT&Tag.",
            per_workflow=10,
        )
        self.assertNotIn("rna-secondary-structure-summary", result["selected_module_ids"])
        self.assertIn(
            "secondary-transcriptional-effect",
            result["scientific_semantics"]["concepts"]["relations"],
        )

    def test_negated_structure_is_not_eligible(self) -> None:
        brief = parse_scientific_semantics(
            "Analyze RNA-seq changes without RNA secondary structure analysis."
        )
        self.assertIn("rna-secondary-structure", brief.negated_concepts["targets"])

    def test_banp_complex_route_is_omics_only_and_has_integration(self) -> None:
        result = route(
            "Integrate BANP RNA-seq, paired multiome RNA and ATAC, HA-BANP CUT&Tag, "
            "S9.6 CUT&Tag with spike-in and RNase control, SCENIC+, IP-MS, and RNA processing "
            "to distinguish direct BANP regulation, R-loop-associated effects, protein-interaction "
            "support, splicing changes, and secondary transcriptional effects.",
            per_workflow=10,
        )
        self.assertEqual(result["matched_workflows"], ["omics"])
        self.assertIsNotNone(result["integration_node"])
        self.assertNotIn("glycosylation-scan", result["execution_module_ids"])
        self.assertNotIn("rna-secondary-structure-summary", result["selected_module_ids"])
        self.assertIn("rna-processing-alternative-splicing", result["selected_module_ids"])
        unresolved = {(item["axis"], item["concept"]) for item in result["unresolved_semantic_requirements"]}
        self.assertNotIn(("targets", "splicing"), unresolved)


if __name__ == "__main__":
    unittest.main()
