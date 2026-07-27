#!/usr/bin/env python3
"""Compile one natural-language objective into an agent-ready research plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.research_plan import compile_research_plan  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("objective")
    parser.add_argument("--per-workflow", type=int, default=3)
    args = parser.parse_args()
    try:
        payload = compile_research_plan(args.objective, per_workflow=args.per_workflow)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
