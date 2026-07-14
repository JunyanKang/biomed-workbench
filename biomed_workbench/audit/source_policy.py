"""Reviewed scope policy for private clean-room source design ledgers."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


PENDING_ACTIONS = frozenset({"rewrite_capability", "redesign_schema"})
COMPUTE_TARGET = "biomed_workbench/services/compute.py"
COMPUTE_EXCLUSION_RATIONALE = (
    "Explicit product boundary: Biomed Workbench does not manage CPU, GPU, containers, Slurm, remote execution, "
    "local-model hosting, environment provisioning, scheduler operations, or compute deployment. Scientific method "
    "selection, compatibility validation, and result quality remain separately in scope."
)


class SourcePolicyError(ValueError):
    """Raised when a source design ledger cannot be refined without ambiguity."""


def apply_scope_policy(row: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Apply only explicit, reviewed product exclusions to one design row."""
    updated = dict(row)
    if updated.get("target") == COMPUTE_TARGET:
        if updated.get("capability_cluster") != "runtime_orchestration":
            raise SourcePolicyError("compute target must belong to runtime_orchestration")
        if updated.get("action") in PENDING_ACTIONS:
            updated["action"] = "retire"
            updated["rationale"] = COMPUTE_EXCLUSION_RATIONALE
            updated["target"] = "excluded/product-boundary/compute-infrastructure"
            updated["reuse_mode"] = "none"
            return updated, "compute-infrastructure-explicitly-excluded"
    return updated, None


def refine_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    refined = []
    transitions: Counter[str] = Counter()
    identities = set()
    for row in rows:
        identity = (row.get("source"), row.get("path"), row.get("source_sha256"))
        if not all(isinstance(value, str) and value for value in identity):
            raise SourcePolicyError("design row lacks source, path, or source_sha256")
        if identity in identities:
            raise SourcePolicyError("design ledger contains a duplicate source identity")
        identities.add(identity)
        original_action = row.get("action")
        updated, rule = apply_scope_policy(row)
        if rule:
            transitions[f"{original_action}->{updated['action']}"] += 1
        refined.append(updated)
    return refined, {
        "schema_version": 1,
        "row_count": len(refined),
        "changed_count": sum(transitions.values()),
        "transitions": dict(sorted(transitions.items())),
        "policy_rules": ["compute-infrastructure-explicitly-excluded"],
    }


def refine_ledger(path: Path) -> dict[str, Any]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SourcePolicyError("design ledger cannot be read") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise SourcePolicyError("design ledger rows must be objects")
    refined, report = refine_rows(rows)
    encoded = "".join(json.dumps(row, sort_keys=True) + "\n" for row in refined)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return report
