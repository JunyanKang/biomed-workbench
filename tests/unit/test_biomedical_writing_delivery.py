import tempfile
import unittest
from pathlib import Path

from biomed_workbench.biomedical_writing import (
    build_biomedical_argument,
    resolve_biomedical_writing_profile,
)
from biomed_workbench.capabilities.academic_writing import (
    audit_academic_prose_revision,
    deliver_biomedical_writing,
)


class BiomedicalWritingDeliveryTests(unittest.TestCase):
    def argument(self, artifact_path: str = ""):
        return build_biomedical_argument(
            central_question="How does loss of factor X alter retinal progenitor differentiation?",
            central_claim="Loss of factor X is associated with delayed progenitor differentiation.",
            study_design="observational",
            evidence_items=[
                {
                    "id": "integration", "evidence_role": "integration",
                    "finding": "Chromatin and transcriptional changes converge on delayed differentiation.",
                    "evidence_type": "multi-omic synthesis", "status": "CANDIDATE",
                    "experimental_unit": "embryo", "effect": "concordant direction",
                    "uncertainty": "three embryos per group", "independent_replicates": 3,
                    "supports_claim": True, "upstream_ids": ["rna", "atac"],
                },
                {
                    "id": "rna", "evidence_role": "discovery",
                    "finding": "Differentiation-associated transcripts were reduced.",
                    "evidence_type": "RNA-seq", "status": "FORMAL",
                    "experimental_unit": "embryo", "effect": "median log2 fold-change -0.8",
                    "uncertainty": "95% CI reported in source table", "independent_replicates": 3,
                    "supports_claim": True, "upstream_ids": [], "artifact_path": artifact_path,
                    "figure_or_table": "Figure 2a",
                },
                {
                    "id": "atac", "evidence_role": "mechanistic-consistency",
                    "finding": "Accessibility decreased near differentiation-associated genes.",
                    "evidence_type": "ATAC-seq", "status": "CANDIDATE",
                    "experimental_unit": "embryo", "effect": "lower accessibility",
                    "uncertainty": "sample-level dispersion reported", "independent_replicates": 3,
                    "supports_claim": True, "upstream_ids": ["rna"],
                },
                {
                    "id": "null", "evidence_role": "boundary-null",
                    "finding": "No change was detected in an unrelated lineage marker set.",
                    "evidence_type": "RNA-seq", "status": "FORMAL", "experimental_unit": "embryo",
                    "effect": "null", "uncertainty": "95% CI crossed zero", "independent_replicates": 3,
                    "supports_claim": False, "upstream_ids": ["rna"],
                },
            ],
            literature_context=[{
                "id": "L1", "doi": "10.1038/s41586-024-07855-6",
                "url": "https://doi.org/10.1038/s41586-024-07855-6",
                "statement": "Tissue stem-cell state is coupled to tissue maintenance.",
                "scope": "adult epithelial tissue", "relation": "contextualises", "verified": True,
            }],
            target_document="research-article", target_section="results",
            competing_explanations=["altered cell-state abundance rather than delayed differentiation"],
        )

    def test_argument_is_reordered_by_biological_job_and_retains_null_boundary(self):
        result = self.argument()
        self.assertTrue(result["ready_for_drafting"])
        self.assertFalse(result["source_order_preserved"])
        self.assertEqual([row["id"] for row in result["evidence_sequence"]], ["rna", "atac", "null", "integration"])

    def test_declared_dependency_precedes_narrative_role(self):
        result = build_biomedical_argument(
            central_question="What supports the integrated model?", central_claim="The data support a bounded model.",
            study_design="observational", target_section="results",
            evidence_items=[
                {"id": "model", "evidence_role": "discovery", "finding": "The integrated model was observed.",
                 "status": "FORMAL", "experimental_unit": "embryo", "upstream_ids": ["context"]},
                {"id": "context", "evidence_role": "mechanistic-consistency", "finding": "Chromatin context supports the model.",
                 "status": "FORMAL", "experimental_unit": "embryo", "upstream_ids": []},
            ], literature_context=[], competing_explanations=["cell-state composition"],
        )
        self.assertEqual([row["id"] for row in result["evidence_sequence"]], ["context", "model"])

    def test_outward_biomedical_text_rejects_internal_and_engineering_language(self):
        result = audit_academic_prose_revision(
            original_text="The registry gate validates the end-to-end pipeline.",
            revised_text="The registry gate validates the end-to-end pipeline.",
            document_type="research-article", section_kind="results", target_venue="Cell",
            scientific_argument=self.argument(),
        )
        codes = {row["code"] for row in result["findings"]}
        self.assertIn("internal-governance-language", codes)
        self.assertIn("engineering-metaphor-in-biomedical-narrative", codes)
        self.assertFalse(result["ready_for_delivery"])

    def test_computational_methods_keeps_legitimate_method_language(self):
        result = audit_academic_prose_revision(
            original_text="The workflow aligned reads to the reference genome.",
            revised_text="The workflow aligned reads to the reference genome.",
            document_type="research-article", section_kind="methods", target_venue="Cell",
            content_domain="computational-methods", scientific_argument=self.argument(),
        )
        self.assertNotIn("engineering-metaphor-in-biomedical-narrative", {row["code"] for row in result["findings"]})

    def test_journal_profiles_distinguish_basic_and_clinical_writing(self):
        cell = resolve_biomedical_writing_profile("Cell")
        jama = resolve_biomedical_writing_profile("JAMA")
        self.assertEqual(cell["research_domain"], "mechanistic-life-science")
        self.assertEqual(jama["research_domain"], "clinical")
        self.assertIn("harms", jama["results_moves"])

    def test_delivery_writes_reopens_and_links_html_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "source.tsv"
            evidence.write_text("gene\tlog2fc\nA\t-0.8\n", encoding="utf-8")
            original = "Our analysis pipeline showed that Differentiation-associated transcripts decreased by 20% [1]."
            revised = "Differentiation-associated transcripts were 20% lower in mutant embryos than in controls [1]."
            result = deliver_biomedical_writing(
                original_text=original, revised_text=revised,
                document_type="research-article", section_kind="results", target_venue="Nature",
                scientific_argument=self.argument(evidence.as_posix()), output_directory=(root / "report").as_posix(),
                structure_policy="preserve", content_domain="biological",
                protected_spans=[{"kind": "result", "text": "Differentiation-associated transcripts"}],
                claim_bindings=[{
                    "claim_id": "C1", "claim": "Differentiation-associated transcripts were lower.",
                    "claim_level": "associational", "evidence_level": "associational", "evidence_ids": ["rna"],
                    "hedging_required": False, "hedging_preserved": True,
                }],
            )
            self.assertTrue(result["ready_for_delivery"])
            self.assertTrue(result["report_files"]["delivery_verified"])
            html = Path(result["report_files"]["html"])
            payload = html.read_text(encoding="utf-8")
            self.assertIn('href="#argument"', payload)
            self.assertIn("source.tsv", payload)
            self.assertIn("10.1038/s41586-024-07855-6", payload)
            self.assertIn(revised, payload)
            self.assertIn("version_id", result["report_files"])
            second = deliver_biomedical_writing(
                original_text=original, revised_text=revised,
                document_type="research-article", section_kind="results", target_venue="Nature",
                scientific_argument=self.argument(evidence.as_posix()), output_directory=(root / "report").as_posix(),
                structure_policy="preserve", content_domain="biological",
                protected_spans=[{"kind": "result", "text": "Differentiation-associated transcripts"}],
                claim_bindings=[{
                    "claim_id": "C1", "claim": "Differentiation-associated transcripts were lower.",
                    "claim_level": "associational", "evidence_level": "associational", "evidence_ids": ["rna"],
                    "hedging_required": False, "hedging_preserved": True,
                }],
            )
            self.assertEqual(result["report_files"]["version_id"], second["report_files"]["version_id"])


if __name__ == "__main__":
    unittest.main()
