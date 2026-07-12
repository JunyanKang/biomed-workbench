import unittest

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.orchestration.quality import evaluate_project_quality
from tests.unit.kernel.test_artifacts import artifact
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.orchestration.test_quality import quality_node, quality_state


class ScientificInferenceGateContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = ModuleRegistry.discover(BUILTIN_ROOT).get("data-profile")

    def codes(self, state, artifact_ids):
        return {finding.code for finding in evaluate_project_quality(state, quality_node(artifact_ids), self.manifest)}

    def test_cross_artifact_identity_build_coordinate_unit_denominator_and_level_mismatches(self):
        first = artifact(id="artifact-one", source_artifact_ids=(), scientific_scope={"unit": "counts"})
        second = artifact(
            id="artifact-two",
            source_artifact_ids=(),
            identifier_namespace="entrez-gene",
            genome_build="GRCh37",
            coordinate_system="one-based-inclusive",
            scientific_scope={"unit": "tpm"},
            denominator="two-lines",
            processing_level="normalized",
            content={"cell_count": 1000},
        )
        codes = self.codes(quality_state(first, second), (first.id, second.id))

        self.assertTrue(
            {
                "IDENTIFIER_NAMESPACE_MISMATCH",
                "GENOME_BUILD_MISMATCH",
                "COORDINATE_SYSTEM_MISMATCH",
                "UNIT_MISMATCH",
                "DENOMINATOR_MISMATCH",
                "PROCESSING_LEVEL_MISMATCH",
            }
            <= codes
        )

    def test_duplicate_circular_confounded_and_outcome_informed_inputs_are_detected(self):
        first = artifact(
            id="artifact-one",
            source_artifact_ids=(),
            content={
                "training_cohort_id": "cohort-a",
                "validation_cohort_id": "cohort-a",
                "completely_confounded": True,
                "threshold_selected_on_outcome": True,
            },
        )
        second = artifact(id="artifact-two", source_artifact_ids=(), content=dict(first.content))
        codes = self.codes(quality_state(first, second), (first.id, second.id))

        self.assertTrue({"DUPLICATED_EVIDENCE", "CIRCULAR_VALIDATION", "COMPLETE_CONFOUNDING", "OUTCOME_INFORMED_THRESHOLD"} <= codes)

    def test_pseudoreplication_unsupported_causality_claim_drift_and_privacy_are_detected(self):
        causal = hypothesis(permitted_claim_strength="causal")
        context = project_context(privacy_level="sensitive", study_design="observational-cohort")
        value = artifact(
            source_artifact_ids=(),
            experimental_unit="single-cell",
            content={"participant_name": "coded-name", "evidence_ids": ["missing-evidence"]},
        )
        codes = self.codes(quality_state(value, context=context, active_hypothesis=causal), (value.id,))

        self.assertTrue({"PSEUDOREPLICATION_RISK", "UNSUPPORTED_CAUSAL_SCOPE", "CLAIM_EVIDENCE_DRIFT", "PRIVACY_VIOLATION"} <= codes)


if __name__ == "__main__":
    unittest.main()
