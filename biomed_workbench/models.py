"""Immutable contracts shared by routing, execution, and research records."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


WORKFLOWS = frozenset({"evidence", "omics", "molecular_design", "imaging", "clinical", "wetlab", "publication"})
KINDS = frozenset({"python", "command", "service", "workflow"})
ACCESS_MODES = frozenset({"offline", "public_api", "optional_api"})
MUTABILITY_MODES = frozenset({"read_only", "writes_output"})
RESULT_STATUSES = frozenset({"completed", "failed", "blocked", "skipped"})
_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
_SECRET_KEY_RE = re.compile(r"(?:api[_-]?key|token|secret|password|credential)", re.IGNORECASE)


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): ("[REDACTED]" if _SECRET_KEY_RE.search(str(key)) else _safe_value(item)) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe_value(item) for item in value]
    return value


@dataclass(frozen=True)
class Capability:
    id: str
    workflow: str
    kind: str
    title: str
    description: str
    entrypoint: str
    input_schema: dict[str, object]
    requirements: tuple[str, ...]
    access: str
    mutability: str

    def __post_init__(self) -> None:
        if not _ID_RE.fullmatch(self.id):
            raise ValueError(f"invalid capability id: {self.id!r}")
        if self.workflow not in WORKFLOWS:
            raise ValueError(f"invalid workflow: {self.workflow!r}")
        if self.kind not in KINDS:
            raise ValueError(f"invalid capability kind: {self.kind!r}")
        if self.access not in ACCESS_MODES:
            raise ValueError(f"invalid access mode: {self.access!r}")
        if self.mutability not in MUTABILITY_MODES:
            raise ValueError(f"invalid mutability mode: {self.mutability!r}")
        if not self.title.strip() or len(self.description.strip()) < 12:
            raise ValueError("capability title and description must be meaningful")
        if not self.entrypoint.strip() or not isinstance(self.input_schema, dict):
            raise ValueError("capability requires an entrypoint and object input schema")
        if not all(isinstance(requirement, str) and requirement.strip() for requirement in self.requirements):
            raise ValueError("capability requirements must be nonempty strings")


@dataclass(frozen=True)
class EvidenceItem:
    identifier: str
    source: str
    claim: str
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Artifact:
    kind: str
    path: str
    description: str


@dataclass(frozen=True)
class ExecutionResult:
    capability_id: str
    status: str
    output: dict[str, Any]
    evidence: tuple[EvidenceItem, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in RESULT_STATUSES:
            raise ValueError(f"invalid result status: {self.status!r}")

    def to_dict(self) -> dict[str, Any]:
        return _safe_value(asdict(self))
