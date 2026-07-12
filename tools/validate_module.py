#!/usr/bin/env python3
"""Validate an independent Biomed Workbench scientific module package."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.contract import ModuleManifest, parse_manifest, version_is_allowed  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry, ModuleRegistryError  # noqa: E402
from biomed_workbench.runner import InputValidationError, _validate  # noqa: E402
from biomed_workbench.version import VERSION  # noqa: E402


class ModuleValidationError(ValueError):
    """Raised only by the isolated case worker for an invalid test case."""


_LOCAL_PATH_PATTERNS = (
    re.compile(r"/(?:Users|home)/[^/\s]+/"),
    re.compile("/private/" + "var/folders/"),
    re.compile(r"file://"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\"),
)
_CASE_FIELDS = frozenset({"name", "input", "expected_subset"})


def _relative_files(module_path: Path) -> set[str]:
    return {path.relative_to(module_path).as_posix() for path in module_path.rglob("*") if path.is_file()}


def _permission_errors(module_path: Path) -> list[str]:
    errors = []
    for path in (module_path, *module_path.rglob("*")):
        if path.is_symlink():
            errors.append(f"symbolic links are not allowed: {path.relative_to(module_path)}")
            continue
        try:
            mode = path.stat().st_mode
        except OSError as exc:
            errors.append(f"cannot inspect permissions: {exc}")
            continue
        if mode & stat.S_IWOTH:
            errors.append(f"world-writable package path is not allowed: {path.relative_to(module_path)}")
        if path.is_file() and not os.access(path, os.R_OK):
            errors.append(f"package file is not readable: {path.relative_to(module_path)}")
    return errors


def _source_path_errors(module_path: Path) -> list[str]:
    errors = []
    for path in module_path.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in _LOCAL_PATH_PATTERNS):
            errors.append(f"machine-local or source path found in {path.relative_to(module_path)}")
    return errors


def _load_cases(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModuleValidationError("tests/cases.json must be readable JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "cases"} or payload["schema_version"] != 1:
        raise ModuleValidationError("tests/cases.json must use the closed schema_version 1 envelope")
    cases = payload["cases"]
    if not isinstance(cases, list) or not cases:
        raise ModuleValidationError("tests/cases.json must contain at least one executable case")
    names = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != _CASE_FIELDS:
            raise ModuleValidationError(f"test case {index} must contain exactly name, input, and expected_subset")
        if not isinstance(case["name"], str) or not case["name"].strip() or case["name"] in names:
            raise ModuleValidationError(f"test case {index} has an invalid or duplicate name")
        if not isinstance(case["input"], dict) or not isinstance(case["expected_subset"], dict):
            raise ModuleValidationError(f"test case {case['name']} input and expected_subset must be objects")
        names.add(case["name"])
    return cases


def _assert_subset(expected: Any, actual: Any, location: str = "output") -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise ModuleValidationError(f"{location} is not an object")
        missing = sorted(set(expected) - set(actual))
        if missing:
            raise ModuleValidationError(f"{location} is missing expected fields: {', '.join(missing)}")
        for key, value in expected.items():
            _assert_subset(value, actual[key], f"{location}.{key}")
    elif actual != expected:
        raise ModuleValidationError(f"{location} differs from the validated expected value")


def _resolve_entrypoint(manifest: ModuleManifest):
    return ModuleRegistry((manifest,), "standalone-validation").resolve_entrypoint(manifest.id)


def _execute_case(module_path: Path, case_index: int) -> dict[str, Any]:
    manifest = parse_manifest(json.loads((module_path / "module.json").read_text(encoding="utf-8")))
    cases = _load_cases(module_path / "tests" / "cases.json")
    case = cases[case_index]
    _validate(manifest.input_schema, case["input"], "input")
    raw = _resolve_entrypoint(manifest)(**case["input"])
    if not isinstance(raw, dict):
        raise ModuleValidationError("module test output must be a JSON object")
    _validate(manifest.output_schema, raw, "output")
    _assert_subset(case["expected_subset"], raw)
    return raw


def _run_case_isolated(module_path: Path, manifest: ModuleManifest, case_index: int) -> None:
    command = [sys.executable, str(Path(__file__).resolve()), "--execute-case", str(module_path), str(case_index)]
    try:
        result = subprocess.run(command, text=False, capture_output=True, timeout=manifest.execution.timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ModuleValidationError(f"test case {case_index} exceeded {manifest.execution.timeout_seconds} seconds") from exc
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip().splitlines()
        detail = message[-1] if message else "isolated test worker failed"
        raise ModuleValidationError(f"test case {case_index} failed: {detail}")
    if len(result.stdout) > manifest.execution.max_output_bytes:
        raise ModuleValidationError(f"test case {case_index} exceeded the declared output size")
    try:
        json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ModuleValidationError(f"test case {case_index} did not produce JSON") from exc


def _evidence_flags(manifest: ModuleManifest) -> tuple[bool, bool, bool, bool]:
    tool_complete = all(
        item.tested_versions and item.allowed_versions and item.version_source.startswith("https://") and item.version_probe
        for item in manifest.tool_requirements
    )
    dependency_complete = bool(manifest.dependencies) and all(
        item.identity
        and item.tested_versions
        and item.allowed_versions
        and item.version_source.startswith("https://")
        and item.verified_at
        and item.version_probe
        and item.version_pattern
        for item in manifest.dependencies
    )
    format_complete = all(
        port.formats
        and all(fmt.versions and fmt.representations and fmt.compression and fmt.orientations for fmt in port.formats)
        for port in (*manifest.input_artifacts, *manifest.output_artifacts)
    )
    compatibility_complete = bool(manifest.compatibility_matrix) and all(
        row.regression_evidence_ids and row.end_to_end_evidence_ids and row.verified_at
        for row in manifest.compatibility_matrix
    )
    return tool_complete, dependency_complete, format_complete, compatibility_complete


def validate_module(path: Path | str, *, require_tests: bool = True, execute_tests: bool = True) -> dict[str, Any]:
    """Return a complete validation report without mutating the module package."""
    module_path = Path(path).expanduser().absolute()
    errors: list[str] = []
    if module_path.is_symlink():
        errors.append("module path must not be a symbolic link")
    expected_files = {"module.json", "tests/cases.json"} if require_tests else {"module.json"}
    allowed_files = {"module.json", "tests/cases.json"}
    if not module_path.is_dir():
        errors.append("module path must be a directory")
    files = _relative_files(module_path) if module_path.is_dir() else set()
    missing = sorted(expected_files - files)
    extra = sorted(files - allowed_files)
    if missing:
        errors.append(f"module package is missing required files: {', '.join(missing)}")
    if extra:
        errors.append(f"module package contains unsupported files: {', '.join(extra)}")
    if module_path.is_dir():
        errors.extend(_permission_errors(module_path))
        errors.extend(_source_path_errors(module_path))

    manifest = None
    manifest_path = module_path / "module.json"
    if manifest_path.is_file():
        try:
            manifest = parse_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
            if module_path.name != manifest.id:
                errors.append("module directory name must exactly match manifest id")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"manifest contract failed: {exc}")

    entrypoint_resolved = False
    compatibility_rows = 0
    tool_complete = dependency_complete = format_complete = compatibility_complete = False
    executed = 0
    if manifest is not None:
        compatibility_rows = len(manifest.compatibility_matrix)
        tool_complete, dependency_complete, format_complete, compatibility_complete = _evidence_flags(manifest)
        if not version_is_allowed(VERSION, manifest.kernel_compatibility):
            errors.append(f"kernel version {VERSION} is outside declared kernel compatibility")
        try:
            _resolve_entrypoint(manifest)
            entrypoint_resolved = True
        except ModuleRegistryError as exc:
            errors.append(str(exc))
        if not tool_complete:
            errors.append("tool version evidence is incomplete")
        if not dependency_complete:
            errors.append("dependency version evidence is incomplete")
        if not format_complete:
            errors.append("input or output format evidence is incomplete")
        if not compatibility_complete:
            errors.append("compatibility regression or end-to-end evidence is incomplete")

    if (module_path / "tests" / "cases.json").is_file():
        try:
            cases = _load_cases(module_path / "tests" / "cases.json")
            if manifest is not None and entrypoint_resolved:
                for index in range(len(cases)):
                    if execute_tests:
                        _run_case_isolated(module_path, manifest, index)
                    executed += 1
        except (ModuleValidationError, InputValidationError) as exc:
            errors.append(str(exc))

    return {
        "schema_version": 1,
        "module_id": manifest.id if manifest else module_path.name,
        "module_version": manifest.version if manifest else None,
        "kernel_version": VERSION,
        "valid": not errors,
        "errors": list(dict.fromkeys(errors)),
        "entrypoint_resolved": entrypoint_resolved,
        "compatibility_rows": compatibility_rows,
        "tool_evidence_complete": tool_complete,
        "dependency_evidence_complete": dependency_complete,
        "format_evidence_complete": format_complete,
        "compatibility_evidence_complete": compatibility_complete,
        "executed_test_cases": executed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module_path", nargs="?")
    parser.add_argument("--no-tests", action="store_true")
    parser.add_argument("--no-execute", action="store_true")
    parser.add_argument("--execute-case", nargs=2, metavar=("MODULE_PATH", "CASE_INDEX"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.execute_case:
        try:
            output = _execute_case(Path(args.execute_case[0]), int(args.execute_case[1]))
        except Exception as exc:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        encoded = json.dumps(output, sort_keys=True).encode("utf-8")
        sys.stdout.buffer.write(encoded)
        return 0
    if not args.module_path:
        parser.error("module_path is required")
    report = validate_module(args.module_path, require_tests=not args.no_tests, execute_tests=not args.no_execute)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
