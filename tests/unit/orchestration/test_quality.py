import unittest

from biomed_workbench.kernel.plans import PlanNode
from biomed_workbench.kernel.state import ProjectState, apply_event
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.orchestration.quality import evaluate_project_quality, interpretation_allowed
from tests.unit.kernel.test_artifacts import artifact
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_hypotheses import hypothesis


def quality_state(*artifacts, context=None, active_hypothesis=None):
    state = ProjectState.create(context or project_context())
    state = apply_event(
        state,
        "hypothesis_added",
        {"hypothesis": (active_hypothesis or hypothesis()).to_dict()},
        rationale="Register a hypothesis for quality evaluation.",
    )
    for value in artifacts:
        state = apply_event(state, "artifact_registered", {"artifact": value.to_dict()}, rationale="Register an artifact for quality evaluation.")
    return state


def quality_node(artifacts):
    return PlanNode(
        id="node-quality-evaluation",
        module_id="data-profile",
        input_bindings={f"input_{index}": artifact_id for index, artifact_id in enumerate(artifacts, start=1)},
        dependencies=(),
        branch_id="branch-quality",
        target_hypothesis_ids=("hypothesis-lineage-shift-v1",),
        expected_evidence_types=("cell-state-association",),
        expected_output_artifact_types=("quality_report",),
        planned_output_artifact_ids={"profile": "artifact-planned-quality"},
        compatibility_row_candidates=("python-3.14.3-inline-json-1",),
        status="pending",
        attempt=0,
    )


class ProjectQualityTests(unittest.TestCase):
    def setUp(self):
        self.manifest = ModuleRegistry.discover(BUILTIN_ROOT).get("data-profile")

    def test_clean_artifact_has_no_blocking_findings(self):
        value = artifact(source_artifact_ids=())
        findings = evaluate_project_quality(quality_state(value), quality_node((value.id,)), self.manifest)

        self.assertTrue(interpretation_allowed(findings))
        self.assertFalse(any(finding.severity in {"fatal", "major"} for finding in findings))

    def test_fatal_and_major_findings_block_interpretation_but_warning_does_not(self):
        values = (
            artifact(id="artifact-one", source_artifact_ids=(), quality_status="warning"),
            artifact(id="artifact-two", source_artifact_ids=(), genome_build="GRCh37", content={"cell_count": 1200}),
        )
        findings = evaluate_project_quality(quality_state(*values), quality_node(tuple(value.id for value in values)), self.manifest)

        self.assertFalse(interpretation_allowed(findings))
        self.assertIn("GENOME_BUILD_MISMATCH", {finding.code for finding in findings})
        self.assertTrue(all(finding.id.startswith("finding-") for finding in findings))
        self.assertTrue(all(finding.remediation_artifact_types for finding in findings if finding.severity in {"fatal", "major"}))

    def test_upstream_major_quality_blocks_execution(self):
        value = artifact(source_artifact_ids=(), quality_status="major")
        findings = evaluate_project_quality(quality_state(value), quality_node((value.id,)), self.manifest)
        finding = next(item for item in findings if item.code == "UPSTREAM_QUALITY_BLOCK")

        self.assertTrue(finding.blocks_execution)
        self.assertTrue(finding.blocks_interpretation)


if __name__ == "__main__":
    unittest.main()
