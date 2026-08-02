#!/usr/bin/env python3
"""Migrate still-valid live reports to dependency-scoped evidence identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.evidence_scope import module_evidence_scope, report_module_ids  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry, ModuleRegistryError  # noqa: E402


def _validate_module_report(report: dict[str, object], registry: ModuleRegistry) -> None:
    module_id = report.get("module_id")
    module_version = report.get("module_version")
    if not isinstance(module_id, str) or not isinstance(module_version, str):
        raise RuntimeError("live report does not declare one module and version")
    try:
        manifest = registry.get(module_id)
    except ModuleRegistryError as exc:
        raise RuntimeError(f"live report references an unknown module: {module_id}") from exc
    if manifest.version != module_version:
        raise RuntimeError(f"live report module version is stale: {module_id}")
    row_id = report.get("compatibility_row_id")
    if row_id is not None and row_id not in {row.id for row in manifest.compatibility_matrix}:
        raise RuntimeError(f"live report compatibility row is stale: {module_id}")
    reported_templates = report.get("templates")
    if reported_templates is not None:
        if not isinstance(reported_templates, dict):
            raise RuntimeError(f"live report template evidence is invalid: {module_id}")
        observed = {
            item.get("name"): item.get("sha256")
            for item in reported_templates.values()
            if isinstance(item, dict)
        }
        template_root = BUILTIN_ROOT / module_id / "templates"
        expected = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(template_root.iterdir())
            if path.is_file()
        }
        if observed != expected:
            raise RuntimeError(f"live report template evidence is stale: {module_id}")


def _validate_multi_module_report(report: dict[str, object], registry: ModuleRegistry) -> None:
    module_ids = report.get("module_ids")
    validations = report.get("module_package_validation")
    if not isinstance(module_ids, list) or not module_ids or not isinstance(validations, dict):
        raise RuntimeError("multi-module live report does not declare validated modules")
    if set(module_ids) != set(validations):
        raise RuntimeError("multi-module live report validation coverage is incomplete")
    for module_id in module_ids:
        if not isinstance(module_id, str) or not isinstance(validations[module_id], dict):
            raise RuntimeError("multi-module live report contains an invalid module record")
        try:
            manifest = registry.get(module_id)
        except ModuleRegistryError as exc:
            raise RuntimeError(f"multi-module live report references an unknown module: {module_id}") from exc
        validation = validations[module_id]
        if validation.get("valid") is not True or validation.get("module_version") != manifest.version:
            raise RuntimeError(f"multi-module live report evidence is stale: {module_id}")


def rebind(report_path: Path, registry: ModuleRegistry) -> bool:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("passed") is not True or "registry_digest" not in report:
        raise RuntimeError(f"not a passing registry-bound live report: {report_path.name}")
    if "module_id" in report:
        _validate_module_report(report, registry)
    elif "module_ids" in report:
        _validate_multi_module_report(report, registry)
    else:
        raise RuntimeError(f"live report has no module identity: {report_path.name}")
    scope = module_evidence_scope(registry, report_module_ids(report)).to_dict()
    if report.get("evidence_scope") == scope:
        return False
    # Keep the historical registry digest as provenance of the installation
    # that produced the result.  It is not rewritten and is not evidence
    # validity: currentness is determined by the dependency slice above.
    report["evidence_scope"] = scope
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, default=[])
    args = parser.parse_args()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    reports = args.report or sorted((ROOT / "reports").glob("*-live-verification.json"))
    rebound = []
    skipped = []
    blocked = []
    for path in reports:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "registry_digest" not in data:
            skipped.append(path.name)
            continue
        try:
            if rebind(path, registry):
                rebound.append(path.name)
        except RuntimeError as exc:
            blocked.append({"report": path.name, "reason": str(exc)})
    print(json.dumps({"blocked": blocked, "registry_digest": registry.digest, "rebound": rebound, "skipped": skipped}, sort_keys=True))
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
