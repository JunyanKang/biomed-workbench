"""Deterministic cross-artifact contract auditing for scientific projects."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any


_MISSING = object()
_MEDIA_TYPES = {"application/json", "text/markdown", "text/plain"}
_SEVERITIES = {"warning", "major"}
_NORMALIZATIONS = {"exact", "whitespace", "casefold_whitespace"}
_RULE_FIELDS = {"id", "kind", "severity", "artifact_ids", "parameters"}
_PROVENANCE_FIELDS = {
    "contract_id",
    "contract_version",
    "owner",
    "reviewed_at",
    "intended_use",
    "rules_independent_from_artifacts",
    "reviewed_for_completeness",
}


def _normalized_text(value: str, mode: str) -> str:
    if mode == "exact":
        return value
    collapsed = " ".join(value.split())
    return collapsed.casefold() if mode == "casefold_whitespace" else collapsed


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(media_type: str, content: Any) -> str:
    serialized = content if isinstance(content, str) else _canonical(content)
    return hashlib.sha256(f"{media_type}\n{serialized}".encode()).hexdigest()


def _pointer(document: Any, path: str) -> Any:
    if path == "#":
        return document
    if not isinstance(path, str) or not path.startswith("#/"):
        raise ValueError("JSON Pointer fragments must be # for the root or start with #/")
    current = document
    for raw_part in path[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
        elif isinstance(current, list):
            if not part.isdigit() or int(part) >= len(current):
                return _MISSING
            current = current[int(part)]
        else:
            return _MISSING
    return current


def _markdown_section(text: str, heading: str | None) -> tuple[str | None, str | None]:
    if heading is None:
        return text, None
    if not isinstance(heading, str) or heading != heading.strip() or not heading:
        raise ValueError("heading must be null or normalized text")
    lines = text.splitlines(keepends=True)
    fenced = False
    candidates: list[tuple[int, int]] = []
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.rstrip("\r\n"))
        if not match:
            continue
        level, title = len(match.group(1)), match.group(2).strip()
        headings.append((index, level, title))
        if title == heading:
            candidates.append((index, level))
    if not candidates:
        return None, "heading_not_found"
    if len(candidates) > 1:
        return None, "heading_ambiguous"
    start, level = candidates[0]
    end = len(lines)
    for index, candidate_level, _ in headings:
        if index > start and candidate_level <= level:
            end = index
            break
    return "".join(lines[start:end]), None


def _require_parameters(parameters: Any, expected: set[str], kind: str) -> dict[str, Any]:
    if not isinstance(parameters, dict) or set(parameters) != expected:
        raise ValueError(f"{kind} parameters must contain exactly {sorted(expected)}")
    return parameters


def _artifact(rule: dict[str, Any], artifacts: dict[str, dict[str, Any]], count: int) -> list[dict[str, Any]]:
    artifact_ids = rule["artifact_ids"]
    if not isinstance(artifact_ids, list) or len(artifact_ids) != count or len(set(artifact_ids)) != count:
        raise ValueError(f"rule {rule['id']} requires {count} unique artifact_ids")
    if any(identifier not in artifacts for identifier in artifact_ids):
        raise ValueError(f"rule {rule['id']} references an unknown artifact")
    return [artifacts[identifier] for identifier in artifact_ids]


def _json_artifact(rule: dict[str, Any], artifacts: dict[str, dict[str, Any]], count: int = 1) -> list[dict[str, Any]]:
    selected = _artifact(rule, artifacts, count)
    if any(item["media_type"] != "application/json" for item in selected):
        raise ValueError(f"rule {rule['id']} requires JSON artifacts")
    return selected


def _text_artifact(rule: dict[str, Any], artifacts: dict[str, dict[str, Any]], count: int = 1) -> list[dict[str, Any]]:
    selected = _artifact(rule, artifacts, count)
    if any(item["media_type"] not in {"text/markdown", "text/plain"} for item in selected):
        raise ValueError(f"rule {rule['id']} requires text artifacts")
    return selected


def _evaluate_rule(rule: dict[str, Any], artifacts: dict[str, dict[str, Any]]) -> tuple[bool, str, dict[str, Any]]:
    kind = rule["kind"]
    parameters = rule["parameters"]
    if kind in {"json_path_exists", "json_path_absent"}:
        artifact = _json_artifact(rule, artifacts)[0]
        params = _require_parameters(parameters, {"path"}, kind)
        exists = _pointer(artifact["content"], params["path"]) is not _MISSING
        passed = exists if kind == "json_path_exists" else not exists
        return passed, "path requirement satisfied" if passed else "path requirement failed", {"path": params["path"], "exists": exists}

    if kind == "json_value_in":
        artifact = _json_artifact(rule, artifacts)[0]
        params = _require_parameters(parameters, {"path", "values"}, kind)
        if not isinstance(params["values"], list) or not params["values"]:
            raise ValueError("json_value_in values must be a nonempty list")
        value = _pointer(artifact["content"], params["path"])
        passed = value is not _MISSING and value in params["values"]
        return passed, "value is in the declared closed set" if passed else "value is missing or outside the declared closed set", {"path": params["path"], "observed": None if value is _MISSING else value}

    if kind == "json_unique_by":
        artifact = _json_artifact(rule, artifacts)[0]
        params = _require_parameters(parameters, {"path", "field"}, kind)
        values = _pointer(artifact["content"], params["path"])
        if not isinstance(values, list):
            return False, "target path is not an array", {"path": params["path"]}
        extracted = [item.get(params["field"], _MISSING) if isinstance(item, dict) else _MISSING for item in values]
        missing_count = sum(value is _MISSING for value in extracted)
        present = [_canonical(value) for value in extracted if value is not _MISSING]
        duplicate_count = len(present) - len(set(present))
        passed = missing_count == 0 and duplicate_count == 0
        return passed, "array field values are complete and unique" if passed else "array field values are missing or duplicated", {"item_count": len(values), "missing_count": missing_count, "duplicate_count": duplicate_count}

    if kind == "json_records_shape":
        artifact = _json_artifact(rule, artifacts)[0]
        params = _require_parameters(parameters, {"path", "required_fields", "forbidden_fields"}, kind)
        required, forbidden = params["required_fields"], params["forbidden_fields"]
        if (
            not isinstance(required, list)
            or not isinstance(forbidden, list)
            or any(not isinstance(field, str) or not field for field in required + forbidden)
            or len(set(required)) != len(required)
            or len(set(forbidden)) != len(forbidden)
            or set(required) & set(forbidden)
        ):
            raise ValueError("json_records_shape fields must be unique, disjoint, nonempty strings")
        records = _pointer(artifact["content"], params["path"])
        malformed = []
        if not isinstance(records, list):
            return False, "target path is not an array", {"path": params["path"]}
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                malformed.append({"index": index, "missing_fields": required, "forbidden_fields_present": []})
                continue
            missing = sorted(set(required) - set(record))
            present_forbidden = sorted(set(forbidden) & set(record))
            if missing or present_forbidden:
                malformed.append({"index": index, "missing_fields": missing, "forbidden_fields_present": present_forbidden})
        passed = not malformed
        return passed, "record field shape is valid" if passed else "records have missing or forbidden fields", {"record_count": len(records), "violation_count": len(malformed), "violations": malformed[:100]}

    if kind in {"json_reference_integrity", "json_acyclic_relation"}:
        artifact = _json_artifact(rule, artifacts)[0]
        if kind == "json_reference_integrity":
            params = _require_parameters(parameters, {"path", "id_field", "reference_fields"}, kind)
            reference_fields = params["reference_fields"]
            if not isinstance(reference_fields, list) or not reference_fields or len(set(reference_fields)) != len(reference_fields):
                raise ValueError("json_reference_integrity reference_fields must be a unique nonempty list")
        else:
            params = _require_parameters(parameters, {"path", "id_field", "edge_field"}, kind)
            reference_fields = [params["edge_field"]]
        records = _pointer(artifact["content"], params["path"])
        if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
            return False, "target path must be an array of records", {"path": params["path"]}
        identifiers = [record.get(params["id_field"], _MISSING) for record in records]
        valid_ids = all(isinstance(identifier, str) and identifier for identifier in identifiers)
        duplicate_ids = len(identifiers) - len(set(identifiers)) if valid_ids else len(identifiers)
        known = set(identifiers) if valid_ids else set()
        unresolved = []
        adjacency: dict[str, list[str]] = {identifier: [] for identifier in known}
        for index, record in enumerate(records):
            for field in reference_fields:
                raw = record.get(field)
                references = [] if raw is None else raw if isinstance(raw, list) else [raw]
                if any(not isinstance(reference, str) or not reference for reference in references):
                    unresolved.append({"index": index, "field": field, "reference": "invalid_reference_shape"})
                    continue
                for reference in references:
                    if reference not in known:
                        unresolved.append({"index": index, "field": field, "reference": reference})
                    elif kind == "json_acyclic_relation" and valid_ids:
                        adjacency[identifiers[index]].append(reference)
        if kind == "json_reference_integrity":
            passed = valid_ids and duplicate_ids == 0 and not unresolved
            return passed, "record references resolve to unique declared IDs" if passed else "record IDs or references are invalid", {"record_count": len(records), "duplicate_id_count": duplicate_ids, "unresolved_count": len(unresolved), "unresolved": unresolved[:100]}
        cycle_nodes = set()
        if valid_ids and duplicate_ids == 0 and not unresolved:
            visiting, visited = set(), set()

            def visit(node: str, trail: list[str]) -> None:
                if node in visiting:
                    cycle_nodes.update(trail[trail.index(node) :])
                    return
                if node in visited:
                    return
                visiting.add(node)
                trail.append(node)
                for neighbor in adjacency[node]:
                    visit(neighbor, trail)
                trail.pop()
                visiting.remove(node)
                visited.add(node)

            for identifier in sorted(known):
                visit(identifier, [])
        passed = valid_ids and duplicate_ids == 0 and not unresolved and not cycle_nodes
        return passed, "relation references resolve and form an acyclic graph" if passed else "relation has invalid IDs, unresolved references, or cycles", {"record_count": len(records), "duplicate_id_count": duplicate_ids, "unresolved_count": len(unresolved), "cycle_node_ids": sorted(cycle_nodes)}

    if kind == "json_conditional_required":
        artifact = _json_artifact(rule, artifacts)[0]
        params = _require_parameters(parameters, {"if_path", "equals", "required_paths"}, kind)
        if not isinstance(params["required_paths"], list) or not params["required_paths"]:
            raise ValueError("json_conditional_required required_paths must be nonempty")
        trigger = _pointer(artifact["content"], params["if_path"])
        applies = trigger is not _MISSING and trigger == params["equals"]
        missing = [path for path in params["required_paths"] if _pointer(artifact["content"], path) is _MISSING] if applies else []
        passed = not missing
        return passed, "conditional requirement satisfied" if passed else "conditional required paths are missing", {"applies": applies, "missing_paths": missing}

    if kind == "json_equal":
        selected = _json_artifact(rule, artifacts, 2)
        params = _require_parameters(parameters, {"paths"}, kind)
        if not isinstance(params["paths"], list) or len(params["paths"]) != 2:
            raise ValueError("json_equal paths must contain exactly two JSON Pointers")
        values = [_pointer(item["content"], path) for item, path in zip(selected, params["paths"], strict=True)]
        passed = all(value is not _MISSING for value in values) and values[0] == values[1]
        return passed, "declared values are equal" if passed else "declared values are missing or unequal", {"paths": params["paths"], "values_present": [value is not _MISSING for value in values]}

    if kind == "json_closed_set":
        artifact = _json_artifact(rule, artifacts)[0]
        params = _require_parameters(parameters, {"path", "values"}, kind)
        observed = _pointer(artifact["content"], params["path"])
        expected = params["values"]
        if not isinstance(observed, list) or not isinstance(expected, list) or len(set(map(_canonical, expected))) != len(expected):
            passed = False
        else:
            passed = set(map(_canonical, observed)) == set(map(_canonical, expected)) and len(observed) == len(expected)
        return passed, "closed set matches exactly" if passed else "closed set has missing, extra, or duplicate members", {"expected_count": len(expected) if isinstance(expected, list) else None, "observed_count": len(observed) if isinstance(observed, list) else None}

    if kind == "numeric_sum":
        artifact = _json_artifact(rule, artifacts)[0]
        params = _require_parameters(parameters, {"path", "field", "expected", "tolerance"}, kind)
        values = _pointer(artifact["content"], params["path"])
        expected, tolerance = params["expected"], params["tolerance"]
        if not isinstance(expected, (int, float)) or isinstance(expected, bool) or not math.isfinite(float(expected)):
            raise ValueError("numeric_sum expected must be finite")
        if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or not math.isfinite(float(tolerance)) or tolerance < 0:
            raise ValueError("numeric_sum tolerance must be finite and nonnegative")
        numbers = []
        valid = isinstance(values, list)
        if valid:
            for item in values:
                value = item.get(params["field"], _MISSING) if isinstance(item, dict) else _MISSING
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                    valid = False
                    break
                numbers.append(float(value))
        observed = math.fsum(numbers) if valid else None
        passed = observed is not None and abs(observed - float(expected)) <= float(tolerance)
        return passed, "numeric sum matches the declared total" if passed else "numeric sum is invalid or outside tolerance", {"item_count": len(numbers), "observed": observed, "expected": float(expected), "tolerance": float(tolerance)}

    if kind in {"text_contains", "text_absent", "text_ordered"}:
        artifact = _text_artifact(rule, artifacts)[0]
        params = _require_parameters(parameters, {"tokens", "heading", "normalization"}, kind)
        tokens, mode = params["tokens"], params["normalization"]
        if not isinstance(tokens, list) or not tokens or any(not isinstance(token, str) or not token for token in tokens):
            raise ValueError(f"{kind} tokens must be nonempty strings")
        if mode not in _NORMALIZATIONS:
            raise ValueError(f"{kind} normalization is unsupported")
        section, section_error = _markdown_section(artifact["content"], params["heading"])
        if section_error:
            return False, section_error, {"heading": params["heading"]}
        haystack = _normalized_text(section or "", mode)
        needles = [_normalized_text(token, mode) for token in tokens]
        positions = [haystack.find(token) for token in needles]
        if kind == "text_contains":
            passed = all(position >= 0 for position in positions)
        elif kind == "text_absent":
            passed = all(position < 0 for position in positions)
        else:
            passed = all(position >= 0 for position in positions) and positions == sorted(positions) and len(set(positions)) == len(positions)
        return passed, "scoped text requirement satisfied" if passed else "scoped text requirement failed", {"heading": params["heading"], "matched_count": sum(position >= 0 for position in positions), "token_count": len(tokens)}

    if kind == "text_mirror":
        selected = _text_artifact(rule, artifacts, 2)
        params = _require_parameters(parameters, {"normalization"}, kind)
        if params["normalization"] not in _NORMALIZATIONS:
            raise ValueError("text_mirror normalization is unsupported")
        values = [_normalized_text(item["content"], params["normalization"]) for item in selected]
        passed = values[0] == values[1]
        return passed, "text artifacts match under the declared normalization" if passed else "text artifacts drift under the declared normalization", {"normalization": params["normalization"]}

    if kind == "sha256_match":
        artifact = _artifact(rule, artifacts, 1)[0]
        params = _require_parameters(parameters, {"expected_sha256"}, kind)
        expected = params["expected_sha256"]
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
        passed = artifact["digest"] == expected
        return passed, "artifact digest matches" if passed else "artifact digest differs", {"observed_sha256": artifact["digest"], "expected_sha256": expected}

    raise ValueError(f"unsupported contract rule kind: {kind}")


def audit_research_contract(
    artifacts: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    contract_provenance: dict[str, Any],
) -> dict[str, Any]:
    """Audit declared cross-artifact invariants without claiming semantic validity."""
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 128:
        raise ValueError("artifacts must contain 1 to 128 records")
    normalized_artifacts: dict[str, dict[str, Any]] = {}
    artifact_report = []
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict) or set(artifact) != {"id", "role", "media_type", "content"}:
            raise ValueError(f"artifact {index} must contain exactly id, role, media_type, and content")
        identifier, role, media_type, content = artifact["id"], artifact["role"], artifact["media_type"], artifact["content"]
        if not isinstance(identifier, str) or identifier != identifier.strip() or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", identifier) or identifier in normalized_artifacts:
            raise ValueError("artifact IDs must be normalized, safe, and unique")
        if not isinstance(role, str) or role != role.strip() or not 1 <= len(role) <= 500:
            raise ValueError(f"artifact {identifier} role must be normalized meaningful text")
        if media_type not in _MEDIA_TYPES:
            raise ValueError(f"artifact {identifier} has an unsupported media_type")
        if media_type == "application/json":
            if not isinstance(content, (dict, list)):
                raise ValueError(f"artifact {identifier} JSON content must be an object or array")
            size = len(_canonical(content).encode())
        else:
            if not isinstance(content, str):
                raise ValueError(f"artifact {identifier} text content must be a string")
            size = len(content.encode())
        if size > 2_000_000:
            raise ValueError(f"artifact {identifier} exceeds the 2 MB contract-audit limit")
        digest = _digest(media_type, content)
        normalized_artifacts[identifier] = {**artifact, "digest": digest}
        artifact_report.append({"id": identifier, "role": role, "media_type": media_type, "byte_count": size, "sha256": digest})

    if not isinstance(rules, list) or not 1 <= len(rules) <= 512:
        raise ValueError("rules must contain 1 to 512 records")
    seen_rule_ids = set()
    rule_results = []
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict) or set(rule) != _RULE_FIELDS:
            raise ValueError(f"rule {index} has an invalid field set")
        identifier = rule["id"]
        if not isinstance(identifier, str) or identifier != identifier.strip() or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", identifier) or identifier in seen_rule_ids:
            raise ValueError("rule IDs must be normalized kebab-case and unique")
        if rule["severity"] not in _SEVERITIES:
            raise ValueError(f"rule {identifier} has an unsupported severity")
        seen_rule_ids.add(identifier)
        passed, message, observed = _evaluate_rule(rule, normalized_artifacts)
        rule_results.append({
            "id": identifier,
            "kind": rule["kind"],
            "severity": rule["severity"],
            "artifact_ids": rule["artifact_ids"],
            "status": "passed" if passed else "failed",
            "message": message,
            "observed": observed,
        })

    if not isinstance(contract_provenance, dict) or set(contract_provenance) != _PROVENANCE_FIELDS:
        raise ValueError("contract_provenance has an invalid field set")
    for field in ("contract_id", "contract_version", "owner", "reviewed_at", "intended_use"):
        value = contract_provenance[field]
        if not isinstance(value, str) or value != value.strip() or not 1 <= len(value) <= 500:
            raise ValueError(f"contract_provenance.{field} must be normalized meaningful text")
    for field in ("rules_independent_from_artifacts", "reviewed_for_completeness"):
        if not isinstance(contract_provenance[field], bool):
            raise ValueError(f"contract_provenance.{field} must be boolean")

    failed_major = [item["id"] for item in rule_results if item["status"] == "failed" and item["severity"] == "major"]
    failed_warnings = [item["id"] for item in rule_results if item["status"] == "failed" and item["severity"] == "warning"]
    provenance_gates = []
    if not contract_provenance["rules_independent_from_artifacts"]:
        provenance_gates.append("rules_not_independent")
    if not contract_provenance["reviewed_for_completeness"]:
        provenance_gates.append("contract_completeness_not_reviewed")
    if failed_major or provenance_gates:
        overall_status = "blocked"
    elif failed_warnings:
        overall_status = "review_required"
    else:
        overall_status = "passed"
    contract_digest = hashlib.sha256(_canonical({"rules": rules, "provenance": contract_provenance}).encode()).hexdigest()
    return {
        "contract_id": contract_provenance["contract_id"],
        "contract_version": contract_provenance["contract_version"],
        "contract_digest": contract_digest,
        "artifact_count": len(artifact_report),
        "rule_count": len(rule_results),
        "artifacts": artifact_report,
        "rule_results": rule_results,
        "failed_major_rule_ids": failed_major,
        "failed_warning_rule_ids": failed_warnings,
        "provenance_gate_ids": provenance_gates,
        "overall_status": overall_status,
        "semantic_validity_assessed": False,
        "quality_gates": [
            "Rules must be specified independently of the artifacts under audit and reviewed for completeness.",
            "A passing structural contract does not establish scientific validity, evidentiary sufficiency, or correctness of conclusions.",
            "Major rule failures and provenance failures block downstream interpretation; warning failures require review.",
        ],
    }
