import unittest
import tempfile
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from biomed_workbench.kernel.scientific_dependency import (
    AnalysisAdmission,
    ArtifactReview,
    PanelInterpretation,
    ScientificDecision,
    ScientificDependencyBundle,
    build_scientific_dependency_graph,
)
from biomed_workbench.kernel.state import ProjectState, apply_event
from biomed_workbench.kernel.scientific_evidence_map import (
    EvidenceFile,
    EvidenceMapVersion,
    EvidenceMapPublication,
    EvidenceUnitSpec,
    NarrativeSource,
    build_scientific_evidence_map,
)
from biomed_workbench.reporting import (
    complete_evidence_map_publication_recovery,
    inspect_evidence_map_publication_recovery,
    publish_evidence_map_transaction,
    publish_evidence_map_version,
    render_bilingual_reports,
    verify_evidence_map_version_index,
)
from tests.unit.kernel.test_state import populated_state, research_plan


def admission():
    return AnalysisAdmission(
        id="admission-cell-state-analysis",
        plan_node_id="node-cell-state-analysis",
        hypothesis_ids=("hypothesis-lineage-shift-v1",),
        rationale_zh="该分析直接检验预先定义的细胞状态变化假设，并保留原始计数作为推断依据。",
        rationale_en="This analysis directly tests the prespecified cell-state hypothesis while retaining raw counts for inference.",
        method="Run the registered single-cell quality workflow before any downstream biological interpretation.",
        official_sources=("https://scanpy.readthedocs.io/en/stable/",),
        alternatives_considered=("Seurat provides an independently implemented alternative for sensitivity analysis.",),
        assumptions=("Cell identifiers and count orientation accurately represent the declared biological samples.",),
        parameter_justifications={"minimum-counts": "The threshold is predeclared from assay depth and must not be tuned against condition labels."},
        acceptance_criteria=("All input cells are accounted for and the retained count matrix reloads without identity drift.",),
        falsification_criteria=("Failure of identity reconciliation or sample-level accounting blocks downstream interpretation.",),
        expected_artifact_types=("quality_report",),
        approved=True,
    )


def review(**overrides):
    values = {
        "id": "review-artifact-counts-01",
        "artifact_id": "artifact-counts-01",
        "artifact_kind": "data",
        "rationale_zh": "该计数矩阵是检验谱系变化假设的输入证据，需要先确认身份、计数层和实验单位。",
        "rationale_en": "This count matrix is input evidence for the lineage hypothesis and requires identity, count-layer, and experimental-unit review.",
        "methods_zh": "依据登记的格式、内容摘要、实验单位和质量字段进行完整性与可追溯性核查。",
        "methods_en": "Integrity and traceability were reviewed from the registered format, content digest, experimental unit, and quality fields.",
        "results_zh": "产物身份和内容摘要一致，未发现阻断后续质量控制分析的结构性问题。",
        "results_en": "Artifact identity and content digest are coherent, with no structural issue blocking downstream quality analysis.",
        "conclusion_zh": "该产物可在保留局限性的前提下进入当前科学证据链，但不能单独支持生物学结论。",
        "conclusion_en": "The artifact may enter the current evidence chain with limitations, but it cannot alone support a biological conclusion.",
        "panels": (),
        "technical_status": "passed",
        "statistical_status": "warning",
        "biological_status": "warning",
        "robustness_status": "warning",
        "limitations_zh": ("尚未完成独立数据集或正交实验验证，当前结论仅限于输入资格。",),
        "limitations_en": ("Independent data or orthogonal experimental validation has not yet been completed; conclusions are limited to input eligibility.",),
        "recommended_action": "retain-with-caveat",
        "source_urls": ("https://www.w3.org/TR/prov-o/",),
    }
    values.update(overrides)
    return ArtifactReview(**values)


