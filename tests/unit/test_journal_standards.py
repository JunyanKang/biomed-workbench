import json
import unittest
from pathlib import Path

from biomed_workbench.capabilities.journal_standards import (
    CATALOG_ROOT,
    _load_catalog,
    journal_targeting_and_compliance,
)


class JournalStandardsTests(unittest.TestCase):
    def test_bilingual_guides_list_every_catalog_journal_and_metric_frame(self):
        catalog, _ = _load_catalog()
        repository_root = Path(CATALOG_ROOT).parents[2]
        for relative_path in (
            "docs/journal-standards.md",
            "docs/journal-standards.zh-CN.md",
        ):
            text = (repository_root / relative_path).read_text(encoding="utf-8")
            table = text.split("<!-- journal-coverage-table:start -->", 1)[1].split(
                "<!-- journal-coverage-table:end -->", 1
            )[0]
            journal_rows = [line for line in table.splitlines() if line.startswith("| [")]
            self.assertEqual(len(journal_rows), catalog["journal_count"])
            self.assertIn("JCR 2026", text)
            self.assertIn("2025 JIF", text)
            for profile in catalog["journals"]:
                self.assertIn(f"| [{profile['title']}]", table)

    def test_active_catalog_is_versioned_complete_and_official_source_bound(self):
        catalog, digest = _load_catalog()
        self.assertGreaterEqual(catalog["journal_count"], 50)
        self.assertEqual(catalog["journal_count"], len(catalog["journals"]))
        self.assertEqual(len({row["id"] for row in catalog["journals"]}), catalog["journal_count"])
        self.assertEqual(len(digest), 64)
        for profile in catalog["journals"]:
            self.assertTrue(profile["standard_version"])
            self.assertRegex(profile["reviewed_on"], r"^20\d\d-\d\d-\d\d$")
            self.assertTrue(profile["official_sources"])
            self.assertTrue(all(url.startswith("https://") for url in profile["official_sources"]))

        index = json.loads((Path(CATALOG_ROOT) / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["active_catalog_version"], catalog["catalog_version"])
        self.assertEqual(index["active_catalog_sha256"], digest)

    def test_recommendation_excludes_impact_factor_and_acceptance_probability(self):
        result = journal_targeting_and_compliance(
            project={
                "summary": "A single-cell developmental atlas with spatial validation and mechanistic perturbation.",
                "study_type": "Article",
                "topics": ["developmental biology", "single-cell", "spatial biology"],
                "methods": ["single-cell RNA sequencing", "spatial transcriptomics"],
                "intended_audience": "cell biologists and developmental biologists",
            },
            top_k=3,
        )
        self.assertEqual(len(result["recommendations"]), 3)
        self.assertFalse(result["policy"]["impact_factor_used"])
        self.assertFalse(result["policy"]["acceptance_probability_claimed"])
        rendered = json.dumps(result).lower()
        self.assertNotIn("acceptance probability\":", rendered)
        self.assertNotIn("impact factor\":", rendered)

    def test_unknown_official_limit_remains_manual_and_blocks_ready_state(self):
        result = journal_targeting_and_compliance(
            project={
                "summary": "A cancer mechanism study with genetic perturbation and translational validation.",
                "study_type": "Article",
                "topics": ["cancer biology"],
                "methods": ["genetic perturbation"],
                "intended_audience": "cancer researchers",
            },
            target_journal_id="nature-cancer",
            manuscript={
                "main_text_words": 3000,
                "abstract_words": 140,
                "display_items": 5,
                "references": 45,
                "sections": ["Abstract", "Introduction", "Results", "Discussion", "Methods"],
                "declarations": [],
            },
        )
        compliance = result["compliance"]
        unknown = {
            row["field"]
            for row in compliance["findings"]
            if row["status"] == "manual-check" and row["limit"] is None
        }
        self.assertTrue({"main_text_words", "display_items", "references"} <= unknown)
        self.assertFalse(compliance["submission_ready"])

    def test_exact_stored_limit_is_enforced_without_guessing(self):
        result = journal_targeting_and_compliance(
            project={
                "summary": "A broad molecular mechanism study intended for a general scientific audience.",
                "study_type": "Article",
                "topics": ["molecular biology"],
                "methods": ["functional genomics"],
                "intended_audience": "general scientists",
            },
            target_journal_id="nature",
            manuscript={
                "main_text_words": 4301,
                "abstract_words": 200,
                "display_items": 6,
                "references": 50,
                "sections": ["Abstract", "Main", "Methods", "References"],
                "declarations": [],
            },
        )
        by_field = {row["field"]: row for row in result["compliance"]["findings"]}
        self.assertEqual(by_field["main_text_words"]["status"], "fail")
        self.assertEqual(by_field["main_text_words"]["limit"], 4300)


if __name__ == "__main__":
    unittest.main()
