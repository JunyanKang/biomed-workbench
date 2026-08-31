#!/usr/bin/env python3
"""Version 1.0 execution reference for sequencing-execution-readiness.

This adapter demonstrates the complete product-owned request and result boundary.
It does not install dependencies, infer missing scientific parameters, or convert
readiness into an execution claim. The JSON result must still be reviewed against
the module quality gates and the project design.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.capabilities.ngs_integration import assess_sequencing_readiness

MODULE_ID = "sequencing-execution-readiness"
MODULE_VERSION = "1.0.0"


def load_request(path: Path) -> dict[str, Any]:
    """Load one bounded request object and fail before scientific execution."""
    if not path.is_file():
        raise ValueError("input request is missing")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("input request must be a nonempty JSON object")
    return payload


def execute_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute the registered capability and attach inspectable version provenance."""
    output = assess_sequencing_readiness(**payload)
    if not isinstance(output, dict) or not output:
        raise RuntimeError("validated capability returned no structured output")
    return {
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "quality_review_required": True,
        "result": output,
    }


def write_output(path: Path, result: dict[str, Any]) -> None:
    """Serialize the exact result without altering scientific values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    if reloaded != result:
        raise RuntimeError("output validation failed after serialization")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    request = load_request(args.request)
    result = execute_request(request)
    write_output(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
