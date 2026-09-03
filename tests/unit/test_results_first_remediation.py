import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from biomed_workbench.figure_semantics import compare_figure_semantics
from biomed_workbench.modules.execution_readiness import ExecutionReadiness
from biomed_workbench.project_import import confirm_existing_project_map, discover_existing_project
from biomed_workbench.reporting.result_view import build_result_view
from biomed_workbench.research_modes import assess_research_mode
from biomed_workbench.scientific_story import build_scientific_story
from biomed_workbench.domain_context import validate_domain_context
from biomed_workbench.capabilities.scientific_review import self_correct_scientific_review
from biomed_workbench.router import route


class ResultsFirstRemediationTests(unittest.TestCase):
    def test_public_maturity_uses_public_case_without_fixture_digest(self):
        record = ExecutionReadiness(
            module_id="example", level="validated", released=True, contract_ready=True,
            executor_ready=True, public_data_validated=True, template_paths=(), assay_readiness=(),
            entry_surface_reachability={}, evidence_axes={"controlled_fixture_executed_and_reloaded": True},
            controlled_fixture_portable_identity_digest=None, reasons=(),
            declared_method_slices=("method-a",), controlled_fixture_executed_slices=("method-a",),
        )
        self.assertTrue(record.engineering_validated)
        self.assertTrue(record.method_validated)
        self.assertEqual(record.public_maturity, "PUBLIC_CASE_VALIDATED")

    def test_multi_method_maturity_requires_every_declared_slice(self):
        record = ExecutionReadiness(
            module_id="example", level="executable", released=True, contract_ready=True,
            executor_ready=True, public_data_validated=False, template_paths=(), assay_readiness=(),
            entry_surface_reachability={}, evidence_axes={"controlled_fixture_executed_and_reloaded": True},
            controlled_fixture_portable_identity_digest="a" * 64, reasons=(),
            declared_method_slices=("cellchat", "secact"),
            controlled_fixture_executed_slices=("cellchat",),
        )
        self.assertFalse(record.engineering_validated)
        self.assertEqual(record.public_maturity, "CONTRACT_ONLY")

    def test_public_router_exposes_only_unified_maturity(self):
        result = route("Run sample-aware CellChat cell-cell communication")
        candidates = [item for step in result["steps"] for item in step["candidates"]]
        communication = next(item for item in candidates if item["id"] == "single-cell-communication")
        self.assertNotIn("registry_contract_label", communication)
        self.assertNotIn("validation_scope", communication)
        self.assertIn(communication["maturity"]["level"], {
            "CONTRACT_ONLY", "EXECUTED_FIXTURE", "PUBLIC_CASE_VALIDATED", "CURRENT_PROJECT_VALIDATED",
        })

    def test_result_view_hides_provenance_until_requested(self):
        panel = SimpleNamespace(panel_id="a", results_zh="观察", results_en="Observation", conclusion_zh="解释", conclusion_en="Interpretation")
        review = SimpleNamespace(
            artifact_id="artifact-1", results_zh="上调", results_en="Increased",
            conclusion_zh="与状态一致", conclusion_en="Consistent with the state",
            limitations_zh=("不能证明因果",), limitations_en=("Does not establish causality",),
            panels=(panel,), overall_status="accepted",
        )
        decision = SimpleNamespace(artifact_id="artifact-1", action="retain", active_evidence=True, next_plan_node_ids=())
        state = SimpleNamespace(
            context=SimpleNamespace(project_id="project-1", scientific_question="What changes?"),
            artifacts=(SimpleNamespace(id="artifact-1", artifact_type="table"),), artifact_reviews=(review,),
            scientific_decisions=(decision,), artifact_reloads=(SimpleNamespace(artifact_id="artifact-1"),),
            observed_executions=(), state_digest="a" * 64,
        )
        thin = build_result_view(state)
        self.assertNotIn("reproducibility", thin)
        self.assertNotIn("artifact_id", thin["scientific_results"][0])
        self.assertEqual(thin["scientific_results"][0]["progress"], "SCIENTIFICALLY_REVIEWED")
        detailed = build_result_view(state, include_reproducibility=True)
        self.assertEqual(detailed["scientific_results"][0]["reproducibility"]["artifact_id"], "artifact-1")

    def test_existing_project_import_is_read_only_and_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Fig2a.pdf").write_bytes(b"%PDF fixture")
            (root / "Fig2a_source.tsv").write_text("x\ty\n1\t2\n", encoding="utf-8")
            (root / "render_Fig2a.py").write_text("output = 'Fig2a.pdf'\n", encoding="utf-8")
            before = sorted(path.name for path in root.iterdir())
            result = discover_existing_project(root)
            self.assertTrue(result["read_only_scan"])
            self.assertEqual(sorted(path.name for path in root.iterdir()), before)
            self.assertTrue(result["candidate_relations"])
            decisions = {
                "relations": {row["id"]: True for row in result["candidate_relations"]},
                "researcher_confirmation": "reviewed by project owner",
            }
            confirmed = confirm_existing_project_map(result, decisions)
            self.assertTrue(confirmed["confirmed_relations"])
            self.assertEqual(confirmed["source_scan_digest"], result["scan_digest"])

    def test_research_modes_keep_exploration_out_of_formal_evidence(self):
        state = SimpleNamespace(plans=(SimpleNamespace(id="plan-1"),), active_plan_id="plan-1", analysis_admissions=(), evidence_map_versions=())
        explore = assess_research_mode(state, "EXPLORE")
        self.assertTrue(explore["ready"])
        self.assertFalse(explore["formal_inclusion_allowed"])
        submission = assess_research_mode(state, "SUBMISSION")
        self.assertFalse(submission["ready"])
        self.assertIn("no published scientific evidence map", submission["blockers"])

    def test_story_selection_uses_unique_scientific_jobs_not_p_values(self):
        story = build_scientific_story([
            {"id": "a", "story_role": "discovery", "unique_information": "A developmental population is selectively reduced", "evidence_type": "single-cell abundance", "upstream_panels": []},
            {"id": "b", "story_role": "mechanistic-consistency", "unique_information": "A developmental population is selectively reduced", "evidence_type": "single-cell abundance", "upstream_panels": []},
            {"id": "c", "story_role": "integration", "unique_information": "Chromatin and expression converge on delayed differentiation", "evidence_type": "multi-omic synthesis", "upstream_panels": ["a"]},
        ])
        self.assertTrue(story["ready"])
        self.assertEqual([item["panel"] for item in story["retained_panels"]], ["a", "c"])
        self.assertEqual(story["excluded_panels"][0]["panel"], "b")

    def test_visual_semantic_regression_detects_aspect_ratio_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference, candidate = root / "reference.png", root / "candidate.png"
            for path, size in ((reference, (600, 400)), (candidate, (800, 300))):
                image = Image.new("RGB", size, "white")
                draw = ImageDraw.Draw(image)
                draw.rectangle((40, 40, size[0] - 40, size[1] - 40), outline="black", width=4)
                image.save(path)
            report = compare_figure_semantics(reference, candidate)
            self.assertFalse(report["automated_pass"])
            self.assertTrue(any(item["code"] == "ASPECT_RATIO_DRIFT" for item in report["findings"]))

    def test_domain_context_separates_literature_from_project_observations(self):
        profile = validate_domain_context({
            "profile_id": "embryonic-retina",
            "version": "2026-09-02",
            "organism": "Mus musculus",
            "tissue_or_system": "embryonic neural retina and RPE",
            "developmental_or_disease_context": ["optic-cup development"],
            "cell_types_or_compartments": ["retinal progenitor cell", "RPE"],
            "established_knowledge": [{
                "statement": "FGF signaling contributes to neural-retina specification.",
                "scope": "vertebrate optic-cup development",
                "doi": "10.1038/example",
            }],
            "project_observations": [{
                "statement": "A ventral progenitor state is reduced in the mutant dataset.",
                "artifact_ids": ["panel-3b-source"],
                "status": "CANDIDATE",
            }],
            "forbidden_inferences": ["Cell-state abundance alone cannot establish tissue loss."],
            "competing_explanations": ["state transition", "selective cell loss"],
            "discriminating_observations": ["lineage-resolved abundance with embryo-level replication"],
        })
        self.assertEqual(profile["established_knowledge"][0]["doi"], "10.1038/example")
        self.assertEqual(profile["project_observations"][0]["status"], "CANDIDATE")
        self.assertTrue(profile["scientific_review_required"])

    def test_scientific_self_correction_uses_domain_discriminator(self):
        domain = {
            "profile_id": "embryonic-retina", "version": "2026-09-03",
            "organism": "Mus musculus", "tissue_or_system": "embryonic retina",
            "developmental_or_disease_context": ["optic-cup development"],
            "cell_types_or_compartments": ["retinal progenitor cell"],
            "established_knowledge": [{
                "statement": "Cell-state abundance can vary during retinal development.",
                "scope": "embryonic neural retina", "doi": "10.1038/example",
            }],
            "project_observations": [{
                "statement": "A progenitor state is reduced in the mutant dataset.",
                "artifact_ids": ["panel-3b-source"], "status": "CANDIDATE",
            }],
            "forbidden_inferences": ["Cell-state abundance establishes anatomical tissue loss"],
            "competing_explanations": ["cell-state transition", "selective cell loss"],
            "discriminating_observations": ["Measure embryo-level anatomy and lineage-resolved abundance in matched specimens."],
        }
        result = self_correct_scientific_review(
            question="What explains the altered progenitor state?", hypothesis="The mutation changes progenitor maintenance.",
            study_design="observational", statistical_unit="embryo",
            observations=[{
                "id": "panel-3b", "observation": "The progenitor-state fraction is lower.",
                "direction": "decrease", "effect_size": -0.2, "uncertainty": "95% CI -0.3 to -0.1",
                "replicates": 3, "status": "candidate",
            }],
            draft_review={
                "methods": "Sample-aware proportion analysis.", "results": "The state fraction was lower.",
                "conclusion": "The observation is consistent with altered progenitor maintenance.",
                "limitations": "Anatomical tissue loss was not measured.", "next_step": "Follow up.",
            }, proposed_action="retain", domain_context=domain,
        )
        corrected = result["corrected_review_brief"]
        self.assertEqual(corrected["discriminating_next_step"], domain["discriminating_observations"][0])
        self.assertEqual(corrected["domain_context"]["profile_id"], "embryonic-retina")


if __name__ == "__main__":
    unittest.main()
