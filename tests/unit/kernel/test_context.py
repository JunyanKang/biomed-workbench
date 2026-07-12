import unittest

from biomed_workbench.kernel.context import Comparison, Constraint, ProjectContext


def project_context(**overrides):
    values = {
        "project_id": "retina-development",
        "objective": "Determine how a perturbation changes retinal progenitor differentiation.",
        "scientific_question": "Does the perturbation alter the transition from progenitor to neuronal states?",
        "species": ("human",),
        "biological_scope": {"tissue": "retina", "system": "organoid"},
        "study_design": "paired-perturbation",
        "experimental_unit": "independent-organoid-line",
        "comparisons": (Comparison("perturbed-vs-control", "perturbed", "control", ("batch",)),),
        "constraints": (Constraint("privacy", "privacy", "No direct participant identifiers may enter project state.", True),),
        "required_deliverables": ("claim_set", "figure_specification"),
        "required_evidence_types": ("molecular_association", "orthogonal_validation"),
        "privacy_level": "controlled",
    }
    values.update(overrides)
    return ProjectContext(**values)


class ProjectContextTests(unittest.TestCase):
    def test_context_preserves_question_design_units_comparisons_and_deliverables(self):
        context = project_context()
        payload = context.to_dict()

        self.assertEqual(context.experimental_unit, "independent-organoid-line")
        self.assertEqual(context.comparisons[0].denominator_group, "control")
        self.assertEqual(payload["biological_scope"]["tissue"], "retina")
        self.assertEqual(payload["required_deliverables"], ["claim_set", "figure_specification"])

    def test_context_detaches_nested_scope_from_caller(self):
        scope = {"tissue": "retina", "assay": "multiome"}
        context = project_context(biological_scope=scope)
        scope["tissue"] = "brain"

        self.assertEqual(context.biological_scope["tissue"], "retina")
        with self.assertRaises(TypeError):
            context.biological_scope["tissue"] = "brain"

    def test_invalid_contexts_block_before_project_creation(self):
        invalid = (
            lambda: project_context(objective=""),
            lambda: project_context(scientific_question=""),
            lambda: project_context(species=()),
            lambda: project_context(experimental_unit=""),
            lambda: project_context(privacy_level="unknown"),
            lambda: project_context(comparisons=(Comparison("same", "control", "control", ()),)),
            lambda: project_context(comparisons=(Comparison("duplicate", "a", "b", ()), Comparison("duplicate", "c", "d", ()))),
            lambda: project_context(constraints=(Constraint("secret", "credential", "Use API_KEY=private", True),)),
        )
        for factory in invalid:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()


if __name__ == "__main__":
    unittest.main()
