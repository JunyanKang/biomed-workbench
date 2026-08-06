import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.kernel.plans import PlanNode, ResearchDAG
from biomed_workbench.kernel.state import ProjectState, _legacy_v1_basis, _migrate_v1_adjudication, apply_event
from biomed_workbench.kernel.execution_chain import delivery_slice_digest
from biomed_workbench.kernel.identity import digest_value
from biomed_workbench.kernel.scientific_evidence_map import EvidenceMapPublication, EvidenceMapVersion
from biomed_workbench.kernel.scientific_dependency import ScientificDependencyBundle
from biomed_workbench.orchestration.state_migration import migrate_map_bound_v1_state
from biomed_workbench.kernel.hypotheses import revise_hypothesis
from tests.unit.kernel.test_artifacts import artifact
from tests.unit.kernel.test_context import project_context
from tests.unit.kernel.test_evidence import evidence_record
from tests.unit.kernel.test_hypotheses import hypothesis


def research_plan(**overrides):
    node = PlanNode(
        id="node-cell-state-analysis",
        module_id="single-cell-qc",
        input_bindings={"single_cell_counts": "artifact-counts-01"},
        dependencies=(),
        branch_id="branch-omics",
        target_hypothesis_ids=("hypothesis-lineage-shift-v1",),
        expected_evidence_types=("cell-state-association",),
        expected_output_artifact_types=("quality_report",),
        planned_output_artifact_ids={"cell_quality": "artifact-planned-cell-quality"},
        compatibility_row_candidates=("python-3.14.3-inline-json-1",),
        status="pending",
        attempt=0,
    )
    values = {
        "id": "plan-lineage-analysis-v1",
        "objective": "Test the lineage-shift hypothesis with quality-controlled molecular evidence.",
        "nodes": (node,),
        "required_output_artifact_types": ("quality_report",),
        "plan_type": "single",
        "revision": 1,
        "parent_plan_id": None,
        "rationale": ("The available count matrix directly supports the selected validation module.",),
    }
    values.update(overrides)
    return ResearchDAG.create(**values)


def populated_state():
    state = ProjectState.create(project_context())
    state = apply_event(
        state,
        "artifact_registered",
        {"artifact": artifact(source_artifact_ids=()).to_dict()},
        rationale="Register the declared count matrix before planning.",
        affected_artifact_ids=("artifact-counts-01",),
    )
    state = apply_event(
        state,
        "hypothesis_added",
        {"hypothesis": hypothesis().to_dict()},
        rationale="Register a falsifiable lineage hypothesis before testing it.",
        affected_hypothesis_ids=("hypothesis-lineage-shift-v1",),
    )
    return state


