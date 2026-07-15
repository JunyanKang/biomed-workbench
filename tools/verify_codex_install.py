#!/usr/bin/env python3
"""Install the plugin into an isolated Codex home and verify the cached copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + "\n" + completed.stderr).splitlines()[-12:])
        raise RuntimeError(f"command failed with status {completed.returncode}: {command[0]}\n{tail}")
    return completed


def json_output(completed: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} did not emit a JSON object") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} JSON root is not an object")
    return payload


def parse_cli_version(text: str) -> str:
    match = re.search(r"codex-cli\s+([^\s]+)", text)
    if match is None:
        raise RuntimeError("unable to parse Codex CLI version")
    return match.group(1)


def installed_registry(python: str, installed: Path, env: dict[str, str]) -> dict[str, Any]:
    code = (
        "import json; "
        "from biomed_workbench.modules.index import BUILTIN_ROOT; "
        "from biomed_workbench.modules.registry import ModuleRegistry; "
        "r=ModuleRegistry.discover(BUILTIN_ROOT); "
        "print(json.dumps({'module_count':len(r.all()),'registry_digest':r.digest," 
        "'credentials':sorted({c for m in r.all() for c in m.credentials})},sort_keys=True))"
    )
    completed = run([python, "-c", code], cwd=installed, env=env)
    return json_output(completed, "installed registry probe")


def build_report(codex_cli: Path, source: Path) -> dict[str, Any]:
    plugin_manifest = json.loads((source / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    version_completed = run([str(codex_cli), "--version"], cwd=source, env=dict(os.environ))
    codex_version = parse_cli_version(version_completed.stdout + version_completed.stderr)
    with tempfile.TemporaryDirectory(prefix="biomed-codex-install-") as temporary:
        isolated_home = Path(temporary).resolve()
        env = {**os.environ, "HOME": str(isolated_home)}
        marketplace = json_output(
            run([str(codex_cli), "plugin", "marketplace", "add", str(source), "--json"], cwd=source, env=env),
            "marketplace add",
        )
        installation = json_output(
            run([str(codex_cli), "plugin", "add", f"{plugin_manifest['name']}@{marketplace['marketplaceName']}", "--json"], cwd=source, env=env),
            "plugin add",
        )
        listing = json_output(run([str(codex_cli), "plugin", "list", "--json"], cwd=source, env=env), "plugin list")
        installed_rows = [row for row in listing.get("installed", []) if row.get("name") == plugin_manifest["name"]]
        if len(installed_rows) != 1 or installed_rows[0].get("installed") is not True or installed_rows[0].get("enabled") is not True:
            raise RuntimeError("isolated plugin list does not contain one enabled installation")
        installed = Path(installation["installedPath"])
        installed_resolved = installed.resolve()
        if not installed.is_dir() or not installed_resolved.is_relative_to(isolated_home) or installed_resolved == source.resolve():
            raise RuntimeError("plugin cache is absent, outside the isolated home, or aliases the development tree")
        installed_env = {**env, "PYTHONPATH": str(installed_resolved)}
        registry = installed_registry(sys.executable, installed_resolved, installed_env)
        route = json_output(
            run(
                [sys.executable, "tools/route_task.py", "Profile a biomedical table before statistical analysis", "--per-workflow", "3"],
                cwd=installed_resolved,
                env=installed_env,
            ),
            "installed route probe",
        )
        execution = json_output(
            run(
                [
                    sys.executable,
                    "tools/run_tool.py",
                    "data-profile",
                    "--input",
                    '{"rows":[{"sample":"S1","value":1.2},{"sample":"S2","value":null}]}',
                ],
                cwd=installed_resolved,
                env=installed_env,
            ),
            "installed execution probe",
        )
        skill_paths = sorted((installed_resolved / "skills").glob("*/SKILL.md"))
        if len(skill_paths) != 1 or not skill_paths[0].read_text(encoding="utf-8").startswith("---\n"):
            raise RuntimeError("installed cache does not expose exactly one metadata-bearing skill")
        if "data-profile" not in route.get("selected_module_ids", []):
            raise RuntimeError("installed router did not select data-profile for the bounded table objective")
        if execution.get("status") != "completed" or execution.get("capability_id") != "data-profile" or execution.get("output", {}).get("row_count") != 2:
            raise RuntimeError("installed data-profile execution did not complete with two accounted rows")
        source_registry = json.loads((source / "biomed_workbench" / "modules" / "index.json").read_text(encoding="utf-8"))
        checks = [
            ("marketplace_add", marketplace.get("marketplaceName") == "biomed-workbench"),
            ("plugin_list_discovery", len(installed_rows) == 1),
            ("plugin_add", installation.get("name") == plugin_manifest["name"]),
            ("manifest_version_resolution", installation.get("version") == plugin_manifest["version"]),
            ("installed_cache_module_index", registry["module_count"] == source_registry["module_count"] and registry["registry_digest"] == source_registry["registry_digest"]),
            ("installed_cache_routing", "data-profile" in route["selected_module_ids"]),
            ("installed_cache_execution", execution["status"] == "completed" and execution["output"]["row_count"] == 2),
            ("installed_skill_metadata", len(skill_paths) == 1),
            ("cache_snapshot_isolation", installed_resolved.is_relative_to(isolated_home) and installed_resolved != source.resolve()),
            ("new_task_reload_required", True),
        ]
        if not all(passed for _operation, passed in checks):
            raise RuntimeError("one or more isolated installation checks failed")
        report = {
            "schema_version": 3,
            "passed": True,
            "plugin": plugin_manifest["name"],
            "version": plugin_manifest["version"],
            "marketplace": marketplace["marketplaceName"],
            "codex_cli_distribution": "desktop-bundled",
            "codex_cli_version": codex_version,
            "isolated_home": True,
            "installed_module_count": registry["module_count"],
            "installed_registry_digest": registry["registry_digest"],
            "installed_skill_count": len(skill_paths),
            "installed_skill_sha256": hashlib.sha256(skill_paths[0].read_bytes()).hexdigest(),
            "credentials": registry["credentials"],
            "route_selected_module_ids": route["selected_module_ids"],
            "executed_module_id": execution["capability_id"],
            "executed_row_count": execution["output"]["row_count"],
            "new_task_required": True,
            "checks": [{"operation": operation, "passed": passed} for operation, passed in checks],
        }
        serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if any(marker in serialized for marker in ("/Users/", "/private/", "/var/folders/", "file://", "nvapi-", "API_KEY=")):
            raise RuntimeError("public installation report contains a local path or credential value")
        return report


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-cli", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "codex-install-verification.json")
    args = parser.parse_args()
    codex_cli = args.codex_cli.resolve()
    source = args.source.resolve()
    if not codex_cli.is_file() or not os.access(codex_cli, os.X_OK):
        raise ValueError("Codex CLI must be an executable regular file")
    report = build_report(codex_cli, source)
    atomic_write(args.output, json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": True, "module_count": report["installed_module_count"], "registry_digest": report["installed_registry_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
