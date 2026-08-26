from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from biomed_workbench.kernel.artifacts import ScientificArtifact
from biomed_workbench.kernel.context import ProjectContext
from biomed_workbench.kernel.project_governance import (
    ResultStatusLedger,
    create_project_lock,
    transition_result_status,
    verify_project_lock,
)
from biomed_workbench.kernel.scientific_dependency import (
    AnalysisAdmission,
    validate_minimal_sufficient_admission,
)
from biomed_workbench.kernel.state import ProjectState, apply_event
from biomed_workbench.minimal_sufficient import assess_method_addition


def _context() -> ProjectContext:
    return ProjectContext.from_dict({
        "project_id": "project-one",
        "objective": "Test project-level governance without making a biological conclusion.",
        "scientific_question": "Can result status remain bound to frozen project identities?",
        "species": ["mus-musculus"],
        "biological_scope": {"tissue": "retina"},
        "study_design": "paired-comparison",
        "experimental_unit": "embryo",
        "comparisons": [{"id": "mutant-vs-control", "numerator_group": "mutant", "denominator_group": "control", "covariates": []}],
        "constraints": [],
        "required_deliverables": ["figure"],
        "required_evidence_types": ["quantitative-result"],
        "privacy_level": "public",
    })


def _admission(identifier: str, node: str, role: str = "primary") -> AnalysisAdmission:
    return AnalysisAdmission(
        id=identifier,
        plan_node_id=node,
        hypothesis_ids=("hypothesis-one",),
        rationale_zh="该分析直接回答预先声明的科学问题并限定结论边界。",
        rationale_en="This analysis directly answers the declared scientific question within a fixed claim boundary.",
        method="A registered analysis method with frozen parameters.",
        official_sources=("https://example.org/official-method",),
        alternatives_considered=("A distinct alternative method was considered before admission.",),
        assumptions=("The declared biological replicate is the unit of condition-level inference.",),
        parameter_justifications={"threshold": "The threshold is frozen before inspecting the scientific result."},
        acceptance_criteria=("The registered output reloads and the declared effect can be evaluated.",),
        falsification_criteria=("A directionally incompatible estimate would weaken the stated hypothesis.",),
        expected_artifact_types=("quantitative-result",),
        approved=True,
        analysis_role=role,
        minimal_sufficient_policy_version="1.0.0",
    )


class MinimalSufficientGovernanceTests(unittest.TestCase):
    def test_method_addition_requires_replacement_or_information_gain(self) -> None:
        self.assertFalse(assess_method_addition(proposed_module_id="new-method")["approved"])
        self.assertTrue(
            assess_method_addition(
                proposed_module_id="new-method",
                decision_information_gain="Tests sensitivity to a different measurement-error assumption.",
            )["approved"]
        )

    def test_admission_quota_blocks_second_primary_for_same_hypothesis(self) -> None:
        first = _admission("admission-one", "node-one")
        second = _admission("admission-two", "node-two")
        validate_minimal_sufficient_admission(SimpleNamespace(analysis_admissions=()), first)
        with self.assertRaisesRegex(ValueError, "quota"):
            validate_minimal_sufficient_admission(SimpleNamespace(analysis_admissions=(first,)), second)

    def test_project_lock_detects_drift_and_formal_promotion_is_not_a_label_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("samples.tsv", "cell-annotation.tsv", "panels.json"):
                (root / name).write_text(f"locked content for {name}\n", encoding="utf-8")
            state = ProjectState.create(_context())
            artifact = ScientificArtifact.create(
                id="result-one",
                artifact_type="quantitative-result",
                schema_version="1",
                format_name="json",
                format_version="1",
                compression="none",
                orientation="record",
                indexes=(),
                producing_module_id=None,
                producing_module_version=None,
                source_artifact_ids=(),
                scientific_scope={"comparison": "mutant-vs-control"},
                experimental_unit="embryo",
                denominator="registered embryos",
                processing_level="review-pending",
                quality_status="unassessed",
                coordinate_system="genomic",
                genome_build="GRCm39",
                annotation_release="GENCODE-M36",
                identifier_namespace="ensembl-gene",
                producer_tool_versions={},
                content={"effect": 0.0},
            )
            state = apply_event(
                state,
                "artifact_registered",
                {"artifact": artifact.to_dict()},
                rationale="Register a controlled result used to test project status transitions.",
                affected_artifact_ids=(artifact.id,),
            )
            lock = create_project_lock({
                "revision": 1,
                "parent_lock_digest": None,
                "sample_sheet": "samples.tsv",
                "cell_annotation": "cell-annotation.tsv",
                "panel_registry": "panels.json",
                "genome_build": "GRCm39",
                "annotation_release": "GENCODE-M36",
                "experimental_unit": "embryo",
                "thresholds": {"fdr": 0.05},
                "colors": {"control": "#0072B2", "mutant": "#D55E00"},
                "formal_output_root": "results/formal",
            }, state, root)
            ledger = ResultStatusLedger.create(state.context.project_id, lock.digest)
            ledger = transition_result_status(
                ledger,
                state=state,
                lock=lock,
                workspace_root=root,
                artifact_id=artifact.id,
                to_status="CANDIDATE",
                validation_scope={"engineering_validated": False, "method_validated": False},
                rationale="Retain this controlled record only as a candidate pending execution and scientific review.",
            )
            self.assertEqual(ledger.events[-1].to_status, "CANDIDATE")
            with self.assertRaisesRegex(ValueError, "input artifacts|execution"):
                transition_result_status(
                    ledger,
                    state=state,
                    lock=lock,
                    workspace_root=root,
                    artifact_id=artifact.id,
                    to_status="FORMAL",
                    validation_scope={"engineering_validated": True, "method_validated": True},
                    rationale="Attempting formal promotion must exercise every scientific promotion gate.",
                )
            (root / "samples.tsv").write_text("drifted\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "drifted"):
                verify_project_lock(lock, state, root)


if __name__ == "__main__":
    unittest.main()