class ProjectStateTests(unittest.TestCase):
    @staticmethod
    def _map_bound_legacy_fixture(root: Path):
        fixture = Path(__file__).parents[2] / "fixtures" / "project_state_v1_gate_adjudications.json"
        legacy = json.loads(fixture.read_text(encoding="utf-8"))
        edge_digest = digest_value([])
        map_basis = {
            "project_id": legacy["context"]["project_id"],
            "version": {
                "version": "1.0.0", "revision": 1, "parent_map_digest": None,
                "change_type": "initial",
                "change_summary_zh": "发布旧版项目状态绑定的首个证据地图版本。",
                "change_summary_en": "Publish the first evidence-map version bound to the legacy project state.",
                "map_kind": "project-snapshot",
            },
            "state_digest": legacy["state_digest"],
            "dependency_bundle_digest": digest_value("legacy-dependency-bundle"),
            "map_kind": "project-snapshot",
            "delivery_slice_digest": digest_value("legacy-delivery-slice"),
            "active_evidence_artifact_ids": [],
            "covered_plan_id": None,
            "covered_node_ids": [],
            "covered_artifact_ids": [],
            "authorized_delivery_node_ids": [],
            "delivery_scope_digest": digest_value("legacy-delivery-scope"),
            "units": [],
            "edges": [],
            "edge_table_digest": edge_digest,
        }
        map_payload = {**map_basis, "digest": digest_value(map_basis)}
        publication = EvidenceMapPublication(
            id=f"evidence-map-1-{map_payload['digest'][:16]}",
            version=EvidenceMapVersion.from_dict(map_basis["version"]),
            map_digest=map_payload["digest"],
            edge_table_digest=edge_digest,
            source_state_digest=legacy["state_digest"],
            dependency_bundle_digest=map_basis["dependency_bundle_digest"],
            map_kind="project-snapshot",
            delivery_slice_digest=map_basis["delivery_slice_digest"],
            active_artifact_ids=(),
            covered_plan_id=None,
            covered_node_ids=(),
            covered_artifact_ids=(),
            authorized_delivery_node_ids=(),
            delivery_scope_digest=map_basis["delivery_scope_digest"],
        )
        version_root = root / "versions" / "v1.0.0"
        version_root.mkdir(parents=True)
        map_path = version_root / "scientific-evidence-map.json"
        map_path.write_text(json.dumps(map_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        file_sha = hashlib.sha256(map_path.read_bytes()).hexdigest()
        index = {
            "schema_version": 1,
            "entries": [{
                "project_id": legacy["context"]["project_id"],
                "version": "1.0.0", "revision": 1, "parent_map_digest": None,
                "change_type": "initial",
                "change_summary_zh": "发布旧版项目状态绑定的首个证据地图版本。",
                "change_summary_en": "Publish the first evidence-map version bound to the legacy project state.",
                "map_digest": publication.map_digest,
                "edge_table_digest": publication.edge_table_digest,
                "files": {"scientific-evidence-map.json": file_sha},
            }],
        }
        (root / "evidence-map-version-index.json").write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (root / "scientific-evidence-map.current.json").write_text(
            json.dumps({
                "project_id": legacy["context"]["project_id"],
                "version": "1.0.0", "revision": 1,
                "map_digest": publication.map_digest,
                "edge_table_digest": publication.edge_table_digest,
            }, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        event_payload = {"publication": publication.to_dict()}
        sequence = legacy["revision"] + 1
        identity_basis = {
            "sequence": sequence,
            "event_type": "evidence_map_published",
            "payload": event_payload,
            "prior_state_digest": legacy["state_digest"],
        }
        event = {
            "id": f"event-{sequence:06d}-{digest_value(identity_basis)[:12]}",
            "sequence": sequence,
            "event_type": "evidence_map_published",
            "payload": event_payload,
            "rationale": "Publish the verified legacy evidence map before schema migration.",
            "trigger_finding_ids": [],
            "affected_artifact_ids": [],
            "affected_hypothesis_ids": [],
            "superseded_action_ids": [],
            "replacement_action_ids": [],
            "prior_results_valid": True,
            "prior_state_digest": legacy["state_digest"],
            "resulting_state_digest": "0" * 64,
        }
        legacy["decisions"].append(event)
        legacy["evidence_map_versions"] = [publication.to_dict()]
        legacy["revision"] = sequence
        legacy["state_digest"] = digest_value(_legacy_v1_basis(legacy))
        legacy["decisions"][-1]["resulting_state_digest"] = legacy["state_digest"]
        return legacy, publication

    def test_map_bound_v1_migrates_non_destructively_then_requires_explicit_republication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy, old_publication = self._map_bound_legacy_fixture(root)
            migrated = migrate_map_bound_v1_state(legacy, evidence_map_root=root)

            self.assertEqual(migrated.schema_version, 2)
            self.assertEqual(migrated.revision, legacy["revision"])
            self.assertEqual(migrated.evidence_map_versions, ())
            self.assertEqual(len(migrated.state_migrations[0].legacy_evidence_maps), 1)
            self.assertEqual(
                migrated.state_migrations[0].legacy_evidence_maps[0].publication,
                old_publication,
            )
            self.assertEqual(migrated.decisions[-1].event_type, "legacy_evidence_map_verified")
            self.assertEqual(ProjectState.from_dict(migrated.to_dict()), migrated)
            recovery = migrated.state_migrations[0].legacy_analysis_admission_recoveries[0]
            self.assertEqual(recovery.recovery_status, "historical-unavailable")
            self.assertFalse(recovery.approved_before_execution)
            with self.assertRaisesRegex(ValueError, "project snapshots only"):
                ScientificDependencyBundle.create(
                    migrated,
                    admissions=(),
                    reviews=(),
                    decisions=(),
                    map_kind="delivery-authorization",
                )

            new_publication = EvidenceMapPublication(
                id="evidence-map-2-republished",
                version=EvidenceMapVersion(
                    version="1.0.1", revision=2,
                    parent_map_digest=old_publication.map_digest,
                    change_type="patch",
                    change_summary_zh="将已验证旧地图明确重新发布到新版项目状态。",
                    change_summary_en="Explicitly republish the verified legacy map lineage against the migrated project state.",
                    map_kind="project-snapshot",
                ),
                map_digest=digest_value("republished-map"),
                edge_table_digest=digest_value([]),
                source_state_digest=migrated.state_digest,
                dependency_bundle_digest=digest_value("republished-dependency-bundle"),
                map_kind="project-snapshot",
                delivery_slice_digest=delivery_slice_digest(migrated),
                active_artifact_ids=(), covered_plan_id=None, covered_node_ids=(),
                covered_artifact_ids=(), authorized_delivery_node_ids=(),
                delivery_scope_digest=digest_value("republished-delivery-scope"),
            )
            republished = apply_event(
                migrated,
                "evidence_map_published",
                {"publication": new_publication.to_dict()},
                rationale="Republish the evidence map against the migrated v2 state.",
            )
            self.assertEqual(republished.evidence_map_versions[-1], new_publication)
            self.assertEqual(ProjectState.from_dict(republished.to_dict()), republished)

            map_path = root / "versions" / "v1.0.0" / "scientific-evidence-map.json"
            map_path.write_text(map_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                migrate_map_bound_v1_state(legacy, evidence_map_root=root)

    def test_previous_release_v1_state_migrates_to_v2_with_exact_receipt_bindings(self):
        fixture = Path(__file__).parents[2] / "fixtures" / "project_state_v1_gate_adjudications.json"
        legacy = json.loads(fixture.read_text(encoding="utf-8"))

        state = ProjectState.from_dict(legacy)

        self.assertEqual(state.schema_version, 2)
        self.assertEqual(state.revision, legacy["revision"])
        self.assertEqual(len(state.gate_adjudications), 3)
        self.assertTrue(all(item.adjudication_mode == "manual" for item in state.gate_adjudications))
        self.assertTrue(all(item.observed_value and item.criterion and item.finding for item in state.gate_adjudications))
        self.assertEqual(len(state.state_migrations), 1)
        self.assertEqual(state.state_migrations[0].source_state_digest, legacy["state_digest"])
        self.assertEqual(state.state_migrations[0].source_revision, legacy["revision"])
        self.assertEqual(ProjectState.from_dict(state.to_dict()), state)

    def test_v1_migration_rejects_tampering_and_unrecoverable_gate_bindings(self):
        fixture = Path(__file__).parents[2] / "fixtures" / "project_state_v1_gate_adjudications.json"
        legacy = json.loads(fixture.read_text(encoding="utf-8"))
        tampered = copy.deepcopy(legacy)
        tampered["gate_adjudications"][0]["gate_result_digest"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "state digest is invalid"):
            ProjectState.from_dict(tampered)
        with self.assertRaisesRegex(ValueError, "cannot recover an exact observed binding"):
            _migrate_v1_adjudication(legacy["gate_adjudications"][0], {})

    def test_events_are_append_only_digest_linked_and_update_ledgers(self):
        state = populated_state()
        prior_digest = state.state_digest
        evidence = evidence_record(artifact_id="artifact-counts-01")

        state = apply_event(
            state,
            "evidence_added",
            {"evidence": evidence.to_dict()},
            rationale="Link the observed contrast to the active hypothesis.",
            trigger_finding_ids=("finding-contrast-direction",),
            affected_artifact_ids=("artifact-counts-01",),
            affected_hypothesis_ids=("hypothesis-lineage-shift-v1",),
        )

        self.assertEqual(state.revision, 3)
        self.assertEqual(tuple(event.sequence for event in state.decisions), (1, 2, 3))
        self.assertEqual(state.decisions[-1].prior_state_digest, prior_digest)
        self.assertEqual(state.decisions[-1].resulting_state_digest, state.state_digest)
        self.assertEqual(state.hypotheses[0].supporting_evidence_ids, ("evidence-cell-state-01",))
        self.assertEqual(state.evidence[0].relation, "supports")

    def test_plan_creation_validates_artifact_hypothesis_and_activates_plan(self):
        state = populated_state()
        plan = research_plan()

        state = apply_event(
            state,
            "plan_created",
            {"plan": plan.to_dict(), "activate": True},
            rationale="Create the first executable capability DAG.",
            affected_artifact_ids=("artifact-counts-01",),
            affected_hypothesis_ids=("hypothesis-lineage-shift-v1",),
            replacement_action_ids=("node-cell-state-analysis",),
        )

        self.assertEqual(state.active_plan_id, plan.id)
        self.assertEqual(state.plans, (plan,))

    def test_pending_node_cannot_jump_directly_to_completed(self):
        state = populated_state()
        plan = research_plan()
        state = apply_event(
            state,
            "plan_created",
            {"plan": plan.to_dict(), "activate": True},
            rationale="Register a pending node before exercising its transition contract.",
        )
        with self.assertRaisesRegex(ValueError, "transition"):
            apply_event(
                state,
                "node_status_changed",
                {"plan_id": plan.id, "node_id": plan.nodes[0].id, "status": "completed", "attempt": 0},
                rationale="A pending node must never become completed without observed execution and review.",
            )

    def test_refuted_hypothesis_remains_when_a_revised_hypothesis_is_added(self):
        state = ProjectState.create(project_context())
        original = hypothesis(status="refuted")
        state = apply_event(state, "hypothesis_added", {"hypothesis": original.to_dict()}, rationale="Preserve the refuted initial mechanism.")
        revised = revise_hypothesis(
            original,
            new_id="hypothesis-survival-shift-v2",
            statement="The perturbation changes apparent neuronal abundance through selective survival rather than fate transition.",
            expected_direction="change",
            status="active",
        )

        state = apply_event(
            state,
            "hypothesis_revised",
            {"hypothesis": revised.to_dict()},
            rationale="Test the survival alternative without erasing the refuted fate mechanism.",
            affected_hypothesis_ids=(original.id, revised.id),
        )

        self.assertEqual(tuple(item.status for item in state.hypotheses), ("refuted", "active"))
        self.assertEqual(state.hypotheses[1].parent_hypothesis_id, original.id)

    def test_unknown_references_unknown_events_and_sensitive_payloads_fail_closed(self):
        state = ProjectState.create(project_context())
        invalid = (
            lambda: apply_event(state, "invented_event", {}, rationale="Unknown events must fail closed."),
            lambda: apply_event(state, "artifact_registered", {"artifact": artifact(source_artifact_ids=("missing-artifact",)).to_dict()}, rationale="Unknown sources are invalid."),
            lambda: apply_event(state, "hypothesis_added", {"hypothesis": hypothesis().to_dict(), "NCBI_API_KEY": "private"}, rationale="Secrets are invalid."),
            lambda: apply_event(state, "hypothesis_added", {"hypothesis": hypothesis().to_dict(), "path": "/Users/researcher/state.json"}, rationale="Paths are invalid."),
        )
        for factory in invalid:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()
        self.assertEqual(state.revision, 0)
        self.assertEqual(state.decisions, ())


if __name__ == "__main__":
    unittest.main()
