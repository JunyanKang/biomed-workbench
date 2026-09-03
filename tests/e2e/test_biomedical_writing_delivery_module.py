import tempfile
import unittest
from pathlib import Path

from biomed_workbench.biomedical_writing import build_biomedical_argument
from biomed_workbench.runner import run


class BiomedicalWritingDeliveryModuleE2ETests(unittest.TestCase):
    def test_registered_module_writes_and_reopens_html(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tsv"
            source.write_text("group\tmean\ncontrol\t1.0\nmutant\t0.8\n", encoding="utf-8")
            argument = build_biomedical_argument(
                central_question="Does factor X loss alter retinal progenitor differentiation?",
                central_claim="Factor X loss is associated with reduced differentiation-marker expression.",
                study_design="observational", target_document="research-article", target_section="results",
                competing_explanations=["a change in cell-state abundance"],
                evidence_items=[{
                    "id": "E1", "evidence_role": "discovery", "finding": "Differentiation-marker expression was lower.",
                    "evidence_type": "RNA-seq", "status": "FORMAL", "experimental_unit": "embryo",
                    "effect": "20% lower", "uncertainty": "95% CI reported", "independent_replicates": 3,
                    "supports_claim": True, "upstream_ids": [], "artifact_path": source.as_posix(),
                    "figure_or_table": "Figure 2a",
                }],
                literature_context=[{
                    "id": "L1", "doi": "10.1038/s41586-024-07855-6",
                    "url": "https://doi.org/10.1038/s41586-024-07855-6",
                    "statement": "A reviewed study provides broader tissue context.",
                    "scope": "adult epithelial tissue", "relation": "contextualises", "verified": True,
                }],
            )
            execution = run("biomedical-writing-delivery", {
                "original_text": "The analysis pipeline showed that marker expression was 20% lower [1].",
                "revised_text": "Marker expression was 20% lower in mutant embryos than in controls [1].",
                "document_type": "research-article", "section_kind": "results", "target_venue": "Nature",
                "scientific_argument": argument, "output_directory": (root / "delivery").as_posix(),
                "content_domain": "biological",
            }, allow_mutation=True).to_dict()
            self.assertEqual(execution["status"], "completed")
            output = execution["output"]
            self.assertTrue(output["report_files"]["delivery_verified"])
            html_path = Path(output["report_files"]["html"])
            self.assertTrue(html_path.is_file())
            html = html_path.read_text(encoding="utf-8")
            self.assertIn('href="#argument"', html)
            self.assertIn(source.resolve().as_uri(), html)
            self.assertIn("10.1038/s41586-024-07855-6", html)


if __name__ == "__main__":
    unittest.main()
