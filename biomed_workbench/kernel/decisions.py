"""Append-only scientific decisions and state-transition evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .identity import freeze_mapping, thaw, validate_identifier


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _ids(values: tuple[str, ...], location: str) -> tuple[str, ...]:
    result = tuple(validate_identifier(value, location) for value in values)
    if len(set(result)) != len(result):
        raise ValueError(f"{location} contains duplicates")
    return result


@dataclass(frozen=True)
class DecisionEvent:
    id: str
    sequence: int
    event_type: str
    rationale: str
    trigger_finding_ids: tuple[str, ...]
    affected_artifact_ids: tuple[str, ...]
    affected_hypothesis_ids: tuple[str, ...]
    superseded_action_ids: tuple[str, ...]
    replacement_action_ids: tuple[str, ...]
    prior_results_valid: bool
    payload: Mapping[str, Any]
    prior_state_digest: str
    resulting_state_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "decision.id"))
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("decision.sequence must be positive")
        object.__setattr__(self, "event_type", validate_identifier(self.event_type, "decision.event_type"))
        if not isinstance(self.rationale, str) or len(self.rationale.strip()) < 12:
            raise ValueError("decision.rationale must be meaningful")
        freeze_mapping({"rationale": self.rationale})
        object.__setattr__(self, "rationale", self.rationale.strip())
        for field in (
            "trigger_finding_ids",
            "affected_artifact_ids",
            "affected_hypothesis_ids",
            "superseded_action_ids",
            "replacement_action_ids",
        ):
            object.__setattr__(self, field, _ids(tuple(getattr(self, field)), f"decision.{field}"))
        if not isinstance(self.prior_results_valid, bool):
            raise ValueError("decision.prior_results_valid must be boolean")
        object.__setattr__(self, "payload", freeze_mapping(self.payload))
        if not _DIGEST_RE.fullmatch(self.prior_state_digest) or not _DIGEST_RE.fullmatch(self.resulting_state_digest):
            raise ValueError("decision state digests must be SHA-256 values")

    def digest_basis(self) -> dict[str, object]:
        payload = self.to_dict()
        del payload["resulting_state_digest"]
        return payload

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "rationale": self.rationale,
            "trigger_finding_ids": list(self.trigger_finding_ids),
            "affected_artifact_ids": list(self.affected_artifact_ids),
            "affected_hypothesis_ids": list(self.affected_hypothesis_ids),
            "superseded_action_ids": list(self.superseded_action_ids),
            "replacement_action_ids": list(self.replacement_action_ids),
            "prior_results_valid": self.prior_results_valid,
            "payload": thaw(self.payload),
            "prior_state_digest": self.prior_state_digest,
            "resulting_state_digest": self.resulting_state_digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DecisionEvent":
        values = dict(payload)
        for field in (
            "trigger_finding_ids",
            "affected_artifact_ids",
            "affected_hypothesis_ids",
            "superseded_action_ids",
            "replacement_action_ids",
        ):
            values[field] = tuple(values[field])
        return cls(**values)
