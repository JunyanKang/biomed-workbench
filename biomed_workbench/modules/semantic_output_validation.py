"""Module-bound semantic admission for externally produced scientific outputs.

Container reload proves that bytes can be read.  This module separately binds
those bytes to a module, output port, declared result schema, primary-payload
digest, structured quality metrics, and (where available) method-specific
scientific invariants.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


_METADATA_FIELDS = {
    "schema_version",
    "module_id",
    "module_version",
    "port",
    "result_schema_id",
    "primary_payload_sha256",
    "analysis_mode",
    "input_accounting",
    "result_accounting",
    "quality_metrics",
    "limitations",
    "empty_result_reason",
}
_TABULAR_MEDIA = {"text/tab-separated-values": "\t", "text/csv": ","}
_PLACEHOLDER_COLUMNS = {"foo", "bar", "x", "y", "column1", "column2", "unnamed"}


def _semantic_metadata(payloads: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], Mapping[str, Any]]:
    matches = [item for item in payloads if item.get("role") == "semantic-metadata"]
    if len(matches) != 1 or matches[0].get("media_type") != "application/json":
        raise ValueError("observed output requires one JSON semantic-metadata payload")
    path = Path(str(matches[0].get("path", "")))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("semantic metadata cannot be reloaded as JSON") from exc
    if not isinstance(value, dict) or set(value) != _METADATA_FIELDS:
        raise ValueError("semantic metadata fields are incomplete or unsupported")
    return value, matches[0]


def _primary(payloads: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    matches = [item for item in payloads if item.get("role") == "primary"]
    if len(matches) != 1:
        raise ValueError("semantic validation requires one primary payload")
    return matches[0]


def _validate_accounting(metadata: Mapping[str, Any], record_count: int) -> None:
    for field in ("input_accounting", "result_accounting"):
        value = metadata[field]
        if not isinstance(value, dict) or not value:
            raise ValueError(f"semantic metadata {field} must be a nonempty object")
        if any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(observed, (int, float))
            or isinstance(observed, bool)
            or not math.isfinite(float(observed))
            or observed < 0
            for key, observed in value.items()
        ):
            raise ValueError(f"semantic metadata {field} contains invalid counts or measures")
    if metadata["result_accounting"].get("reported_records") != record_count:
        raise ValueError("semantic result accounting differs from the declared record count")
    reason = metadata["empty_result_reason"]
    if record_count == 0:
        if not isinstance(reason, str) or len(reason.strip()) < 12:
            raise ValueError("empty scientific results require a reason and input accounting")
    elif reason is not None:
        raise ValueError("nonempty scientific results cannot declare an empty-result reason")


def _read_table(primary: Mapping[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    delimiter = _TABULAR_MEDIA.get(str(primary.get("media_type")))
    if delimiter is None:
        raise ValueError("the semantic profile requires a tabular primary payload")
    path = Path(str(primary.get("path", "")))
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader((line for line in handle if not line.startswith("#")), delimiter=delimiter)
        columns = list(reader.fieldnames or ())
        rows = list(reader)
    normalized = [item.strip().lower() for item in columns]
    if len(columns) < 2 or len(set(normalized)) != len(normalized):
        raise ValueError("scientific result table requires unique semantic columns")
    if set(normalized) <= _PLACEHOLDER_COLUMNS or any(not item for item in normalized):
        raise ValueError("scientific result table uses placeholder or empty column names")
    return normalized, rows


def _ratio(value: str, field: str) -> tuple[int, int]:
    try:
        numerator_text, denominator_text = value.split("/", 1)
        numerator, denominator = int(numerator_text), int(denominator_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"functional enrichment {field} must use numerator/denominator") from exc
    if denominator <= 0 or numerator < 0 or numerator > denominator:
        raise ValueError(f"functional enrichment {field} is outside its valid range")
    return numerator, denominator


def _probability(value: str, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"functional enrichment {field} must be numeric") from exc
    if not math.isfinite(result) or result < 0 or result > 1:
        raise ValueError(f"functional enrichment {field} must lie in [0, 1]")
    return result


def _validate_functional_enrichment(
    metadata: Mapping[str, Any],
    primary: Mapping[str, Any],
    record_count: int,
) -> None:
    mode = metadata["analysis_mode"]
    if mode not in {"ora", "gsea"}:
        raise ValueError("functional enrichment analysis_mode must be ora or gsea")
    if record_count == 0:
        return
    columns, rows = _read_table(primary)
    required = {
        "ora": {
            "term_id", "term_name", "p_value", "adjusted_p_value", "gene_ratio",
            "background_ratio", "gene_set_size", "overlap_genes",
        },
        "gsea": {
            "term_id", "term_name", "enrichment_score", "normalized_enrichment_score",
            "p_value", "adjusted_p_value", "gene_set_size", "leading_edge",
        },
    }[mode]
    if not required <= set(columns):
        raise ValueError(f"functional enrichment {mode} table omits required scientific columns")
    if len(rows) != record_count:
        raise ValueError("functional enrichment rows differ from result accounting")
    for row in rows:
        raw_p = _probability(row["p_value"], "p_value")
        adjusted_p = _probability(row["adjusted_p_value"], "adjusted_p_value")
        if adjusted_p + 1e-15 < raw_p:
            raise ValueError("functional enrichment adjusted P value is smaller than its raw P value")
        try:
            size = int(row["gene_set_size"])
        except (TypeError, ValueError) as exc:
            raise ValueError("functional enrichment gene_set_size must be an integer") from exc
        if size <= 0:
            raise ValueError("functional enrichment gene_set_size must be positive")
        if mode == "ora":
            overlap, _ = _ratio(row["gene_ratio"], "gene_ratio")
            _ratio(row["background_ratio"], "background_ratio")
            if overlap > size or not row["overlap_genes"].strip():
                raise ValueError("functional enrichment overlap is inconsistent with the gene-set size")
        else:
            for field in ("enrichment_score", "normalized_enrichment_score"):
                try:
                    score = float(row[field])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"functional enrichment {field} must be numeric") from exc
                if not math.isfinite(score):
                    raise ValueError(f"functional enrichment {field} must be finite")
            if not row["leading_edge"].strip():
                raise ValueError("GSEA results require a nonempty leading edge")


def validate_observed_output_semantics(
    *,
    content: Mapping[str, Any],
    payloads: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
    profile: str,
) -> bool:
    """Validate module identity, accounting, primary bytes, and profile semantics."""
    metadata, _ = _semantic_metadata(payloads)
    primary = _primary(payloads)
    expected_identity = {
        "schema_version": 1,
        "module_id": context.get("module_id"),
        "module_version": context.get("module_version"),
        "port": context.get("port"),
        "result_schema_id": f"{context.get('module_id')}:{context.get('port')}:{profile}",
    }
    if any(metadata.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("semantic metadata identity differs from the frozen module output contract")
    primary_path = Path(str(primary.get("path", "")))
    if hashlib.sha256(primary_path.read_bytes()).hexdigest() != metadata["primary_payload_sha256"]:
        raise ValueError("semantic metadata is not bound to the imported primary payload")
    if not isinstance(metadata["limitations"], list) or any(
        not isinstance(item, str) or len(item.strip()) < 4 for item in metadata["limitations"]
    ):
        raise ValueError("semantic metadata limitations must be an explicit string array")
    metrics = metadata["quality_metrics"]
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError("semantic metadata requires structured quality metrics")
    record_count = int(content.get("record_count", -1))
    _validate_accounting(metadata, record_count)
    if profile == "functional-enrichment-v1":
        _validate_functional_enrichment(metadata, primary, record_count)
    elif profile != f"{context.get('module_id')}-{str(context.get('port')).replace('_', '-')}-v1":
        raise ValueError("observed output semantic profile is unsupported")
    elif primary.get("media_type") in _TABULAR_MEDIA:
        _, rows = _read_table(primary)
        if len(rows) != record_count:
            raise ValueError("scientific result table differs from declared result accounting")
    return True


def evaluate_structured_gate(
    *,
    payloads: Sequence[Mapping[str, Any]],
    metric_key: str,
    metric_type: str,
    operator: str,
    threshold: object,
) -> dict[str, object]:
    """Read a structured metric and let the plugin, not the caller, compare it."""
    metadata, evidence_payload = _semantic_metadata(payloads)
    metrics = metadata["quality_metrics"]
    if not isinstance(metrics, dict) or metric_key not in metrics:
        raise ValueError(f"semantic quality metric is missing: {metric_key}")
    observed = metrics[metric_key]
    expected = {
        "boolean": bool,
        "integer": int,
        "number": (int, float),
        "string": str,
    }[metric_type]
    if not isinstance(observed, expected) or (metric_type in {"integer", "number"} and isinstance(observed, bool)):
        raise ValueError(f"semantic quality metric has the wrong type: {metric_key}")
    if metric_type == "number" and not math.isfinite(float(observed)):
        raise ValueError(f"semantic quality metric is non-finite: {metric_key}")
    comparisons = {
        "equals": lambda: observed == threshold,
        "not-equals": lambda: observed != threshold,
        "greater-than": lambda: observed > threshold,
        "greater-or-equal": lambda: observed >= threshold,
        "less-than": lambda: observed < threshold,
        "less-or-equal": lambda: observed <= threshold,
    }
    passed = bool(comparisons[operator]())
    return {
        "status": "passed" if passed else "failed",
        "observed_metric": json.dumps(observed, sort_keys=True, separators=(",", ":")),
        "threshold": json.dumps(
            {"operator": operator, "value": threshold}, sort_keys=True, separators=(",", ":")
        ),
        "evidence_payload_sha256": evidence_payload["sha256"],
    }
