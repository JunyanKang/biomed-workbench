"""Project locks and explicit result-status transitions.

The project state records scientific events.  This companion contract freezes
the project-wide choices that must not drift between those events and controls
which reviewed results may enter formal figures.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping

from .execution_chain import validate_artifact_execution_chain
from .identity import digest_value, freeze_mapping, thaw, validate_identifier
from .state import ProjectState


RESULT_STATUSES = frozenset({"FORMAL", "CANDIDATE", "SENSITIVITY", "DEPRECATED"})
_TRANSITIONS = {
    None: frozenset({"CANDIDATE", "SENSITIVITY"}),
    "CANDIDATE": frozenset({"FORMAL", "SENSITIVITY", "DEPRECATED"}),
    "SENSITIVITY": frozenset({"FORMAL", "CANDIDATE", "DEPRECATED"}),
    "FORMAL": frozenset({"DEPRECATED"}),
    "DEPRECATED": frozenset(),
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_path(root: Path, value: str, *, must_be_file: bool) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("project-lock path must be nonempty")
    path = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("project-lock paths must remain inside the project root") from exc
    if must_be_file and not path.is_file():
        raise ValueError(f"project-lock file is missing: {value}")
    return path


@dataclass(frozen=True)
class LockedFile:
    role: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", validate_identifier(self.role, "project_lock.file.role"))
        if not isinstance(self.relative_path, str) or not self.relative_path:
            raise ValueError("project-lock file path must be nonempty")
        if len(self.sha256) != 64 or set(self.sha256) - set("0123456789abcdef"):
            raise ValueError("project-lock file digest must be lowercase SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "relative_path": self.relative_path, "sha256": self.sha256}


@dataclass(frozen=True)
class ProjectLock:
    schema_version: int
    project_id: str
    revision: int
    parent_lock_digest: str | None
    context_digest: str
    genome_build: str
    annotation_release: str
    experimental_unit: str
    thresholds: Mapping[str, Any]
    colors: Mapping[str, str]
    formal_output_root: str
    files: tuple[LockedFile, ...]
    digest: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("project-lock schema version is unsupported")
        object.__setattr__(self, "project_id", validate_identifier(self.project_id, "project_lock.project_id"))
        if not isinstance(self.revision, int) or self.revision < 1:
            raise ValueError("project-lock revision must be positive")
        for field in ("parent_lock_digest", "context_digest", "digest"):
            value = getattr(self, field)
            if value is not None and (len(value) != 64 or set(value) - set("0123456789abcdef")):
                raise ValueError(f"project_lock.{field} must be lowercase SHA-256")
        if self.revision == 1 and self.parent_lock_digest is not None:
            raise ValueError("first project-lock revision cannot name a parent")
        if self.revision > 1 and self.parent_lock_digest is None:
            raise ValueError("later project-lock revisions require the parent lock digest")
        for field in ("genome_build", "annotation_release", "experimental_unit", "formal_output_root"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise ValueError(f"project_lock.{field} must be nonempty")
        object.__setattr__(self, "thresholds", freeze_mapping(self.thresholds))
        colors = freeze_mapping(self.colors)
        if not colors or any(not isinstance(value, str) or not value.strip() for value in colors.values()):
            raise ValueError("project-lock colors must freeze named display values")
        object.__setattr__(self, "colors", colors)
        files = tuple(self.files)
        if {item.role for item in files} != {"sample-sheet", "cell-annotation", "panel-registry"}:
            raise ValueError("project lock requires sample sheet, cell annotation and panel registry files")
        object.__setattr__(self, "files", files)
        basis = self.to_dict(include_digest=False)
        if self.digest != digest_value(basis):
            raise ValueError("project-lock digest is invalid")

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "revision": self.revision,
            "parent_lock_digest": self.parent_lock_digest,
            "context_digest": self.context_digest,
            "genome_build": self.genome_build,
            "annotation_release": self.annotation_release,
            "experimental_unit": self.experimental_unit,
            "thresholds": thaw(self.thresholds),
            "colors": thaw(self.colors),
            "formal_output_root": self.formal_output_root,
            "files": [item.to_dict() for item in self.files],
        }
        if include_digest:
            payload["digest"] = self.digest
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProjectLock":
        values = dict(payload)
        values["files"] = tuple(LockedFile(**item) for item in values["files"])
        return cls(**values)


def create_project_lock(config: Mapping[str, Any], state: ProjectState, workspace_root: Path) -> ProjectLock:
    root = workspace_root.resolve(strict=True)
    required = {
        "revision", "parent_lock_digest", "sample_sheet", "cell_annotation", "panel_registry",
        "genome_build", "annotation_release", "experimental_unit", "thresholds", "colors", "formal_output_root",
    }
    if set(config) != required:
        raise ValueError("project-lock configuration fields are incomplete or unsupported")
    if config["experimental_unit"] != state.context.experimental_unit:
        raise ValueError("project-lock experimental unit differs from the project context")
    locked: list[LockedFile] = []
    for role, key in (
        ("sample-sheet", "sample_sheet"),
        ("cell-annotation", "cell_annotation"),
        ("panel-registry", "panel_registry"),
    ):
        path = _project_path(root, str(config[key]), must_be_file=True)
        locked.append(LockedFile(role, str(path.relative_to(root)), _sha256_file(path)))
    formal_root = _project_path(root, str(config["formal_output_root"]), must_be_file=False)
    if formal_root.exists() and not formal_root.is_dir():
        raise ValueError("formal output root exists but is not a directory")
    genome_build = str(config["genome_build"])
    annotation_release = str(config["annotation_release"])
    if any(item.genome_build is not None and item.genome_build != genome_build for item in state.artifacts):
        raise ValueError("registered artifact genome build differs from the project lock")
    if any(item.annotation_release is not None and item.annotation_release != annotation_release for item in state.artifacts):
        raise ValueError("registered artifact annotation release differs from the project lock")
    values = {
        "schema_version": 1,
        "project_id": state.context.project_id,
        "revision": int(config["revision"]),
        "parent_lock_digest": config["parent_lock_digest"],
        "context_digest": digest_value(state.context.to_dict()),
        "genome_build": genome_build,
        "annotation_release": annotation_release,
        "experimental_unit": str(config["experimental_unit"]),
        "thresholds": config["thresholds"],
        "colors": config["colors"],
        "formal_output_root": str(formal_root.relative_to(root)),
        "files": tuple(locked),
    }
    return ProjectLock(**values, digest=digest_value({
        **values,
        "thresholds": thaw(freeze_mapping(values["thresholds"])),
        "colors": thaw(freeze_mapping(values["colors"])),
        "files": [item.to_dict() for item in locked],
    }))


def verify_project_lock(lock: ProjectLock, state: ProjectState, workspace_root: Path) -> None:
    root = workspace_root.resolve(strict=True)
    if lock.project_id != state.context.project_id or lock.context_digest != digest_value(state.context.to_dict()):
        raise ValueError("project lock belongs to a different project context")
    if lock.experimental_unit != state.context.experimental_unit:
        raise ValueError("project experimental unit drifted after locking")
    for item in lock.files:
        path = _project_path(root, item.relative_path, must_be_file=True)
        if _sha256_file(path) != item.sha256:
            raise ValueError(f"locked project file drifted: {item.role}")


@dataclass(frozen=True)
class ResultStatusEvent:
    id: str
    sequence: int
    artifact_id: str
    from_status: str | None
    to_status: str
    project_state_digest: str
    project_lock_digest: str
    review_id: str | None
    decision_id: str | None
    module_engineering_validated: bool
    module_method_validated: bool
    project_promoted: bool
    figure_contract_digest: str | None
    rationale: str
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "result_status.id"))
        object.__setattr__(self, "artifact_id", validate_identifier(self.artifact_id, "result_status.artifact_id"))
        if self.from_status is not None and self.from_status not in RESULT_STATUSES:
            raise ValueError("result-status source is unsupported")
        if self.to_status not in RESULT_STATUSES or self.to_status not in _TRANSITIONS[self.from_status]:
            raise ValueError("result-status transition is unsupported")
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("result-status sequence must be positive")
        for field in ("project_state_digest", "project_lock_digest", "figure_contract_digest", "digest"):
            value = getattr(self, field)
            if value is not None and (len(value) != 64 or set(value) - set("0123456789abcdef")):
                raise ValueError(f"result_status.{field} must be lowercase SHA-256")
        if not isinstance(self.rationale, str) or len(self.rationale.strip()) < 12:
            raise ValueError("result-status rationale must explain the scientific decision")
        if self.project_promoted != (self.to_status == "FORMAL"):
            raise ValueError("project_promoted is true exactly for FORMAL status")
        if self.to_status == "FORMAL" and not self.module_method_validated:
            raise ValueError("FORMAL status requires method validation")
        basis = self.to_dict(include_digest=False)
        if self.digest != digest_value(basis):
            raise ValueError("result-status event digest is invalid")

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload = {field: getattr(self, field) for field in self.__dataclass_fields__ if field != "digest"}
        if include_digest:
            payload["digest"] = self.digest
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResultStatusEvent":
        return cls(**dict(payload))


@dataclass(frozen=True)
class ResultStatusLedger:
    schema_version: int
    project_id: str
    project_lock_digest: str
    events: tuple[ResultStatusEvent, ...]
    digest: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("result-status ledger schema is unsupported")
        object.__setattr__(self, "project_id", validate_identifier(self.project_id, "result_ledger.project_id"))
        events = tuple(self.events)
        if tuple(item.sequence for item in events) != tuple(range(1, len(events) + 1)):
            raise ValueError("result-status event sequence is not continuous")
        latest: dict[str, str] = {}
        for item in events:
            if item.project_lock_digest != self.project_lock_digest or item.from_status != latest.get(item.artifact_id):
                raise ValueError("result-status history is not a valid lock-bound state machine")
            latest[item.artifact_id] = item.to_status
        object.__setattr__(self, "events", events)
        if self.digest != digest_value(self.to_dict(include_digest=False)):
            raise ValueError("result-status ledger digest is invalid")

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "project_lock_digest": self.project_lock_digest,
            "events": [item.to_dict() for item in self.events],
        }
        if include_digest:
            payload["digest"] = self.digest
        return payload

    @classmethod
    def create(cls, project_id: str, project_lock_digest: str) -> "ResultStatusLedger":
        basis = {"schema_version": 1, "project_id": project_id, "project_lock_digest": project_lock_digest, "events": []}
        return cls(**basis, digest=digest_value(basis))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResultStatusLedger":
        values = dict(payload)
        values["events"] = tuple(ResultStatusEvent.from_dict(item) for item in values["events"])
        return cls(**values)


def transition_result_status(
    ledger: ResultStatusLedger,
    *,
    state: ProjectState,
    lock: ProjectLock,
    workspace_root: Path,
    artifact_id: str,
    to_status: str,
    validation_scope: Mapping[str, Any],
    rationale: str,
    figure_contract_digest: str | None = None,
) -> ResultStatusLedger:
    verify_project_lock(lock, state, workspace_root)
    if ledger.project_id != state.context.project_id or ledger.project_lock_digest != lock.digest:
        raise ValueError("result-status ledger differs from the active project lock")
    artifact = next((item for item in state.artifacts if item.id == artifact_id), None)
    if artifact is None:
        raise ValueError("result-status transition references an unknown artifact")
    if artifact.experimental_unit != lock.experimental_unit:
        raise ValueError("artifact experimental unit differs from the project lock")
    latest = next((item for item in reversed(ledger.events) if item.artifact_id == artifact_id), None)
    from_status = latest.to_status if latest is not None else None
    review = next((item for item in state.artifact_reviews if item.artifact_id == artifact_id), None)
    decision = next((item for item in state.scientific_decisions if item.artifact_id == artifact_id), None)
    engineering_validated = validation_scope.get("engineering_validated") is True
    method_validated = validation_scope.get("method_validated") is True
    if to_status == "FORMAL":
        validate_artifact_execution_chain(state, artifact_id)
        if review is None or review.overall_status not in {"passed", "warning"}:
            raise ValueError("FORMAL promotion requires a nonblocking scientific artifact review")
        if decision is None or not decision.active_evidence:
            raise ValueError("FORMAL promotion requires an explicit retained-evidence decision")
        if not engineering_validated or not method_validated:
            raise ValueError("FORMAL promotion requires engineering- and method-validated module evidence")
        if review.artifact_kind == "figure" and figure_contract_digest is None:
            raise ValueError("FORMAL figure promotion requires its locked figure-contract digest")
    values = {
        "id": f"result-status-{len(ledger.events) + 1:06d}-{artifact_id}",
        "sequence": len(ledger.events) + 1,
        "artifact_id": artifact_id,
        "from_status": from_status,
        "to_status": to_status,
        "project_state_digest": state.state_digest,
        "project_lock_digest": lock.digest,
        "review_id": review.id if review is not None else None,
        "decision_id": decision.id if decision is not None else None,
        "module_engineering_validated": engineering_validated,
        "module_method_validated": method_validated,
        "project_promoted": to_status == "FORMAL",
        "figure_contract_digest": figure_contract_digest,
        "rationale": rationale,
    }
    event = ResultStatusEvent(**values, digest=digest_value(values))
    events = (*ledger.events, event)
    basis = {
        "schema_version": ledger.schema_version,
        "project_id": ledger.project_id,
        "project_lock_digest": ledger.project_lock_digest,
        "events": [item.to_dict() for item in events],
    }
    return ResultStatusLedger(**{**basis, "events": events}, digest=digest_value(basis))
