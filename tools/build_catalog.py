#!/usr/bin/env python3
"""Generate the publishable operational catalog from the validated registry."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.catalog import all_capabilities, capability_to_dict, resolve_entrypoint  # noqa: E402
from biomed_workbench.version import VERSION  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tools" / "catalog.json")
    args = parser.parse_args()
    capabilities = all_capabilities()
    for capability in capabilities:
        resolve_entrypoint(capability)
    payload = {"schema_version": 2, "version": VERSION, "entry_count": len(capabilities), "entries": [capability_to_dict(item) for item in capabilities]}
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"entry_count": len(capabilities), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
