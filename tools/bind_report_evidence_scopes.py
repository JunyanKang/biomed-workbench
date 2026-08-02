#!/usr/bin/env python3
"""Bind module-specific reports to their actual manifest/template dependency slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.evidence_scope import module_evidence_scope, report_module_ids  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def bind(path: Path, registry: ModuleRegistry) -> bool:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise RuntimeError(f"report root is not an object: {path.name}")
    module_ids = report_module_ids(report)
    if not module_ids:
        return False
    scope = module_evidence_scope(registry, module_ids).to_dict()
    if report.get("evidence_scope") == scope:
        return False
    if "evidence_scope" in report:
        raise RuntimeError(
            f"report dependency slice changed and requires fresh execution or an "
            f"audited metadata-only migration: {path.name}"
        )
    safe_initial_binding = report.get("registry_digest") == registry.digest
    nested = report.get("module")
    if isinstance(nested, dict) and isinstance(nested.get("id"), str):
        manifest_path = BUILTIN_ROOT / nested["id"] / "module.json"
        safe_initial_binding = safe_initial_binding or nested.get(
            "manifest_sha256"
        ) == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    migration = report.get("execution_contract_migration")
    if isinstance(migration, dict):
        safe_initial_binding = safe_initial_binding or (
            migration.get("migration_type") == "execution-contract-metadata-only"
            and migration.get("current_manifest_sha256")
            == (
                nested.get("manifest_sha256")
                if isinstance(nested, dict)
                else None
            )
        )
    if not safe_initial_binding:
        raise RuntimeError(
            f"historical report lacks a current module-level binding and cannot "
            f"adopt an evidence scope automatically: {path.name}"
        )
    report["evidence_scope"] = scope
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, default=[])
    args = parser.parse_args()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    paths = args.report or sorted((ROOT / "reports").glob("*.json"))
    bound: list[str] = []
    skipped: list[str] = []
    blocked: list[dict[str, str]] = []
    for path in paths:
        try:
            if bind(path, registry):
                bound.append(path.name)
            else:
                skipped.append(path.name)
        except RuntimeError as exc:
            blocked.append({"report": path.name, "reason": str(exc)})
    print(
        json.dumps(
            {"blocked": blocked, "bound": bound, "skipped": skipped},
            sort_keys=True,
        )
    )
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
