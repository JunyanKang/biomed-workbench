#!/usr/bin/env python3
"""Rebind public-case reports after manifest-only product metadata changes."""

from __future__ import annotations

import argparse
import hashlib
import itertools
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


def _prior_manifest(
    module_id: str,
    reported_manifest_sha: str,
) -> tuple[dict[str, object], str]:
    """Reconstruct only the immediately prior execution-contract representation.

    The transformation is deliberately reversible and byte-preserving.  It
    does not consult an arbitrary older Git revision, so unrelated scientific
    manifest changes cannot be smuggled into a metadata re-attestation.
    """
    current = (BUILTIN_ROOT / module_id / "module.json").read_bytes()
    base = current.replace(
        b"packaged_parameterized_workflow",
        b"codex_generated_project_code",
    ).replace(
        b"packaged_parameterized_project_analysis",
        b"codex_generated_project_analysis",
    )
    marker = b'"requires_adaptation": false'
    parts = base.split(marker)
    occurrence_count = len(parts) - 1
    if occurrence_count > 12:
        raise RuntimeError(f"too many adaptation flags for bounded migration: {module_id}")
    for reverse_flags in itertools.product((False, True), repeat=occurrence_count):
        candidate = parts[0]
        for reverse, suffix in zip(reverse_flags, parts[1:]):
            candidate += (
                b'"requires_adaptation": true' if reverse else marker
            ) + suffix
        candidate_sha = hashlib.sha256(candidate).hexdigest()
        if candidate_sha == reported_manifest_sha:
            return json.loads(candidate.decode("utf-8")), candidate_sha
    raise RuntimeError(
        f"public-case manifest is not the reversible prior execution contract: {module_id}"
    )


def _json_differences(
    old: object,
    new: object,
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], object, object]]:
    if isinstance(old, dict) and isinstance(new, dict):
        differences: list[tuple[tuple[str, ...], object, object]] = []
        for key in sorted(set(old) | set(new)):
            if key not in old or key not in new:
                differences.append(((*path, str(key)), old.get(key), new.get(key)))
            else:
                differences.extend(_json_differences(old[key], new[key], (*path, str(key))))
        return differences
    if isinstance(old, list) and isinstance(new, list):
        differences = []
        for index in range(max(len(old), len(new))):
            prior = old[index] if index < len(old) else None
            current = new[index] if index < len(new) else None
            differences.extend(_json_differences(prior, current, (*path, str(index))))
        return differences
    return [] if old == new else [(path, old, new)]


def _allowed_execution_contract_change(
    path: tuple[str, ...],
    old: object,
    new: object,
) -> bool:
    if path == ("agent_protocol", "mode"):
        return old == "codex_generated_project_code" and new == "packaged_parameterized_workflow"
    if len(path) >= 3 and path[-3:] == ("handoff_type", "enum", "0"):
        return (
            old == "codex_generated_project_analysis"
            and new == "packaged_parameterized_project_analysis"
        )
    if len(path) >= 3 and path[0] == "code_templates" and path[-1] == "requires_adaptation":
        return old is True and new is False
    return False


def _validate_metadata_only_manifest_migration(
    module_id: str,
    reported_manifest_sha: object,
) -> dict[str, object] | None:
    current_path = BUILTIN_ROOT / module_id / "module.json"
    current_sha = _sha256(current_path)
    if reported_manifest_sha == current_sha:
        return None
    if not isinstance(reported_manifest_sha, str):
        raise RuntimeError(f"public-case manifest digest is invalid: {module_id}")
    old_manifest, old_sha = _prior_manifest(module_id, reported_manifest_sha)
    current_manifest = json.loads(current_path.read_text(encoding="utf-8"))
    differences = _json_differences(old_manifest, current_manifest)
    if not differences or any(
        not _allowed_execution_contract_change(path, old, new)
        for path, old, new in differences
    ):
        raise RuntimeError(
            f"public-case manifest change is not an execution-contract-only migration: {module_id}"
        )
    return {
        "schema_version": 1,
        "migration_type": "execution-contract-metadata-only",
        "prior_manifest_sha256": old_sha,
        "current_manifest_sha256": current_sha,
        "changed_fields": [".".join(path) for path, _old, _new in differences],
        "templates_unchanged": True,
        "template_sha256": _current_template_hashes(module_id),
        "scientific_outputs_recomputed": False,
        "reason": (
            "The packaged template files and observed scientific outputs are unchanged; "
            "only the release contract was corrected from manual adaptation to a packaged parameterized workflow."
        ),
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
    migration = _validate_metadata_only_manifest_migration(
        module_id,
        module.get("manifest_sha256"),
    )
    new_manifest_sha = _sha256(BUILTIN_ROOT / module_id / "module.json")
    changed = module.get("manifest_sha256") != new_manifest_sha
    module["manifest_sha256"] = new_manifest_sha
    if migration is not None:
        report["execution_contract_migration"] = migration
        changed = True
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
