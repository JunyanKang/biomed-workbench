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

from biomed_workbench.catalog import CapabilityResolutionError  # noqa: E402
from biomed_workbench.runner import (  # noqa: E402
    CapabilityExecutionError,
    InputValidationError,
    MutationPermissionError,
    run,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capability_id")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--input", default="{}", help="JSON object passed to the capability")
    inputs.add_argument("--input-file", type=Path, help="Path to a JSON object")
    parser.add_argument("--allow-mutation", action="store_true")
    args = parser.parse_args()
    try:
        raw = args.input_file.read_text(encoding="utf-8") if args.input_file else args.input
        payload = json.loads(raw)
        result = run(args.capability_id, payload, allow_mutation=args.allow_mutation)
    except json.JSONDecodeError:
        print(json.dumps({"error": "input is not valid JSON"}), file=sys.stderr)
        return 2
    except (CapabilityResolutionError, InputValidationError, MutationPermissionError, CapabilityExecutionError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
