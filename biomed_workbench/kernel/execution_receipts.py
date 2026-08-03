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
    module_id: str
    module_version: str
    request_digest: str
    compatibility_row_id: str
    planned_output_artifact_ids: Mapping[str, str]
    protocol: Mapping[str, Any]
    execution_state: str = "prepared-not-run"

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "execution_handoff.id"))
        object.__setattr__(self, "module_id", validate_identifier(self.module_id, "execution_handoff.module_id"))
        object.__setattr__(self, "module_version", _version(self.module_version, "execution_handoff.module_version"))
        object.__setattr__(self, "request_digest", _digest(self.request_digest, "execution_handoff.request_digest"))
        object.__setattr__(self, "compatibility_row_id", _version(self.compatibility_row_id, "execution_handoff.compatibility_row_id"))
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
        module_id: str,
        module_version: str,
        request_digest: str,
        compatibility_row_id: str,
        planned_output_artifact_ids: Mapping[str, str],
        protocol: Mapping[str, Any],
    ) -> "ExecutionHandoff":
        basis = {
            "module_id": module_id,
            "module_version": module_version,
            "request_digest": request_digest,
            "compatibility_row_id": compatibility_row_id,
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
            "module_id": self.module_id,
            "module_version": self.module_version,
            "request_digest": self.request_digest,
            "compatibility_row_id": self.compatibility_row_id,
            "planned_output_artifact_ids": thaw(self.planned_output_artifact_ids),
            "protocol": thaw(self.protocol),
            "execution_state": self.execution_state,
        }


@dataclass(frozen=True)
class ObservedExecutionReceipt:
    """Observed process completion bound to the exact prepared handoff."""

    id: str
    handoff_id: str
    module_id: str
    module_version: str
    compatibility_row_id: str
    parameters_digest: str
    runtime_versions: Mapping[str, str]
    output_payload_digests: Mapping[str, str]
    process_exit_code: int
    execution_state: str = "observed-completed"

    def __post_init__(self) -> None:
        for field in ("id", "handoff_id", "module_id"):
            object.__setattr__(self, field, validate_identifier(getattr(self, field), f"observed_execution.{field}"))
        object.__setattr__(self, "module_version", _version(self.module_version, "observed_execution.module_version"))
        object.__setattr__(self, "compatibility_row_id", _version(self.compatibility_row_id, "observed_execution.compatibility_row_id"))
        object.__setattr__(self, "parameters_digest", _digest(self.parameters_digest, "observed_execution.parameters_digest"))
        versions = freeze_mapping(self.runtime_versions)
        if not versions or any(not _VERSION_RE.fullmatch(str(value)) for value in versions.values()):
            raise ValueError("observed execution requires explicit runtime versions")
        object.__setattr__(self, "runtime_versions", versions)
        outputs = freeze_mapping(self.output_payload_digests)
        if not outputs:
            raise ValueError("observed execution requires declared output payload digests")
        for value in outputs.values():
            _digest(str(value), "observed_execution.output_payload_digest")
        object.__setattr__(self, "output_payload_digests", outputs)
        if self.process_exit_code != 0 or self.execution_state != "observed-completed":
            raise ValueError("only an observed zero-exit execution can form a completion receipt")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "handoff_id": self.handoff_id,
            "module_id": self.module_id,
            "module_version": self.module_version,
            "compatibility_row_id": self.compatibility_row_id,
            "parameters_digest": self.parameters_digest,
            "runtime_versions": thaw(self.runtime_versions),
            "output_payload_digests": thaw(self.output_payload_digests),
            "process_exit_code": self.process_exit_code,
            "execution_state": self.execution_state,
        }

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
        if self.output_schema_valid is not True:
            raise ValueError("artifact reload receipt requires a valid output schema")
        object.__setattr__(self, "content_digest", _digest(self.content_digest, "artifact_reload.content_digest"))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "observed_execution_receipt_id": self.observed_execution_receipt_id,
            "artifact_id": self.artifact_id,
            "payload_digests": thaw(self.payload_digests),
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
    artifact_reload_receipt_ids: tuple[str, ...]
    review_status: str
    finding_ids: tuple[str, ...]
    reviewer_role: str
    active_evidence_allowed: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "scientific_review.id"))
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

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
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
