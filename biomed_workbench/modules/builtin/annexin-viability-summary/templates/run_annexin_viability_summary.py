#!/usr/bin/env python3
"""Project template for an already reviewed Annexin/viability quadrant table.

Adapt only request construction after reviewing compensation, controls, parent
gates, and biological sample identity. This template does not set thresholds.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any

for candidate in Path(__file__).resolve().parents:
    if (candidate / "biomed_workbench").is_dir():
        if str(candidate) not in sys.path: sys.path.insert(0, str(candidate))
        break
from biomed_workbench.project_templates import ProjectTemplateError, execute_project_template, write_template_result

MODULE_ID = "annexin-viability-summary"
MODULE_VERSION = "1.0.0"
ENTRYPOINT = "biomed_workbench.capabilities.quantitative_assays:summarize_annexin_viability_quadrants"
REQUIRED_PARAMETER_FIELDS = ("quadrant_events",)
INPUT_ARTIFACT_PORTS = ("annexin_quadrants",)
OUTPUT_ARTIFACT_PORTS = ("apoptosis_summary",)
QUALITY_GATE_IDS = ("annexin-quadrant-contract", "annexin-interpretation-boundary")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True); parser.add_argument("--output", required=True)
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
    missing = sorted(set(REQUIRED_PARAMETER_FIELDS) - set(parameters))
    if missing:
        raise ProjectTemplateError(f"parameters omit required fields: {', '.join(missing)}")
    ports = {item.get("port") for item in artifacts if isinstance(item, dict)}
    if ports != set(INPUT_ARTIFACT_PORTS) or len(ports) != len(artifacts):
        raise ProjectTemplateError("request must bind one unique reviewed Annexin quadrant artifact")


def validate_result(result: dict[str, object]) -> None:
    if result.get("module_id") != MODULE_ID or result.get("module_version") != MODULE_VERSION:
        raise ProjectTemplateError("module identity differs from the template")
    if tuple(result.get("quality_gate_ids", ())) != QUALITY_GATE_IDS:
        raise ProjectTemplateError("quality-gate binding differs from the template")
    if not isinstance(result.get("result"), dict) or not isinstance(result.get("provenance"), dict):
        raise ProjectTemplateError("result or provenance is missing after quadrant summary")
    if not result.get("request_digest"):
        raise ProjectTemplateError("request digest is missing after quadrant summary")

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
