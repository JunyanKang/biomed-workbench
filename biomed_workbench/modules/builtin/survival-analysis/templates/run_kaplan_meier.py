#!/usr/bin/env python3
"""Project template for bounded Kaplan-Meier survival analysis.

This template is an agent-facing reference. It validates a project JSON file,
calls the product implementation, records runtime provenance, and writes a
finite structured output for review. It does not make treatment, prognosis, or
patient-specific clinical recommendations.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from biomed_workbench.capabilities.clinical import kaplan_meier


def load_payload(path: Path) -> dict[str, Any]:
    """Read and validate the JSON envelope before any analysis is run."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"could not read input JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    return payload


def finite_number(value: Any, field: str, index: int) -> float:
    """Convert one duration and reject non-finite or negative values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field}[{index}] must be numeric")
    number = float(value)
    if not (number >= 0.0 and number < float("inf")):
        raise ValueError(f"{field}[{index}] must be finite and non-negative")
    return number


def normalize_inputs(payload: dict[str, Any]) -> tuple[list[float], list[int], dict[str, Any]]:
    """Extract durations, events, and optional study metadata."""
    durations_raw = payload.get("durations")
    events_raw = payload.get("events")
    metadata = payload.get("metadata", {})
    if not isinstance(durations_raw, list) or not isinstance(events_raw, list):
        raise ValueError("input requires list fields: durations and events")
    if len(durations_raw) != len(events_raw) or not durations_raw:
        raise ValueError("durations and events must be nonempty and aligned")
    if len(durations_raw) > 1_000_000:
        raise ValueError("analysis is bounded to one million records")
    durations = [finite_number(value, "durations", index) for index, value in enumerate(durations_raw)]
    events: list[int] = []
    for index, value in enumerate(events_raw):
        if value not in (0, 1):
            raise ValueError(f"events[{index}] must be 0 for censoring or 1 for event")
        events.append(int(value))
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be an object when supplied")
    return durations, events, metadata or {}


def quality_checks(result: dict[str, Any]) -> list[str]:
    """Run scientific validation checks on the serialized survival output."""
    curve = result.get("curve")
    if not isinstance(curve, list) or not curve:
        raise ValueError("Kaplan-Meier curve output is empty")
    previous_time = -1.0
    previous_survival = 1.0
    warnings: list[str] = []
    for row in curve:
        if not isinstance(row, dict):
            raise ValueError("each curve row must be an object")
        time = float(row["time"])
        survival = float(row["survival"])
        if time < previous_time:
            raise ValueError("curve times are not sorted")
        if not 0.0 <= survival <= previous_survival:
            raise ValueError("survival estimates must be monotonic in [0, 1]")
        previous_time = time
        previous_survival = survival
    if result.get("events", 0) == 0:
        warnings.append("no events were observed; median survival and event-dependent claims are not interpretable")
    if result.get("median_survival") is None:
        warnings.append("median survival was not reached in the observed follow-up")
    return warnings


def build_output(input_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Run the analysis and return output with version provenance."""
    durations, events, metadata = normalize_inputs(payload)
    result = kaplan_meier(durations, events)
    warnings = quality_checks(result)
    return {
        "module_id": "survival-analysis",
        "input_path": str(input_path),
        "metadata": metadata,
        "result": result,
        "quality": {
            "record_count": len(durations),
            "event_count": sum(events),
            "warning_count": len(warnings),
            "warnings": warnings,
            "clinical_boundary": "research summary only; no diagnosis, treatment, triage, or patient-specific prognosis",
        },
        "provenance": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "template": "run_kaplan_meier.py",
            "argv": sys.argv[1:],
        },
    }


def save_output(path: Path, output: dict[str, Any]) -> None:
    """Write the analysis output without silently overwriting directories."""
    if path.exists() and path.is_dir():
        raise ValueError("output path is a directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded Kaplan-Meier survival analysis")
    parser.add_argument("--input-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = load_payload(args.input_json)
    output = build_output(args.input_json, payload)
    save_output(args.output_json, output)


if __name__ == "__main__":
    main()
