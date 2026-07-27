#!/usr/bin/env python3
"""Project template for observed dilution-plate CFU enumeration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


for candidate in Path(__file__).resolve().parents:
    if (candidate / "biomed_workbench").is_dir():
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        break

from biomed_workbench.project_templates import ProjectTemplateError, execute_project_template, write_template_result


MODULE_ID = "cfu-enumeration"
MODULE_VERSION = "1.0.0"
QUALITY_GATE_IDS = (
    "cfu-observed-plate-contract",
    "cfu-countable-range-policy",
    "cfu-heterogeneity-and-claim-boundary",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Validated project request JSON")
    parser.add_argument("--output", required=True, help="New result and provenance JSON")
    return parser.parse_args()


def load_request(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ProjectTemplateError("request must be a stable regular JSON file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectTemplateError("request is not readable JSON") from exc
    if not isinstance(value, dict):
        raise ProjectTemplateError("request root must be a JSON object")
    return value


def validate_request(request: dict[str, Any]) -> None:
    parameters = request.get("parameters")
    artifacts = request.get("artifacts")
    if not isinstance(parameters, dict) or not isinstance(artifacts, list):
        raise ProjectTemplateError("request requires object parameters and array artifacts")
    if "plates" not in parameters:
        raise ProjectTemplateError("request must preserve observed plate measurements")
    ports = {item.get("port") for item in artifacts if isinstance(item, dict)}
    if ports != {"dilution_plate_observations"} or len(ports) != len(artifacts):
        raise ProjectTemplateError("request must bind one unique dilution-plate observations artifact")


def validate_result(result: dict[str, object]) -> None:
    if result.get("module_id") != MODULE_ID or result.get("module_version") != MODULE_VERSION:
        raise ProjectTemplateError("module identity differs from the template")
    if tuple(result.get("quality_gate_ids", ())) != QUALITY_GATE_IDS:
        raise ProjectTemplateError("quality-gate binding differs from the template")
    summary = result.get("result")
    required = {"estimate_admissible", "enumeration_status", "plate_results", "quality_gates"}
    if not result.get("request_digest") or not isinstance(summary, dict) or not required.issubset(summary):
        raise ProjectTemplateError("CFU result lacks a request binding or plate diagnostics")


def main() -> int:
    args = parse_args()
    request = load_request(Path(args.request))
    validate_request(request)
    result = execute_project_template(MODULE_ID, QUALITY_GATE_IDS, request)
    validate_result(result)
    write_template_result(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
