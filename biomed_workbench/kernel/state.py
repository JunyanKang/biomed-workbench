"""Canonical project state, validated transitions, serialization, and replay."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .artifacts import ScientificArtifact
from .context import ProjectContext
from .decisions import DecisionEvent
from .evidence import EvidenceRecord, add_evidence
from .execution_receipts import (
    ArtifactReloadReceipt,
    ExecutionHandoff,
    ObservedExecutionReceipt,
    ScientificReviewReceipt,
)
from .execution_chain import (
    delivery_slice_digest,
    gate_adjudication_bundle_digest,
    validate_delivery_prerequisites,
    validate_gate_adjudication_binding,
    validate_gate_adjudication_chain,
    validate_gate_adjudication_reviewability,
    validate_gate_adjudication_retention,
    validate_node_execution_chain,
    validate_revision_target_contract,
    validate_validated_delivery_state,
)
from .hypotheses import Hypothesis, add_hypothesis, attach_evidence
from .identity import digest_value, freeze_mapping, thaw, validate_identifier
from .observed_output_protocol import (
    validate_handoff_receipt_gate_coverage,
    validate_observed_output_protocol,
)
from .plans import NODE_STATUSES, PlanNode, ResearchDAG
from .scientific_dependency import (
    AnalysisAdmission,
    ArtifactReview,
    LegacyAnalysisAdmissionRecovery,
    REEXECUTE_DECISION_ACTIONS,
    ScientificDecision,
    ScientificGateAdjudication,
)
from .scientific_evidence_map import EvidenceMapPublication


EVENT_TYPES = frozenset(
    {
        "artifact_registered",
        "hypothesis_added",
        "hypothesis_revised",
        "hypothesis_assessed",
        "evidence_added",
        "plan_created",
        "plan_revised",
        "node_status_changed",
        "node_execution_recorded",
        "execution_handoff_recorded",
        "execution_observed",
        "artifact_reloaded",
        "execution_reviewed",
        "quality_finding_recorded",
        "analysis_admission_recorded",
        "artifact_review_recorded",
        "scientific_gate_adjudicated",
        "scientific_decision_recorded",
        "evidence_map_published",
        "legacy_evidence_map_verified",
    }
)

PROJECT_STATE_SCHEMA_VERSION = 2
STATE_MIGRATION_CONTRACT_VERSION = "1.2.0"
SUPPORTED_STATE_MIGRATION_CONTRACT_VERSIONS = frozenset({"1.0.0", "1.2.0"})


@dataclass(frozen=True)
class LegacyEvidenceMapRecord:
    id: str
    publication: EvidenceMapPublication
    store_entry_digest: str
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "legacy_evidence_map.id"))
        if not isinstance(self.publication, EvidenceMapPublication):
            raise ValueError("legacy evidence map requires its exact publication")
        for field in ("store_entry_digest", "digest"):
            value = getattr(self, field)
            if not isinstance(value, str) or len(value) != 64 or set(value) - set("0123456789abcdef"):
                raise ValueError(f"legacy evidence map {field} must be SHA-256")
        basis = {
            "id": self.id,
            "publication": self.publication.to_dict(),
            "store_entry_digest": self.store_entry_digest,
        }
        if self.digest != digest_value(basis):
            raise ValueError("legacy evidence map digest is invalid")

    @classmethod
    def create(cls, publication: EvidenceMapPublication, *, store_entry_digest: str) -> "LegacyEvidenceMapRecord":
        identity = f"legacy-map-{publication.version.revision}-{publication.map_digest[:16]}"
        basis = {
            "id": identity,
            "publication": publication.to_dict(),
            "store_entry_digest": store_entry_digest,
        }
        return cls(identity, publication, store_entry_digest, digest_value(basis))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "publication": self.publication.to_dict(),
            "store_entry_digest": self.store_entry_digest,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LegacyEvidenceMapRecord":
        values = dict(payload)
        values["publication"] = EvidenceMapPublication.from_dict(values["publication"])
        return cls(**values)


@dataclass(frozen=True)
class StateMigrationRecord:
    id: str
    from_schema_version: int
    to_schema_version: int
    source_state_digest: str
    source_revision: int
    migrated_event_count: int
    contract_version: str
    digest: str
    legacy_evidence_maps: tuple[LegacyEvidenceMapRecord, ...] = ()
    legacy_analysis_admission_recoveries: tuple[LegacyAnalysisAdmissionRecovery, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "state_migration.id"))
        if (self.from_schema_version, self.to_schema_version) != (1, 2):
            raise ValueError("state migration schema transition is unsupported")
        if not isinstance(self.source_revision, int) or self.source_revision < 0:
            raise ValueError("state migration source revision is invalid")
        if (
            not isinstance(self.source_state_digest, str)
            or len(self.source_state_digest) != 64
            or set(self.source_state_digest) - set("0123456789abcdef")
        ):
            raise ValueError("state migration source digest must be SHA-256")
        if self.migrated_event_count != self.source_revision:
            raise ValueError("state migration event count must equal the source revision")
        if self.contract_version not in SUPPORTED_STATE_MIGRATION_CONTRACT_VERSIONS:
            raise ValueError("state migration contract version is unsupported")
        legacy_maps = tuple(self.legacy_evidence_maps)
        if any(not isinstance(item, LegacyEvidenceMapRecord) for item in legacy_maps):
            raise ValueError("state migration legacy evidence maps are invalid")
        if tuple(item.publication.version.revision for item in legacy_maps) != tuple(range(1, len(legacy_maps) + 1)):
            raise ValueError("state migration legacy evidence map revisions are not continuous")
        object.__setattr__(self, "legacy_evidence_maps", legacy_maps)
        recoveries = tuple(self.legacy_analysis_admission_recoveries)
        if any(not isinstance(item, LegacyAnalysisAdmissionRecovery) for item in recoveries):
            raise ValueError("state migration legacy admission recoveries are invalid")
        if len({item.plan_node_id for item in recoveries}) != len(recoveries):
            raise ValueError("state migration legacy admission recoveries duplicate plan nodes")
        if recoveries and (self.contract_version != "1.2.0" or not legacy_maps):
            raise ValueError("legacy admission recovery requires a map-bound migration contract")
        legacy_maps_by_digest = {item.publication.map_digest: item for item in legacy_maps}
        for recovery in recoveries:
            if recovery.source_state_digest != self.source_state_digest:
                raise ValueError("legacy admission recovery source state differs from its migration")
            source_map = legacy_maps_by_digest.get(recovery.source_map_digest)
            if source_map is None:
                raise ValueError("legacy admission recovery source map is not a verified migration map")
            covered = recovery.plan_node_id in source_map.publication.covered_node_ids
            if covered != (recovery.source_map_coverage_status == "covered"):
                raise ValueError("legacy admission recovery source map coverage status is inconsistent")
        object.__setattr__(self, "legacy_analysis_admission_recoveries", recoveries)
        basis = {
            "id": self.id,
            "from_schema_version": self.from_schema_version,
            "to_schema_version": self.to_schema_version,
            "source_state_digest": self.source_state_digest,
            "source_revision": self.source_revision,
            "migrated_event_count": self.migrated_event_count,
            "contract_version": self.contract_version,
        }
        if legacy_maps:
            basis["legacy_evidence_maps"] = [item.to_dict() for item in legacy_maps]
        if recoveries:
            basis["legacy_analysis_admission_recoveries"] = [item.to_dict() for item in recoveries]
        if self.digest != digest_value(basis):
            raise ValueError("state migration digest does not match its source identity")

    @classmethod
    def create(
        cls,
        *,
        source_state_digest: str,
        source_revision: int,
        legacy_evidence_maps: tuple[LegacyEvidenceMapRecord, ...] = (),
        legacy_analysis_admission_recoveries: tuple[LegacyAnalysisAdmissionRecovery, ...] = (),
    ) -> "StateMigrationRecord":
        identity = f"migration-v1-v2-{source_state_digest[:16]}"
        contract_version = "1.2.0" if legacy_analysis_admission_recoveries else "1.0.0"
        basis = {
            "id": identity,
            "from_schema_version": 1,
            "to_schema_version": 2,
            "source_state_digest": source_state_digest,
            "source_revision": source_revision,
            "migrated_event_count": source_revision,
            "contract_version": contract_version,
        }
        if legacy_evidence_maps:
            basis["legacy_evidence_maps"] = [item.to_dict() for item in legacy_evidence_maps]
        if legacy_analysis_admission_recoveries:
            basis["legacy_analysis_admission_recoveries"] = [
                item.to_dict() for item in legacy_analysis_admission_recoveries
            ]
        return cls(
            identity, 1, 2, source_state_digest, source_revision, source_revision,
            contract_version, digest_value(basis), tuple(legacy_evidence_maps),
            tuple(legacy_analysis_admission_recoveries),
        )

    def to_dict(self) -> dict[str, object]:
        payload = {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
            if field not in {"legacy_evidence_maps", "legacy_analysis_admission_recoveries"}
        }
        if self.legacy_evidence_maps:
            payload["legacy_evidence_maps"] = [item.to_dict() for item in self.legacy_evidence_maps]
        if self.legacy_analysis_admission_recoveries:
            payload["legacy_analysis_admission_recoveries"] = [
                item.to_dict() for item in self.legacy_analysis_admission_recoveries
            ]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StateMigrationRecord":
        values = dict(payload)
        values["legacy_evidence_maps"] = tuple(
            LegacyEvidenceMapRecord.from_dict(item)
            for item in values.get("legacy_evidence_maps", ())
        )
        values["legacy_analysis_admission_recoveries"] = tuple(
            LegacyAnalysisAdmissionRecovery.from_dict(item)
            for item in values.get("legacy_analysis_admission_recoveries", ())
        )
        return cls(**values)


def _state_basis(
    context: ProjectContext,
    artifacts: tuple[ScientificArtifact, ...],
    hypotheses: tuple[Hypothesis, ...],
    evidence: tuple[EvidenceRecord, ...],
    gate_adjudications: tuple[ScientificGateAdjudication, ...],
    admissions: tuple[AnalysisAdmission, ...],
    artifact_reviews: tuple[ArtifactReview, ...],
    scientific_decisions: tuple[ScientificDecision, ...],
    evidence_map_versions: tuple[EvidenceMapPublication, ...],
    execution_handoffs: tuple[ExecutionHandoff, ...],
    observed_executions: tuple[ObservedExecutionReceipt, ...],
    artifact_reloads: tuple[ArtifactReloadReceipt, ...],
    execution_reviews: tuple[ScientificReviewReceipt, ...],
    decisions: tuple[DecisionEvent, ...],
    plans: tuple[ResearchDAG, ...],
    active_plan_id: str | None,
    revision: int,
    *,
    schema_version: int = PROJECT_STATE_SCHEMA_VERSION,
    state_migrations: tuple[StateMigrationRecord, ...] = (),
) -> dict[str, object]:
    basis = {
        "schema_version": schema_version,
        "context": context.to_dict(),
        "artifacts": [item.to_dict() for item in artifacts],
        "hypotheses": [item.to_dict() for item in hypotheses],
        "evidence": [item.to_dict() for item in evidence],
        "decisions": [item.digest_basis() for item in decisions],
        "plans": [item.to_dict() for item in plans],
        "active_plan_id": active_plan_id,
        "revision": revision,
    }
    if state_migrations:
        basis["state_migrations"] = [item.to_dict() for item in state_migrations]
    if gate_adjudications:
        basis["gate_adjudications"] = [item.to_dict() for item in gate_adjudications]
    if admissions or artifact_reviews or scientific_decisions or evidence_map_versions:
        basis.update(
            {
                "analysis_admissions": [item.to_dict() for item in admissions],
                "artifact_reviews": [item.to_dict() for item in artifact_reviews],
                "scientific_decisions": [item.to_dict() for item in scientific_decisions],
                "evidence_map_versions": [item.to_dict() for item in evidence_map_versions],
            }
        )
    if execution_handoffs or observed_executions or artifact_reloads or execution_reviews:
        basis.update(
            {
                "execution_handoffs": [item.to_dict() for item in execution_handoffs],
                "observed_executions": [item.to_dict() for item in observed_executions],
                "artifact_reloads": [item.to_dict() for item in artifact_reloads],
                "execution_reviews": [item.to_dict() for item in execution_reviews],
            }
        )
    return basis


@dataclass(frozen=True)
class ProjectState:
    schema_version: int
    context: ProjectContext
    artifacts: tuple[ScientificArtifact, ...]
    hypotheses: tuple[Hypothesis, ...]
    evidence: tuple[EvidenceRecord, ...]
    gate_adjudications: tuple[ScientificGateAdjudication, ...]
    analysis_admissions: tuple[AnalysisAdmission, ...]
    artifact_reviews: tuple[ArtifactReview, ...]
    scientific_decisions: tuple[ScientificDecision, ...]
    evidence_map_versions: tuple[EvidenceMapPublication, ...]
    execution_handoffs: tuple[ExecutionHandoff, ...]
    observed_executions: tuple[ObservedExecutionReceipt, ...]
    artifact_reloads: tuple[ArtifactReloadReceipt, ...]
    execution_reviews: tuple[ScientificReviewReceipt, ...]
    state_migrations: tuple[StateMigrationRecord, ...]
    decisions: tuple[DecisionEvent, ...]
    plans: tuple[ResearchDAG, ...]
    active_plan_id: str | None
    revision: int
    state_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != PROJECT_STATE_SCHEMA_VERSION or not isinstance(self.context, ProjectContext):
            raise ValueError("project state schema or context is invalid")
        for field, expected in (
            ("artifacts", ScientificArtifact),
            ("hypotheses", Hypothesis),
            ("evidence", EvidenceRecord),
            ("gate_adjudications", ScientificGateAdjudication),
            ("analysis_admissions", AnalysisAdmission),
            ("artifact_reviews", ArtifactReview),
            ("scientific_decisions", ScientificDecision),
            ("evidence_map_versions", EvidenceMapPublication),
            ("execution_handoffs", ExecutionHandoff),
            ("observed_executions", ObservedExecutionReceipt),
            ("artifact_reloads", ArtifactReloadReceipt),
            ("execution_reviews", ScientificReviewReceipt),
            ("state_migrations", StateMigrationRecord),
            ("decisions", DecisionEvent),
            ("plans", ResearchDAG),
        ):
            values = tuple(getattr(self, field))
            if any(not isinstance(item, expected) for item in values) or len({item.id for item in values}) != len(values):
                raise ValueError(f"project state {field} must be valid and uniquely identified")
            object.__setattr__(self, field, values)
        if not isinstance(self.revision, int) or self.revision < 0 or self.revision != len(self.decisions):
            raise ValueError("project state revision must equal its event count")
        if tuple(event.sequence for event in self.decisions) != tuple(range(1, self.revision + 1)):
            raise ValueError("project state event sequences must be monotonic")
        artifact_ids = {item.id for item in self.artifacts}
        hypothesis_ids = {item.id for item in self.hypotheses}
        plan_ids = {item.id for item in self.plans}
        plan_nodes = {node.id: node for plan in self.plans for node in plan.nodes}
        for migration in self.state_migrations:
            if self.revision < migration.source_revision:
                continue
            for recovery in migration.legacy_analysis_admission_recoveries:
                node = plan_nodes.get(recovery.plan_node_id)
                if node is None:
                    raise ValueError("legacy admission recovery references an unknown migrated plan node")
                if (
                    recovery.hypothesis_ids != node.target_hypothesis_ids
                    or recovery.expected_artifact_types != node.expected_output_artifact_types
                ):
                    raise ValueError("legacy admission recovery differs from its migrated plan-node contract")
        if any(not set(item.source_artifact_ids) <= artifact_ids for item in self.artifacts):
            raise ValueError("artifact lineage references unknown inputs")
        if any(item.parent_hypothesis_id is not None and item.parent_hypothesis_id not in hypothesis_ids for item in self.hypotheses):
            raise ValueError("hypothesis lineage references an unknown parent")
        if any(item.artifact_id not in artifact_ids or item.hypothesis_id not in hypothesis_ids for item in self.evidence):
            raise ValueError("evidence references unknown state objects")
        if self.active_plan_id is not None and self.active_plan_id not in plan_ids:
            raise ValueError("active plan is not present in project state")
        if any(item.plan_node_id not in plan_nodes or not set(item.hypothesis_ids) <= hypothesis_ids for item in self.analysis_admissions):
            raise ValueError("analysis admission references unknown plan or hypothesis objects")
        if len({item.plan_node_id for item in self.analysis_admissions}) != len(self.analysis_admissions):
            raise ValueError("each plan node may have only one analysis admission")
        if any(item.artifact_id not in artifact_ids for item in self.artifact_reviews):
            raise ValueError("artifact review references an unknown artifact")
        for item in self.gate_adjudications:
            if item.artifact_id not in artifact_ids:
                raise ValueError("gate adjudication references an unknown artifact")
            validate_gate_adjudication_binding(self, item)
        if len({(item.artifact_id, item.gate_id) for item in self.gate_adjudications}) != len(self.gate_adjudications):
            raise ValueError("each artifact gate may have only one scientific adjudication")
        review_by_id = {item.id: item for item in self.artifact_reviews}
        if len({item.artifact_id for item in self.artifact_reviews}) != len(self.artifact_reviews):
            raise ValueError("each artifact may have only one scientific review")
        for item in self.scientific_decisions:
            review = review_by_id.get(item.review_id)
            if review is None or review.artifact_id != item.artifact_id or not set(item.hypothesis_ids) <= hypothesis_ids:
                raise ValueError("scientific decision references an unknown or mismatched review")
            if not set(item.next_plan_node_ids) <= set(plan_nodes):
                raise ValueError("scientific decision references an unknown next plan node")
            if not set(item.next_hypothesis_ids) <= hypothesis_ids:
                raise ValueError("scientific decision references an unknown revised hypothesis")
            if item.action == "revise-hypothesis" and any(
                next(
                    value for value in self.hypotheses if value.id == revised_id
                ).parent_hypothesis_id not in item.hypothesis_ids
                for revised_id in item.next_hypothesis_ids
            ):
                raise ValueError("revise-hypothesis decision must bind a registered child hypothesis")
            if item.action in REEXECUTE_DECISION_ACTIONS:
                validate_revision_target_contract(self, item)
            if item.active_evidence and review.overall_status in {"major", "fatal", "unassessed"}:
                raise ValueError("blocking or unassessed artifacts cannot become active evidence")
            validate_gate_adjudication_chain(self, item.artifact_id)
        if len({item.artifact_id for item in self.scientific_decisions}) != len(self.scientific_decisions):
            raise ValueError("each artifact may have only one scientific decision")
        handoffs = {item.id: item for item in self.execution_handoffs}
        for item in self.execution_handoffs:
            validate_observed_output_protocol(item.protocol)
        if any(
            item.plan_node_id not in plan_nodes
            or plan_nodes[item.plan_node_id].module_id != item.module_id
            for item in self.execution_handoffs
        ):
            raise ValueError("execution handoff references an unknown or mismatched plan node")
        observed = {item.id: item for item in self.observed_executions}
        for item in self.observed_executions:
            node = plan_nodes.get(item.plan_node_id)
            if node is None or node.module_id != item.module_id:
                raise ValueError("observed execution references an unknown or mismatched plan node")
            if item.source_kind == "handoff":
                handoff = handoffs.get(item.handoff_id or "")
                if (
                    handoff is None
                    or handoff.plan_node_id != item.plan_node_id
                    or handoff.module_id != item.module_id
                    or handoff.module_version != item.module_version
                    or handoff.compatibility_row_id != item.compatibility_row_id
                    or handoff.request_digest != item.parameters_digest
                    or digest_value(handoff.to_dict()) != item.execution_request_digest
                    or set(handoff.planned_output_artifact_ids.values()) != set(item.output_artifact_digests)
                ):
                    raise ValueError("observed execution receipt chain differs from its handoff")
                validate_handoff_receipt_gate_coverage(handoff, item)
        reloads = {item.id: item for item in self.artifact_reloads}
        for item in self.artifact_reloads:
            execution = observed.get(item.observed_execution_receipt_id)
            artifact = next((value for value in self.artifacts if value.id == item.artifact_id), None)
            if (
                execution is None
                or artifact is None
                or item.artifact_id not in execution.output_artifact_digests
                or execution.output_artifact_digests[item.artifact_id] != item.content_digest
                or artifact.content_digest != item.content_digest
                or artifact.producing_module_id != execution.module_id
                or artifact.producing_module_version != execution.module_version
            ):
                raise ValueError("artifact reload receipt chain is incomplete or mismatched")
        for item in self.execution_reviews:
            execution = observed.get(item.observed_execution_receipt_id)
            linked = tuple(reloads.get(value) for value in item.artifact_reload_receipt_ids)
            if (
                execution is None
                or execution.plan_node_id != item.plan_node_id
                or any(value is None for value in linked)
                or {value.observed_execution_receipt_id for value in linked if value is not None} != {execution.id}
                or {value.artifact_id for value in linked if value is not None} != set(execution.output_artifact_digests)
            ):
                raise ValueError("execution integrity review does not cover one complete observed execution")
        legacy_maps = tuple(
            item
            for migration in self.state_migrations
            for item in migration.legacy_evidence_maps
        )
        first_revision = len(legacy_maps) + 1
        if tuple(item.version.revision for item in self.evidence_map_versions) != tuple(
            range(first_revision, first_revision + len(self.evidence_map_versions))
        ):
            raise ValueError("evidence map publications must have continuous revisions")
        if self.evidence_map_versions and legacy_maps and (
            self.evidence_map_versions[0].version.parent_map_digest
            != legacy_maps[-1].publication.map_digest
        ):
            raise ValueError("republished evidence map does not continue the verified legacy map chain")
        expected = digest_value(
            _state_basis(
                self.context,
                self.artifacts,
                self.hypotheses,
                self.evidence,
                self.gate_adjudications,
                self.analysis_admissions,
                self.artifact_reviews,
                self.scientific_decisions,
                self.evidence_map_versions,
                self.execution_handoffs,
                self.observed_executions,
                self.artifact_reloads,
                self.execution_reviews,
                self.decisions,
                self.plans,
                self.active_plan_id,
                self.revision,
                schema_version=self.schema_version,
                state_migrations=self.state_migrations,
            )
        )
        if self.state_digest != expected:
            raise ValueError("project state digest does not match canonical state")
        if self.decisions and self.decisions[-1].resulting_state_digest != self.state_digest:
            raise ValueError("latest decision does not resolve to the project state digest")

    @classmethod
    def create(
        cls,
        context: ProjectContext,
        *,
        state_migrations: tuple[StateMigrationRecord, ...] = (),
    ) -> "ProjectState":
        basis = _state_basis(
            context, (), (), (), (), (), (), (), (), (), (), (), (), (), (), None, 0,
            state_migrations=state_migrations,
        )
        return cls(
            schema_version=PROJECT_STATE_SCHEMA_VERSION, context=context, artifacts=(), hypotheses=(), evidence=(),
            gate_adjudications=(), analysis_admissions=(), artifact_reviews=(),
            scientific_decisions=(), evidence_map_versions=(), execution_handoffs=(),
            observed_executions=(), artifact_reloads=(), execution_reviews=(),
            state_migrations=state_migrations, decisions=(),
            plans=(), active_plan_id=None, revision=0, state_digest=digest_value(basis),
        )

    def to_dict(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "context": self.context.to_dict(),
            "artifacts": [item.to_dict() for item in self.artifacts],
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "evidence": [item.to_dict() for item in self.evidence],
            "analysis_admissions": [item.to_dict() for item in self.analysis_admissions],
            "artifact_reviews": [item.to_dict() for item in self.artifact_reviews],
            "scientific_decisions": [item.to_dict() for item in self.scientific_decisions],
            "evidence_map_versions": [item.to_dict() for item in self.evidence_map_versions],
            "execution_handoffs": [item.to_dict() for item in self.execution_handoffs],
            "observed_executions": [item.to_dict() for item in self.observed_executions],
            "artifact_reloads": [item.to_dict() for item in self.artifact_reloads],
            "execution_reviews": [item.to_dict() for item in self.execution_reviews],
            "state_migrations": [item.to_dict() for item in self.state_migrations],
            "decisions": [item.to_dict() for item in self.decisions],
            "plans": [item.to_dict() for item in self.plans],
            "active_plan_id": self.active_plan_id,
            "revision": self.revision,
            "state_digest": self.state_digest,
        }
        if self.gate_adjudications:
            payload["gate_adjudications"] = [item.to_dict() for item in self.gate_adjudications]
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProjectState":
        if payload.get("schema_version") == 1:
            return _migrate_v1_project_state(payload)
        receipt_fields = {"execution_handoffs", "observed_executions", "artifact_reloads", "execution_reviews"}
        expected_fields = {"schema_version", "context", "artifacts", "hypotheses", "evidence", "gate_adjudications", "analysis_admissions", "artifact_reviews", "scientific_decisions", "evidence_map_versions", *receipt_fields, "state_migrations", "decisions", "plans", "active_plan_id", "revision", "state_digest"}
        pre_gate_fields = expected_fields - {"gate_adjudications"}
        pre_receipt_fields = pre_gate_fields - receipt_fields
        legacy_fields = pre_receipt_fields - {"analysis_admissions", "artifact_reviews", "scientific_decisions", "evidence_map_versions"}
        if frozenset(payload) not in {frozenset(expected_fields), frozenset(pre_gate_fields), frozenset(pre_receipt_fields), frozenset(legacy_fields)}:
            raise ValueError("project state uses an unsupported serialized field set")
        normalized = dict(payload)
        for field in ("gate_adjudications", "analysis_admissions", "artifact_reviews", "scientific_decisions", "evidence_map_versions", *sorted(receipt_fields)):
            normalized.setdefault(field, [])
        state = cls(
            schema_version=normalized["schema_version"],
            context=ProjectContext.from_dict(normalized["context"]),
            artifacts=tuple(ScientificArtifact.from_dict(item) for item in normalized["artifacts"]),
            hypotheses=tuple(Hypothesis.from_dict(item) for item in normalized["hypotheses"]),
            evidence=tuple(EvidenceRecord.from_dict(item) for item in normalized["evidence"]),
            gate_adjudications=tuple(ScientificGateAdjudication.from_dict(item) for item in normalized["gate_adjudications"]),
            analysis_admissions=tuple(AnalysisAdmission.from_dict(item) for item in normalized["analysis_admissions"]),
            artifact_reviews=tuple(ArtifactReview.from_dict(item) for item in normalized["artifact_reviews"]),
            scientific_decisions=tuple(ScientificDecision.from_dict(item) for item in normalized["scientific_decisions"]),
            evidence_map_versions=tuple(EvidenceMapPublication.from_dict(item) for item in normalized["evidence_map_versions"]),
            execution_handoffs=tuple(ExecutionHandoff.from_dict(item) for item in normalized["execution_handoffs"]),
            observed_executions=tuple(ObservedExecutionReceipt.from_dict(item) for item in normalized["observed_executions"]),
            artifact_reloads=tuple(ArtifactReloadReceipt.from_dict(item) for item in normalized["artifact_reloads"]),
            execution_reviews=tuple(ScientificReviewReceipt.from_dict(item) for item in normalized["execution_reviews"]),
            state_migrations=tuple(StateMigrationRecord.from_dict(item) for item in normalized["state_migrations"]),
            decisions=tuple(DecisionEvent.from_dict(item) for item in normalized["decisions"]),
            plans=tuple(ResearchDAG.from_dict(item) for item in normalized["plans"]),
            active_plan_id=normalized["active_plan_id"],
            revision=normalized["revision"],
            state_digest=normalized["state_digest"],
        )
        if replay(state.context, state.decisions, state_migrations=state.state_migrations).to_dict() != state.to_dict():
            raise ValueError("serialized project state does not match event replay")
        return state


def _legacy_v1_basis(payload: Mapping[str, Any]) -> dict[str, object]:
    decisions = []
    for event in payload.get("decisions", []):
        basis = dict(event)
        basis.pop("resulting_state_digest", None)
        decisions.append(basis)
    basis: dict[str, object] = {
        "schema_version": 1,
        "context": payload["context"],
        "artifacts": payload.get("artifacts", []),
        "hypotheses": payload.get("hypotheses", []),
        "evidence": payload.get("evidence", []),
        "decisions": decisions,
        "plans": payload.get("plans", []),
        "active_plan_id": payload.get("active_plan_id"),
        "revision": payload.get("revision", 0),
    }
    if payload.get("gate_adjudications"):
        basis["gate_adjudications"] = payload["gate_adjudications"]
    if any(payload.get(field) for field in (
        "analysis_admissions", "artifact_reviews", "scientific_decisions", "evidence_map_versions"
    )):
        basis.update({
            "analysis_admissions": payload.get("analysis_admissions", []),
            "artifact_reviews": payload.get("artifact_reviews", []),
            "scientific_decisions": payload.get("scientific_decisions", []),
            "evidence_map_versions": payload.get("evidence_map_versions", []),
        })
    if any(payload.get(field) for field in (
        "execution_handoffs", "observed_executions", "artifact_reloads", "execution_reviews"
    )):
        basis.update({
            "execution_handoffs": payload.get("execution_handoffs", []),
            "observed_executions": payload.get("observed_executions", []),
            "artifact_reloads": payload.get("artifact_reloads", []),
            "execution_reviews": payload.get("execution_reviews", []),
        })
    return basis


def _validate_legacy_v1_envelope(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        raise ValueError("legacy migration requires project state schema v1")
    receipt_fields = {"execution_handoffs", "observed_executions", "artifact_reloads", "execution_reviews"}
    expected_fields = {
        "schema_version", "context", "artifacts", "hypotheses", "evidence",
        "gate_adjudications", "analysis_admissions", "artifact_reviews",
        "scientific_decisions", "evidence_map_versions", *receipt_fields,
        "decisions", "plans", "active_plan_id", "revision", "state_digest",
    }
    supported = {
        frozenset(expected_fields),
        frozenset(expected_fields - {"gate_adjudications"}),
        frozenset(expected_fields - {"gate_adjudications"} - receipt_fields),
        frozenset(
            expected_fields
            - {"gate_adjudications"}
            - receipt_fields
            - {"analysis_admissions", "artifact_reviews", "scientific_decisions", "evidence_map_versions"}
        ),
    }
    if frozenset(payload) not in supported:
        raise ValueError("legacy v1 project state uses an unsupported serialized field set")
    source_digest = payload.get("state_digest")
    if source_digest != digest_value(_legacy_v1_basis(payload)):
        raise ValueError("legacy v1 project state digest is invalid")
    decisions = payload.get("decisions", [])
    revision = payload.get("revision")
    if not isinstance(decisions, list) or revision != len(decisions):
        raise ValueError("legacy v1 event count is inconsistent")
    empty = {
        "schema_version": 1,
        "context": payload["context"],
        "artifacts": [],
        "hypotheses": [],
        "evidence": [],
        "decisions": [],
        "plans": [],
        "active_plan_id": None,
        "revision": 0,
    }
    expected_prior = digest_value(empty)
    for sequence, event in enumerate(decisions, start=1):
        if event.get("sequence") != sequence or event.get("prior_state_digest") != expected_prior:
            raise ValueError("legacy v1 event chain is broken")
        identity_basis = {
            "sequence": sequence,
            "event_type": event.get("event_type"),
            "payload": event.get("payload"),
            "prior_state_digest": expected_prior,
        }
        expected_id = f"event-{sequence:06d}-{digest_value(identity_basis)[:12]}"
        if event.get("id") != expected_id:
            raise ValueError("legacy v1 event identity is invalid")
        expected_prior = event.get("resulting_state_digest")
    if expected_prior != source_digest:
        raise ValueError("legacy v1 event chain does not terminate at its state digest")


def _migrate_v1_adjudication(
    payload: Mapping[str, Any],
    observed_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, object]:
    values = dict(payload)
    structured_fields = {"adjudication_mode", "observed_value", "criterion", "finding"}
    present = structured_fields & set(values)
    if present and present != structured_fields:
        raise ValueError("legacy v1 gate adjudication has only a partial structured binding")
    if not present:
        observed = observed_by_id.get(str(values.get("observed_execution_receipt_id")))
        gate_id = str(values.get("gate_id"))
        result = (observed or {}).get("postflight_results", {}).get(gate_id)
        evaluations = result.get("evaluations", []) if isinstance(result, Mapping) else []
        evaluation = next(
            (
                item for item in evaluations
                if isinstance(item, Mapping) and item.get("port") == values.get("port")
            ),
            None,
        )
        result_digest = (observed or {}).get("postflight_result_digests", {}).get(gate_id)
        if (
            evaluation is None
            or result_digest != values.get("gate_result_digest")
            or evaluation.get("evaluator_type") != values.get("evaluator_type")
            or evaluation.get("evidence_payload_sha256") != values.get("evidence_payload_sha256")
        ):
            raise ValueError(
                f"legacy v1 gate adjudication cannot recover an exact observed binding: {values.get('id')}"
            )
        values.update({
            "adjudication_mode": "manual",
            "observed_value": str(evaluation.get("observed_metric")),
            "criterion": str(evaluation.get("threshold")),
            "finding": str(evaluation.get("reason")),
        })
    values.setdefault("evaluator_identity", None)
    values.setdefault("evaluator_version", None)
    values.setdefault("evaluator_sha256", None)
    return values


def _migrate_v1_project_state(
    payload: Mapping[str, Any],
    *,
    verified_legacy_maps: tuple[LegacyEvidenceMapRecord, ...] = (),
) -> ProjectState:
    """Migrate a digest-valid v1 event log and recover exact gate bindings from its receipt."""
    _validate_legacy_v1_envelope(payload)
    if payload.get("evidence_map_versions") and not verified_legacy_maps:
        raise ValueError(
            "legacy v1 state with a published evidence map requires explicit map republication after migration"
        )
    legacy_publications = tuple(
        EvidenceMapPublication.from_dict(item) for item in payload.get("evidence_map_versions", [])
    )
    if legacy_publications != tuple(item.publication for item in verified_legacy_maps):
        raise ValueError("verified legacy evidence maps differ from the v1 project state")
    observed_by_id = {
        str(item["id"]): item for item in payload.get("observed_executions", [])
    }
    migrated_adjudications = {
        str(item["id"]): _migrate_v1_adjudication(item, observed_by_id)
        for item in payload.get("gate_adjudications", [])
    }
    legacy_admitted_node_ids = {
        str(item["plan_node_id"]) for item in payload.get("analysis_admissions", [])
    }
    admission_recoveries: tuple[LegacyAnalysisAdmissionRecovery, ...] = ()
    if verified_legacy_maps:
        recovered: list[LegacyAnalysisAdmissionRecovery] = []
        source_map = verified_legacy_maps[-1].publication
        for plan_payload in payload.get("plans", []):
            plan = ResearchDAG.from_dict(plan_payload)
            for node in plan.nodes:
                if node.id not in legacy_admitted_node_ids:
                    recovered.append(
                        LegacyAnalysisAdmissionRecovery.create(
                            plan_node_id=node.id,
                            hypothesis_ids=node.target_hypothesis_ids,
                            expected_artifact_types=node.expected_output_artifact_types,
                            source_state_digest=str(payload["state_digest"]),
                            source_map_digest=source_map.map_digest,
                            source_map_coverage_status=(
                                "covered" if node.id in source_map.covered_node_ids else "not-covered"
                            ),
                        )
                    )
        admission_recoveries = tuple(sorted(recovered, key=lambda item: item.plan_node_id))
    migration = StateMigrationRecord.create(
        source_state_digest=str(payload["state_digest"]),
        source_revision=int(payload["revision"]),
        legacy_evidence_maps=verified_legacy_maps,
        legacy_analysis_admission_recoveries=admission_recoveries,
    )
    state = ProjectState.create(
        ProjectContext.from_dict(payload["context"]),
        state_migrations=(migration,),
    )
    migrated_decisions: dict[str, dict[str, object]] = {}
    for raw_event in payload.get("decisions", []):
        event = DecisionEvent.from_dict(raw_event)
        event_payload = thaw(event.payload)
        if event.event_type == "scientific_gate_adjudicated":
            adjudication_id = str(event_payload.get("adjudication", {}).get("id"))
            if adjudication_id not in migrated_adjudications:
                raise ValueError("legacy v1 adjudication event has no matching top-level record")
            event_payload = {"adjudication": migrated_adjudications[adjudication_id]}
        elif event.event_type == "scientific_decision_recorded":
            decision_payload = dict(event_payload["decision"])
            if decision_payload.get("gate_adjudication_digest") is not None:
                decision_payload["gate_adjudication_digest"] = gate_adjudication_bundle_digest(
                    state,
                    str(decision_payload["artifact_id"]),
                )
            event_payload = {"decision": decision_payload}
            migrated_decisions[str(decision_payload["id"])] = decision_payload
        elif event.event_type == "evidence_map_published":
            publication = EvidenceMapPublication.from_dict(event_payload["publication"])
            record = next(
                (item for item in verified_legacy_maps if item.publication == publication),
                None,
            )
            if record is None:
                raise ValueError("legacy v1 evidence-map event lacks a verified immutable publication")
            event_payload = {"legacy_evidence_map_record_id": record.id}
            event = replace(event, event_type="legacy_evidence_map_verified")
        state = apply_event(
            state,
            event.event_type,
            event_payload,
            rationale=event.rationale,
            trigger_finding_ids=event.trigger_finding_ids,
            affected_artifact_ids=event.affected_artifact_ids,
            affected_hypothesis_ids=event.affected_hypothesis_ids,
            superseded_action_ids=event.superseded_action_ids,
            replacement_action_ids=event.replacement_action_ids,
            prior_results_valid=event.prior_results_valid,
        )
    expected = dict(payload)
    expected["gate_adjudications"] = list(migrated_adjudications.values())
    expected["scientific_decisions"] = [
        migrated_decisions.get(str(item["id"]), dict(item))
        for item in payload.get("scientific_decisions", [])
    ]
    actual = state.to_dict()
    for field in (
        "context", "artifacts", "hypotheses", "evidence", "gate_adjudications",
        "analysis_admissions", "artifact_reviews", "scientific_decisions",
        "execution_handoffs", "observed_executions", "artifact_reloads",
        "execution_reviews", "plans", "active_plan_id", "revision",
    ):
        if actual.get(field, []) != expected.get(field, []):
            raise ValueError(f"legacy v1 migration replay differs from serialized state field: {field}")
    return state


def migrate_v1_project_state_with_verified_maps(
    payload: Mapping[str, Any],
    records: tuple[LegacyEvidenceMapRecord, ...],
) -> ProjectState:
    """Public migration entry after an external immutable-store verification."""
    return _migrate_v1_project_state(payload, verified_legacy_maps=records)


def _apply_payload(state: ProjectState, event_type: str, payload: Mapping[str, Any]):
    artifacts, hypotheses, evidence = state.artifacts, state.hypotheses, state.evidence
    gate_adjudications = state.gate_adjudications
    admissions, reviews = state.analysis_admissions, state.artifact_reviews
    scientific_decisions, evidence_map_versions = state.scientific_decisions, state.evidence_map_versions
    execution_handoffs, observed_executions = state.execution_handoffs, state.observed_executions
    artifact_reloads, execution_reviews = state.artifact_reloads, state.execution_reviews
    plans, active_plan_id = state.plans, state.active_plan_id
    if event_type == "artifact_registered":
        if set(payload) != {"artifact"}:
            raise ValueError("artifact_registered payload must contain exactly artifact")
        item = ScientificArtifact.from_dict(payload["artifact"])
        if item.id in {value.id for value in artifacts} or not set(item.source_artifact_ids) <= {value.id for value in artifacts}:
            raise ValueError("artifact registration has duplicate or unknown lineage")
        artifacts = (*artifacts, item)
    elif event_type in {"hypothesis_added", "hypothesis_revised"}:
        if set(payload) != {"hypothesis"}:
            raise ValueError(f"{event_type} payload must contain exactly hypothesis")
        item = Hypothesis.from_dict(payload["hypothesis"])
        if event_type == "hypothesis_added" and item.parent_hypothesis_id is not None:
            raise ValueError("hypothesis_added cannot introduce a revision")
        if event_type == "hypothesis_revised" and item.parent_hypothesis_id is None:
            raise ValueError("hypothesis_revised requires a parent")
        hypotheses = add_hypothesis(hypotheses, item)
    elif event_type == "evidence_added":
        if set(payload) != {"evidence"}:
            raise ValueError("evidence_added payload must contain exactly evidence")
        item = EvidenceRecord.from_dict(payload["evidence"])
        if item.artifact_id not in {value.id for value in artifacts} or item.hypothesis_id not in {value.id for value in hypotheses}:
            raise ValueError("evidence references unknown state objects")
        evidence = add_evidence(evidence, item)
        hypotheses = tuple(attach_evidence(value, item) if value.id == item.hypothesis_id else value for value in hypotheses)
    elif event_type in {"plan_created", "plan_revised"}:
        if set(payload) != {"plan", "activate"} or not isinstance(payload["activate"], bool):
            raise ValueError(f"{event_type} payload must contain exactly plan and boolean activate")
        item = ResearchDAG.from_dict(payload["plan"])
        if item.id in {value.id for value in plans}:
            raise ValueError("plan ID already exists")
        if event_type == "plan_created" and item.parent_plan_id is not None:
            raise ValueError("plan_created cannot introduce a revision")
        if event_type == "plan_revised" and (item.parent_plan_id is None or item.parent_plan_id not in {value.id for value in plans}):
            raise ValueError("plan_revised requires a known parent")
        artifact_ids = {value.id for value in artifacts}
        hypothesis_ids = {value.id for value in hypotheses}
        output_owner = {artifact_id: node.id for node in item.nodes for artifact_id in node.planned_output_artifact_ids.values()}
        inherited_output_ids: set[str] = set()
        if event_type == "plan_revised":
            parent = next(value for value in plans if value.id == item.parent_plan_id)
            parent_nodes = {node.id: node for node in parent.nodes}
            for node in item.nodes:
                previous = parent_nodes.get(node.id)
                if set(node.planned_output_artifact_ids.values()) & artifact_ids:
                    reviewed_outputs = set(node.planned_output_artifact_ids.values()) <= {
                        value.artifact_id for value in reviews
                    }
                    undecided_outputs = not set(node.planned_output_artifact_ids.values()) & {
                        value.artifact_id for value in scientific_decisions
                    }
                    if (
                        previous is None
                        or node != previous
                        or not (
                            node.status == "completed"
                            or (node.status == "awaiting_review" and reviewed_outputs and undecided_outputs)
                        )
                    ):
                        raise ValueError(
                            "revised plans may inherit only unchanged completed nodes or reviewed undecided sources"
                        )
                    validate_node_execution_chain(
                        state,
                        node.id,
                        require_completed_node=node.status == "completed",
                        require_active_decisions=False,
                    )
                    inherited_output_ids.update(node.planned_output_artifact_ids.values())
        if (set(output_owner) & artifact_ids) - inherited_output_ids:
            raise ValueError("planned outputs cannot overwrite registered artifacts")
        for node in item.nodes:
            if not set(node.target_hypothesis_ids) <= hypothesis_ids:
                raise ValueError("plan nodes reference unknown hypotheses")
            for artifact_id in node.input_bindings.values():
                if artifact_id in artifact_ids:
                    continue
                owner = output_owner.get(artifact_id)
                if owner is None or owner not in node.dependencies:
                    raise ValueError("plan nodes reference unknown artifacts or undeclared producer dependencies")
        plans = (*plans, item)
        if payload["activate"]:
            active_plan_id = item.id
    elif event_type == "node_status_changed":
        if set(payload) != {"plan_id", "node_id", "status", "attempt"} or payload["status"] not in NODE_STATUSES:
            raise ValueError("node_status_changed payload is invalid")
        if not isinstance(payload["attempt"], int) or payload["attempt"] < 0:
            raise ValueError("node status attempt must be nonnegative")
        plan_index = next((index for index, value in enumerate(plans) if value.id == payload["plan_id"]), None)
        if plan_index is None:
            raise ValueError("node status references an unknown plan")
        plan = plans[plan_index]
        current_node = next((node for node in plan.nodes if node.id == payload["node_id"]), None)
        if current_node is None:
            raise ValueError("node status references an unknown node")
        transitions = {
            "pending": {"ready", "running", "blocked", "skipped", "superseded"},
            "ready": {"running", "blocked", "skipped", "superseded"},
            "running": {"pending", "awaiting_observed_execution", "awaiting_review", "completed", "blocked", "failed"},
            "prepared": {"awaiting_observed_execution", "blocked", "failed"},
            "awaiting_observed_execution": {"awaiting_review", "blocked", "failed"},
            "awaiting_review": {"completed", "pending", "skipped", "blocked", "failed", "superseded"},
            "blocked": {"pending", "superseded", "skipped"},
            "failed": {"pending", "superseded", "skipped"},
            "completed": set(),
            "skipped": set(),
            "superseded": set(),
        }
        if payload["status"] != current_node.status and payload["status"] not in transitions[current_node.status]:
            raise ValueError(f"invalid plan-node status transition: {current_node.status} -> {payload['status']}")
        if payload["status"] == "running" and payload["attempt"] != current_node.attempt + 1:
            raise ValueError("running transition must increment the node attempt exactly once")
        if payload["status"] != "running" and payload["attempt"] != current_node.attempt:
            raise ValueError("non-running transition cannot change the node attempt")
        if current_node.status == "awaiting_review" and payload["status"] == "completed":
            validate_node_execution_chain(
                state,
                current_node.id,
                require_completed_node=False,
                require_active_decisions=True,
            )
        nodes = tuple(
            replace(node, status=payload["status"], attempt=payload["attempt"])
            if node.id == payload["node_id"]
            else node
            for node in plan.nodes
        )
        updated = ResearchDAG.create(
            id=plan.id,
            objective=plan.objective,
            nodes=nodes,
            required_output_artifact_types=plan.required_output_artifact_types,
            plan_type=plan.plan_type,
            revision=plan.revision,
            parent_plan_id=plan.parent_plan_id,
            rationale=plan.rationale,
        )
        plans = tuple(updated if index == plan_index else value for index, value in enumerate(plans))
    elif event_type == "hypothesis_assessed":
        if set(payload) != {"hypothesis_id", "status"}:
            raise ValueError("hypothesis_assessed payload is invalid")
        if payload["hypothesis_id"] not in {item.id for item in hypotheses}:
            raise ValueError("hypothesis assessment references an unknown hypothesis")
        hypotheses = tuple(replace(item, status=payload["status"]) if item.id == payload["hypothesis_id"] else item for item in hypotheses)
    elif event_type == "node_execution_recorded":
        if set(payload) != {"execution"} or not isinstance(payload["execution"], dict):
            raise ValueError("node_execution_recorded payload is invalid")
        if payload["execution"].get("node_id") not in {node.id for plan in plans for node in plan.nodes}:
            raise ValueError("node execution references an unknown plan node")
    elif event_type == "execution_handoff_recorded":
        if set(payload) != {"handoff"}:
            raise ValueError("execution_handoff_recorded payload is invalid")
        item = ExecutionHandoff.from_dict(payload["handoff"])
        validate_observed_output_protocol(item.protocol)
        plan_node = next((node for plan in plans for node in plan.nodes if node.id == item.plan_node_id), None)
        if (
            plan_node is None
            or plan_node.module_id != item.module_id
            or item.id in {value.id for value in execution_handoffs}
            or item.plan_node_id in {value.plan_node_id for value in execution_handoffs}
            or set(item.planned_output_artifact_ids.values()) != set(plan_node.planned_output_artifact_ids.values())
            or item.compatibility_row_id not in plan_node.compatibility_row_candidates
        ):
            raise ValueError("execution handoff is duplicate or differs from its plan node")
        execution_handoffs = (*execution_handoffs, item)
    elif event_type == "execution_observed":
        if set(payload) != {"receipt"}:
            raise ValueError("execution_observed payload is invalid")
        item = ObservedExecutionReceipt.from_dict(payload["receipt"])
        plan_node = next((node for plan in plans for node in plan.nodes if node.id == item.plan_node_id), None)
        handoff = next((value for value in execution_handoffs if value.id == item.handoff_id), None)
        if (
            plan_node is None
            or plan_node.module_id != item.module_id
            or item.id in {value.id for value in observed_executions}
            or item.plan_node_id in {value.plan_node_id for value in observed_executions}
            or set(item.output_artifact_digests) != set(plan_node.planned_output_artifact_ids.values())
            or item.compatibility_row_id not in plan_node.compatibility_row_candidates
            or (item.source_kind == "handoff" and item.handoff_id not in {value.id for value in execution_handoffs})
        ):
            raise ValueError("observed execution is duplicate or differs from its plan and handoff")
        if item.source_kind == "handoff" and handoff is not None:
            validate_handoff_receipt_gate_coverage(handoff, item)
        observed_executions = (*observed_executions, item)
    elif event_type == "artifact_reloaded":
        if set(payload) != {"receipt", "artifact"}:
            raise ValueError("artifact_reloaded payload is invalid")
        receipt = ArtifactReloadReceipt.from_dict(payload["receipt"])
        artifact = ScientificArtifact.from_dict(payload["artifact"])
        observed = next((value for value in observed_executions if value.id == receipt.observed_execution_receipt_id), None)
        if (
            observed is None
            or artifact.id != receipt.artifact_id
            or artifact.id in {value.id for value in artifacts}
            or receipt.id in {value.id for value in artifact_reloads}
            or not set(artifact.source_artifact_ids) <= {value.id for value in artifacts}
            or artifact.producing_module_id != observed.module_id
            or artifact.producing_module_version != observed.module_version
            or artifact.content_digest != receipt.content_digest
            or observed.output_artifact_digests.get(artifact.id) != artifact.content_digest
            or receipt.observed_output_contract_digest != observed.observed_output_contract_digest
        ):
            raise ValueError("reloaded artifact is duplicate or differs from observed execution")
        artifacts = (*artifacts, artifact)
        artifact_reloads = (*artifact_reloads, receipt)
    elif event_type == "execution_reviewed":
        if set(payload) != {"receipt"}:
            raise ValueError("execution_reviewed payload is invalid")
        item = ScientificReviewReceipt.from_dict(payload["receipt"])
        observed = next((value for value in observed_executions if value.id == item.observed_execution_receipt_id), None)
        reload_by_id = {value.id: value for value in artifact_reloads}
        linked = tuple(reload_by_id.get(value) for value in item.artifact_reload_receipt_ids)
        if (
            observed is None
            or observed.plan_node_id != item.plan_node_id
            or item.id in {value.id for value in execution_reviews}
            or item.plan_node_id in {value.plan_node_id for value in execution_reviews}
            or any(value is None for value in linked)
            or {value.artifact_id for value in linked if value is not None} != set(observed.output_artifact_digests)
        ):
            raise ValueError("execution review is duplicate or does not cover every reloaded output")
        execution_reviews = (*execution_reviews, item)
    elif event_type == "quality_finding_recorded":
        if set(payload) != {"finding"} or not isinstance(payload["finding"], dict):
            raise ValueError("quality_finding_recorded payload is invalid")
    elif event_type == "analysis_admission_recorded":
        if set(payload) != {"admission"}:
            raise ValueError("analysis_admission_recorded payload is invalid")
        item = AnalysisAdmission.from_dict(payload["admission"])
        plan_nodes = {node.id: node for plan in plans for node in plan.nodes}
        if item.plan_node_id not in plan_nodes or item.plan_node_id in {value.plan_node_id for value in admissions}:
            raise ValueError("analysis admission requires one known, previously unadmitted plan node")
        if not set(item.hypothesis_ids) <= {value.id for value in hypotheses}:
            raise ValueError("analysis admission references an unknown hypothesis")
        if item.approved and not set(plan_nodes[item.plan_node_id].expected_output_artifact_types) <= set(item.expected_artifact_types):
            raise ValueError("approved analysis admission omits planned output types")
        admissions = (*admissions, item)
    elif event_type == "artifact_review_recorded":
        if set(payload) != {"review"}:
            raise ValueError("artifact_review_recorded payload is invalid")
        item = ArtifactReview.from_dict(payload["review"])
        if item.artifact_id not in {value.id for value in artifacts} or item.artifact_id in {value.artifact_id for value in reviews}:
            raise ValueError("artifact review requires one known, previously unreviewed artifact")
        validate_gate_adjudication_reviewability(state, item.artifact_id)
        expected_gate_ids = tuple(sorted(
            value.id for value in gate_adjudications if value.artifact_id == item.artifact_id
        ))
        if tuple(sorted(item.gate_adjudication_ids)) != expected_gate_ids:
            # Input/direct artifacts have no gate adjudications; handoff artifacts must cover all pending gates.
            raise ValueError("artifact review does not name its exact gate adjudication set")
        if any(
            value.artifact_id == item.artifact_id and value.status in {"rejected", "unresolved"}
            for value in gate_adjudications
        ) and item.overall_status not in {"major", "fatal"}:
            raise ValueError("rejected or unresolved gates require a major or fatal artifact review")
        reviews = (*reviews, item)
    elif event_type == "scientific_gate_adjudicated":
        if set(payload) != {"adjudication"}:
            raise ValueError("scientific_gate_adjudicated payload is invalid")
        item = ScientificGateAdjudication.from_dict(payload["adjudication"])
        if item.id in {value.id for value in gate_adjudications} or any(
            value.artifact_id == item.artifact_id and value.gate_id == item.gate_id
            for value in gate_adjudications
        ):
            raise ValueError("scientific gate adjudication is duplicate")
        validate_gate_adjudication_binding(state, item)
        gate_adjudications = (*gate_adjudications, item)
    elif event_type == "scientific_decision_recorded":
        if set(payload) != {"decision"}:
            raise ValueError("scientific_decision_recorded payload is invalid")
        item = ScientificDecision.from_dict(payload["decision"])
        review = next((value for value in reviews if value.id == item.review_id), None)
        if review is None or review.artifact_id != item.artifact_id or item.artifact_id in {value.artifact_id for value in scientific_decisions}:
            raise ValueError("scientific decision requires the matching, previously undecided review")
        active_plan = next((value for value in plans if value.id == active_plan_id), None)
        if active_plan is None or not set(item.next_plan_node_ids) <= {value.id for value in active_plan.nodes}:
            raise ValueError("scientific decision next nodes must belong to the active plan")
        revised_hypotheses = {value.id: value for value in hypotheses if value.id in item.next_hypothesis_ids}
        if item.action == "revise-hypothesis" and (
            set(revised_hypotheses) != set(item.next_hypothesis_ids)
            or any(value.parent_hypothesis_id not in item.hypothesis_ids for value in revised_hypotheses.values())
        ):
            raise ValueError("revise-hypothesis decision must bind a registered child hypothesis")
        if item.active_evidence and review.overall_status in {"major", "fatal", "unassessed"}:
            raise ValueError("blocking or unassessed review cannot release active evidence")
        expected_gate_digest = gate_adjudication_bundle_digest(state, item.artifact_id)
        if item.gate_adjudication_digest != expected_gate_digest:
            raise ValueError("scientific decision does not bind the exact gate adjudication set")
        if item.active_evidence:
            validate_gate_adjudication_retention(
                state,
                item.artifact_id,
                decision_action=item.action,
            )
        if item.action in REEXECUTE_DECISION_ACTIONS:
            validate_revision_target_contract(state, item, require_pending=True)
        scientific_decisions = (*scientific_decisions, item)
    elif event_type == "legacy_evidence_map_verified":
        if set(payload) != {"legacy_evidence_map_record_id"}:
            raise ValueError("legacy_evidence_map_verified payload is invalid")
        records = {
            item.id
            for migration in state.state_migrations
            for item in migration.legacy_evidence_maps
        }
        if payload["legacy_evidence_map_record_id"] not in records:
            raise ValueError("legacy evidence-map event is absent from the migration ledger")
    elif event_type == "evidence_map_published":
        if set(payload) != {"publication"}:
            raise ValueError("evidence_map_published payload is invalid")
        item = EvidenceMapPublication.from_dict(payload["publication"])
        if item.source_state_digest != state.state_digest:
            raise ValueError("evidence map publication must bind the immediately preceding project state")
        if item.delivery_slice_digest != delivery_slice_digest(state):
            raise ValueError("evidence map publication delivery slice is stale or mismatched")
        active_artifacts = {value.artifact_id for value in scientific_decisions if value.active_evidence}
        if set(item.active_artifact_ids) != active_artifacts:
            raise ValueError("evidence map publication active artifacts differ from current decisions")
        if item.map_kind == "validated-delivery":
            validate_validated_delivery_state(state)
        elif item.map_kind == "delivery-authorization":
            if len(item.authorized_delivery_node_ids) != 1:
                raise ValueError("delivery authorization must name exactly one delivery node")
            scope = validate_delivery_prerequisites(state, item.authorized_delivery_node_ids[0])
            if (
                item.covered_plan_id != scope.plan_id
                or item.covered_node_ids != scope.covered_node_ids
                or item.covered_artifact_ids != scope.covered_artifact_ids
                or item.delivery_scope_digest != scope.digest
            ):
                raise ValueError("delivery authorization map does not match its exact upstream slice")
        legacy_maps = tuple(
            value
            for migration in state.state_migrations
            for value in migration.legacy_evidence_maps
        )
        expected_revision = len(legacy_maps) + len(evidence_map_versions) + 1
        if item.version.revision != expected_revision:
            raise ValueError("evidence map publication revision is not continuous")
        expected_parent = (
            evidence_map_versions[-1].map_digest
            if evidence_map_versions
            else (legacy_maps[-1].publication.map_digest if legacy_maps else None)
        )
        if item.version.parent_map_digest != expected_parent:
            raise ValueError("evidence map publication parent does not match the active map")
        evidence_map_versions = (*evidence_map_versions, item)
    return (
        artifacts,
        hypotheses,
        evidence,
        gate_adjudications,
        admissions,
        reviews,
        scientific_decisions,
        evidence_map_versions,
        execution_handoffs,
        observed_executions,
        artifact_reloads,
        execution_reviews,
        plans,
        active_plan_id,
    )


def apply_event(
    state: ProjectState,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    rationale: str,
    trigger_finding_ids: tuple[str, ...] = (),
    affected_artifact_ids: tuple[str, ...] = (),
    affected_hypothesis_ids: tuple[str, ...] = (),
    superseded_action_ids: tuple[str, ...] = (),
    replacement_action_ids: tuple[str, ...] = (),
    prior_results_valid: bool = True,
) -> ProjectState:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unsupported project event type: {event_type}")
    safe_payload = thaw(freeze_mapping(payload))
    (
        artifacts,
        hypotheses,
        evidence,
        gate_adjudications,
        admissions,
        reviews,
        scientific_decisions,
        evidence_map_versions,
        execution_handoffs,
        observed_executions,
        artifact_reloads,
        execution_reviews,
        plans,
        active_plan_id,
    ) = _apply_payload(state, event_type, safe_payload)
    known_artifacts = {item.id for item in artifacts}
    known_hypotheses = {item.id for item in hypotheses}
    if not set(affected_artifact_ids) <= known_artifacts or not set(affected_hypothesis_ids) <= known_hypotheses:
        raise ValueError("decision metadata references unknown affected state objects")
    known_actions = {node.id for plan in plans for node in plan.nodes}
    if not set(superseded_action_ids) <= known_actions or not set(replacement_action_ids) <= known_actions:
        raise ValueError("decision metadata references unknown plan actions")
    sequence = state.revision + 1
    identity_basis = {
        "sequence": sequence,
        "event_type": event_type,
        "payload": safe_payload,
        "prior_state_digest": state.state_digest,
    }
    event_id = f"event-{sequence:06d}-{digest_value(identity_basis)[:12]}"
    provisional = DecisionEvent(
        id=event_id,
        sequence=sequence,
        event_type=event_type,
        rationale=rationale,
        trigger_finding_ids=trigger_finding_ids,
        affected_artifact_ids=affected_artifact_ids,
        affected_hypothesis_ids=affected_hypothesis_ids,
        superseded_action_ids=superseded_action_ids,
        replacement_action_ids=replacement_action_ids,
        prior_results_valid=prior_results_valid,
        payload=safe_payload,
        prior_state_digest=state.state_digest,
        resulting_state_digest="0" * 64,
    )
    decisions = (*state.decisions, provisional)
    resulting_digest = digest_value(
        _state_basis(
            state.context,
            artifacts,
            hypotheses,
            evidence,
            gate_adjudications,
            admissions,
            reviews,
            scientific_decisions,
            evidence_map_versions,
            execution_handoffs,
            observed_executions,
            artifact_reloads,
            execution_reviews,
            decisions,
            plans,
            active_plan_id,
            sequence,
            schema_version=state.schema_version,
            state_migrations=state.state_migrations,
        )
    )
    final_event = replace(provisional, resulting_state_digest=resulting_digest)
    return ProjectState(
        schema_version=state.schema_version,
        context=state.context,
        artifacts=artifacts,
        hypotheses=hypotheses,
        evidence=evidence,
        gate_adjudications=gate_adjudications,
        analysis_admissions=admissions,
        artifact_reviews=reviews,
        scientific_decisions=scientific_decisions,
        evidence_map_versions=evidence_map_versions,
        execution_handoffs=execution_handoffs,
        observed_executions=observed_executions,
        artifact_reloads=artifact_reloads,
        execution_reviews=execution_reviews,
        state_migrations=state.state_migrations,
        decisions=(*state.decisions, final_event),
        plans=plans,
        active_plan_id=active_plan_id,
        revision=sequence,
        state_digest=resulting_digest,
    )


def replay(
    context: ProjectContext,
    decisions: tuple[DecisionEvent, ...],
    *,
    state_migrations: tuple[StateMigrationRecord, ...] = (),
) -> ProjectState:
    state = ProjectState.create(context, state_migrations=state_migrations)
    for expected in decisions:
        if expected.sequence != state.revision + 1 or expected.prior_state_digest != state.state_digest:
            raise ValueError("decision sequence or prior-state chain is broken")
        generated = apply_event(
            state,
            expected.event_type,
            thaw(expected.payload),
            rationale=expected.rationale,
            trigger_finding_ids=expected.trigger_finding_ids,
            affected_artifact_ids=expected.affected_artifact_ids,
            affected_hypothesis_ids=expected.affected_hypothesis_ids,
            superseded_action_ids=expected.superseded_action_ids,
            replacement_action_ids=expected.replacement_action_ids,
            prior_results_valid=expected.prior_results_valid,
        )
        if generated.decisions[-1] != expected:
            raise ValueError("decision event does not match deterministic replay")
        state = generated
    return state
