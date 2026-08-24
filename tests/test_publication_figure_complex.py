from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tools.publish_publication_figure_acceptance import build


class PublicationFigureComplexAcceptanceTests(unittest.TestCase):
    def test_information_dense_public_case(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            payload = build(Path(temp) / "report.json")
        self.assertEqual(payload["status"], "passed")
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["module_id"], "publication-figure-package")
        self.assertTrue(payload["output_package_validated"])
        self.assertEqual(payload["complexity"]["panel_count"], 6)
        self.assertGreaterEqual(payload["complexity"]["registered_rendering_rows"], 1200)
        self.assertEqual(payload["complexity"]["heatmap_cells"], 400)
        self.assertEqual(payload["complexity"]["case_level_points"], 1138)
        self.assertTrue(payload["acceptance"]["all_registered_rows_assigned"])
        self.assertEqual(payload["acceptance"]["label_overlap_pairs"], 0)
        self.assertTrue(payload["acceptance"]["pdf_svg_png_reloaded"])
        self.assertTrue(payload["acceptance"]["editable_pdf_text"])
        self.assertTrue(payload["execution"]["visual_render_reviewed"])
        self.assertFalse(payload["scientific_summary"]["biological_or_diagnostic_claim_made"])


if __name__ == "__main__":
    unittest.main()
