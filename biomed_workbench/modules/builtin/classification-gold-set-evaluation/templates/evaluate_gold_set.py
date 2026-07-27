#!/usr/bin/env python3
"""Project template for classification gold-set evaluation.

Use this when a project has an independently adjudicated gold set and a model,
agent, or pipeline output that must be evaluated with explicit leakage,
support, threshold, and regression checks.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from biomed_workbench.capabilities.evaluation import evaluate_classification_gold_set


def load_json(path: Path) -> dict[str, Any]:
    """Read a closed-schema JSON request from disk."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"could not read input JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    return payload


def require_list(payload: dict[str, Any], field: str) -> list[Any]:
    """Extract a nonempty list field."""
    value = payload.get(field)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a nonempty list")
    return value


def validate_gold_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the request envelope before the module implementation runs."""
    cases = require_list(payload, "cases")
    labels = require_list(payload, "labels")
    thresholds = require_list(payload, "thresholds")
    gold_provenance = payload.get("gold_provenance")
    baseline_metrics = payload.get("baseline_metrics")
    regression_limit = payload.get("regression_limit", 0.05)
    if not isinstance(gold_provenance, dict):
        raise ValueError("gold_provenance must be an object")
    if baseline_metrics is not None and not isinstance(baseline_metrics, list):
        raise ValueError("baseline_metrics must be a list when supplied")
    if isinstance(regression_limit, bool) or not isinstance(regression_limit, (int, float)):
        raise ValueError("regression_limit must be numeric")
    seen_ids = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"cases[{index}] must be an object")
        identifier = case.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen_ids:
            raise ValueError("case IDs must be nonempty and unique")
        seen_ids.add(identifier)
    return {
        "cases": cases,
        "labels": labels,
        "thresholds": thresholds,
        "gold_provenance": gold_provenance,
        "baseline_metrics": baseline_metrics,
        "regression_limit": float(regression_limit),
    }


def validate_output(result: dict[str, Any]) -> list[str]:
    """Confirm the output carries interpretable quality and provenance fields."""
    if not isinstance(result.get("dataset_digest"), str) or len(result["dataset_digest"]) != 64:
        raise ValueError("result must include a SHA-256 dataset digest")
    if not isinstance(result.get("threshold_results"), list):
        raise ValueError("result must include threshold_results")
    if not isinstance(result.get("interpretation_allowed"), bool):
        raise ValueError("result must include interpretation_allowed")
    warnings: list[str] = []
    if not result["interpretation_allowed"]:
        warnings.append("one or more gold-set gates failed; downstream claims must remain blocked")
    failed_thresholds = [row for row in result["threshold_results"] if isinstance(row, dict) and row.get("passed") is False]
    if failed_thresholds:
        warnings.append(f"{len(failed_thresholds)} declared threshold checks failed")
    return warnings


def build_output(input_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Run the evaluation and serialize review-ready output."""
    request = validate_gold_request(payload)
    result = evaluate_classification_gold_set(**request)
    warnings = validate_output(result)
    return {
        "module_id": "classification-gold-set-evaluation",
        "input_path": str(input_path),
        "result": result,
        "quality": {
            "case_count": len(request["cases"]),
            "label_count": len(request["labels"]),
            "threshold_count": len(request["thresholds"]),
            "warning_count": len(warnings),
            "warnings": warnings,
            "scientific_boundary": "benchmark validity applies only to the declared gold-set version and task",
        },
        "provenance": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "template": "evaluate_gold_set.py",
            "argv": sys.argv[1:],
        },
    }


def write_json(path: Path, output: dict[str, Any]) -> None:
    """Write the structured output JSON."""
    if path.exists() and path.is_dir():
        raise ValueError("output path is a directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a classification gold set")
    parser.add_argument("--input-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = load_json(args.input_json)
    output = build_output(args.input_json, payload)
    write_json(args.output_json, output)


if __name__ == "__main__":
    main()
