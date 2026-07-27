#!/usr/bin/env python3
"""Project template for reviewed CFSE or CellTrace generation summaries.

The request must bind generation labels to a predeclared peak model or gates.
This template calculates proliferation metrics only; it never invents peaks.
"""

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


MODULE_ID = "dye-dilution-proliferation"
MODULE_VERSION = "1.0.0"
ENTRYPOINT = "biomed_workbench.capabilities.quantitative_assays:summarize_dye_dilution_proliferation"
REQUIRED_PARAMETER_FIELDS = ("generation_events",)
INPUT_ARTIFACT_PORTS = ("generation_assignments",)
OUTPUT_ARTIFACT_PORTS = ("proliferation_summary",)
QUALITY_GATE_IDS = ("dye-dilution-generation-contract", "dye-dilution-claim-boundary")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Validated project request JSON")
    parser.add_argument("--output", required=True, help="New result and provenance JSON")
    return parser.parse_args()


def load_request(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ProjectTemplateError("request must be a stable regular JSON file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectTemplateError("request is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise ProjectTemplateError("request root must be a JSON object")
    return payload


def validate_request(request: dict[str, Any]) -> None:
    parameters = request.get("parameters")
    artifacts = request.get("artifacts")
    if not isinstance(parameters, dict) or not isinstance(artifacts, list):
        raise ProjectTemplateError("request requires object parameters and array artifacts")
    missing = sorted(set(REQUIRED_PARAMETER_FIELDS) - set(parameters))
    if missing:
        raise ProjectTemplateError(f"parameters omit required fields: {', '.join(missing)}")
    ports = {item.get("port") for item in artifacts if isinstance(item, dict)}
    if not set(INPUT_ARTIFACT_PORTS) <= ports or len(ports) != len(artifacts):
        raise ProjectTemplateError("request must bind one unique reviewed-generation artifact")


def main() -> int:
    args = parse_args()
    request = load_request(Path(args.request))
    validate_request(request)
    result = execute_project_template(MODULE_ID, QUALITY_GATE_IDS, request)
    if result.get("module_id") != MODULE_ID or result.get("module_version") != MODULE_VERSION:
        raise ProjectTemplateError("module identity differs from the template")
    if tuple(result.get("quality_gate_ids", ())) != QUALITY_GATE_IDS:
        raise ProjectTemplateError("quality-gate binding differs from the template")
    write_template_result(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
