#!/usr/bin/env python3
"""Rebind public-case reports after manifest-only product metadata changes."""

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
from biomed_workbench.modules.registry import ModuleRegistry, ModuleRegistryError  # noqa: E402


UPSTREAM_PUBLIC_REPORTS = {
    "public-case-zebrafish-cellrank.json": ROOT / "reports" / "public-case-zebrafish-regvelo.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _current_template_hashes(module_id: str) -> dict[str, str]:
    template_root = BUILTIN_ROOT / module_id / "templates"
    if not template_root.is_dir():
        return {}
    return {
        path.name: _sha256(path)
        for path in sorted(template_root.iterdir())
        if path.is_file()
    }


def _validate_template_binding(module_id: str, evidence: object) -> None:
    current = _current_template_hashes(module_id)
    if isinstance(evidence, str):
        if evidence not in set(current.values()):
            raise RuntimeError(f"public-case template evidence is stale for {module_id}")
        return
    if isinstance(evidence, dict):
        observed = {str(key): str(value) for key, value in evidence.items()}
        if observed != {key: current[key] for key in observed if key in current}:
            raise RuntimeError(f"public-case template evidence is stale for {module_id}")
        return
    raise RuntimeError(f"public-case template evidence is invalid for {module_id}")


def rebind_public_case(path: Path, registry: ModuleRegistry) -> bool:
    report = json.loads(path.read_text(encoding="utf-8"))
    module = report.get("module")
    if not isinstance(report, dict) or not isinstance(module, dict):
        return False
    if report.get("passed") is not True:
        raise RuntimeError(f"public-case report is not passing: {path.name}")
    if report.get("case_type") != "public-data-end-to-end":
        raise RuntimeError(f"public-case report has an unexpected case type: {path.name}")

    module_id = module.get("id")
    module_version = module.get("version")
    if not isinstance(module_id, str) or not isinstance(module_version, str):
        raise RuntimeError(f"public-case report does not declare module identity: {path.name}")
    try:
        manifest = registry.get(module_id)
    except ModuleRegistryError as exc:
        raise RuntimeError(f"public-case report references an unknown module: {module_id}") from exc
    if manifest.version != module_version:
        raise RuntimeError(f"public-case report module version is stale: {module_id}")
    row_id = module.get("compatibility_row_id")
    if row_id not in {row.id for row in manifest.compatibility_matrix}:
        raise RuntimeError(f"public-case report compatibility row is stale: {module_id}")

    _validate_template_binding(module_id, module.get("template_sha256"))
    new_manifest_sha = _sha256(BUILTIN_ROOT / module_id / "module.json")
    changed = module.get("manifest_sha256") != new_manifest_sha
    module["manifest_sha256"] = new_manifest_sha
    if "registry_digest" in module and module["registry_digest"] != registry.digest:
        module["registry_digest"] = registry.digest
        changed = True

    upstream = UPSTREAM_PUBLIC_REPORTS.get(path.name)
    source = report.get("source")
    if upstream is not None and isinstance(source, dict):
        upstream_hash = _sha256(upstream)
        if source.get("upstream_report_sha256") != upstream_hash:
            source["upstream_report_sha256"] = upstream_hash
            changed = True

    if changed:
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, default=[])
    args = parser.parse_args()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    reports = args.report or sorted((ROOT / "reports").glob("public-case-*.json"))
    rebound = []
    skipped = []
    blocked = []
    for report_path in reports:
        try:
            if rebind_public_case(report_path, registry):
                rebound.append(report_path.name)
            else:
                skipped.append(report_path.name)
        except RuntimeError as exc:
            blocked.append({"report": report_path.name, "reason": str(exc)})
    for report_path in reports:
        if report_path.name not in UPSTREAM_PUBLIC_REPORTS:
            continue
        try:
            if rebind_public_case(report_path, registry) and report_path.name not in rebound:
                rebound.append(report_path.name)
        except RuntimeError as exc:
            blocked.append({"report": report_path.name, "reason": str(exc)})
    print(json.dumps({"blocked": blocked, "rebound": sorted(rebound), "registry_digest": registry.digest, "skipped": sorted(skipped)}, sort_keys=True))
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
