"""Immutable plan-node and research-DAG state contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .identity import digest_value, freeze_mapping, thaw, validate_identifier


NODE_STATUSES = frozenset(
    {
        "pending",
        "ready",
        "running",
        "prepared",
        "awaiting_observed_execution",
        "awaiting_review",
        "completed",
        "blocked",
        "failed",
        "superseded",
        "skipped",
    }
)
PLAN_TYPES = frozenset({"single", "serial", "parallel", "mixed"})
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_ACTIONS = frozenset({"rerun-same-method", "rerun-adjusted-parameters", "switch-method"})
REVISION_EQUIVALENCE_CLASSES = frozenset({
    "same-method",
    "contract-equivalent",
    "decision-role-alternative-with-method-specific-evidence",
    "scope-downgrade",
})
CLAIM_SCOPE_TRANSITIONS = frozenset({
    "preserve-method-and-claim-scope",
    "preserve-claim-scope",
    "reset-to-target-method-specific-evidence",
    "narrow-to-target-scope",
})


def _ids(values: tuple[str, ...], location: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    result = tuple(validate_identifier(value, location) for value in values)
    if not allow_empty and not result:
        raise ValueError(f"{location} must not be empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{location} contains duplicates")
    return result


def _tokens(values: tuple[str, ...], location: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    result = tuple(values)
    if not allow_empty and not result:
        raise ValueError(f"{location} must not be empty")
    if any(not isinstance(value, str) or not _TOKEN_RE.fullmatch(value) for value in result) or len(set(result)) != len(result):
        raise ValueError(f"{location} contains invalid or duplicate tokens")
    return result


def _meaningful(value: str, location: str, minimum: int = 12) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(f"{location} must be meaningful text")
    freeze_mapping({location: value.strip()})
    return value.strip()


@dataclass(frozen=True)
class RevisionTargetContract:
    """Frozen node-level replacement identity prepared against a live registry."""

    id: str
    source_node_id: str
    target_node_id: str
    action: str
    source_module_id: str
    target_module_id: str
    source_manifest_digest: str
    target_manifest_digest: str
    alternative_relation_digest: str
    input_contract_digest: str
    output_contract_digest: str
    source_request_digest: str
    target_request_digest: str
    rationale: str
    scientific_equivalence_class: str
    claim_scope_transition: str
    digest: str

    def __post_init__(self) -> None:
        for field in ("id", "source_node_id", "target_node_id", "source_module_id", "target_module_id"):
            object.__setattr__(self, field, validate_identifier(getattr(self, field), f"revision_contract.{field}"))
        if self.source_node_id == self.target_node_id:
            raise ValueError("revision contract source and target nodes must differ")
        if self.action not in REVISION_ACTIONS:
            raise ValueError("revision contract action is unsupported")
        for field in (
            "source_manifest_digest", "target_manifest_digest", "alternative_relation_digest",
            "input_contract_digest", "output_contract_digest", "source_request_digest",
            "target_request_digest", "digest",
        ):
            if not isinstance(getattr(self, field), str) or not _DIGEST_RE.fullmatch(getattr(self, field)):
                raise ValueError(f"revision contract {field} must be SHA-256")
        object.__setattr__(self, "rationale", _meaningful(self.rationale, "revision_contract.rationale"))
        if self.scientific_equivalence_class not in REVISION_EQUIVALENCE_CLASSES:
            raise ValueError("revision contract scientific equivalence class is unsupported")
        if self.claim_scope_transition not in CLAIM_SCOPE_TRANSITIONS:
            raise ValueError("revision contract claim scope transition is unsupported")
        expected_transition = {
            "same-method": "preserve-method-and-claim-scope",
            "contract-equivalent": "preserve-claim-scope",
            "decision-role-alternative-with-method-specific-evidence": "reset-to-target-method-specific-evidence",
            "scope-downgrade": "narrow-to-target-scope",
        }[self.scientific_equivalence_class]
        if self.claim_scope_transition != expected_transition:
            raise ValueError("revision contract equivalence class and claim scope transition disagree")
        basis = {field: getattr(self, field) for field in self.__dataclass_fields__ if field != "digest"}
        if self.digest != digest_value(basis):
            raise ValueError("revision contract digest does not match its frozen content")

    @classmethod
    def create(cls, **values: Any) -> "RevisionTargetContract":
        if "digest" in values:
            raise ValueError("revision contract create computes its digest")
        return cls(**values, digest=digest_value(values))

    def to_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RevisionTargetContract":
        return cls(**dict(payload))


@dataclass(frozen=True)
class PlanNode:
    id: str
    module_id: str
    input_bindings: Mapping[str, str]
    dependencies: tuple[str, ...]
    branch_id: str
    target_hypothesis_ids: tuple[str, ...]
    expected_evidence_types: tuple[str, ...]
    expected_output_artifact_types: tuple[str, ...]
    planned_output_artifact_ids: Mapping[str, str]
    compatibility_row_candidates: tuple[str, ...]
    status: str
    attempt: int
    planned_request_digest: str | None = None
    revision_of_node_id: str | None = None
    parameter_overrides: Mapping[str, Any] | None = None
    revision_contract: RevisionTargetContract | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "plan_node.id"))
        object.__setattr__(self, "module_id", validate_identifier(self.module_id, "plan_node.module_id"))
        bindings = freeze_mapping(self.input_bindings)
        if any(not _TOKEN_RE.fullmatch(port) or not isinstance(artifact_id, str) for port, artifact_id in bindings.items()):
            raise ValueError("plan node input bindings must map ports to artifact IDs")
        for artifact_id in bindings.values():
            validate_identifier(artifact_id, "plan_node.input_bindings")
        object.__setattr__(self, "input_bindings", bindings)
        dependencies = _ids(tuple(self.dependencies), "plan_node.dependencies")
        if self.id in dependencies:
            raise ValueError("plan node cannot depend on itself")
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "branch_id", validate_identifier(self.branch_id, "plan_node.branch_id"))
        object.__setattr__(self, "target_hypothesis_ids", _ids(tuple(self.target_hypothesis_ids), "plan_node.target_hypothesis_ids"))
        object.__setattr__(self, "expected_evidence_types", _ids(tuple(self.expected_evidence_types), "plan_node.expected_evidence_types"))
        object.__setattr__(self, "expected_output_artifact_types", _ids(tuple(self.expected_output_artifact_types), "plan_node.expected_output_artifact_types", allow_empty=False))
        outputs = freeze_mapping(self.planned_output_artifact_ids)
        if not outputs or any(not _TOKEN_RE.fullmatch(port) or not isinstance(artifact_id, str) for port, artifact_id in outputs.items()):
            raise ValueError("plan node outputs must map ports to planned artifact IDs")
        for artifact_id in outputs.values():
            validate_identifier(artifact_id, "plan_node.planned_output_artifact_ids")
        if len(set(outputs.values())) != len(outputs) or set(outputs.values()) & set(bindings.values()):
            raise ValueError("planned output artifact IDs must be unique and differ from inputs")
        object.__setattr__(self, "planned_output_artifact_ids", outputs)
        object.__setattr__(self, "compatibility_row_candidates", _tokens(tuple(self.compatibility_row_candidates), "plan_node.compatibility_row_candidates", allow_empty=False))
        if self.status not in NODE_STATUSES:
            raise ValueError("plan node status is unsupported")
        if not isinstance(self.attempt, int) or isinstance(self.attempt, bool) or self.attempt < 0:
            raise ValueError("plan node attempt must be nonnegative")
        if self.planned_request_digest is not None and (
            not isinstance(self.planned_request_digest, str)
            or not _DIGEST_RE.fullmatch(self.planned_request_digest)
        ):
            raise ValueError("plan node planned request digest must be SHA-256")
        if self.revision_of_node_id is not None:
            object.__setattr__(
                self,
                "revision_of_node_id",
                validate_identifier(self.revision_of_node_id, "plan_node.revision_of_node_id"),
            )
            if self.revision_of_node_id == self.id:
                raise ValueError("plan node cannot be its own revision target")
        overrides = freeze_mapping(self.parameter_overrides or {})
        object.__setattr__(self, "parameter_overrides", overrides)
        if self.revision_contract is not None:
            if not isinstance(self.revision_contract, RevisionTargetContract):
                raise ValueError("plan node revision contract is invalid")
            if (
                self.revision_of_node_id is None
                or self.revision_contract.source_node_id != self.revision_of_node_id
                or self.revision_contract.target_node_id != self.id
                or self.revision_contract.target_module_id != self.module_id
                or self.revision_contract.target_request_digest != self.planned_request_digest
            ):
                raise ValueError("plan node differs from its frozen revision contract")
        elif self.revision_of_node_id is not None:
            raise ValueError("revision target node requires a frozen revision contract")
        if self.revision_of_node_id is None and (overrides or self.planned_request_digest is not None):
            raise ValueError("only a revision target may freeze parameter overrides or request identity")

    def to_dict(self) -> dict[str, object]:
        payload = {
            "id": self.id,
            "module_id": self.module_id,
            "input_bindings": thaw(self.input_bindings),
            "dependencies": list(self.dependencies),
            "branch_id": self.branch_id,
            "target_hypothesis_ids": list(self.target_hypothesis_ids),
            "expected_evidence_types": list(self.expected_evidence_types),
            "expected_output_artifact_types": list(self.expected_output_artifact_types),
            "planned_output_artifact_ids": thaw(self.planned_output_artifact_ids),
            "compatibility_row_candidates": list(self.compatibility_row_candidates),
            "status": self.status,
            "attempt": self.attempt,
        }
        if self.planned_request_digest is not None:
            payload["planned_request_digest"] = self.planned_request_digest
        if self.revision_of_node_id is not None:
            payload["revision_of_node_id"] = self.revision_of_node_id
        if self.parameter_overrides:
            payload["parameter_overrides"] = thaw(self.parameter_overrides)
        if self.revision_contract is not None:
            payload["revision_contract"] = self.revision_contract.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PlanNode":
        values = dict(payload)
        values.setdefault("planned_request_digest", None)
        values.setdefault("revision_of_node_id", None)
        values.setdefault("parameter_overrides", {})
        contract = values.get("revision_contract")
        values["revision_contract"] = RevisionTargetContract.from_dict(contract) if contract is not None else None
        for field in (
            "dependencies",
            "target_hypothesis_ids",
            "expected_evidence_types",
            "expected_output_artifact_types",
            "compatibility_row_candidates",
        ):
            values[field] = tuple(values[field])
        return cls(**values)


def _dag_basis(values: Mapping[str, Any]) -> dict[str, object]:
    return {
        "id": values["id"],
        "objective": values["objective"],
        "nodes": [node.to_dict() for node in values["nodes"]],
        "required_output_artifact_types": list(values["required_output_artifact_types"]),
        "plan_type": values["plan_type"],
        "revision": values["revision"],
        "parent_plan_id": values["parent_plan_id"],
        "rationale": list(values["rationale"]),
    }


@dataclass(frozen=True)
class ResearchDAG:
    id: str
    objective: str
    nodes: tuple[PlanNode, ...]
    required_output_artifact_types: tuple[str, ...]
    plan_type: str
    revision: int
    parent_plan_id: str | None
    rationale: tuple[str, ...]
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "plan.id"))
        object.__setattr__(self, "objective", _meaningful(self.objective, "plan.objective", 24))
        nodes = tuple(self.nodes)
        if not nodes or any(not isinstance(node, PlanNode) for node in nodes) or len({node.id for node in nodes}) != len(nodes):
            raise ValueError("plan nodes must be nonempty and uniquely identified")
        node_ids = {node.id for node in nodes}
        if any(not set(node.dependencies) <= node_ids for node in nodes):
            raise ValueError("plan node references an unknown dependency")
        if any(
            node.revision_of_node_id is not None
            and node.revision_of_node_id not in node_ids
            for node in nodes
        ):
            raise ValueError("plan node references an unknown revision source")
        if any(
            node.revision_of_node_id is not None
            and next(value for value in nodes if value.id == node.revision_of_node_id).revision_of_node_id is not None
            for node in nodes
        ):
            raise ValueError("revision targets cannot form a chained replacement hierarchy")
        _validate_acyclic(nodes)
        planned_ids = [artifact_id for node in nodes for artifact_id in node.planned_output_artifact_ids.values()]
        if len(set(planned_ids)) != len(planned_ids):
            raise ValueError("planned artifact IDs must be unique across the DAG")
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "required_output_artifact_types", _ids(tuple(self.required_output_artifact_types), "plan.required_output_artifact_types", allow_empty=False))
        if self.plan_type not in PLAN_TYPES:
            raise ValueError("plan.plan_type is unsupported")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("plan.revision must be positive")
        if self.parent_plan_id is None:
            if self.revision != 1:
                raise ValueError("initial plans must use revision 1")
        else:
            object.__setattr__(self, "parent_plan_id", validate_identifier(self.parent_plan_id, "plan.parent_plan_id"))
            if self.parent_plan_id == self.id or self.revision == 1:
                raise ValueError("revised plans require a distinct parent and revision greater than 1")
        rationale = tuple(_meaningful(value, "plan.rationale") for value in self.rationale)
        if not rationale:
            raise ValueError("plan rationale must not be empty")
        object.__setattr__(self, "rationale", rationale)
        if self.digest != digest_value(_dag_basis(self.__dict__)):
            raise ValueError("plan digest does not match canonical content")

    @classmethod
    def create(cls, **values: Any) -> "ResearchDAG":
        if "digest" in values:
            raise ValueError("create computes plan digest automatically")
        normalized = dict(values)
        normalized["nodes"] = tuple(normalized["nodes"])
        normalized["required_output_artifact_types"] = tuple(normalized["required_output_artifact_types"])
        normalized["rationale"] = tuple(normalized["rationale"])
        return cls(**normalized, digest=digest_value(_dag_basis(normalized)))

    def to_dict(self) -> dict[str, object]:
        return {**_dag_basis(self.__dict__), "digest": self.digest}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResearchDAG":
        values = dict(payload)
        values["nodes"] = tuple(PlanNode.from_dict(item) for item in values["nodes"])
        values["required_output_artifact_types"] = tuple(values["required_output_artifact_types"])
        values["rationale"] = tuple(values["rationale"])
        return cls(**values)


def _validate_acyclic(nodes: tuple[PlanNode, ...]) -> None:
    dependencies = {node.id: set(node.dependencies) for node in nodes}
    ready = sorted(node_id for node_id, values in dependencies.items() if not values)
    visited = []
    while ready:
        node_id = ready.pop(0)
        visited.append(node_id)
        for target in sorted(dependencies):
            if node_id in dependencies[target]:
                dependencies[target].remove(node_id)
                if not dependencies[target] and target not in visited and target not in ready:
                    ready.append(target)
                    ready.sort()
    if len(visited) != len(nodes):
        raise ValueError("research DAG contains a dependency cycle")
