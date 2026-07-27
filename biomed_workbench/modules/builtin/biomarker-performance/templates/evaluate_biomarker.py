#!/usr/bin/env python3
"""Project template for binary biomarker performance evaluation.

The template expects a JSON object containing labels, scores, and a prespecified
threshold. It validates the finite inputs, calls the workbench implementation,
and writes bounded research-use output with provenance and interpretation
limits.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import sys
from pathlib import Path
from typing import Any

from biomed_workbench.capabilities.clinical import biomarker_performance


def read_input(path: Path) -> dict[str, Any]:
    """Load a structured JSON biomarker evaluation request."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"could not read input JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    return payload


def finite_score(value: Any, field: str, index: int | None = None) -> float:
    """Normalize one numeric score or threshold with strict finite checks."""
    label = field if index is None else f"{field}[{index}]"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    score = float(value)
    if not math.isfinite(score):
        raise ValueError(f"{label} must be finite")
    return score


def normalize_payload(payload: dict[str, Any]) -> tuple[list[int], list[float], float, dict[str, Any]]:
    """Validate labels, scores, threshold, and optional metadata."""
    labels_raw = payload.get("labels")
    scores_raw = payload.get("scores")
    threshold_raw = payload.get("threshold")
    metadata = payload.get("metadata", {})
    if not isinstance(labels_raw, list) or not isinstance(scores_raw, list):
        raise ValueError("input requires list fields: labels and scores")
    if len(labels_raw) != len(scores_raw) or not labels_raw:
        raise ValueError("labels and scores must be nonempty and aligned")
    if len(labels_raw) > 1_000_000:
        raise ValueError("evaluation is bounded to one million observations")
    labels: list[int] = []
    for index, value in enumerate(labels_raw):
        if value not in (0, 1):
            raise ValueError(f"labels[{index}] must be 0 or 1")
        labels.append(int(value))
    scores = [finite_score(value, "scores", index) for index, value in enumerate(scores_raw)]
    threshold = finite_score(threshold_raw, "threshold")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be an object when supplied")
    return labels, scores, threshold, metadata or {}


def validate_result(result: dict[str, Any]) -> list[str]:
    """Check scientific validity and generate non-blocking warnings."""
    for field in ("sensitivity", "specificity", "positive_predictive_value", "negative_predictive_value", "accuracy", "roc_auc"):
        value = result.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"{field} must be finite")
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError(f"{field} must be within [0, 1]")
    confusion = result.get("confusion")
    if not isinstance(confusion, dict):
        raise ValueError("result.confusion must be an object")
    warnings: list[str] = []
    if confusion.get("true_positive", 0) + confusion.get("false_negative", 0) == 0:
        warnings.append("no positive class observations; sensitivity is not externally generalizable")
    if confusion.get("true_negative", 0) + confusion.get("false_positive", 0) == 0:
        warnings.append("no negative class observations; specificity is not externally generalizable")
    return warnings


def build_output(input_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Run the biomarker evaluation and package provenance."""
    labels, scores, threshold, metadata = normalize_payload(payload)
    result = biomarker_performance(labels, scores, threshold)
    warnings = validate_result(result)
    return {
        "module_id": "biomarker-performance",
        "input_path": str(input_path),
        "metadata": metadata,
        "result": result,
        "quality": {
            "observation_count": len(labels),
            "positive_count": sum(labels),
            "negative_count": len(labels) - sum(labels),
            "warning_count": len(warnings),
            "warnings": warnings,
            "clinical_boundary": "diagnostic research evaluation only; not a clinical diagnostic recommendation",
        },
        "provenance": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "template": "evaluate_biomarker.py",
            "argv": sys.argv[1:],
        },
    }


def write_output(path: Path, output: dict[str, Any]) -> None:
    """Save the output JSON for downstream review."""
    if path.exists() and path.is_dir():
        raise ValueError("output path is a directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate binary biomarker performance")
    parser.add_argument("--input-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = read_input(args.input_json)
    output = build_output(args.input_json, payload)
    write_output(args.output_json, output)


if __name__ == "__main__":
    main()
