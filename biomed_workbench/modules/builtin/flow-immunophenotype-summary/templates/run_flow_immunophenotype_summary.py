#!/usr/bin/env python3
"""Execute reviewed flow-cytometry marker patterns with project-bound provenance.

Build the request only after checking the actual compensation, transformation,
threshold basis, panel identity, parent gates, and biological sample identity.
This template reports marker-rule patterns and never upgrades them into a cell
identity or clinical conclusion.
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


MODULE_ID = "flow-immunophenotype-summary"
MODULE_VERSION = "1.0.0"
REQUIRED_PARAMETERS = ("events", "gates", "population_rules", "control_review")
INPUT_PORTS = ("events", "gates")
QUALITY_GATES = ("immunophenotype-event-lineage", "immunophenotype-control-review", "immunophenotype-identity-boundary")


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
    missing = sorted(set(REQUIRED_PARAMETERS) - set(parameters))
    if missing:
        raise ProjectTemplateError(f"parameters omit required fields: {', '.join(missing)}")
    ports = [item.get("port") for item in artifacts if isinstance(item, dict)]
    if set(ports) != set(INPUT_PORTS) or len(ports) != len(INPUT_PORTS):
        raise ProjectTemplateError("request must bind one event table and one reviewed parent-gate artifact")
    review = parameters["control_review"]
    if not isinstance(review, dict) or not all(review.get(key) is True for key in ("compensation_reviewed", "transformation_declared", "threshold_basis_reviewed")):
        raise ProjectTemplateError("control review must pass before descriptive marker-pattern interpretation")


def validate_result(result: dict[str, object]) -> None:
    if result.get("module_id") != MODULE_ID or result.get("module_version") != MODULE_VERSION:
        raise ProjectTemplateError("module identity or version differs from the template")
    if tuple(result.get("quality_gate_ids", ())) != QUALITY_GATES:
        raise ProjectTemplateError("result does not retain every blocking quality gate")
    if not isinstance(result.get("result"), dict) or not result.get("request_digest"):
        raise ProjectTemplateError("result, provenance, or request digest is missing")
    if result["result"].get("review_status") != "eligible_for_descriptive_pattern_interpretation":
        raise ProjectTemplateError("marker-pattern result is blocked pending control review")


def main() -> int:
    args = parse_args()
    request = load_request(Path(args.request))
    validate_request(request)
    result = execute_project_template(MODULE_ID, QUALITY_GATES, request)
    validate_result(result)
    write_template_result(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
