"""Typed receipts that separate preparation, observation, reload, and review."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .identity import digest_value, freeze_mapping, thaw, validate_identifier


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z+._-]*$")
REVIEW_STATUSES = frozenset({"accepted", "revise", "rejected"})


def _digest(value: str, location: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ValueError(f"{location} must be a SHA-256 digest")
    return value


def _version(value: str, location: str) -> str:
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        raise ValueError(f"{location} must be an explicit version token")
    return value


@dataclass(frozen=True)
class ExecutionHandoff:
    """A deterministic execution request that proves preparation, never execution."""

    id: str
    plan_node_id: str
    module_id: str
    module_version: str
    request_digest: str
    compatibility_row_id: str
    observed_output_contract_digest: str
    planned_output_artifact_ids: Mapping[str, str]
    protocol: Mapping[str, Any]
    execution_state: str = "prepared-not-run"

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "execution_handoff.id"))
        object.__setattr__(self, "plan_node_id", validate_identifier(self.plan_node_id, "execution_handoff.plan_node_id"))
        object.__setattr__(self, "module_id", validate_identifier(self.module_id, "execution_handoff.module_id"))
        object.__setattr__(self, "module_version", _version(self.module_version, "execution_handoff.module_version"))
        object.__setattr__(self, "request_digest", _digest(self.request_digest, "execution_handoff.request_digest"))
        object.__setattr__(self, "compatibility_row_id", _version(self.compatibility_row_id, "execution_handoff.compatibility_row_id"))
        object.__setattr__(self, "observed_output_contract_digest", _digest(self.observed_output_contract_digest, "execution_handoff.observed_output_contract_digest"))
        outputs = freeze_mapping(self.planned_output_artifact_ids)
        if not outputs:
            raise ValueError("execution handoff must retain its planned output identities")
        for port, artifact_id in outputs.items():
            validate_identifier(str(port), "execution_handoff.output_port")
            validate_identifier(str(artifact_id), "execution_handoff.output_artifact_id")
        object.__setattr__(self, "planned_output_artifact_ids", outputs)
        object.__setattr__(self, "protocol", freeze_mapping(self.protocol))
        if self.execution_state != "prepared-not-run":
            raise ValueError("execution handoff state must remain prepared-not-run")

    @classmethod
    def create(
        cls,
        *,
        plan_node_id: str,
        module_id: str,
        module_version: str,
        request_digest: str,
        compatibility_row_id: str,
        observed_output_contract_digest: str,
        planned_output_artifact_ids: Mapping[str, str],
        protocol: Mapping[str, Any],
    ) -> "ExecutionHandoff":
        basis = {
            "plan_node_id": plan_node_id,
            "module_id": module_id,
            "module_version": module_version,
            "request_digest": request_digest,
            "compatibility_row_id": compatibility_row_id,
            "observed_output_contract_digest": observed_output_contract_digest,
            "planned_output_artifact_ids": dict(planned_output_artifact_ids),
            "protocol": dict(protocol),
            "execution_state": "prepared-not-run",
        }
        return cls(id=f"handoff-{digest_value(basis)[:24]}", **basis)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionHandoff":
        return cls(**dict(payload))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "plan_node_id": self.plan_node_id,
            "module_id": self.module_id,
            "module_version": self.module_version,
            "request_digest": self.request_digest,
            "compatibility_row_id": self.compatibility_row_id,
            "observed_output_contract_digest": self.observed_output_contract_digest,
            "planned_output_artifact_ids": thaw(self.planned_output_artifact_ids),
            "protocol": thaw(self.protocol),
            "execution_state": self.execution_state,
        }


@dataclass(frozen=True)
class ObservedExecutionReceipt:
    """Observed process completion bound to the exact prepared handoff."""

    id: str
    plan_node_id: str
    execution_request_id: str
    execution_request_digest: str
    source_kind: str
    handoff_id: str | None
    module_id: str
    module_version: str
    compatibility_row_id: str
    observed_output_contract_digest: str
    parameters_digest: str
    runtime_versions: Mapping[str, str]
    output_artifact_digests: Mapping[str, str]
    postflight_result_digests: Mapping[str, str]
    process_exit_code: int
    postflight_results: Mapping[str, Any] | None = None
    execution_state: str = "observed-completed"

    def __post_init__(self) -> None:
        for field in ("id", "plan_node_id", "execution_request_id", "module_id"):
            object.__setattr__(self, field, validate_identifier(getattr(self, field), f"observed_execution.{field}"))
        object.__setattr__(self, "execution_request_digest", _digest(self.execution_request_digest, "observed_execution.execution_request_digest"))
        if self.source_kind not in {"handoff", "command", "direct"}:
            raise ValueError("observed execution source kind is unsupported")
        if self.source_kind == "handoff":
            if self.handoff_id is None or self.handoff_id != self.execution_request_id:
                raise ValueError("handoff execution must bind its exact handoff ID")
            object.__setattr__(self, "handoff_id", validate_identifier(self.handoff_id, "observed_execution.handoff_id"))
        elif self.handoff_id is not None:
            raise ValueError("direct and command execution receipts cannot declare a handoff")
        object.__setattr__(self, "module_version", _version(self.module_version, "observed_execution.module_version"))
        object.__setattr__(self, "compatibility_row_id", _version(self.compatibility_row_id, "observed_execution.compatibility_row_id"))
        object.__setattr__(self, "observed_output_contract_digest", _digest(self.observed_output_contract_digest, "observed_execution.observed_output_contract_digest"))
        object.__setattr__(self, "parameters_digest", _digest(self.parameters_digest, "observed_execution.parameters_digest"))
        versions = freeze_mapping(self.runtime_versions)
        if not versions or any(not _VERSION_RE.fullmatch(str(value)) for value in versions.values()):
            raise ValueError("observed execution requires explicit runtime versions")
        object.__setattr__(self, "runtime_versions", versions)
        outputs = freeze_mapping(self.output_artifact_digests)
        if not outputs:
            raise ValueError("observed execution requires declared output artifact digests")
        for artifact_id, value in outputs.items():
            validate_identifier(str(artifact_id), "observed_execution.output_artifact_id")
            _digest(str(value), "observed_execution.output_artifact_digest")
        object.__setattr__(self, "output_artifact_digests", outputs)
        postflight = freeze_mapping(self.postflight_result_digests)
        for gate_id, value in postflight.items():
            validate_identifier(str(gate_id), "observed_execution.postflight_gate_id")
            _digest(str(value), "observed_execution.postflight_result_digest")
        object.__setattr__(self, "postflight_result_digests", postflight)
        results = freeze_mapping(self.postflight_results or {})
        if results and set(results) != set(postflight):
            raise ValueError("observed execution gate results and digests must cover the same gates")
        for gate_id, result in results.items():
            if not isinstance(result, Mapping) or result.get("status") not in {
                "passed", "failed", "requires_review", "not_evaluable"
            }:
                raise ValueError(f"observed execution has an invalid gate result: {gate_id}")
            if digest_value(thaw(result)) != postflight[str(gate_id)]:
                raise ValueError(f"observed execution gate result digest differs from its result: {gate_id}")
        object.__setattr__(self, "postflight_results", results)
        if self.process_exit_code != 0 or self.execution_state != "observed-completed":
            raise ValueError("only an observed zero-exit execution can form a completion receipt")

    @classmethod
    def create(
        cls,
        *,
        plan_node_id: str,
        module_id: str,
        module_version: str,
        compatibility_row_id: str,
        observed_output_contract_digest: str,
        parameters_digest: str,
        runtime_versions: Mapping[str, str],
        output_artifact_digests: Mapping[str, str],
        postflight_result_digests: Mapping[str, str],
        postflight_results: Mapping[str, Any] | None = None,
        process_exit_code: int,
        source_kind: str,
        execution_request_digest: str,
        handoff: ExecutionHandoff | None = None,
    ) -> "ObservedExecutionReceipt":
        if source_kind == "handoff":
            if handoff is None:
                raise ValueError("handoff execution receipt requires the prepared handoff")
            expected = {
                "plan_node_id": handoff.plan_node_id,
                "module_id": handoff.module_id,
                "module_version": handoff.module_version,
                "compatibility_row_id": handoff.compatibility_row_id,
                "observed_output_contract_digest": handoff.observed_output_contract_digest,
                "parameters_digest": handoff.request_digest,
                "output_artifact_ids": set(handoff.planned_output_artifact_ids.values()),
            }
            observed = {
                "plan_node_id": plan_node_id,
                "module_id": module_id,
                "module_version": module_version,
                "compatibility_row_id": compatibility_row_id,
                "observed_output_contract_digest": observed_output_contract_digest,
                "parameters_digest": parameters_digest,
                "output_artifact_ids": set(output_artifact_digests),
            }
            if observed != expected or execution_request_digest != digest_value(handoff.to_dict()):
                raise ValueError("observed execution differs from its prepared handoff")
            request_id = handoff.id
            handoff_id = handoff.id
        else:
            if handoff is not None:
                raise ValueError("only handoff execution may supply a prepared handoff")
            request_id = f"execution-request-{execution_request_digest[:24]}"
            handoff_id = None
        basis = {
            "plan_node_id": plan_node_id,
            "execution_request_id": request_id,
            "execution_request_digest": execution_request_digest,
            "source_kind": source_kind,
            "handoff_id": handoff_id,
            "module_id": module_id,
            "module_version": module_version,
            "compatibility_row_id": compatibility_row_id,
            "observed_output_contract_digest": observed_output_contract_digest,
            "parameters_digest": parameters_digest,
            "runtime_versions": dict(runtime_versions),
            "output_artifact_digests": dict(output_artifact_digests),
            "postflight_result_digests": dict(postflight_result_digests),
            "process_exit_code": process_exit_code,
            "execution_state": "observed-completed",
        }
        if postflight_results:
            basis["postflight_results"] = dict(postflight_results)
        return cls(id=f"observed-{digest_value(basis)[:24]}", **basis)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "id": self.id,
            "plan_node_id": self.plan_node_id,
            "execution_request_id": self.execution_request_id,
            "execution_request_digest": self.execution_request_digest,
            "source_kind": self.source_kind,
            "handoff_id": self.handoff_id,
            "module_id": self.module_id,
            "module_version": self.module_version,
            "compatibility_row_id": self.compatibility_row_id,
            "observed_output_contract_digest": self.observed_output_contract_digest,
            "parameters_digest": self.parameters_digest,
            "runtime_versions": thaw(self.runtime_versions),
            "output_artifact_digests": thaw(self.output_artifact_digests),
            "postflight_result_digests": thaw(self.postflight_result_digests),
            "process_exit_code": self.process_exit_code,
            "execution_state": self.execution_state,
        }
        if self.postflight_results:
            payload["postflight_results"] = thaw(self.postflight_results)
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObservedExecutionReceipt":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ArtifactReloadReceipt:
    """Proof that declared outputs were reloaded and matched their scientific contract."""

    id: str
    observed_execution_receipt_id: str
    artifact_id: str
    payload_digests: Mapping[str, str]
    observed_output_contract_digest: str
    reload_validator_id: str | None
    output_schema_valid: bool
    content_digest: str

    def __post_init__(self) -> None:
        for field in ("id", "observed_execution_receipt_id", "artifact_id"):
            object.__setattr__(self, field, validate_identifier(getattr(self, field), f"artifact_reload.{field}"))
        payloads = freeze_mapping(self.payload_digests)
        if not payloads:
            raise ValueError("artifact reload requires payload identities")
        for value in payloads.values():
            _digest(str(value), "artifact_reload.payload_digest")
        object.__setattr__(self, "payload_digests", payloads)
        object.__setattr__(self, "observed_output_contract_digest", _digest(self.observed_output_contract_digest, "artifact_reload.observed_output_contract_digest"))
        if self.reload_validator_id is not None:
            object.__setattr__(self, "reload_validator_id", validate_identifier(self.reload_validator_id, "artifact_reload.reload_validator_id"))
        if self.output_schema_valid is not True:
            raise ValueError("artifact reload receipt requires a valid output schema")
        object.__setattr__(self, "content_digest", _digest(self.content_digest, "artifact_reload.content_digest"))

    @classmethod
    def create(
        cls,
        *,
        observed_execution: ObservedExecutionReceipt,
        artifact_id: str,
        payload_digests: Mapping[str, str],
        observed_output_contract_digest: str,
        reload_validator_id: str | None,
        content_digest: str,
        output_schema_valid: bool,
    ) -> "ArtifactReloadReceipt":
        if observed_execution.output_artifact_digests.get(artifact_id) != content_digest:
            raise ValueError("reloaded artifact digest differs from observed execution output")
        if observed_execution.observed_output_contract_digest != observed_output_contract_digest:
            raise ValueError("reloaded artifact contract differs from observed execution")
        normalized_payloads = dict(payload_digests) or {"content": content_digest}
        basis = {
            "observed_execution_receipt_id": observed_execution.id,
            "artifact_id": artifact_id,
            "payload_digests": normalized_payloads,
            "observed_output_contract_digest": observed_output_contract_digest,
            "reload_validator_id": reload_validator_id,
            "output_schema_valid": output_schema_valid,
            "content_digest": content_digest,
        }
        return cls(id=f"reload-{digest_value(basis)[:24]}", **basis)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "observed_execution_receipt_id": self.observed_execution_receipt_id,
            "artifact_id": self.artifact_id,
            "payload_digests": thaw(self.payload_digests),
            "observed_output_contract_digest": self.observed_output_contract_digest,
            "reload_validator_id": self.reload_validator_id,
            "output_schema_valid": self.output_schema_valid,
            "content_digest": self.content_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactReloadReceipt":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ScientificReviewReceipt:
    """Decision on whether reloaded artifacts may become active scientific evidence."""

    id: str
    plan_node_id: str
    observed_execution_receipt_id: str
    artifact_reload_receipt_ids: tuple[str, ...]
    review_status: str
    finding_ids: tuple[str, ...]
    reviewer_role: str
    active_evidence_allowed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "scientific_review.id"))
        object.__setattr__(self, "plan_node_id", validate_identifier(self.plan_node_id, "scientific_review.plan_node_id"))
        object.__setattr__(self, "observed_execution_receipt_id", validate_identifier(self.observed_execution_receipt_id, "scientific_review.observed_execution_receipt_id"))
        reload_ids = tuple(validate_identifier(value, "scientific_review.artifact_reload_receipt_id") for value in self.artifact_reload_receipt_ids)
        if not reload_ids or len(set(reload_ids)) != len(reload_ids):
            raise ValueError("scientific review requires unique artifact reload receipts")
        object.__setattr__(self, "artifact_reload_receipt_ids", reload_ids)
        if self.review_status not in REVIEW_STATUSES:
            raise ValueError("scientific review status is unsupported")
        findings = tuple(validate_identifier(value, "scientific_review.finding_id") for value in self.finding_ids)
        if len(set(findings)) != len(findings):
            raise ValueError("scientific review finding IDs must be unique")
        object.__setattr__(self, "finding_ids", findings)
        object.__setattr__(self, "reviewer_role", validate_identifier(self.reviewer_role, "scientific_review.reviewer_role"))
        if self.active_evidence_allowed is not (self.review_status == "accepted"):
            raise ValueError("only accepted scientific review may release active evidence")

    @classmethod
    def create(
        cls,
        *,
        observed_execution: ObservedExecutionReceipt,
        reload_receipts: tuple[ArtifactReloadReceipt, ...],
        finding_ids: tuple[str, ...] = (),
        review_status: str = "accepted",
        reviewer_role: str = "execution-integrity-review",
    ) -> "ScientificReviewReceipt":
        if not reload_receipts or {
            item.observed_execution_receipt_id for item in reload_receipts
        } != {observed_execution.id}:
            raise ValueError("execution integrity review requires reloads from one observed execution")
        if {item.artifact_id for item in reload_receipts} != set(observed_execution.output_artifact_digests):
            raise ValueError("execution integrity review must cover every observed output artifact")
        basis = {
            "plan_node_id": observed_execution.plan_node_id,
            "observed_execution_receipt_id": observed_execution.id,
            "artifact_reload_receipt_ids": [item.id for item in reload_receipts],
            "review_status": review_status,
            "finding_ids": list(finding_ids),
            "reviewer_role": reviewer_role,
            "active_evidence_allowed": review_status == "accepted",
        }
        return cls(id=f"execution-review-{digest_value(basis)[:24]}", **basis)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "plan_node_id": self.plan_node_id,
            "observed_execution_receipt_id": self.observed_execution_receipt_id,
            "artifact_reload_receipt_ids": list(self.artifact_reload_receipt_ids),
            "review_status": self.review_status,
            "finding_ids": list(self.finding_ids),
            "reviewer_role": self.reviewer_role,
            "active_evidence_allowed": self.active_evidence_allowed,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificReviewReceipt":
        values = dict(payload)
        values["artifact_reload_receipt_ids"] = tuple(values["artifact_reload_receipt_ids"])
        values["finding_ids"] = tuple(values["finding_ids"])
        return cls(**values)
