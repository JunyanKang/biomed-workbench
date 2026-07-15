"""Path-private binding rules for source capability receipts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


class SourceBindingError(ValueError):
    """Raised when a private binding rule is ambiguous or unsafe."""


_RULE_FIELDS = {"id", "resolution", "module_ids", "project_evidence_ids", "criteria"}
_CRITERIA_FIELDS = {"source", "capability_cluster", "path_prefixes", "path_exact"}
_BINDING_FIELDS = {"receipt_id", "resolution", "module_ids", "project_evidence_ids"}


def _receipt_id(row: Mapping[str, Any]) -> str:
    values = (row.get("source"), row.get("path"), row.get("source_sha256"))
    if not all(isinstance(value, str) and value for value in values):
        raise SourceBindingError("design row lacks source, path, or source_sha256")
    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()


def _validate_rule(rule: Any) -> dict[str, Any]:
    if not isinstance(rule, dict) or set(rule) != _RULE_FIELDS:
        raise SourceBindingError("binding rule uses unsupported fields")
    if not isinstance(rule["id"], str) or not rule["id"]:
        raise SourceBindingError("binding rule id is invalid")
    if rule["resolution"] not in {"implemented", "superseded"}:
        raise SourceBindingError("binding rule resolution is invalid")
    for field in ("module_ids", "project_evidence_ids"):
        values = rule[field]
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values) or len(values) != len(set(values)):
            raise SourceBindingError(f"binding rule {field} is invalid")
    if not (rule["module_ids"] or rule["project_evidence_ids"]):
        raise SourceBindingError("binding rule must name module or project evidence")
    criteria = rule["criteria"]
    if not isinstance(criteria, dict) or not set(criteria) <= _CRITERIA_FIELDS or not criteria:
        raise SourceBindingError("binding rule criteria are invalid")
    for field in ("source", "capability_cluster"):
        if field in criteria and (not isinstance(criteria[field], str) or not criteria[field]):
            raise SourceBindingError(f"binding rule criterion {field} is invalid")
    for field in ("path_prefixes", "path_exact"):
        if field in criteria:
            values = criteria[field]
            if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
                raise SourceBindingError(f"binding rule criterion {field} is invalid")
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


def apply_binding_rules(
    design_rows: list[dict[str, Any]],
    existing_bindings: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validated_rules = [_validate_rule(rule) for rule in rules]
    if len({rule["id"] for rule in validated_rules}) != len(validated_rules):
        raise SourceBindingError("binding rule ids must be unique")
    bindings: dict[str, dict[str, Any]] = {}
    for binding in existing_bindings:
        if not isinstance(binding, dict) or set(binding) != _BINDING_FIELDS:
            raise SourceBindingError("existing binding row is invalid")
        receipt = binding.get("receipt_id")
        if not isinstance(receipt, str) or receipt in bindings:
            raise SourceBindingError("existing binding receipt is invalid or duplicated")
        bindings[receipt] = binding
    matches_by_rule = {rule["id"]: 0 for rule in validated_rules}
    matched_receipts: dict[str, str] = {}
    for row in design_rows:
        matched = [rule for rule in validated_rules if _matches(row, rule["criteria"])]
        if len(matched) > 1:
            raise SourceBindingError("one source receipt matches multiple binding rules")
        if not matched:
            continue
        rule = matched[0]
        matches_by_rule[rule["id"]] += 1
        if row.get("action") not in {"rewrite_capability", "redesign_schema"}:
            raise SourceBindingError("binding rule matched a non-pending design action")
        receipt = _receipt_id(row)
        matched_receipts[receipt] = rule["id"]
        candidate = {
            "receipt_id": receipt,
            "resolution": rule["resolution"],
            "module_ids": list(rule["module_ids"]),
            "project_evidence_ids": list(rule["project_evidence_ids"]),
        }
        if receipt in bindings:
            if bindings[receipt] != candidate:
                raise SourceBindingError("binding rule conflicts with an existing receipt binding")
            continue
        bindings[receipt] = candidate
    if any(count == 0 for count in matches_by_rule.values()):
        raise SourceBindingError("every binding rule must match at least one current design row")
    ordered = [bindings[receipt] for receipt in sorted(bindings)]
    return ordered, {
        "schema_version": 2,
        "rule_count": len(validated_rules),
        "matched_receipt_count": len(matched_receipts),
        "total_binding_count": len(ordered),
        "bindings_by_rule": matches_by_rule,
    }


def _read_jsonl(path: Path, *, header: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceBindingError("private JSONL file cannot be read") from exc
    if header is not None:
        if not rows or rows[0] != header:
            raise SourceBindingError("private JSONL header is missing or invalid")
        rows = rows[1:]
    if any(not isinstance(row, dict) for row in rows):
        raise SourceBindingError("private JSONL rows must be objects")
    return rows


def apply_binding_rule_files(design_path: Path, bindings_path: Path, rules_path: Path) -> dict[str, Any]:
    design_rows = _read_jsonl(design_path)
    existing = _read_jsonl(bindings_path, header={"schema_version": 2, "type": "bindings"})
    try:
        rules_payload = json.loads(rules_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceBindingError("private binding rules cannot be read") from exc
    if not isinstance(rules_payload, dict) or set(rules_payload) != {"schema_version", "rules"} or rules_payload["schema_version"] != 1 or not isinstance(rules_payload["rules"], list):
        raise SourceBindingError("private binding rules envelope is invalid")
    bindings, report = apply_binding_rules(design_rows, existing, rules_payload["rules"])
    lines = [json.dumps({"schema_version": 2, "type": "bindings"}, sort_keys=True)]
    lines.extend(json.dumps(binding, sort_keys=True) for binding in bindings)
    encoded = "\n".join(lines) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{bindings_path.name}.", dir=bindings_path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, bindings_path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return report
