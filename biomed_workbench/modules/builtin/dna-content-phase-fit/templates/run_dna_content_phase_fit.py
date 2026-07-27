#!/usr/bin/env python3
"""Project template for diagnostic-bound DNA-content phase fitting.

Only provide DNA values after compensation, debris exclusion, live-singlet
gating, doublet exclusion, and control review. This template never changes
those upstream decisions or converts a blocked fit into phase evidence.
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

from biomed_workbench.project_templates import (
    ProjectTemplateError,
    execute_project_template,
    write_template_result,
)


MODULE_ID = "dna-content-phase-fit"
MODULE_VERSION = "1.0.0"
ENTRYPOINT = "biomed_workbench.capabilities.quantitative_assays:fit_dna_content_phases"
REQUIRED_PARAMETER_FIELDS = ("dna_values",)
INPUT_ARTIFACT_PORTS = ("dna_content_events",)
OUTPUT_ARTIFACT_PORTS = ("cell_cycle_summary",)
QUALITY_GATE_IDS = ("dna-content-fit-admissibility", "dna-content-interpretation-boundary")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Validated project request JSON")
    parser.add_argument("--output", required=True, help="New result and provenance JSON")
    return parser.parse_args()


def load_request(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ProjectTemplateError("request must be a stable regular JSON file")
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectTemplateError("request is not readable JSON") from exc
    if not isinstance(request, dict):
        raise ProjectTemplateError("request root must be a JSON object")
    return request


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
        raise ProjectTemplateError("request must bind one unique reviewed DNA-content artifact")


def validate_result(result: dict[str, object]) -> None:
    if result.get("module_id") != MODULE_ID or result.get("module_version") != MODULE_VERSION:
        raise ProjectTemplateError("module identity differs from the template")
    if tuple(result.get("quality_gate_ids", ())) != QUALITY_GATE_IDS:
        raise ProjectTemplateError("quality-gate binding differs from the template")
    summary = result.get("result")
    if not isinstance(summary, dict) or not isinstance(result.get("provenance"), dict):
        raise ProjectTemplateError("result or provenance is missing after fit")
    if not result.get("request_digest") or "fit_admissible" not in summary:
        raise ProjectTemplateError("fit result lacks its request binding or diagnostic status")


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