def decision(**overrides):
    values = {
        "id": "decision-artifact-counts-01",
        "review_id": "review-artifact-counts-01",
        "artifact_id": "artifact-counts-01",
        "hypothesis_ids": ("hypothesis-lineage-shift-v1",),
        "action": "retain-with-caveat",
        "rationale_zh": "技术身份检查通过，但统计和生物学结论仍需后续分析，因此作为带限制的有效证据保留。",
        "rationale_en": "Technical identity checks pass, while statistical and biological conclusions require downstream analyses, so the artifact is retained with caveats.",
        "active_evidence": True,
        "next_plan_node_ids": ("node-cell-state-analysis",),
    }
    values.update(overrides)
    return ScientificDecision(**values)


def state_with_plan():
    state = populated_state()
    plan = research_plan()
    return apply_event(
        state,
        "plan_created",
        {"plan": plan.to_dict(), "activate": True},
        rationale="Approve one predeclared analysis after scientific admission review.",
        affected_artifact_ids=("artifact-counts-01",),
        affected_hypothesis_ids=("hypothesis-lineage-shift-v1",),
        replacement_action_ids=("node-cell-state-analysis",),
    )


def evidence_map(state, bundle, root: Path, version: EvidenceMapVersion):
    files = {
        "data/counts.tsv": "gene\tcell\nA\t1\n",
        "scripts/analyze.py": "print('validated analysis')\n",
        "results/qualified-counts.tsv": "metric\tvalue\ncells\t1\n",
        "captions/counts.md": "Count matrix eligibility and provenance review.\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    spec = EvidenceUnitSpec(
        id="evidence-unit-counts",
        group_id="data-counts",
        artifact_id="artifact-counts-01",
        panel_id=None,
        analysis_admission_ids=("admission-cell-state-analysis",),
        predecessor_unit_ids=(),
        prerequisite_conclusion_zh="该数据单元是项目起始输入，尚无前置 panel 结论，但必须先通过身份和质量资格核查。",
        prerequisite_conclusion_en="This data unit is the initial project input and has no predecessor panel conclusion, but identity and quality eligibility must be reviewed first.",
        files=(
            EvidenceFile.from_workspace(id="file-counts-input", role="registered-data", path="data/counts.tsv", media_type="text/tab-separated-values", workspace_root=root),
            EvidenceFile.from_workspace(id="file-counts-script", role="analysis-script", path="scripts/analyze.py", media_type="text/x-python", workspace_root=root),
            EvidenceFile.from_workspace(id="file-counts-result", role="final-data", path="results/qualified-counts.tsv", media_type="text/tab-separated-values", workspace_root=root),
            EvidenceFile.from_workspace(id="file-counts-caption", role="caption", path="captions/counts.md", media_type="text/markdown", workspace_root=root),
        ),
        narrative_sources=(
            NarrativeSource(
                id="source-fair-principles",
                role="original-study",
                title="The FAIR Guiding Principles for scientific data management and stewardship",
                doi="10.1038/sdata.2016.18",
                url="https://doi.org/10.1038/sdata.2016.18",
            ),
        ),
    )
    return build_scientific_evidence_map(
        state,
        bundle,
        (spec,),
        workspace_root=root,
        version=version,
    )


