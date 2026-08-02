#!/usr/bin/env python3
"""Reissue observed evidence after a checksum-bound runtime asset relocation."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.evidence_scope import module_evidence_scope  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


MODULE_ID = "bulk-rbp-rna-binding"
RELOCATIONS = {
    "rip-seq": {
        "reports": (
            "bulk-rbp-rna-binding-ripseq-live-verification.json",
            "public-case-ripseeker-prc2-official.json",
        ),
        "implementation": "biomed_workbench/implementations/ripseeker.py",
        "prior_implementation_sha256": "3f853380eec012cea90be7de0d2eea9fbc4c1316ab0d8dfada38d9e647554511",
        "assets": (
            {
                "prior_path": "biomed_workbench/modules/builtin/bulk-rbp-rna-binding/templates/Dockerfile.ripseeker",
                "prior_sha256": "19f84accdbed146e975023849161fc37f8856b04d38a7af96e357fde00b2803c",
                "current_path": "biomed_workbench/runtime_compat/ripseeker/Dockerfile",
                "current_sha256": "362dd0358fda33ce55ca57334263474b83b16d561c2b215d6f9660259829d3f4",
                "content_change": "Docker build-context path only",
            },
            {
                "prior_path": "biomed_workbench/modules/builtin/bulk-rbp-rna-binding/templates/ripseeker-bioconductor-3.11-namespace.patch",
                "prior_sha256": "085b74e5eab2f18fda66eeff8b9d770738398f46eb8934bc6042a7601a30f5a4",
                "current_path": "biomed_workbench/runtime_compat/ripseeker/bioconductor-3.11-namespace.patch",
                "current_sha256": "085b74e5eab2f18fda66eeff8b9d770738398f46eb8934bc6042a7601a30f5a4",
                "content_change": "none",
            },
        ),
        "obsolete_template_keys": (
            "Dockerfile.laceseq",
            "Dockerfile.ripseeker",
            "ripseeker-bioconductor-3.11-namespace.patch",
        ),
    },
    "lace-seq": {
        "reports": (
            "bulk-rbp-rna-binding-laceseq-live-verification.json",
            "public-case-laceseq-srr10173391-srr10173407.json",
        ),
        "implementation": "biomed_workbench/implementations/laceseq_fastq.py",
        "prior_implementation_sha256": "4b0da0113f4a38ee35639ca9ec2f6f511b55b12a2b9c8f53aad6d810f7c81a69",
        "assets": (
            {
                "prior_path": "biomed_workbench/modules/builtin/bulk-rbp-rna-binding/templates/Dockerfile.laceseq",
                "prior_sha256": "51ab5ceb783fe0e7d660b69d6e2900327a952e82231ec34abf75be52381f7e79",
                "current_path": "biomed_workbench/runtime_compat/laceseq/Dockerfile",
                "current_sha256": "51ab5ceb783fe0e7d660b69d6e2900327a952e82231ec34abf75be52381f7e79",
                "content_change": "none",
            },
        ),
        "obsolete_template_keys": (
            "Dockerfile.laceseq",
            "Dockerfile.ripseeker",
            "ripseeker-bioconductor-3.11-namespace.patch",
        ),
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_asset_records(value: Any, assets: tuple[dict[str, str], ...]) -> int:
    replacements = 0
    if isinstance(value, dict):
        path = value.get("path")
        for asset in assets:
            if path == asset["prior_path"]:
                if value.get("sha256") != asset["prior_sha256"]:
                    raise RuntimeError(f"stale prior checksum for {path}")
                value["path"] = asset["current_path"]
                value["sha256"] = asset["current_sha256"]
                replacements += 1
            elif path == asset["current_path"]:
                if value.get("sha256") != asset["current_sha256"]:
                    raise RuntimeError(f"stale current checksum for {path}")
        for child in value.values():
            replacements += replace_asset_records(child, assets)
    elif isinstance(value, list):
        for child in value:
            replacements += replace_asset_records(child, assets)
    return replacements


def migrate_report(path: Path, assay: str, spec: dict[str, Any], scope: dict[str, Any]) -> bool:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("passed") is not True or report.get("assay") != assay:
        raise RuntimeError(f"not a passing {assay} report: {path}")
    implementation = report.get("implementation")
    implementation_path = ROOT / spec["implementation"]
    current_implementation_sha256 = sha256(implementation_path)
    if not isinstance(implementation, dict) or implementation.get("path") != spec["implementation"]:
        raise RuntimeError(f"unexpected implementation identity: {path}")
    existing = report.get("runtime_asset_relocation")
    if implementation.get("sha256") == current_implementation_sha256 and isinstance(existing, dict):
        return False
    if implementation.get("sha256") != spec["prior_implementation_sha256"]:
        raise RuntimeError(f"prior implementation checksum is not approved: {path}")
    for asset in spec["assets"]:
        current_path = ROOT / asset["current_path"]
        if not current_path.is_file() or sha256(current_path) != asset["current_sha256"]:
            raise RuntimeError(f"current runtime asset differs from the approved relocation: {current_path}")
    prior_scope = report.get("evidence_scope")
    replacements = replace_asset_records(report, spec["assets"])
    templates = report.get("templates")
    if isinstance(templates, dict):
        for key in spec["obsolete_template_keys"]:
            templates.pop(key, None)
    runtime = report.get("execution", {}).get("runtime")
    if assay == "lace-seq" and isinstance(runtime, dict) and isinstance(runtime.get("dockerfile"), dict):
        dockerfile = runtime["dockerfile"]
        if dockerfile.get("sha256") != spec["assets"][0]["current_sha256"]:
            raise RuntimeError(f"LACE-seq runtime Dockerfile checksum is stale: {path}")
        dockerfile["name"] = "Dockerfile"
    implementation["sha256"] = current_implementation_sha256
    report["evidence_scope"] = scope
    report["runtime_asset_relocation"] = {
        "schema_version": 1,
        "migration_type": "checksum-bound-runtime-asset-relocation",
        "reviewed_on": date.today().isoformat(),
        "prior_implementation_sha256": spec["prior_implementation_sha256"],
        "current_implementation_sha256": current_implementation_sha256,
        "prior_evidence_scope": prior_scope,
        "current_evidence_scope": scope,
        "assets": list(spec["assets"]),
        "asset_records_rewritten": replacements,
        "scientific_parameters_changed": False,
        "scientific_outputs_recomputed": False,
        "reason": (
            "Runtime build assets were separated from scientific templates. The implementation change is "
            "restricted to locating those checksum-bound assets; previously observed inputs, parameters, "
            "container identities, output checksums and biological results are unchanged."
        ),
    }
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def main() -> int:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    scope = module_evidence_scope(registry, [MODULE_ID]).to_dict()
    changed: list[str] = []
    for assay, spec in RELOCATIONS.items():
        for name in spec["reports"]:
            path = ROOT / "reports" / name
            if migrate_report(path, assay, spec, scope):
                changed.append(name)
    print(json.dumps({"passed": True, "reissued": changed, "module_scope": scope}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
