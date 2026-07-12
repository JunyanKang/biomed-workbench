#!/usr/bin/env python3
"""Search the source-neutral Biomed Workbench capability registry."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.catalog import all_capabilities, capability_to_dict, resolve  # noqa: E402
from biomed_workbench.router import score_capability  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="*")
    parser.add_argument("--workflow")
    parser.add_argument("--id", dest="capability_id")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.capability_id:
        try:
            rows = [capability_to_dict(resolve(args.capability_id))]
        except Exception as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
    else:
        capabilities = [item for item in all_capabilities() if not args.workflow or item.workflow == args.workflow]
        query = " ".join(args.query).strip()
        if query:
            capabilities.sort(key=lambda item: (-score_capability(item, query, [args.workflow] if args.workflow else []), item.id))
        rows = [capability_to_dict(item) for item in capabilities[: args.limit]]
    print(json.dumps({"count": len(rows), "capabilities": rows}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
