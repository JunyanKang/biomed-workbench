#!/usr/bin/env python3
"""Capture path-free official validation evidence for the Codex plugin contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


EVIDENCE_ID = "codex-plugin-manifest-contract-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_validator(arguments: list[str], expected_text: str) -> dict[str, object]:
    completed = subprocess.run(
        arguments,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    output = "\n".join(value.strip() for value in (completed.stdout, completed.stderr) if value.strip())
    if completed.returncode != 0 or expected_text not in output:
        raise RuntimeError("official Codex contract validation failed")
    return {"passed": True, "exit_code": completed.returncode, "result_marker": expected_text}


def verify(plugin_validator: Path, skill_validator: Path) -> dict[str, object]:
    if not plugin_validator.is_file() or not skill_validator.is_file():
        raise RuntimeError("official Codex validator is unavailable")
    manifest_path = ROOT / ".codex-plugin" / "plugin.json"
    skill_path = ROOT / "skills" / "biomed-workbench"
    skill_manifest = skill_path / "SKILL.md"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    index = json.loads((ROOT / "biomed_workbench" / "modules" / "index.json").read_text(encoding="utf-8"))
    snapshot_path = ROOT / "reports" / "module-registry-verification.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if (
        manifest.get("name") != "biomed-workbench"
        or manifest.get("skills") != "./skills/"
        or not isinstance(manifest.get("version"), str)
        or not skill_manifest.is_file()
        or len(list((ROOT / "skills").glob("*/SKILL.md"))) != 1
        or index.get("registry_digest") != registry.digest
        or snapshot.get("passed") is not True
        or snapshot.get("source_checkout", {}).get("registry_digest") != registry.digest
        or snapshot.get("installed_cache", {}).get("registry_digest") != registry.digest
    ):
        raise RuntimeError("plugin manifest, single skill, generated index, or isolated registry snapshot is stale")
    plugin_result = _run_validator(
        [sys.executable, str(plugin_validator.resolve()), str(ROOT)],
        "Plugin validation passed:",
    )
    skill_result = _run_validator(
        [sys.executable, str(skill_validator.resolve()), str(skill_path)],
        "Skill is valid!",
    )
    return {
        "schema_version": 1,
        "passed": True,
        "evidence_id": EVIDENCE_ID,
        "evidence_type": "codex-plugin-contract",
        "plugin": {
            "name": manifest["name"],
            "version": manifest["version"],
            "manifest_sha256": _sha256(manifest_path),
            "single_skill_entry": True,
            "skill_sha256": _sha256(skill_manifest),
        },
        "official_validation": {
            "plugin_validator": {**plugin_result, "sha256": _sha256(plugin_validator)},
            "skill_validator": {**skill_result, "sha256": _sha256(skill_validator)},
        },
        "isolated_registry_snapshot": {
            "passed": True,
            "report_sha256": _sha256(snapshot_path),
            "module_count": len(registry.all()),
            "registry_digest": registry.digest,
            "source_and_snapshot_indexes_match": snapshot["installed_cache"]["index_bytes_match_source"],
            "new_task_required": snapshot["installed_cache"]["new_task_required"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-validator", type=Path, required=True)
    parser.add_argument("--skill-validator", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "plugin-contract-verification.json")
    args = parser.parse_args()
    report = verify(args.plugin_validator, args.skill_validator)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"evidence_id": report["evidence_id"], "module_count": report["isolated_registry_snapshot"]["module_count"], "passed": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
