#!/usr/bin/env python3
"""Create deterministic module-local templates for uncovered bioinformatics modules."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.template_quality import is_bioinformatics_module  # noqa: E402


def _identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _template_source(payload: dict[str, object], template_path: str) -> str:
    manifest = parse_manifest(payload)
    required = tuple(manifest.input_schema.get("required", ()))
    input_ports = tuple(port.name for port in manifest.input_artifacts)
    output_ports = tuple(port.name for port in manifest.output_artifacts)
    gates = tuple(gate.id for gate in manifest.quality_gates if gate.blocks_interpretation)
    return f'''#!/usr/bin/env python3
"""Project template for {manifest.title.lower()}.

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


MODULE_ID = {manifest.id!r}
MODULE_VERSION = {manifest.version!r}
ENTRYPOINT = {manifest.entrypoint!r}
REQUIRED_PARAMETER_FIELDS = {required!r}
INPUT_ARTIFACT_PORTS = {input_ports!r}
OUTPUT_ARTIFACT_PORTS = {output_ports!r}
QUALITY_GATE_IDS = {gates!r}


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
        raise ProjectTemplateError(f"parameters omit required fields: {{', '.join(missing)}}")
    observed_ports = {{item.get("port") for item in artifacts if isinstance(item, dict)}}
    missing_ports = sorted(set(INPUT_ARTIFACT_PORTS) - observed_ports)
    if missing_ports:
        raise ProjectTemplateError(f"artifact snapshots omit ports: {{', '.join(missing_ports)}}")
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
'''


def scaffold(*, check: bool) -> tuple[int, list[str]]:
    changed = []
    covered = 0
    for manifest_path in sorted(BUILTIN_ROOT.glob("*/module.json")):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = parse_manifest(payload)
        if not is_bioinformatics_module(manifest) or manifest.agent_protocol is not None:
            continue
        template_name = f"run_{_identifier(manifest.id)}.py"
        relative = f"templates/{template_name}"
        template_path = manifest_path.parent / relative
        blocking_gates = [gate.id for gate in manifest.quality_gates if gate.blocks_interpretation]
        expected_metadata = [
            {
                "path": relative,
                "language": "python",
                "purpose": f"Execute and validate {manifest.title.lower()} against real project inputs and the module compatibility contract.",
                "quality_gate_ids": blocking_gates,
                "requires_adaptation": True,
            }
        ]
        source = _template_source(payload, relative)
        if payload.get("code_templates") != expected_metadata or not template_path.is_file() or template_path.read_text(encoding="utf-8") != source:
            changed.append(manifest.id)
            if not check:
                template_path.parent.mkdir(parents=True, exist_ok=True)
                template_path.write_text(source, encoding="utf-8")
                payload["code_templates"] = expected_metadata
                manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        covered += 1
    return covered, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    covered, changed = scaffold(check=args.check)
    print(json.dumps({"eligible_module_count": covered, "changed_modules": changed, "passed": not (args.check and changed)}, indent=2))
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
