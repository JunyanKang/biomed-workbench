"""One-to-one, path-private reconciliation of assimilated source files."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping


class ReconciliationError(ValueError):
    """Raised when private source and design ledgers do not reconcile exactly."""


_EXCLUDED_ACTIONS = {"exclude_generated", "exclude_sensitive", "retire"}
_SUPERSEDED_ACTIONS = {"rewrite_codex_native", "rewrite_workflow", "learn_product_pattern"}
_GUIDANCE_ACTIONS = {"synthesize_guidance", "replace_asset"}
_IMPLEMENTED_ACTIONS = {"rewrite_test"}
_PENDING_ACTIONS = {"rewrite_capability", "redesign_schema"}
_PROVENANCE_ACTIONS = {"retain_provenance"}
_ALL_ACTIONS = _EXCLUDED_ACTIONS | _SUPERSEDED_ACTIONS | _GUIDANCE_ACTIONS | _IMPLEMENTED_ACTIONS | _PENDING_ACTIONS | _PROVENANCE_ACTIONS
_SOURCE_DISPOSITIONS = {"generated_runtime", "merge", "obsolete", "provenance_only", "rewrite", "sensitive"}


def _rows(path: Path, *, skip_manifest_header: bool = False) -> Iterable[dict[str, object]]:
    try:
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                payload = json.loads(line)
                if skip_manifest_header and number == 1 and payload.get("type") == "manifest":
                    continue
                if not isinstance(payload, dict):
                    raise ReconciliationError("private ledger row is not an object")
                yield payload
    except (OSError, json.JSONDecodeError) as exc:
        raise ReconciliationError("private ledger cannot be read") from exc


def _key(row: Mapping[str, object], *, design: bool) -> tuple[str, str, str]:
    digest_field = "source_sha256" if design else "sha256"
    values = (row.get("source"), row.get("path"), row.get(digest_field))
    if not all(isinstance(value, str) and value for value in values):
        raise ReconciliationError("private ledger row lacks source, path, or digest identity")
    return values  # type: ignore[return-value]


def _indexed_rows(path: Path, *, design: bool, skip_manifest_header: bool = False) -> dict[tuple[str, str, str], dict[str, object]]:
    indexed: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in _rows(path, skip_manifest_header=skip_manifest_header):
        key = _key(row, design=design)
        if key in indexed:
            raise ReconciliationError("private ledger contains a duplicate source identity")
        indexed[key] = row
    return indexed


def _classification(action: str) -> tuple[str, str]:
    if action in _EXCLUDED_ACTIONS:
        return "excluded", "generated-sensitive-obsolete-exclusion"
    if action in _SUPERSEDED_ACTIONS:
        return "superseded", "unified-codex-skill-and-research-kernel"
    if action in _GUIDANCE_ACTIONS:
        return "guidance", "source-neutral-scientific-guidance"
    if action in _IMPLEMENTED_ACTIONS:
        return "implemented", "independent-regression-and-release-tests"
    if action in _PENDING_ACTIONS:
        return "pending", "requires-specific-module-and-execution-evidence"
    if action in _PROVENANCE_ACTIONS:
        return "provenance", "notice-and-attribution-surface"
    raise ReconciliationError(f"unknown source design action: {action}")


def _receipt_id(source: str, path: str, digest: str) -> str:
    return hashlib.sha256(f"{source}\0{path}\0{digest}".encode("utf-8")).hexdigest()


def reconcile_ledgers(
    manifest_path: Path,
    design_path: Path,
    *,
    module_count: int,
    registry_digest: str,
    skill_sha256: str,
    test_count: int,
    private_output: Path | None = None,
) -> dict[str, object]:
    if (
        module_count <= 0
        or test_count <= 0
        or len(registry_digest) != 64
        or len(skill_sha256) != 64
        or any(character not in "0123456789abcdef" for character in registry_digest + skill_sha256)
    ):
        raise ReconciliationError("current workbench evidence identity is incomplete")
    source_rows = _indexed_rows(manifest_path, design=False, skip_manifest_header=True)
    design_rows = _indexed_rows(design_path, design=True)
    if len(source_rows) != len(design_rows) or set(source_rows) != set(design_rows):
        raise ReconciliationError("source and design ledgers are not an exact one-to-one mapping")
    if len(source_rows) == 0:
        raise ReconciliationError("source ledgers contain no file records")
    status_counts = Counter()
    source_counts: dict[str, Counter[str]] = defaultdict(Counter)
    cluster_counts: dict[str, Counter[str]] = defaultdict(Counter)
    action_counts = Counter()
    receipt_digest = hashlib.sha256()
    output = private_output.open("w", encoding="utf-8") if private_output is not None else None
    try:
        for source, path, digest in sorted(source_rows):
            source_row = source_rows[(source, path, digest)]
            design = design_rows[(source, path, digest)]
            action = design.get("action")
            cluster = design.get("capability_cluster")
            disposition = source_row.get("disposition")
            if action not in _ALL_ACTIONS or not isinstance(cluster, str) or not cluster:
                raise ReconciliationError("source design record lacks a supported action or capability cluster")
            if disposition not in _SOURCE_DISPOSITIONS:
                raise ReconciliationError("source manifest record lacks a supported disposition")
            status, evidence = _classification(action)
            receipt = {
                "receipt_id": _receipt_id(source, path, digest),
                "source": source,
                "source_sha256": digest,
                "capability_cluster": cluster,
                "source_disposition": disposition,
                "design_action": action,
                "reconciliation_status": status,
                "evidence_class": evidence,
            }
            canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
            receipt_digest.update(canonical.encode("utf-8"))
            receipt_digest.update(b"\n")
            if output is not None:
                private_row = {**receipt, "private_path": path}
                output.write(json.dumps(private_row, sort_keys=True) + "\n")
            status_counts[status] += 1
            source_counts[source][status] += 1
            cluster_counts[cluster][status] += 1
            action_counts[action] += 1
    finally:
        if output is not None:
            output.close()
    reconciled = sum(status_counts[status] for status in ("implemented", "superseded", "guidance", "excluded", "provenance"))
    return {
        "schema_version": 1,
        "passed": True,
        "file_count": len(source_rows),
        "reconciled_count": reconciled,
        "pending_count": status_counts["pending"],
        "status_counts": dict(sorted(status_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "source_status_counts": {source: dict(sorted(counts.items())) for source, counts in sorted(source_counts.items())},
        "cluster_status_counts": {cluster: dict(sorted(counts.items())) for cluster, counts in sorted(cluster_counts.items())},
        "receipt_root_digest": receipt_digest.hexdigest(),
        "current_evidence": {
            "module_count": module_count,
            "registry_digest": registry_digest,
            "skill_sha256": skill_sha256,
            "test_count": test_count,
        },
        "status_definitions": {
            "implemented": "The source behavior is represented by independent tests; capability-level module binding is still required for executable or schema records.",
            "superseded": "The source-specific workflow or interface is replaced by the unified Codex skill and research kernel.",
            "guidance": "Scientific or interaction lessons are retained as source-neutral guidance rather than source code.",
            "excluded": "Generated, sensitive, obsolete, or out-of-scope material is intentionally absent from the plugin.",
            "provenance": "License and attribution information is retained separately from operational code.",
            "pending": "A specific independent module, compatibility row, regression test, and representative execution have not yet been bound to this source record.",
        },
        "limitations": [
            "The public summary is path-free; exact source path membership is verified locally against the ignored private ledgers.",
            "Pending records are not counted as implemented or superseded and prevent a source-union completeness claim.",
        ],
    }
