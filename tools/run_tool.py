#!/usr/bin/env python3
"""Run one registered Biomed Workbench capability with validated JSON input."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from biomed_workbench.public_execution import PublicExecutionError, execute_public_module  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capability_id")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--input", default="{}", help="JSON object passed to the capability")
    inputs.add_argument("--input-file", type=Path, help="Path to a JSON object")
    parser.add_argument("--allow-mutation", action="store_true")
    parser.add_argument("--project-root", type=Path, help="Existing project directory used for content-addressed artifacts")
    parser.add_argument("--artifact-bindings", type=Path, help="JSON file containing project_context and exact input artifact bindings")
    parser.add_argument("--compatibility-row", help="Exact module compatibility row to execute")
    parser.add_argument("--state", type=Path, help="Project-state path inside --project-root; a project-scoped default is used when omitted")
    args = parser.parse_args()
    try:
        raw = args.input_file.read_text(encoding="utf-8") if args.input_file else args.input
        payload = json.loads(raw)
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get(args.capability_id)
        strict_values = (args.project_root, args.artifact_bindings, args.compatibility_row)
        if any(value is not None for value in strict_values) and not all(value is not None for value in strict_values):
            raise PublicExecutionError(
                "EXECUTION_CONTEXT_INCOMPLETE",
                "strict execution requires --project-root, --artifact-bindings, and --compatibility-row together",
            )
        if not all(value is not None for value in strict_values):
            raise PublicExecutionError(
                "INPUT_ARTIFACT_REQUIRED",
                "public scientific execution requires --project-root, --artifact-bindings, and --compatibility-row",
            )
        bindings = json.loads(args.artifact_bindings.read_text(encoding="utf-8"))
        if not isinstance(bindings, dict):
            raise PublicExecutionError("ARTIFACT_BINDING_INVALID", "--artifact-bindings must decode to an object")
        result_payload = execute_public_module(
            args.capability_id,
            payload,
            project_root=args.project_root,
            artifact_bindings=bindings,
            compatibility_row_id=args.compatibility_row,
            allow_mutation=args.allow_mutation,
            state_path=args.state,
        ).to_dict()
    except json.JSONDecodeError:
        print(json.dumps({"error": "input is not valid JSON"}), file=sys.stderr)
        return 2
    except PublicExecutionError as exc:
        print(json.dumps({"code": exc.code, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(json.dumps({"code": type(exc).__name__, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result_payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
