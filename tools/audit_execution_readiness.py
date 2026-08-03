#!/usr/bin/env python3
"""Audit whether every released analysis runs without editing source templates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.execution_readiness import assess_execution_readiness  # noqa: E402
from biomed_workbench.modules.evidence_scope import (  # noqa: E402
    evidence_scope_is_current,
    report_module_ids,
)
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def _implementation_is_current(report: dict[str, object]) -> bool:
    implementation = report.get("implementation")
    if not isinstance(implementation, dict):
        return True
    relative = implementation.get("path")
    digest = implementation.get("sha256")
    if relative is None and digest is None:
        return True
    if not isinstance(relative, str) or not isinstance(digest, str):
        return False
    path = ROOT / relative
    return (
        path.is_file()
        and len(digest) == 64
        and hashlib.sha256(path.read_bytes()).hexdigest() == digest
    )


def build() -> dict[str, object]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    validated_modules: set[str] = set()
    validated_assays: dict[str, set[str]] = {}
    reports_root = ROOT / "reports"
    for path in sorted(reports_root.glob("public-case-*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(report, dict)
            and report.get("passed") is True
            and evidence_scope_is_current(report, registry)
            and _implementation_is_current(report)
        ):
            module_ids = report_module_ids(report)
            validated_modules.update(module_ids)
            assay_values: list[str] = []
            if isinstance(report.get("assay"), str):
                assay_values.append(report["assay"])
            if isinstance(report.get("assays"), list):
                assay_values.extend(value for value in report["assays"] if isinstance(value, str))
            execution = report.get("execution")
            if isinstance(execution, dict) and isinstance(execution.get("assay"), str):
                assay_values.append(execution["assay"])
            for module_id in module_ids:
                validated_assays.setdefault(module_id, set()).update(value.lower() for value in assay_values)
    records = [
        assess_execution_readiness(
            BUILTIN_ROOT / manifest.id,
            manifest,
            public_data_validated=manifest.id in validated_modules,
            public_data_validated_assays=frozenset(validated_assays.get(manifest.id, set())),
        ).to_dict()
        for manifest in registry.all()
    ]
    counts: dict[str, int] = {}
    for record in records:
        counts[record["level"]] = counts.get(record["level"], 0) + 1
    blocked = [record["module_id"] for record in records if not record["executor_ready"]]
    axis_counts = {
        axis: sum(record["evidence_axes"][axis] is True for record in records)
        for axis in (
            "contract_valid",
            "adapter_static_reachable",
            "controlled_fixture_executed_and_reloaded",
            "representative_or_public_case_validated",
            "current_project_reviewed",
        )
    }
    return {
        "schema_version": 4,
        "registry_digest": registry.digest,
        "module_count": len(records),
        "counts": counts,
        "axis_counts": axis_counts,
        "blocked_module_ids": blocked,
        "passed": axis_counts["contract_valid"] == len(records),
        "single_maturity_count_is_authoritative": False,
        "status_model": {
            "contract_valid": "The versioned module contract parses and all referenced packaged assets satisfy release rules.",
            "adapter_static_reachable": "At least one declared execution surface reaches packaged implementation code rather than only a suggestion or editable template.",
            "controlled_fixture_executed_and_reloaded": "A controlled fixture has exercised the registered implementation and its declared output reload path.",
            "representative_or_public_case_validated": "A current dependency-scoped representative or public-data case passed its declared gates.",
            "current_project_reviewed": "The current project has observed execution, artifact reload, scientific review, and an accepted decision; generic release reports never set this axis.",
            "scaffolded": "A no-edit contract exists, but no external scientific workflow is executed.",
            "executable": "A controlled fixture executes the registered implementation and reloads declared outputs; this does not imply current-project scientific completion.",
            "validated": "Executable evidence is supplemented by a current dependency-scoped public-data acceptance case.",
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build()
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
