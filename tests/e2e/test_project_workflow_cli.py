import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.scientific_dependency import AnalysisAdmission
from biomed_workbench.kernel.state import ProjectState
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_hypotheses import hypothesis
from tests.unit.kernel.test_state import ProjectStateTests
from tests.unit.orchestration.test_controller import serial_fixture
from tests.unit.orchestration.test_planner import inline_artifact


ROOT = Path(__file__).resolve().parents[2]


class ProjectWorkflowCliTests(unittest.TestCase):
    def test_map_bound_v1_migration_cli_verifies_store_and_preserves_legacy_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            publication_root = root / "legacy-maps"
            legacy, old_publication = ProjectStateTests._map_bound_legacy_fixture(publication_root)
            legacy_path = root / "project-state-v1.json"
            migrated_path = root / "project-state-v2.json"
            legacy_path.write_text(json.dumps(legacy, indent=2, sort_keys=True), encoding="utf-8")
            legacy_bytes = legacy_path.read_bytes()

            migrated = subprocess.run(
                [
                    sys.executable,
                    "tools/project_workflow.py",
                    "migrate-state-v1",
                    "--legacy-state",
                    str(legacy_path),
                    "--state",
                    str(migrated_path),
                    "--evidence-map-root",
                    str(publication_root),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            summary = json.loads(migrated.stdout)
            self.assertEqual(summary["migration_status"], "awaiting-evidence-map-republication")
            self.assertEqual(summary["verified_legacy_evidence_maps"], 1)
            self.assertEqual(legacy_path.read_bytes(), legacy_bytes)
            state = ProjectState.from_dict(json.loads(migrated_path.read_text(encoding="utf-8")))
            record = state.state_migrations[0].legacy_evidence_maps[0]
            self.assertEqual(record.publication.map_digest, old_publication.map_digest)
            self.assertEqual(state.evidence_map_versions, ())

    def test_init_and_admit_persist_replayable_append_only_state(self):
        temporary_registry, _registry, _state, plan = serial_fixture()
        self.addCleanup(temporary_registry.cleanup)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context_path = root / "context.json"
            hypotheses_path = root / "hypotheses.json"
            artifacts_path = root / "artifacts.json"
            plan_path = root / "plan.json"
            state_path = root / "project-state.json"
            admission_path = root / "admission.json"
            context_path.write_text(json.dumps(project_context().to_dict()), encoding="utf-8")
            hypotheses_path.write_text(json.dumps([hypothesis().to_dict()]), encoding="utf-8")
            artifacts_path.write_text(json.dumps([inline_artifact("artifact-counts", "count_matrix").to_dict()]), encoding="utf-8")
            plan_path.write_text(json.dumps(plan.to_dict()), encoding="utf-8")
            initialized = subprocess.run(
                [
                    sys.executable,
                    "tools/project_workflow.py",
                    "init",
                    "--context",
                    str(context_path),
                    "--hypotheses",
                    str(hypotheses_path),
                    "--artifacts",
                    str(artifacts_path),
                    "--plan",
                    str(plan_path),
                    "--state",
                    str(state_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            node = plan.nodes[0]
            admission = AnalysisAdmission(
                id=f"admission-{node.id}",
                plan_node_id=node.id,
                hypothesis_ids=(hypothesis().id,),
                rationale_zh="该上游分析用于生成后续假设检验所需的规范化数据。",
                rationale_en="This upstream analysis produces normalized data required for downstream hypothesis testing.",
                method="Execute the exact registered normalization module under its declared compatibility contract.",
                official_sources=("https://example.org/official-method",),
                alternatives_considered=("Use the manifest-declared alternative only after a documented compatibility failure.",),
                assumptions=("Input identity, experimental units, and denominator metadata are correct and reviewed.",),
                parameter_justifications={"default": "Manifest defaults are retained for this deterministic state-machine fixture."},
                acceptance_criteria=("The declared output is reloaded and passes its registered artifact contract.",),
                falsification_criteria=("A missing output or blocking quality finding prevents scientific release.",),
                expected_artifact_types=node.expected_output_artifact_types,
                approved=True,
            )
            admission_path.write_text(json.dumps(admission.to_dict()), encoding="utf-8")
            admitted = subprocess.run(
                [sys.executable, "tools/project_workflow.py", "admit", "--state", str(state_path), "--input", str(admission_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(admitted.returncode, 0, admitted.stderr)
            restored = ProjectState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
            self.assertEqual(restored.analysis_admissions, (admission,))
            self.assertEqual(restored.active_plan_id, plan.id)


if __name__ == "__main__":
    unittest.main()
