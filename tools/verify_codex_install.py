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
        project_root = isolated_home / "scientific-project"
        project_root.mkdir()
        binding_path = isolated_home / "data-profile-bindings.json"
        binding_path.write_text(
            json.dumps(
                {
                    "project_context": {
                        "project_id": "installed-data-profile",
                        "objective": "Verify strict public execution from the isolated installed plugin cache.",
                        "scientific_question": "Does the registered table retain complete row and missing-value accounting?",
                        "species": ["human"],
                        "biological_scope": {"verification": "installed-cache"},
                        "study_design": "release-verification",
                        "experimental_unit": "record",
                        "comparisons": [{"id": "accounting-check", "numerator_group": "observed", "denominator_group": "declared", "covariates": []}],
                        "constraints": [],
                        "required_deliverables": ["table-profile"],
                        "required_evidence_types": ["technical-accounting"],
                        "privacy_level": "public",
                    },
                    "hypotheses": [
                        {
                            "id": "hypothesis-installed-table-accounting",
                            "statement": "The registered table retains complete row and missing-value accounting after profiling.",
                            "biological_scope": {"verification": "installed-cache"},
                            "experimental_unit": "record",
                            "comparison_id": "accounting-check",
                            "expected_direction": "no-change",
                            "expected_observations": ["The output reports exactly two registered rows."],
                            "disconfirming_observations": ["The output row accounting differs from the two registered rows."],
                            "alternative_explanations": ["An input-binding or installed-cache defect could alter the observed accounting."],
                            "required_evidence_types": ["technical-accounting"],
                            "minimum_independent_evidence_groups": 1,
                            "permitted_claim_strength": "descriptive",
                            "status": "active",
                            "supporting_evidence_ids": [],
                            "conflicting_evidence_ids": [],
                            "missing_evidence_types": ["technical-accounting"],
                            "parent_hypothesis_id": None,
                            "revision": 1,
                        }
                    ],
                    "analysis_admission": {
                        "rationale_zh": "在隔离安装副本中验证公开入口、项目绑定和表格行数核对。",
                        "rationale_en": "Verify the public entry, project binding, and table row accounting in the isolated installation.",
                        "method": "Use the packaged data-profile implementation through the strict project-bound public entry.",
                        "official_sources": ["https://github.com/JunyanKang/biomed-workbench"],
                        "alternatives_considered": ["An internal runner probe would not validate the strict public entry."],
                        "assumptions": ["The two inline records are the complete bounded release fixture."],
                        "parameter_justifications": {"rows": "Two rows cover present and missing values without external data."},
                        "acceptance_criteria": ["The execution completes and stops for scientific artifact review with two accounted rows."],
                        "falsification_criteria": ["Any public-entry error, row mismatch, or missing review gate fails installation verification."],
                        "approved": True,
                    },
                    "artifacts": {
                        "records": {
                            "artifact_id": "artifact-installed-table",
                            "format_name": "inline-json",
                            "format_version": "1",
                            "compression": "none",
                            "orientation": "request-object",
                            "indexes": [],
                            "scientific_scope": {"verification": "installed-cache"},
                            "denominator": "two-registered-records",
                            "processing_level": "declared",
                            "quality_status": "passed",
                            "representation": "structured",
                            "content": {},
                            "payload_files": [],
                        }
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        execution = json_output(
            run(
                [
                    sys.executable,
                    "tools/run_tool.py",
                    "data-profile",
                    "--input",
                    '{"rows":[{"sample":"S1","value":1.2},{"sample":"S2","value":null}]}',
                    "--project-root",
                    str(project_root),
                    "--artifact-bindings",
                    str(binding_path),
                    "--compatibility-row",
                    "python-3.14.3-inline-json-1",
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
        output_rows = (
            execution.get("output_artifacts", [{}])[0]
            .get("content", {})
            .get("row_count")
        )
        if (
            execution.get("execution_status") != "completed"
            or execution.get("scientific_status") != "awaiting_review"
            or execution.get("module_id") != "data-profile"
            or execution.get("stop_reason") != "awaiting_artifact_review"
            or output_rows != 2
            or not (project_root / str(execution.get("project_state_path", ""))).is_file()
        ):
            raise RuntimeError("installed data-profile execution did not complete with two accounted rows")
        source_registry = json.loads((source / "biomed_workbench" / "modules" / "index.json").read_text(encoding="utf-8"))
        checks = [
            ("marketplace_add", marketplace.get("marketplaceName") == "biomed-workbench"),
            ("plugin_list_discovery", len(installed_rows) == 1),
            ("plugin_add", installation.get("name") == plugin_manifest["name"]),
            ("manifest_version_resolution", installation.get("version") == plugin_manifest["version"]),
            ("installed_cache_module_index", registry["module_count"] == source_registry["module_count"] and registry["registry_digest"] == source_registry["registry_digest"]),
            ("installed_cache_routing", "data-profile" in route["selected_module_ids"]),
            ("installed_cache_execution", execution["execution_status"] == "completed" and execution["scientific_status"] == "awaiting_review" and execution["stop_reason"] == "awaiting_artifact_review" and output_rows == 2),
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
            "executed_module_id": execution["module_id"],
            "executed_row_count": output_rows,
            "execution_stop_reason": execution["stop_reason"],
            "new_task_required": True,
            "checks": [{"operation": operation, "passed": passed} for operation, passed in checks],
        }
        serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if any(marker in serialized for marker in ("/Users/", "/private/", "/var/folders/", "file://", "API_KEY=", "ACCESS_TOKEN=")):
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
