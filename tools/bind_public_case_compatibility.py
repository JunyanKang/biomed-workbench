#!/usr/bin/env python3
"""Bind passing public cases to the unique compatibility row that cites them."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cited_rows(registry: ModuleRegistry) -> dict[str, list[tuple[str, str, str]]]:
    cited: dict[str, list[tuple[str, str, str]]] = {}
    for manifest in registry.all():
        for row in manifest.compatibility_matrix:
            for evidence_id in row.end_to_end_evidence_ids[1:]:
                cited.setdefault(evidence_id, []).append((manifest.id, manifest.version, row.id))
    return cited


def bind(path: Path, registry: ModuleRegistry, citations: dict[str, list[tuple[str, str, str]]]) -> bool:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("passed") is not True:
        return False
    case_id = report.get("case_id")
    matches = citations.get(str(case_id), [])
    if not matches:
        return False
    if len(matches) != 1:
        raise RuntimeError(f"public evidence id is cited by multiple compatibility rows: {case_id}")
    module_id, module_version, row_id = matches[0]
    module = report.get("module")
    if not isinstance(module, dict) or module.get("id") != module_id or module.get("version") != module_version:
        raise RuntimeError(f"public case module identity differs from its citing compatibility row: {path.name}")
    existing = module.get("compatibility_row_id")
    if existing == row_id:
        return False
    if existing is not None:
        raise RuntimeError(f"public case already binds a different compatibility row: {path.name}")
    before = sha256(path)
    module["compatibility_row_id"] = row_id
    report["compatibility_binding_migration"] = {
        "schema_version": 1,
        "migration_type": "registry-cited-public-evidence-binding",
        "reviewed_on": date.today().isoformat(),
        "case_id": case_id,
        "module_id": module_id,
        "module_version": module_version,
        "compatibility_row_id": row_id,
        "report_sha256_before_binding": before,
        "scientific_outputs_recomputed": False,
        "reason": (
            "The current module compatibility row uniquely cites this already passing public case. "
            "The binding adds release metadata only; source data, execution, parameters and results are unchanged."
        ),
    }
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, default=[])
    args = parser.parse_args()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    citations = cited_rows(registry)
    paths = args.report or sorted((ROOT / "reports").glob("public-case-*.json"))
    changed: list[str] = []
    for path in paths:
        resolved = path.resolve()
        if resolved.parent != (ROOT / "reports").resolve():
            raise RuntimeError("public case must be a direct child of reports/")
        if bind(resolved, registry, citations):
            changed.append(resolved.name)
    print(json.dumps({"passed": True, "bound": changed, "cited_public_cases": len(citations)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
