"""Append-only publication and verification for scientific evidence-map versions."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..kernel.identity import digest_value
from ..kernel.scientific_evidence_map import ScientificEvidenceMap
from ..kernel.scientific_evidence_map import EvidenceMapPublication
from ..kernel.state import ProjectState
from .scientific_dependency_reports import write_bilingual_reports


INDEX_NAME = "evidence-map-version-index.json"
CURRENT_NAME = "scientific-evidence-map.current.json"
TRANSACTION_NAME = ".evidence-map-publication-transaction.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semver(value: str) -> tuple[int, int, int]:
    return tuple(int(item) for item in value.split("."))  # type: ignore[return-value]


def _validate_transition(previous: dict[str, Any] | None, evidence_map: ScientificEvidenceMap) -> None:
    version = evidence_map.version
    if previous is None:
        if version.revision != 1 or version.parent_map_digest is not None:
            raise ValueError("the first published evidence map must be revision 1 without a parent")
        return
    if version.revision != previous["revision"] + 1:
        raise ValueError("evidence map revisions must increase by exactly one")
    if evidence_map.project_id != previous["project_id"]:
        raise ValueError("an evidence map version chain cannot change project identity")
    if version.parent_map_digest != previous["map_digest"]:
        raise ValueError("evidence map parent digest does not match the latest published map")
    old = _semver(previous["version"])
    new = _semver(version.version)
    if new <= old:
        raise ValueError("evidence map semantic versions must increase")
    expected = {
        "patch": new[0] == old[0] and new[1] == old[1] and new[2] > old[2],
        "minor": new[0] == old[0] and new[1] > old[1],
        "major": new[0] > old[0],
    }
    if not expected.get(version.change_type, False):
        raise ValueError("evidence map semantic version does not match its declared change type")


def _read_index(output_root: Path) -> dict[str, Any]:
    path = output_root / INDEX_NAME
    if not path.exists():
        return {"schema_version": 1, "entries": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("entries"), list):
        raise ValueError("evidence map version index is invalid")
    return payload


def verify_evidence_map_version_index(output_root: Path) -> dict[str, Any]:
    index = _read_index(output_root)
    previous = None
    indexed_directories: set[str] = set()
    for entry in index["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("evidence map version index entry is invalid")
        if previous is None:
            if entry["revision"] != 1 or entry["parent_map_digest"] is not None:
                raise ValueError("evidence map version history does not start at revision 1")
            if entry.get("change_type") != "initial":
                raise ValueError("the first evidence map version must use the initial change type")
        else:
            if entry["project_id"] != previous["project_id"]:
                raise ValueError("evidence map version history changes project identity")
            if entry["revision"] != previous["revision"] + 1 or entry["parent_map_digest"] != previous["map_digest"]:
                raise ValueError("evidence map version history is not a continuous parent-digest chain")
            old = _semver(previous["version"])
            new = _semver(entry["version"])
            if new <= old:
                raise ValueError("evidence map semantic versions must increase")
            expected = {
                "patch": new[0] == old[0] and new[1] == old[1] and new[2] > old[2],
                "minor": new[0] == old[0] and new[1] > old[1],
                "major": new[0] > old[0],
            }
            if not expected.get(entry.get("change_type"), False):
                raise ValueError("evidence map history contains an invalid semantic-version transition")
        version_directory = output_root / "versions" / f"v{entry['version']}"
        indexed_directories.add(version_directory.name)
        for filename, expected in entry["files"].items():
            path = version_directory / filename
            if not path.is_file() or _sha256(path) != expected:
                raise ValueError(f"published evidence-map file is missing or changed: {filename}")
        map_payload = json.loads((version_directory / "scientific-evidence-map.json").read_text(encoding="utf-8"))
        map_basis = {key: value for key, value in map_payload.items() if key != "digest"}
        computed_edge_digest = digest_value(map_payload.get("edges"))
        computed_map_digest = digest_value(map_basis)
        if (
            map_payload.get("digest") != computed_map_digest
            or map_payload.get("edge_table_digest") != computed_edge_digest
            or computed_map_digest != entry["map_digest"]
            or computed_edge_digest != entry["edge_table_digest"]
        ):
            raise ValueError("published evidence map differs from its version index")
        previous = entry
    versions_root = output_root / "versions"
    actual_directories = (
        {path.name for path in versions_root.iterdir() if path.is_dir()}
        if versions_root.is_dir()
        else set()
    )
    if actual_directories != indexed_directories:
        raise ValueError(
            "evidence map versions contain an unindexed or missing immutable directory"
        )
    current_path = output_root / CURRENT_NAME
    if index["entries"]:
        if not current_path.is_file():
            raise ValueError("evidence map current-version pointer is missing")
        current = json.loads(current_path.read_text(encoding="utf-8"))
        last = index["entries"][-1]
        if current != {
            "project_id": last["project_id"],
            "version": last["version"],
            "revision": last["revision"],
            "map_digest": last["map_digest"],
            "edge_table_digest": last["edge_table_digest"],
        }:
            raise ValueError("evidence map current-version pointer is stale")
    elif current_path.exists():
        raise ValueError("evidence map current-version pointer exists without a version history")
    return index


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def _publication_lock(output_root: Path):
    lock_path = output_root / ".evidence-map-publish.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _publish_evidence_map_version_locked(
    evidence_map: ScientificEvidenceMap,
    output_root: Path,
    *,
    workspace_root: Path,
) -> Path:
    evidence_map.validate_integrity()
    output_root.mkdir(parents=True, exist_ok=True)
    index = verify_evidence_map_version_index(output_root)
    previous = index["entries"][-1] if index["entries"] else None
    _validate_transition(previous, evidence_map)
    version_directory = output_root / "versions" / f"v{evidence_map.version.version}"
    if version_directory.exists():
        raise ValueError("evidence map version directory already exists and cannot be overwritten")
    with tempfile.TemporaryDirectory(prefix=".evidence-map-version-", dir=output_root) as temporary:
        staging = Path(temporary) / f"v{evidence_map.version.version}"
        outputs = write_bilingual_reports(
            evidence_map,
            staging,
            workspace_root=workspace_root,
        )
        files = {path.name: _sha256(path) for path in outputs}
        entry = {
            "project_id": evidence_map.project_id,
            "version": evidence_map.version.version,
            "revision": evidence_map.version.revision,
            "parent_map_digest": evidence_map.version.parent_map_digest,
            "change_type": evidence_map.version.change_type,
            "change_summary_zh": evidence_map.version.change_summary_zh,
            "change_summary_en": evidence_map.version.change_summary_en,
            "map_digest": evidence_map.digest,
            "edge_table_digest": evidence_map.edge_table_digest,
            "files": files,
        }
        version_directory.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, version_directory)
    index["entries"].append(entry)
    _atomic_json(output_root / INDEX_NAME, index)
    _atomic_json(
        output_root / CURRENT_NAME,
        {
            "project_id": evidence_map.project_id,
            "version": evidence_map.version.version,
            "revision": evidence_map.version.revision,
            "map_digest": evidence_map.digest,
            "edge_table_digest": evidence_map.edge_table_digest,
        },
    )
    verify_evidence_map_version_index(output_root)
    return version_directory


def publish_evidence_map_version(
    evidence_map: ScientificEvidenceMap,
    output_root: Path,
    *,
    workspace_root: Path,
) -> Path:
    """Publish one immutable version under an exclusive project-level lock."""
    output_root.mkdir(parents=True, exist_ok=True)
    with _publication_lock(output_root):
        return _publish_evidence_map_version_locked(
            evidence_map,
            output_root,
            workspace_root=workspace_root,
        )


def inspect_evidence_map_publication_recovery(
    output_root: Path,
    *,
    state_path: Path | None = None,
) -> dict[str, object]:
    """Report interrupted publication states without changing or deleting files."""
    output_root = output_root.resolve(strict=False)
    journal_path = output_root / TRANSACTION_NAME
    journal = json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.is_file() else None
    index = _read_index(output_root)
    indexed = {f"v{item['version']}" for item in index["entries"]}
    versions_root = output_root / "versions"
    present = {item.name for item in versions_root.iterdir() if item.is_dir()} if versions_root.is_dir() else set()
    staged = sorted(item.name for item in output_root.glob(".evidence-map-version-*") if item.is_dir())
    state_publications: set[str] = set()
    if state_path is not None and state_path.is_file():
        state = ProjectState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
        state_publications = {item.map_digest for item in state.evidence_map_versions}
    indexed_digests = {item["map_digest"] for item in index["entries"]}
    status = "clean"
    if staged:
        status = "staged"
    elif present - indexed:
        status = "unindexed"
    elif state_path is not None and indexed_digests - state_publications:
        status = "state-unregistered"
    elif journal is not None:
        status = str(journal.get("status", "interrupted"))
    return {
        "status": status,
        "journal": journal,
        "staged_directories": staged,
        "unindexed_versions": sorted(present - indexed),
        "state_unregistered_map_digests": sorted(indexed_digests - state_publications) if state_path is not None else [],
    }


def publish_evidence_map_transaction(
    evidence_map: ScientificEvidenceMap,
    publication: EvidenceMapPublication,
    prospective_state: ProjectState,
    *,
    state_path: Path,
    output_root: Path,
    workspace_root: Path,
) -> Path:
    """Publish immutable map files and the already-validated state under one recoverable lock."""
    if publication.map_digest != evidence_map.digest:
        raise ValueError("evidence map publication differs from the map being published")
    if not prospective_state.evidence_map_versions or prospective_state.evidence_map_versions[-1] != publication:
        raise ValueError("prospective project state does not contain the exact evidence map publication")
    output_root.mkdir(parents=True, exist_ok=True)
    journal_path = output_root / TRANSACTION_NAME
    with _publication_lock(output_root):
        if journal_path.exists():
            raise ValueError("an interrupted evidence-map publication requires read-only recovery inspection")
        journal = {
            "schema_version": 1,
            "status": "prepared",
            "map_digest": evidence_map.digest,
            "target_state_digest": prospective_state.state_digest,
            "version": evidence_map.version.version,
        }
        _atomic_json(journal_path, journal)
        try:
            version_directory = _publish_evidence_map_version_locked(
                evidence_map,
                output_root,
                workspace_root=workspace_root,
            )
            journal["status"] = "files-published-state-pending"
            _atomic_json(journal_path, journal)
            _atomic_json(state_path, prospective_state.to_dict())
            journal_path.unlink()
            return version_directory
        except Exception:
            # The journal is intentionally retained. Recovery inspection is
            # read-only and never guesses whether immutable evidence is safe to remove.
            raise