class ScientificDependencyTests(unittest.TestCase):
    def test_complete_review_builds_graph_and_two_full_reports(self):
        state = state_with_plan()
        bundle = ScientificDependencyBundle.create(
            state,
            admissions=(admission(),),
            reviews=(review(),),
            decisions=(decision(),),
        )
        graph = build_scientific_dependency_graph(state, bundle)
        with tempfile.TemporaryDirectory() as temporary:
            mapped = evidence_map(
                state,
                bundle,
                Path(temporary),
                EvidenceMapVersion(
                    version="1.0.0",
                    revision=1,
                    parent_map_digest=None,
                    change_type="initial",
                    change_summary_zh="建立首版科学证据地图并登记全部文件级证据链。",
                    change_summary_en="Create the initial scientific evidence map and register every file-level evidence chain.",
                ),
            )
            reports = render_bilingual_reports(mapped, workspace_root=Path(temporary))
            (Path(temporary) / "data/counts.tsv").write_text(
                "gene\tcell\nA\t2\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "checksum-mismatched"):
                render_bilingual_reports(mapped, workspace_root=Path(temporary))

        self.assertEqual(graph.active_evidence_artifact_ids, ("artifact-counts-01",))
        self.assertEqual(reports.evidence_map_digest, mapped.digest)
        self.assertIn("科学依据与假设", reports.chinese_markdown)
        self.assertIn("分析方法", reports.chinese_markdown)
        self.assertIn("结果与科学结论", reports.chinese_markdown)
        self.assertIn("Scientific rationale and hypothesis", reports.english_markdown)
        self.assertIn("Methods", reports.english_markdown)
        self.assertIn("Results and scientific conclusion", reports.english_markdown)
        self.assertIn("SHA-256", reports.english_markdown)
        self.assertIn("10.1038/sdata.2016.18", reports.english_markdown)

    def test_snapshot_may_describe_pending_input_but_validated_delivery_rejects_it(self):
        state = state_with_plan()
        snapshot = ScientificDependencyBundle.create(
            state,
            admissions=(admission(),),
            reviews=(review(),),
            decisions=(decision(),),
            map_kind="project-snapshot",
        )
        self.assertEqual(snapshot.map_kind, "project-snapshot")
        with self.assertRaisesRegex(ValueError, "executed, reloaded, reviewed, and retained|reload receipt"):
            ScientificDependencyBundle.create(
                state,
                admissions=(admission(),),
                reviews=(review(),),
                decisions=(decision(),),
                map_kind="validated-delivery",
            )

    def test_missing_review_or_decision_is_rejected(self):
        state = state_with_plan()
        with self.assertRaisesRegex(ValueError, "every registered artifact"):
            ScientificDependencyBundle.create(
                state,
                admissions=(admission(),),
                reviews=(),
                decisions=(),
            )

    def test_blocking_review_cannot_be_retained_as_active_evidence(self):
        state = state_with_plan()
        with self.assertRaisesRegex(ValueError, "cannot become active evidence"):
            ScientificDependencyBundle.create(
                state,
                admissions=(admission(),),
                reviews=(review(technical_status="fatal"),),
                decisions=(decision(),),
            )

    def test_version_publication_is_append_only_and_parent_digest_chained(self):
        state = state_with_plan()
        bundle = ScientificDependencyBundle.create(
            state,
            admissions=(admission(),),
            reviews=(review(),),
            decisions=(decision(),),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            first = evidence_map(
                state,
                bundle,
                workspace,
                EvidenceMapVersion(
                    version="1.0.0",
                    revision=1,
                    parent_map_digest=None,
                    change_type="initial",
                    change_summary_zh="建立首版科学证据地图并冻结全部证据链。",
                    change_summary_en="Create the initial evidence map and freeze all evidence chains.",
                ),
            )
            publish_root = root / "published"
            publish_evidence_map_version(first, publish_root, workspace_root=workspace)
            second = evidence_map(
                state,
                bundle,
                workspace,
                EvidenceMapVersion(
                    version="1.0.1",
                    revision=2,
                    parent_map_digest=first.digest,
                    change_type="patch",
                    change_summary_zh="补充版本说明但不改变科学结论和证据状态。",
                    change_summary_en="Clarify version documentation without changing scientific conclusions or evidence status.",
                ),
            )
            publish_evidence_map_version(second, publish_root, workspace_root=workspace)
            index = verify_evidence_map_version_index(publish_root)

            self.assertEqual([item["version"] for item in index["entries"]], ["1.0.0", "1.0.1"])
            self.assertEqual(index["entries"][1]["parent_map_digest"], first.digest)
            self.assertTrue((publish_root / "versions/v1.0.0/scientific-evidence-map.json").is_file())
            self.assertTrue((publish_root / "versions/v1.0.1/scientific-evidence-report.zh-CN.md").is_file())
            with self.assertRaisesRegex(ValueError, "already exists|increase"):
                publish_evidence_map_version(second, publish_root, workspace_root=workspace)

            index_path = publish_root / "evidence-map-version-index.json"
            original_index = json.loads(index_path.read_text(encoding="utf-8"))
            invalid_transition = json.loads(json.dumps(original_index))
            invalid_transition["entries"][1]["change_type"] = "minor"
            index_path.write_text(
                json.dumps(invalid_transition, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "semantic-version transition"):
                verify_evidence_map_version_index(publish_root)
            index_path.write_text(
                json.dumps(original_index, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            map_path = publish_root / "versions/v1.0.1/scientific-evidence-map.json"
            map_payload = json.loads(map_path.read_text(encoding="utf-8"))
            map_payload["scientific_question"] = "A silently altered scientific question."
            map_path.write_text(
                json.dumps(map_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            forged_index = json.loads(json.dumps(original_index))
            forged_index["entries"][1]["files"]["scientific-evidence-map.json"] = hashlib.sha256(
                map_path.read_bytes()
            ).hexdigest()
            index_path.write_text(
                json.dumps(forged_index, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "differs from its version index"):
                verify_evidence_map_version_index(publish_root)

    def test_transaction_publishes_files_and_state_without_an_unregistered_gap(self):
        state = state_with_plan()
        state = apply_event(state, "analysis_admission_recorded", {"admission": admission().to_dict()}, rationale="Record the approved map analysis admission.")
        state = apply_event(state, "artifact_review_recorded", {"review": review().to_dict()}, rationale="Record the bilingual input qualification review.")
        state = apply_event(state, "scientific_decision_recorded", {"decision": decision().to_dict()}, rationale="Retain the qualified input for the project snapshot.")
        bundle = ScientificDependencyBundle.create(
            state,
            admissions=state.analysis_admissions,
            reviews=state.artifact_reviews,
            decisions=state.scientific_decisions,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            mapped = evidence_map(
                state,
                bundle,
                workspace,
                EvidenceMapVersion(
                    version="1.0.0",
                    revision=1,
                    parent_map_digest=None,
                    change_type="initial",
                    change_summary_zh="以可恢复事务发布首版项目快照及其项目状态登记。",
                    change_summary_en="Publish the first project snapshot and state registration through a recoverable transaction.",
                ),
            )
            publication = EvidenceMapPublication.from_map(mapped)
            prospective = apply_event(
                state,
                "evidence_map_published",
                {"publication": publication.to_dict()},
                rationale="Bind the exact immutable map digest to the project before transaction commit.",
            )
            state_path = root / "project-state.json"
            publish_root = root / "published"
            state_path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            publish_evidence_map_transaction(
                mapped,
                publication,
                prospective,
                state_path=state_path,
                output_root=publish_root,
                workspace_root=workspace,
            )
            reloaded = ProjectState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
            self.assertEqual(reloaded.state_digest, prospective.state_digest)
            self.assertEqual(inspect_evidence_map_publication_recovery(publish_root, state_path=state_path)["status"], "clean")

    def test_interrupted_transaction_can_complete_only_from_verified_pending_state(self):
        state = state_with_plan()
        state = apply_event(state, "analysis_admission_recorded", {"admission": admission().to_dict()}, rationale="Record admission.")
        state = apply_event(state, "artifact_review_recorded", {"review": review().to_dict()}, rationale="Record review.")
        state = apply_event(state, "scientific_decision_recorded", {"decision": decision().to_dict()}, rationale="Record decision.")
        bundle = ScientificDependencyBundle.create(
            state, admissions=state.analysis_admissions, reviews=state.artifact_reviews,
            decisions=state.scientific_decisions,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            mapped = evidence_map(
                state, bundle, workspace,
                EvidenceMapVersion(
                    version="1.0.0", revision=1, parent_map_digest=None, change_type="initial",
                    change_summary_zh="验证中断后完成项目状态登记。",
                    change_summary_en="Verify completion of project-state registration after interruption.",
                ),
            )
            publication = EvidenceMapPublication.from_map(mapped)
            prospective = apply_event(
                state, "evidence_map_published", {"publication": publication.to_dict()},
                rationale="Prepare the exact publication state.",
            )
            state_path = root / "project-state.json"
            state_path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            publish_root = root / "published"
            from biomed_workbench.reporting import evidence_map_versions as versions
            original_atomic = versions._atomic_json

            def interrupt_state_write(path, payload):
                if Path(path) == state_path:
                    raise OSError("simulated state-write interruption")
                return original_atomic(path, payload)

            with patch.object(versions, "_atomic_json", side_effect=interrupt_state_write):
                with self.assertRaisesRegex(OSError, "simulated"):
                    publish_evidence_map_transaction(
                        mapped, publication, prospective, state_path=state_path,
                        output_root=publish_root, workspace_root=workspace,
                    )
            self.assertEqual(
                inspect_evidence_map_publication_recovery(publish_root, state_path=state_path)["status"],
                "state-unregistered",
            )
            recovered = complete_evidence_map_publication_recovery(publish_root, state_path=state_path)
            self.assertEqual(recovered["status"], "clean")
            self.assertEqual(
                ProjectState.from_dict(json.loads(state_path.read_text(encoding="utf-8"))).state_digest,
                prospective.state_digest,
            )

            second_state_path = root / "second-project-state.json"
            second_state_path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            second_publish_root = root / "second-published"

            def interrupt_second_state_write(path, payload):
                if Path(path) == second_state_path:
                    raise OSError("simulated second state-write interruption")
                return original_atomic(path, payload)

            with patch.object(versions, "_atomic_json", side_effect=interrupt_second_state_write):
                with self.assertRaisesRegex(OSError, "simulated second"):
                    publish_evidence_map_transaction(
                        mapped, publication, prospective, state_path=second_state_path,
                        output_root=second_publish_root, workspace_root=workspace,
                    )
            wrong_target = root / "wrong-project-state.json"
            wrong_target.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "recovery target differs"):
                complete_evidence_map_publication_recovery(second_publish_root, state_path=wrong_target)
            second_state_path.write_text(
                json.dumps(prospective.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            next((second_publish_root / ".evidence-map-pending-states").glob("*.json")).unlink()
            recovered_after_state_write = complete_evidence_map_publication_recovery(
                second_publish_root,
                state_path=second_state_path,
            )
            self.assertEqual(recovered_after_state_write["status"], "clean")

    def test_figure_panels_create_global_story_and_file_level_mind_maps(self):
        state = state_with_plan()
        panels = tuple(
            PanelInterpretation(
                panel_id=panel_id,
                rationale_zh=f"{panel_id} 用于检验预先登记的细胞状态假设并连接跨 panel 故事线。",
                rationale_en=f"{panel_id} tests the preregistered cell-state hypothesis and contributes to the cross-panel story.",
                methods_zh=f"{panel_id} 使用登记数据和固定参数生成，并保留脚本、renderer 和最终图文件。",
                methods_en=f"{panel_id} is generated from registered data with fixed parameters and retained scripts, renderer, and final figure.",
                results_zh=f"{panel_id} 显示了与当前证据范围一致的质量控制结果，但不单独建立因果关系。",
                results_en=f"{panel_id} shows quality-control results consistent with the current evidence scope but does not alone establish causality.",
                conclusion_zh=f"{panel_id} 仅支持带限制的描述性结论，并需与相邻 panel 联合解读。",
                conclusion_en=f"{panel_id} supports only a caveated descriptive conclusion and requires joint interpretation with adjacent panels.",
            )
            for panel_id in ("panel-a", "panel-b")
        )
        figure_review = review(artifact_kind="figure", panels=panels)
        bundle = ScientificDependencyBundle.create(
            state,
            admissions=(admission(),),
            reviews=(figure_review,),
            decisions=(decision(),),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specs = []
            for panel_id, predecessor in (("panel-a", ()), ("panel-b", ("unit-panel-a",))):
                resources = {
                    f"fig/{panel_id}/registered.tsv": "x\ty\n1\t2\n",
                    f"fig/{panel_id}/plot.tsv": "x\ty\n1\t2\n",
                    f"fig/{panel_id}/analysis.py": "print('analysis')\n",
                    f"fig/{panel_id}/renderer.py": "print('renderer')\n",
                    f"fig/{panel_id}/final.png": f"{panel_id}-png",
                    f"fig/{panel_id}/final.pdf": f"{panel_id}-pdf",
                    f"fig/{panel_id}/caption.md": f"Caption for {panel_id}.\n",
                }
                for relative, content in resources.items():
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                roles = (
                    ("registered", "registered-data", "registered.tsv", "text/tab-separated-values"),
                    ("plot", "plot-data", "plot.tsv", "text/tab-separated-values"),
                    ("analysis", "analysis-script", "analysis.py", "text/x-python"),
                    ("renderer", "renderer", "renderer.py", "text/x-python"),
                    ("png", "final-png", "final.png", "image/png"),
                    ("pdf", "final-pdf", "final.pdf", "application/pdf"),
                    ("caption", "caption", "caption.md", "text/markdown"),
                )
                specs.append(
                    EvidenceUnitSpec(
                        id=f"unit-{panel_id}",
                        group_id="figure-one",
                        artifact_id="artifact-counts-01",
                        panel_id=panel_id,
                        analysis_admission_ids=("admission-cell-state-analysis",),
                        predecessor_unit_ids=predecessor,
                        prerequisite_conclusion_zh=f"{panel_id} 的前置结论已登记；panel-b 必须明确依赖 panel-a。",
                        prerequisite_conclusion_en=f"The prerequisite conclusion for {panel_id} is registered; panel-b must explicitly depend on panel-a.",
                        files=tuple(
                            EvidenceFile.from_workspace(
                                id=f"file-{panel_id}-{suffix}",
                                role=role,
                                path=f"fig/{panel_id}/{filename}",
                                media_type=media_type,
                                workspace_root=root,
                            )
                            for suffix, role, filename, media_type in roles
                        ),
                        narrative_sources=(
                            NarrativeSource(
                                id=f"source-{panel_id}-fair",
                                role="original-study",
                                title="The FAIR Guiding Principles for scientific data management and stewardship",
                                doi="10.1038/sdata.2016.18",
                                url="https://doi.org/10.1038/sdata.2016.18",
                            ),
                        ),
                    )
                )
            mapped = build_scientific_evidence_map(
                state,
                bundle,
                tuple(specs),
                workspace_root=root,
                version=EvidenceMapVersion(
                    version="1.0.0",
                    revision=1,
                    parent_map_digest=None,
                    change_type="initial",
                    change_summary_zh="建立含跨 panel 故事线和文件级证据链的首版地图。",
                    change_summary_en="Create the initial map with a cross-panel story and file-level evidence chains.",
                ),
            )
            reports = render_bilingual_reports(mapped, workspace_root=root)

        self.assertEqual(
            [(edge.source, edge.target) for edge in mapped.story_edges],
            [("unit-panel-a", "unit-panel-b")],
        )
        self.assertTrue(any(edge.relation == "to-renderer" for edge in mapped.detail_edges))
        renderer_targets = {
            edge.target
            for edge in mapped.detail_edges
            if edge.source == "file-panel-a-renderer"
        }
        self.assertEqual(
            renderer_targets,
            {"file-panel-a-pdf", "file-panel-a-png"},
        )
        self.assertIn("panel-a", reports.english_markdown)
        self.assertIn("panel-b", reports.english_markdown)

    def test_unindexed_immutable_version_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            publish_root = Path(temporary)
            orphan = publish_root / "versions" / "v9.9.9"
            orphan.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "unindexed"):
                verify_evidence_map_version_index(publish_root)


if __name__ == "__main__":
    unittest.main()
