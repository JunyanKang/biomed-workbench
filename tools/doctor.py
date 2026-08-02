#!/usr/bin/env python3
"""Diagnose whether an installed Biomed Workbench can serve Codex safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORE_PYTHON = (3, 10)


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    summary: str
    action: str | None = None
    details: dict[str, object] | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_runtime() -> Check:
    detected = platform.python_version()
    if sys.version_info[:2] < CORE_PYTHON:
        return Check(
            id="core-runtime",
            status="fail",
            summary=f"Python {detected} is below the core minimum.",
            action="Install Python 3.10 or newer, then rerun tools/workbench doctor.",
            details={"detected": detected, "minimum": "3.10"},
        )
    return Check(
        id="core-runtime",
        status="pass",
        summary=f"Core tools can run with Python {detected}.",
        details={
            "detected": detected,
            "executable": sys.executable,
            "minimum": "3.10",
            "scientific_versions": "detected and recorded per module at execution time",
        },
    )


def _check_manifest() -> Check:
    manifest_path = ROOT / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check(
            id="plugin-manifest",
            status="fail",
            summary="The Codex plugin manifest is missing or invalid.",
            action="Restore .codex-plugin/plugin.json from the installed package.",
            details={"error": str(exc)},
        )
    required = {
        "name": "biomed-workbench",
        "skills": "./skills/",
        "license": "Apache-2.0",
    }
    invalid = {key: manifest.get(key) for key, value in required.items() if manifest.get(key) != value}
    if invalid:
        return Check(
            id="plugin-manifest",
            status="fail",
            summary="The plugin manifest identity or component paths are invalid.",
            action="Reinstall Biomed Workbench from its marketplace source.",
            details={"invalid": invalid},
        )
    return Check(
        id="plugin-manifest",
        status="pass",
        summary=f"Plugin manifest {manifest.get('version', 'unknown')} is readable.",
        details={"version": manifest.get("version"), "sha256": _sha256(manifest_path)},
    )


def _check_skill() -> Check:
    skill_path = ROOT / "skills" / "biomed-workbench" / "SKILL.md"
    metadata_path = skill_path.parent / "agents" / "openai.yaml"
    missing = [
        path.relative_to(ROOT).as_posix()
        for path in (skill_path, metadata_path)
        if not path.is_file()
    ]
    if missing:
        return Check(
            id="codex-entrypoint",
            status="fail",
            summary="The unified Codex skill entry is incomplete.",
            action="Reinstall the plugin and open a new Codex task.",
            details={"missing": missing},
        )
    return Check(
        id="codex-entrypoint",
        status="pass",
        summary="The single user-facing skill and Codex metadata are present.",
        details={"skill_sha256": _sha256(skill_path)},
    )


def _check_registry() -> Check:
    try:
        from biomed_workbench.modules.index import BUILTIN_ROOT
        from biomed_workbench.modules.registry import ModuleRegistry

        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        modules = registry.all()
    except Exception as exc:
        return Check(
            id="module-registry",
            status="fail",
            summary="The scientific module registry cannot be loaded.",
            action="Run tools/workbench validate and repair the reported package error.",
            details={"error_type": type(exc).__name__, "error": str(exc)},
        )
    maturity: dict[str, int] = {}
    access: dict[str, int] = {}
    for module in modules:
        maturity[module.maturity] = maturity.get(module.maturity, 0) + 1
        access[module.access] = access.get(module.access, 0) + 1
    return Check(
        id="module-registry",
        status="pass",
        summary=f"Loaded {len(modules)} independently registered scientific modules.",
        details={
            "module_count": len(modules),
            "registry_digest": registry.digest,
            "maturity": dict(sorted(maturity.items())),
            "access": dict(sorted(access.items())),
        },
    )


def _check_routing() -> Check:
    try:
        from biomed_workbench.research_plan import compile_research_plan

        routed = compile_research_plan(
            "Validate donor-aware single-cell RNA analysis, revise the hypothesis, "
            "and prepare a publication-grade evidence package."
        )
    except Exception as exc:
        return Check(
            id="unified-routing",
            status="fail",
            summary="The unified scientific router did not complete a smoke test.",
            action="Run tools/workbench validate and inspect routing tests.",
            details={"error_type": type(exc).__name__, "error": str(exc)},
        )
    selected = routed.get("selected_module_ids", [])
    if (
        not selected
        or not routed.get("execution_layers")
        or routed.get("plan_type") not in {"single", "serial", "parallel", "mixed"}
    ):
        return Check(
            id="unified-routing",
            status="fail",
            summary="The router returned an incomplete execution plan.",
            action="Inspect module intents and artifact dependencies before use.",
            details={"plan_type": routed.get("plan_type"), "selected_module_ids": selected},
        )
    return Check(
        id="unified-routing",
        status="pass",
        summary=f"The unified entry produced a {routed['plan_type']} scientific plan.",
        details={
            "matched_workflows": routed.get("matched_workflows", []),
            "selected_module_ids": selected,
            "execution_layer_count": len(routed.get("execution_layers", [])),
        },
    )


def _check_optional_credentials() -> Check:
    from biomed_workbench.services.credentials import credential_sources

    sources = credential_sources()
    return Check(
        id="optional-credentials",
        status="pass",
        summary="Optional credential policy is valid.",
        details={
            "NCBI_API_KEY": (
                "configured"
                if sources["NCBI_API_KEY"] != "not-configured"
                else "not configured"
            ),
            "NCBI_API_KEY_source": sources["NCBI_API_KEY"],
            "required_for_core_use": False,
        },
    )


def diagnose() -> dict[str, object]:
    checks: tuple[Callable[[], Check], ...] = (
        _check_runtime,
        _check_manifest,
        _check_skill,
        _check_registry,
        _check_routing,
        _check_optional_credentials,
    )
    results = tuple(check() for check in checks)
    counts = {
        status: sum(item.status == status for item in results)
        for status in ("pass", "warn", "fail")
    }
    return {
        "schema_version": 1,
        "plugin": "biomed-workbench",
        "passed": counts["fail"] == 0,
        "summary": counts,
        "checks": [asdict(item) for item in results],
        "next_action": (
            "Open a new Codex task after install or update, then state one scientific objective."
            if counts["fail"] == 0
            else "Resolve every failed check before scientific execution."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a failure when a warning is present.",
    )
    args = parser.parse_args()
    report = diagnose()
    print(json.dumps(report, indent=2, sort_keys=True))
    warnings = int(report["summary"]["warn"])
    return 0 if report["passed"] and (not args.strict or warnings == 0) else 2


if __name__ == "__main__":
    raise SystemExit(main())
