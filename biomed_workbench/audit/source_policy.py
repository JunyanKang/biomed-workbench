"""Reviewed scope policy for private clean-room source design ledgers."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


PENDING_ACTIONS = frozenset({"rewrite_capability", "redesign_schema"})
COMPUTE_TARGET = "biomed_workbench/services/compute.py"
COMPUTE_EXCLUDED_TARGET = "excluded/product-boundary/compute-infrastructure"
COMPUTE_EXCLUSION_RATIONALE = (
    "Explicit product boundary: Biomed Workbench does not manage CPU, GPU, containers, Slurm, remote execution, "
    "local-model hosting, environment provisioning, scheduler operations, or compute deployment. Scientific method "
    "selection, compatibility validation, and result quality remain separately in scope."
)
_RULE_FIELDS = {"id", "target", "rationale", "criteria"}
_CRITERIA_FIELDS = {"source", "capability_cluster", "path_prefixes", "path_exact"}


class SourcePolicyError(ValueError):
    """Raised when a source design ledger cannot be refined without ambiguity."""


def _validate_rule(rule: Any) -> dict[str, Any]:
    if not isinstance(rule, dict) or set(rule) != _RULE_FIELDS:
        raise SourcePolicyError("private scope rule uses unsupported fields")
    if not isinstance(rule["id"], str) or not rule["id"].endswith("-explicitly-excluded"):
        raise SourcePolicyError("private scope rule id is invalid")
    if not isinstance(rule["target"], str) or not rule["target"].startswith("excluded/product-boundary/"):
        raise SourcePolicyError("private scope rule target is invalid")
    if not isinstance(rule["rationale"], str) or len(rule["rationale"]) < 80:
        raise SourcePolicyError("private scope rule rationale is insufficient")
    criteria = rule["criteria"]
    if not isinstance(criteria, dict) or not criteria or not set(criteria) <= _CRITERIA_FIELDS:
        raise SourcePolicyError("private scope rule criteria are invalid")
    for field in ("source", "capability_cluster"):
        if field in criteria and (not isinstance(criteria[field], str) or not criteria[field]):
            raise SourcePolicyError(f"private scope rule criterion {field} is invalid")
    for field in ("path_prefixes", "path_exact"):
        if field in criteria:
            values = criteria[field]
            if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
                raise SourcePolicyError(f"private scope rule criterion {field} is invalid")
    return rule


def _matches(row: Mapping[str, Any], criteria: Mapping[str, Any]) -> bool:
    if criteria.get("source") and row.get("source") != criteria["source"]:
        return False
    if criteria.get("capability_cluster") and row.get("capability_cluster") != criteria["capability_cluster"]:
        return False
    path = row.get("path")
    if not isinstance(path, str):
        return False
    if criteria.get("path_prefixes") and not any(path.startswith(prefix) for prefix in criteria["path_prefixes"]):
        return False
    if criteria.get("path_exact") and path not in criteria["path_exact"]:
        return False
    return True


def apply_scope_policy(row: dict[str, Any], rules: Iterable[dict[str, Any]] = ()) -> tuple[dict[str, Any], str | None]:
    """Apply only explicit, reviewed product exclusions to one design row."""
    updated = dict(row)
    if updated.get("target") in {COMPUTE_TARGET, COMPUTE_EXCLUDED_TARGET}:
        if updated.get("capability_cluster") != "runtime_orchestration":
            raise SourcePolicyError("compute target must belong to runtime_orchestration")
        if updated.get("action") in PENDING_ACTIONS or updated.get("target") == COMPUTE_EXCLUDED_TARGET:
            updated["action"] = "retire"
            updated["rationale"] = COMPUTE_EXCLUSION_RATIONALE
            updated["target"] = COMPUTE_EXCLUDED_TARGET
            updated["reuse_mode"] = "none"
            return updated, "compute-infrastructure-explicitly-excluded"
    matched = [rule for rule in rules if _matches(updated, rule["criteria"])]
    if len(matched) > 1:
        raise SourcePolicyError("one source row matches multiple private scope rules")
    if matched:
        rule = matched[0]
        if updated.get("action") not in PENDING_ACTIONS and not (updated.get("action") == "retire" and updated.get("target") == rule["target"]):
            raise SourcePolicyError("private scope rule matched an incompatible non-pending row")
        updated["action"] = "retire"
        updated["rationale"] = rule["rationale"]
        updated["target"] = rule["target"]
        updated["reuse_mode"] = "none"
        return updated, rule["id"]
    return updated, None


def refine_rows(rows: Iterable[dict[str, Any]], rules: Iterable[dict[str, Any]] = ()) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validated_rules = [_validate_rule(rule) for rule in rules]
    if len({rule["id"] for rule in validated_rules}) != len(validated_rules):
        raise SourcePolicyError("private scope rule ids must be unique")
    refined = []
    transitions: Counter[str] = Counter()
    matches: Counter[str] = Counter()
    identities = set()
    for row in rows:
        identity = (row.get("source"), row.get("path"), row.get("source_sha256"))
        if not all(isinstance(value, str) and value for value in identity):
            raise SourcePolicyError("design row lacks source, path, or source_sha256")
        if identity in identities:
            raise SourcePolicyError("design ledger contains a duplicate source identity")
        identities.add(identity)
        original_action = row.get("action")
        updated, rule = apply_scope_policy(row, validated_rules)
        if rule:
            matches[rule] += 1
            if original_action == "retire":
                original_action = "redesign_schema" if row.get("role") == "structured_scientific_asset" else "rewrite_capability"
            transitions[f"{original_action}->{updated['action']}"] += 1
        refined.append(updated)
    if any(matches[rule["id"]] == 0 for rule in validated_rules):
        raise SourcePolicyError("every private scope rule must match at least one current design row")
    return refined, {
        "schema_version": 1,
        "row_count": len(refined),
        "changed_count": sum(transitions.values()),
        "transitions": dict(sorted(transitions.items())),
        "policy_rules": ["compute-infrastructure-explicitly-excluded", *[rule["id"] for rule in validated_rules]],
    }


def refine_ledger(path: Path, rules_path: Path | None = None) -> dict[str, Any]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SourcePolicyError("design ledger cannot be read") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise SourcePolicyError("design ledger rows must be objects")
    rules: list[dict[str, Any]] = []
    if rules_path is not None:
        try:
            payload = json.loads(rules_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SourcePolicyError("private scope rules cannot be read") from exc
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "rules"} or payload["schema_version"] != 1 or not isinstance(payload["rules"], list):
            raise SourcePolicyError("private scope rules envelope is invalid")
        rules = payload["rules"]
    refined, report = refine_rows(rows, rules)
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
