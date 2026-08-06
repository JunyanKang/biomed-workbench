import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.execution_chain import gate_adjudication_bundle_digest
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
            self.assertEqual(summary["migration_status"], "awaiting-scientific-dependency-recovery")
            self.assertEqual(summary["missing_analysis_admission_node_ids"], [])
            self.assertEqual(summary["legacy_admission_recovery_node_ids"], ["node-functional-enrichment"])
            self.assertEqual(
                set(summary["missing_artifact_review_ids"]),
                {"artifact-genes", "artifact-universe", "artifact-enrichment-result"},
            )
            self.assertTrue(summary["delivery_permanently_blocked_by_legacy_recovery"])
            self.assertFalse(summary["delivery_prerequisites_currently_satisfied"])
            self.assertEqual(summary["required_next_map_revision"], 2)
            self.assertEqual(summary["required_parent_map_digest"], old_publication.map_digest)
            self.assertEqual(summary["verified_legacy_evidence_maps"], 1)
            self.assertEqual(legacy_path.read_bytes(), legacy_bytes)
            state = ProjectState.from_dict(json.loads(migrated_path.read_text(encoding="utf-8")))
            record = state.state_migrations[0].legacy_evidence_maps[0]
            self.assertEqual(record.publication.map_digest, old_publication.map_digest)
            self.assertEqual(state.evidence_map_versions, ())

            recovery = state.state_migrations[0].legacy_analysis_admission_recoveries[0]
            self.assertFalse(recovery.approved_before_execution)
            self.assertEqual(recovery.evidence_scope, "project-snapshot-only")
            self.assertEqual(recovery.source_map_coverage_status, "not-covered")
            hypothesis_id = state.hypotheses[0].id
            for artifact in state.artifacts:
                gate_ids = sorted(
                    item.id for item in state.gate_adjudications if item.artifact_id == artifact.id
                )
                review = {
                    "id": f"review-migrated-{artifact.id}",
                    "artifact_id": artifact.id,
                    "artifact_kind": "data",
                    "rationale_zh": "迁移后依据保留的产物身份、来源链和质量记录重新完成双语科学评审。",
                    "rationale_en": "After migration, review the preserved artifact identity, provenance chain, and quality records in both languages.",
                    "methods_zh": "核对登记内容、来源产物、执行回执、质量门禁及旧版不可变证据地图的对应关系。",
                    "methods_en": "Check registered content, source artifacts, execution receipts, quality gates, and the immutable legacy evidence-map linkage.",
                    "results_zh": "该产物身份与迁移后的状态记录一致；历史事前准入不可证明，因此仅用于项目快照。",
                    "results_en": "The artifact identity agrees with the migrated state; historical prior admission is unavailable, so use is limited to a project snapshot.",
                    "conclusion_zh": "在明确历史准入缺失且不提升证据强度的条件下，该产物可进入迁移后的项目快照。",
                    "conclusion_en": "The artifact may enter the migrated project snapshot while explicitly preserving the missing historical admission and without increasing evidence strength.",
                    "panels": [],
                    "technical_status": "passed",
                    "statistical_status": "warning",
                    "biological_status": "warning",
                    "robustness_status": "warning",
                    "limitations_zh": ["旧版状态未保存可证明的事前分析准入，因此不能授权科研交付。"],
                    "limitations_en": ["The legacy state lacks provable prior analysis admission and therefore cannot authorize scientific delivery."],
                    "recommended_action": "retain-with-caveat",
                    "source_urls": ["https://www.w3.org/TR/prov-o/"],
                    "gate_adjudication_ids": gate_ids,
                }
                review_path = root / f"{review['id']}.json"
                review_path.write_text(json.dumps(review), encoding="utf-8")
                reviewed = subprocess.run(
                    [sys.executable, "tools/project_workflow.py", "review", "--state", str(migrated_path), "--input", str(review_path)],
                    cwd=ROOT, check=False, capture_output=True, text=True,
                )
                self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
                current = ProjectState.from_dict(json.loads(migrated_path.read_text(encoding="utf-8")))
                decision = {
                    "id": f"decision-migrated-{artifact.id}",
                    "review_id": review["id"],
                    "artifact_id": artifact.id,
                    "hypothesis_ids": [hypothesis_id],
                    "action": "retain-with-caveat",
                    "rationale_zh": "保留迁移产物用于历史项目快照，同时维持事前准入不可证明和不可用于交付授权的限制。",
                    "rationale_en": "Retain the migrated artifact for a historical project snapshot while preserving the unavailable-prior-admission and no-delivery-authorization limits.",
                    "active_evidence": True,
                    "next_plan_node_ids": [],
                }
                gate_digest = gate_adjudication_bundle_digest(current, artifact.id)
                if gate_digest is not None:
                    decision["gate_adjudication_digest"] = gate_digest
                decision_path = root / f"{decision['id']}.json"
                decision_path.write_text(json.dumps(decision), encoding="utf-8")
                decided = subprocess.run(
                    [sys.executable, "tools/project_workflow.py", "decide", "--state", str(migrated_path), "--input", str(decision_path)],
                    cwd=ROOT, check=False, capture_output=True, text=True,
                )
                self.assertEqual(decided.returncode, 0, decided.stderr)

            workspace = root / "workspace"
            specs = []
            for index, artifact_id in enumerate(("artifact-genes", "artifact-universe", "artifact-enrichment-result"), start=1):
                files = []
                for role, relative, media_type in (
                    ("registered-data", f"data/{artifact_id}.tsv", "text/tab-separated-values"),
                    ("analysis-script", f"scripts/{artifact_id}.py", "text/x-python"),
                    ("final-data", f"results/{artifact_id}.tsv", "text/tab-separated-values"),
                    ("caption", f"captions/{artifact_id}.md", "text/markdown"),
                ):
                    path = workspace / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(f"verified migrated artifact {artifact_id}\n", encoding="utf-8")
                    files.append({
                        "id": f"file-{index}-{role}", "role": role, "path": relative,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "media_type": media_type,
                    })
                specs.append({
                    "id": f"unit-migrated-{index}", "group_id": f"group-migrated-{index}",
                    "artifact_id": artifact_id, "panel_id": None,
                    "analysis_admission_ids": [recovery.id], "predecessor_unit_ids": [],
                    "prerequisite_conclusion_zh": "该迁移数据单元依赖已验证的旧版状态与不可变证据地图，但不存在可证明的事前准入。",
                    "prerequisite_conclusion_en": "This migrated data unit depends on the verified legacy state and immutable map, while provable prior admission is unavailable.",
                    "files": files,
                    "narrative_sources": [{
                        "id": f"source-migrated-{index}", "role": "original-study",
                        "title": "The FAIR Guiding Principles for scientific data management and stewardship",
                        "doi": "10.1038/sdata.2016.18", "url": "https://doi.org/10.1038/sdata.2016.18",
                    }],
                })
            specs_path = root / "evidence-units.json"
            specs_path.write_text(json.dumps(specs), encoding="utf-8")
            version_path = root / "map-version.json"
            version_path.write_text(json.dumps({
                "version": "1.0.1", "revision": 2,
                "parent_map_digest": old_publication.map_digest, "change_type": "patch",
                "change_summary_zh": "在保留历史准入缺失边界的前提下重新发布迁移后的项目快照。",
                "change_summary_en": "Republish the migrated project snapshot while preserving the unavailable historical-admission boundary.",
                "map_kind": "project-snapshot",
            }), encoding="utf-8")
            republished = subprocess.run(
                [
                    sys.executable, "tools/project_workflow.py", "map", "--state", str(migrated_path),
                    "--workspace", str(workspace), "--specs", str(specs_path),
                    "--version", str(version_path), "--publish-root", str(publication_root),
                ],
                cwd=ROOT, check=False, capture_output=True, text=True,
            )
            self.assertEqual(republished.returncode, 0, republished.stderr)
            republished_state = ProjectState.from_dict(json.loads(migrated_path.read_text(encoding="utf-8")))
            self.assertEqual(republished_state.evidence_map_versions[-1].version.revision, 2)
            self.assertEqual(republished_state.evidence_map_versions[-1].version.parent_map_digest, old_publication.map_digest)
            self.assertTrue((publication_root / "versions" / "v1.0.1" / "scientific-evidence-map.json").is_file())
            self.assertEqual(legacy_path.read_bytes(), legacy_bytes)

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
