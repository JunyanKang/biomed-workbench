#!/usr/bin/env python3
"""Project template for select a PCR primer pair.

Codex should inspect the real project artifacts and adapt only the request
construction. Scientific execution remains bound to the versioned module,
format contracts, and blocking quality gates declared below.
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


MODULE_ID = 'pcr-primer-pair-selection'
MODULE_VERSION = '1.0.0'
ENTRYPOINT = 'biomed_workbench.capabilities.molecular:select_pcr_primer_pair'
REQUIRED_PARAMETER_FIELDS = ('template', 'pairs')
INPUT_ARTIFACT_PORTS = ('primer_design',)
OUTPUT_ARTIFACT_PORTS = ('pcr_simulation_request',)
QUALITY_GATE_IDS = ('pcr-primer-selection-contract',)


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


def validate_request_shape(request: dict[str, Any]) -> None:
    parameters = request.get("parameters")
    artifacts = request.get("artifacts")
    if not isinstance(parameters, dict) or not isinstance(artifacts, list):
        raise ProjectTemplateError("request requires object parameters and array artifacts")
    missing = sorted(set(REQUIRED_PARAMETER_FIELDS) - set(parameters))
    if missing:
        raise ProjectTemplateError(f"parameters omit required fields: {', '.join(missing)}")
    observed_ports = {item.get("port") for item in artifacts if isinstance(item, dict)}
    missing_ports = sorted(set(INPUT_ARTIFACT_PORTS) - observed_ports)
    if missing_ports:
        raise ProjectTemplateError(f"artifact snapshots omit ports: {', '.join(missing_ports)}")
    if len(observed_ports) != len(artifacts):
        raise ProjectTemplateError("artifact snapshots must be objects with unique port names")


def validate_result(result: dict[str, object]) -> None:
    if result.get("module_id") != MODULE_ID or result.get("module_version") != MODULE_VERSION:
        raise ProjectTemplateError("executed module identity or version differs from the template")
    if tuple(result.get("quality_gate_ids", ())) != QUALITY_GATE_IDS:
        raise ProjectTemplateError("result does not retain the complete blocking quality-gate binding")
    if not isinstance(result.get("result"), dict) or not isinstance(result.get("provenance"), dict):
        raise ProjectTemplateError("result or provenance is missing after scientific execution")
    if not result.get("request_digest"):
        raise ProjectTemplateError("request digest is missing after scientific execution")


def main() -> int:
    args = parse_args()
    request = load_request(Path(args.request))
    validate_request_shape(request)
    result = execute_project_template(MODULE_ID, QUALITY_GATE_IDS, request)
    validate_result(result)
    write_template_result(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
