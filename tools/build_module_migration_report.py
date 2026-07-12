#!/usr/bin/env python3
"""Rebuild current registry evidence against the immutable 48-capability baseline."""

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
from tools.build_tool_compatibility_matrix import build_compatibility_report  # noqa: E402


def build() -> tuple[dict[str, object], dict[str, object]]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    modules = {module.id: module for module in registry.all()}
    baseline = json.loads((ROOT / "tests" / "fixtures" / "migration-baseline-ids.json").read_text(encoding="utf-8"))
    if set(baseline) != {"schema_version", "module_ids"} or baseline["schema_version"] != 1:
        raise RuntimeError("migration baseline envelope is invalid")
    legacy_ids = set(baseline["module_ids"])
    catalog_rows = {
        row["id"]: row
        for row in json.loads((ROOT / "tools" / "catalog.json").read_text(encoding="utf-8"))["entries"]
    }
    if len(legacy_ids) != 48 or not legacy_ids <= set(modules) or set(catalog_rows) != set(modules):
        raise RuntimeError("current registry no longer preserves the immutable migration baseline")
    migration = {
        "schema_version": 1,
        "legacy_capability_count": len(legacy_ids),
        "module_count": len(modules),
        "module_ids": sorted(modules),
        "expanded_module_ids": sorted(set(modules) - legacy_ids),
        "entrypoint_parity_count": sum(modules[module_id].entrypoint == catalog_rows[module_id]["entrypoint"] for module_id in legacy_ids),
        "input_schema_parity_count": sum(modules[module_id].input_schema == catalog_rows[module_id]["input_schema"] for module_id in legacy_ids),
        "scientific_contract_complete_count": sum(
            bool(module.questions and module.preconditions and module.assumptions and module.quality_gates and module.limitations and module.evidence_effects)
            for module in modules.values()
        ),
        "compatibility_contract_complete_count": sum(bool(module.dependencies and module.compatibility_matrix) for module in modules.values()),
        "registry_digest": registry.digest,
        "runtime_external_paths_present": False,
    }
    return migration, build_compatibility_report(registry)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migration-output", type=Path, default=ROOT / "reports" / "module-registry-migration.json")
    parser.add_argument("--compatibility-output", type=Path, default=ROOT / "reports" / "tool-compatibility-matrix.json")
    args = parser.parse_args()
    migration, compatibility = build()
    args.migration_output.write_text(json.dumps(migration, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.compatibility_output.write_text(json.dumps(compatibility, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_count": migration["module_count"], "expanded_module_count": len(migration["expanded_module_ids"]), "registry_digest": migration["registry_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
