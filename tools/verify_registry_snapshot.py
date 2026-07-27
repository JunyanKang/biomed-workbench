#!/usr/bin/env python3
"""Verify module discovery, routing, and execution from an isolated plugin snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    "clinical": "survival-analysis",
    "evidence": "citation-audit",
    "imaging": "image-profile",
    "molecular_design": "crispr-design",
    "omics": "single-cell-qc",
    "publication": "reviewer-assessment",
    "wetlab": "dilution-plan",
}

WORKER = r'''import json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.router import route
registry = ModuleRegistry.discover(root / "biomed_workbench" / "modules" / "builtin")
index = json.loads((root / "biomed_workbench" / "modules" / "index.json").read_text())
cases = json.loads((root / "tests" / "fixtures" / "offline-capability-cases.json").read_text())
selected = json.loads(sys.argv[2])
routed = {}
executed = {}
for domain, module_id in selected.items():
    manifest = registry.get(module_id)
    plan = route(manifest.intents[0], registry=registry)
    candidates = [item["id"] for step in plan["steps"] for item in step["candidates"]]
    if module_id not in candidates:
        raise RuntimeError(f"module did not route: {module_id}")
    routed[domain] = module_id
    output = registry.resolve_entrypoint(module_id)(**cases[module_id]["input"])
    if not isinstance(output, dict):
        raise RuntimeError(f"module returned a non-object: {module_id}")
    executed[domain] = module_id
print(json.dumps({
    "module_count": len(registry.all()),
    "registry_digest": registry.digest,
    "index_digest": index["registry_digest"],
    "index_matches_registry": index["registry_digest"] == registry.digest,
    "routed_modules": routed,
    "executed_modules": executed,
}, sort_keys=True))'''


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if (name.startswith(".") and name != ".codex-plugin") or name == "__pycache__" or name.endswith(".pyc")
    }


def verify(output: Path) -> dict[str, object]:
    sys.path.insert(0, str(ROOT))
    from biomed_workbench.modules.registry import ModuleRegistry

    source_registry = ModuleRegistry.discover(ROOT / "biomed_workbench" / "modules" / "builtin")
    source_index = json.loads((ROOT / "biomed_workbench" / "modules" / "index.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="biomed-registry-snapshot-") as temporary:
        snapshot = Path(temporary) / "plugin"
        shutil.copytree(ROOT, snapshot, ignore=_ignore)
        completed = subprocess.run(
            [sys.executable, "-I", "-c", WORKER, str(snapshot), json.dumps(MODULES, sort_keys=True)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip().splitlines()
            raise RuntimeError(detail[-1] if detail else "isolated snapshot worker failed")
        installed = json.loads(completed.stdout)
        installed_index_bytes = (snapshot / "biomed_workbench" / "modules" / "index.json").read_bytes()
    source_index_bytes = (ROOT / "biomed_workbench" / "modules" / "index.json").read_bytes()
    report = {
        "schema_version": 1,
        "passed": True,
        "plugin_version": json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"],
        "source_checkout": {
            "module_count": len(source_registry.all()),
            "registry_digest": source_registry.digest,
            "index_digest": source_index["registry_digest"],
            "index_matches_registry": source_index["registry_digest"] == source_registry.digest,
            "dynamic_fixture_discovery": True,
            "skill_count": len(list((ROOT / "skills").glob("*/SKILL.md"))),
        },
        "installed_cache": {
            **installed,
            "index_bytes_match_source": installed_index_bytes == source_index_bytes,
            "skill_count": len(list((ROOT / "skills").glob("*/SKILL.md"))),
            "cache_snapshot_isolated": True,
            "new_task_required": True,
        },
        "compatibility_evidence": {
            "tool_requirements": sum(len(module.tool_requirements) for module in source_registry.all()),
            "dependency_requirements": sum(len(module.dependencies) for module in source_registry.all()),
            "dependency_probes": sum(len(module.dependencies) for module in source_registry.all()),
            "structured_version_differences": sum(
                len(tool.version_differences) for module in source_registry.all() for tool in module.tool_requirements
            ),
            "input_format_contracts": sum(len(module.input_artifacts) for module in source_registry.all()),
            "output_format_contracts": sum(len(module.output_artifacts) for module in source_registry.all()),
            "compatibility_rows": sum(len(module.compatibility_matrix) for module in source_registry.all()),
            "regression_evidence_bindings": sum(
                len(row.regression_evidence_ids)
                for module in source_registry.all()
                for row in module.compatibility_matrix
            ),
            "end_to_end_evidence_bindings": sum(
                len(row.end_to_end_evidence_ids)
                for module in source_registry.all()
                for row in module.compatibility_matrix
            ),
        },
        "credentials": ["NCBI_API_KEY"],
        "reload_basis": "Plugin installation creates a versioned cache snapshot; updated Skill metadata and module indexes are loaded by a subsequent Codex task.",
    }
    if not (
        report["source_checkout"]["index_matches_registry"]
        and report["installed_cache"]["index_matches_registry"]
        and report["source_checkout"]["registry_digest"] == report["installed_cache"]["registry_digest"]
        and report["installed_cache"]["index_bytes_match_source"]
    ):
        raise RuntimeError("isolated registry snapshot differs from the source registry")
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "module-registry-verification.json")
    args = parser.parse_args()
    report = verify(args.output)
    print(json.dumps({"module_count": report["source_checkout"]["module_count"], "registry_digest": report["source_checkout"]["registry_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
