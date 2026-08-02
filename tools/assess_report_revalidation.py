#!/usr/bin/env python3
"""Classify whether scientific evidence must be reused, reissued, retested, or rerun."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.evidence_scope import (  # noqa: E402
    evidence_scope_is_current,
    report_module_ids,
)
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(report: dict[str, Any]) -> tuple[str, str] | None:
    implementation = report.get("implementation")
    if not isinstance(implementation, dict):
        return None
    candidates = (
        (implementation.get("path"), implementation.get("sha256")),
        (implementation.get("template_path"), implementation.get("template_sha256")),
    )
    for relative, digest in candidates:
        if isinstance(relative, str) and isinstance(digest, str) and len(digest) == 64:
            return relative, digest
    return None


def assess(path: Path, registry: ModuleRegistry) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("passed") is not True:
        return {"report": path.name, "decision": "blocked", "reason": "report is not passing"}
    module_ids = report_module_ids(report)
    if not module_ids:
        return {"report": path.name, "decision": "blocked", "reason": "module identity is absent"}
    identity = _identity(report)
    implementation_current: bool | None = None
    implementation_record = None
    if identity is not None:
        relative, expected = identity
        current_path = (ROOT / relative).resolve()
        safe = current_path.is_relative_to(ROOT) and current_path.is_file()
        observed = sha256(current_path) if safe else None
        implementation_current = observed == expected
        implementation_record = {
            "path": relative,
            "executed_sha256": expected,
            "current_sha256": observed,
            "current": implementation_current,
        }
    scope_current = evidence_scope_is_current(report, registry)
    if implementation_current is False:
        decision = "scientific_rerun_required"
        reason = "the executable scientific implementation differs from the observed run"
    elif implementation_current is None:
        decision = "manual_scientific_review_required"
        reason = "the report does not bind an executable implementation identity"
    elif not scope_current:
        decision = "metadata_scope_review_required"
        reason = "the scientific implementation is unchanged but its module-scoped metadata changed"
    else:
        decision = "reuse_without_recomputation"
        reason = "the executable implementation and dependency-scoped evidence identity are current"
    return {
        "report": path.name,
        "report_sha256": sha256(path),
        "module_ids": module_ids,
        "implementation": implementation_record,
        "evidence_scope_current": scope_current,
        "decision": decision,
        "reason": reason,
    }


def build(paths: list[Path]) -> dict[str, Any]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    records = [assess(path.expanduser().resolve(), registry) for path in paths]
    counts: dict[str, int] = {}
    for record in records:
        counts[record["decision"]] = counts.get(record["decision"], 0) + 1
    return {
        "schema_version": 1,
        "policy": {
            "scientific_implementation_change": "scientific_rerun_required",
            "runtime_or_dependency_policy_change": "targeted_compatibility_retest_required",
            "module_scoped_metadata_change": "metadata_scope_review_required",
            "global_registry_or_documentation_change": "no_scientific_recomputation",
        },
        "registry_digest": registry.digest,
        "records": records,
        "counts": counts,
        "passed": all(record["decision"] == "reuse_without_recomputation" for record in records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build(args.report)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "counts": payload["counts"]}, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
