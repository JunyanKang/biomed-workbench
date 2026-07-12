#!/usr/bin/env python3
"""Generate the module index and v0.2 compatibility catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT, COMPATIBILITY_CATALOG, MODULE_INDEX, write_generated_indexes  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-root", type=Path, default=BUILTIN_ROOT)
    parser.add_argument("--module-index", type=Path, default=MODULE_INDEX)
    parser.add_argument("--catalog", type=Path, default=COMPATIBILITY_CATALOG)
    args = parser.parse_args()
    registry = ModuleRegistry.discover(args.module_root)
    write_generated_indexes(registry, args.module_index, args.catalog)
    print(json.dumps({"module_count": len(registry.all()), "registry_digest": registry.digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
