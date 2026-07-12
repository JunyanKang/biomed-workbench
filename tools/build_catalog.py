#!/usr/bin/env python3
"""Generate the v0.2 compatibility catalog from independent modules."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT, build_compatibility_catalog  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "tools" / "catalog.json")
    args = parser.parse_args()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    for module in registry.all():
        registry.resolve_entrypoint(module.id)
    payload = build_compatibility_catalog(registry)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"entry_count": payload["entry_count"], "output": args.output.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
