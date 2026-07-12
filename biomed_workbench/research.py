"""Structured records for the Codex-native scientific research lifecycle."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .models import EvidenceItem, ExecutionResult


LIFECYCLE_STATES = ("frame", "plan", "investigate", "design", "interpret", "deliver", "audit")
STAGE_STATUSES = frozenset({"completed", "skipped", "blocked", "failed"})
_SECRET_KEY_RE = re.compile(r"(?:api[_-]?key|token|secret|password|credential)", re.IGNORECASE)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): ("[REDACTED]" if _SECRET_KEY_RE.search(str(key)) else _redact(item)) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_redact(item) for item in value]
    return value


@dataclass(frozen=True)
class ResearchAction:
    capability_id: str
    inputs: dict[str, Any]
    purpose: str

    def __post_init__(self) -> None:
        if not self.capability_id.strip() or not self.purpose.strip():
            raise ValueError("research actions require a capability and scientific purpose")


@dataclass(frozen=True)
class StageRecord:
    name: str
    status: str
    rationale: str

    def __post_init__(self) -> None:
        if self.name not in LIFECYCLE_STATES:
            raise ValueError(f"invalid research stage: {self.name}")
        if self.status not in STAGE_STATUSES or not self.rationale.strip():
            raise ValueError("research stage requires a valid status and rationale")


@dataclass(frozen=True)
class ResearchRecord:
    objective: str
    inputs: dict[str, Any]
    plan: tuple[ResearchAction, ...]
    stages: tuple[StageRecord, ...]
    executions: tuple[ExecutionResult, ...]
    evidence: tuple[EvidenceItem, ...]
    conclusions: tuple[str, ...]
    limitations: tuple[str, ...]
    next_decisions: tuple[str, ...]
    summary: str

    def __post_init__(self) -> None:
        if not self.objective.strip() or not self.summary.strip():
            raise ValueError("research records require an objective and summary")
        stage_names = tuple(stage.name for stage in self.stages)
        if stage_names and stage_names != LIFECYCLE_STATES[: len(stage_names)]:
            raise ValueError("research stages must follow lifecycle order")

    def to_dict(self) -> dict[str, Any]:
        return _redact(asdict(self))
