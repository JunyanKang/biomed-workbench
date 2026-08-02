#!/usr/bin/env python3
"""Reissue a passing report scope after an explicitly reviewed metadata change."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.evidence_scope import (  # noqa: E402
    module_evidence_scope,
    report_module_ids,
)
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


ALLOWED_METADATA_FIELDS = frozenset({
    "maturity",
    "description",
    "limitations",
    "module-registration",
    "additive-unexecuted-adapter",
    "additive-independently-validated-assay-arm",
    "independent-backend-change",
    "compatibility-policy",
    "application-lifecycle",
})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_implementation(report: dict[str, object]) -> dict[str, object] | None:
    value = report.get("implementation")
    if not isinstance(value, dict):
        return None
    relative = value.get("path")
    digest = value.get("sha256")
    if not isinstance(relative, str) or not isinstance(digest, str):
        raise RuntimeError("implementation identity is incomplete")
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or sha256(path) != digest:
        raise RuntimeError("executed implementation is not current")
    return {"path": relative, "sha256": digest}


def reissue(
    path: Path,
    *,
    registry: ModuleRegistry,
    changed_fields: tuple[str, ...],
    reason: str,
) -> bool:
    if path.parent.resolve() != (ROOT / "reports").resolve():
        raise RuntimeError("report must be a direct child of reports/")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("passed") is not True:
        raise RuntimeError("only passing reports can be reissued")
    module_ids = report_module_ids(report)
    if not module_ids:
        raise RuntimeError("report has no module identity")
    if not changed_fields or not set(changed_fields) <= ALLOWED_METADATA_FIELDS:
        raise RuntimeError("changed fields are absent or outside the metadata allow-list")
    prior = report.get("evidence_scope")
    if not isinstance(prior, dict) or len(str(prior.get("module_slice_digest", ""))) != 64:
        raise RuntimeError("report has no valid prior evidence scope")
    current = module_evidence_scope(registry, module_ids).to_dict()
    if prior == current:
        return False
    compatibility_policy_only = set(changed_fields) == {"compatibility-policy"}
    implementation = None if compatibility_policy_only else current_implementation(report)
    if implementation is None and set(changed_fields) - {
        "maturity",
        "description",
        "limitations",
        "module-registration",
        "compatibility-policy",
        "application-lifecycle",
    }:
        raise RuntimeError("a report without implementation identity can only receive presentation metadata changes")
    before = sha256(path)
    report["evidence_scope"] = current
    report["evidence_scope_migration"] = {
        "schema_version": 1,
        "migration_type": "reviewed-metadata-only-scope-reissue",
        "reissued_on": date.today().isoformat(),
        "prior_evidence_scope": prior,
        "current_evidence_scope": current,
        "changed_fields": sorted(set(changed_fields)),
        "reason": reason,
        "executed_implementation_current": implementation,
        "scientific_outputs_recomputed": False,
        "report_sha256_before_reissue": before,
    }
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--changed-field", action="append", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if len(args.reason.strip()) < 40:
        raise SystemExit("--reason must document the reviewed change in at least 40 characters")
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    changed = []
    for report in args.report:
        if reissue(
            report.resolve(),
            registry=registry,
            changed_fields=tuple(args.changed_field),
            reason=args.reason.strip(),
        ):
            changed.append(report.name)
    print(json.dumps({"reissued": changed, "registry_digest": registry.digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
