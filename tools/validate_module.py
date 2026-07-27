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
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.contract import ModuleManifest, parse_manifest, version_is_allowed  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry, ModuleRegistryError  # noqa: E402
from biomed_workbench.modules.template_quality import referenced_template_paths, validate_module_templates  # noqa: E402
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
_CASE_REQUIRED_FIELDS = frozenset({"name", "input", "expected_subset"})
_CASE_OPTIONAL_FIELDS = frozenset({"http_fixtures"})
_HTTP_FIXTURE_REQUIRED_FIELDS = frozenset({"url", "status", "headers"})
_HTTP_FIXTURE_BODY_FIELDS = frozenset({"json", "text"})
_HTTP_FIXTURE_OPTIONAL_FIELDS = frozenset({"method", "request_json", "request_text", "request_form", "json", "text"})
_AGENT_ASSET_RE = re.compile(r"^(?:templates|validators)/[a-z][a-z0-9_]*(?:\.(?:py|R|md|ipynb))$")


def _is_transient_package_file(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}


def _relative_files(module_path: Path) -> set[str]:
    return {
        path.relative_to(module_path).as_posix()
        for path in module_path.rglob("*")
        if path.is_file() and not _is_transient_package_file(path)
    }


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
        if _is_transient_package_file(path):
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
        if (
            not isinstance(case, dict)
            or not _CASE_REQUIRED_FIELDS <= set(case)
            or set(case) - _CASE_REQUIRED_FIELDS - _CASE_OPTIONAL_FIELDS
        ):
            raise ModuleValidationError(
                f"test case {index} must contain name, input, expected_subset, and only supported optional fields"
            )
        if not isinstance(case["name"], str) or not case["name"].strip() or case["name"] in names:
            raise ModuleValidationError(f"test case {index} has an invalid or duplicate name")
        if not isinstance(case["input"], dict) or not isinstance(case["expected_subset"], dict):
            raise ModuleValidationError(f"test case {case['name']} input and expected_subset must be objects")
        fixtures = case.get("http_fixtures", [])
        if not isinstance(fixtures, list):
            raise ModuleValidationError(f"test case {case['name']} http_fixtures must be an array")
        fixture_urls = set()
        for fixture_index, fixture in enumerate(fixtures):
            if (
                not isinstance(fixture, dict)
                or not _HTTP_FIXTURE_REQUIRED_FIELDS <= set(fixture)
                or set(fixture) - _HTTP_FIXTURE_REQUIRED_FIELDS - _HTTP_FIXTURE_OPTIONAL_FIELDS
                or len(_HTTP_FIXTURE_BODY_FIELDS & set(fixture)) != 1
            ):
                raise ModuleValidationError(
                    f"test case {case['name']} HTTP fixture {fixture_index} has an invalid field set"
                )
            url = fixture["url"]
            headers = fixture["headers"]
            method = fixture.get("method", "GET")
            fixture_key = (method, url)
            if method not in {"GET", "POST"}:
                raise ModuleValidationError(f"test case {case['name']} HTTP fixture method must be GET or POST")
            if not isinstance(url, str) or not url.startswith("https://") or fixture_key in fixture_urls:
                raise ModuleValidationError(f"test case {case['name']} HTTP fixture method/URL pairs must be unique HTTPS targets")
            if not isinstance(fixture["status"], int) or not 200 <= fixture["status"] <= 599:
                raise ModuleValidationError(f"test case {case['name']} HTTP fixture status must be 200..599")
            if (
                not isinstance(headers, dict)
                or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items())
                or ("json" in fixture and not isinstance(fixture["json"], (dict, list)))
                or ("text" in fixture and not isinstance(fixture["text"], str))
            ):
                raise ModuleValidationError(f"test case {case['name']} HTTP fixture headers and response body are invalid")
            request_body_fields = {field for field in ("request_json", "request_text", "request_form") if field in fixture}
            if method == "GET" and request_body_fields:
                raise ModuleValidationError(f"test case {case['name']} GET fixture cannot declare a request body")
            if method == "POST" and len(request_body_fields) != 1:
                raise ModuleValidationError(f"test case {case['name']} POST fixture requires exactly one supported request body")
            if "request_json" in fixture and not isinstance(fixture["request_json"], dict):
                raise ModuleValidationError(f"test case {case['name']} request_json must be an object")
            if "request_text" in fixture and not isinstance(fixture["request_text"], str):
                raise ModuleValidationError(f"test case {case['name']} request_text must be a string")
            if "request_form" in fixture and (not isinstance(fixture["request_form"], dict) or not fixture["request_form"] or any(not isinstance(key, str) or not isinstance(value, str) for key, value in fixture["request_form"].items())):
                raise ModuleValidationError(f"test case {case['name']} request_form must be a nonempty string object")
            fixture_urls.add(fixture_key)
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
    fixtures = case.get("http_fixtures", [])
    public_databases = None
    eutils = None
    original_transport = None
    original_eutils_transport = None
    pending_urls = {(fixture.get("method", "GET"), fixture["url"]) for fixture in fixtures}
    if fixtures:
        if manifest.execution.kind != "service":
            raise ModuleValidationError("HTTP fixtures are allowed only for service modules")
        from biomed_workbench.services import public_databases
        from biomed_workbench.services import eutils

        from biomed_workbench.services.public_databases import HTTPResponse

        fixture_by_url = {(fixture.get("method", "GET"), fixture["url"]): fixture for fixture in fixtures}

        def fixture_transport(url: str, _headers: dict[str, str], _timeout: float) -> HTTPResponse:
            fixture = fixture_by_url.get(("GET", url))
            if fixture is None:
                raise ModuleValidationError(f"service test attempted an undeclared URL: {url}")
            pending_urls.discard(("GET", url))
            body = (
                json.dumps(fixture["json"], separators=(",", ":"), sort_keys=True).encode("utf-8")
                if "json" in fixture
                else fixture["text"].encode("utf-8")
            )
            return HTTPResponse(fixture["status"], fixture["headers"], body)

        def fixture_post_transport(url: str, _headers: dict[str, str], request_body: bytes, _timeout: float) -> HTTPResponse:
            fixture = fixture_by_url.get(("POST", url))
            if fixture is None:
                raise ModuleValidationError(f"service test attempted an undeclared POST URL: {url}")
            if "request_json" in fixture:
                try:
                    request_json = json.loads(request_body)
                except json.JSONDecodeError:
                    raise ModuleValidationError("service test emitted a non-JSON POST body") from None
                if request_json != fixture["request_json"]:
                    raise ModuleValidationError(f"service test POST body differs from the declared fixture: {url}")
            elif "request_text" in fixture and request_body.decode("utf-8", errors="strict") != fixture["request_text"]:
                raise ModuleValidationError(f"service test POST body differs from the declared fixture: {url}")
            elif "request_form" in fixture:
                observed = {key: values[0] for key, values in parse_qs(request_body.decode("ascii", errors="strict"), keep_blank_values=True).items() if len(values) == 1}
                if observed != fixture["request_form"]:
                    raise ModuleValidationError(f"service test POST form differs from the declared fixture: {url}")
            pending_urls.discard(("POST", url))
            body = (
                json.dumps(fixture["json"], separators=(",", ":"), sort_keys=True).encode("utf-8")
                if "json" in fixture
                else fixture["text"].encode("utf-8")
            )
            return HTTPResponse(fixture["status"], fixture["headers"], body)

        original_transport = public_databases._default_transport
        original_post_transport = public_databases._default_post_transport
        public_databases._default_transport = fixture_transport
        public_databases._default_post_transport = fixture_post_transport
        original_eutils_transport = eutils._default_transport

        def fixture_eutils_transport(url: str, data: bytes | None, _headers: dict[str, str], _timeout: float):
            method = "POST" if data is not None else "GET"
            fixture = fixture_by_url.get((method, url))
            if fixture is None:
                raise ModuleValidationError(f"service test attempted an undeclared {method} URL: {url}")
            if method == "POST" and "request_form" in fixture:
                observed = {key: values[0] for key, values in parse_qs(data.decode("ascii", errors="strict"), keep_blank_values=True).items() if len(values) == 1}
                if observed != fixture["request_form"]:
                    raise ModuleValidationError(f"service test POST form differs from the declared fixture: {url}")
            pending_urls.discard((method, url))
            body = json.dumps(fixture["json"], separators=(",", ":"), sort_keys=True).encode("utf-8") if "json" in fixture else fixture["text"].encode("utf-8")
            return eutils.HTTPResponse(fixture["status"], fixture["headers"], body)

        eutils._default_transport = fixture_eutils_transport
    try:
        raw = _resolve_entrypoint(manifest)(**case["input"])
    finally:
        if public_databases is not None and original_transport is not None:
            public_databases._default_transport = original_transport
            public_databases._default_post_transport = original_post_transport
        if eutils is not None and original_eutils_transport is not None:
            eutils._default_transport = original_eutils_transport
    if pending_urls:
        remaining = ", ".join(f"{method} {url}" for method, url in sorted(pending_urls))
        raise ModuleValidationError(f"service test did not consume declared HTTP fixtures: {remaining}")
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
    extra = sorted(path for path in files - allowed_files if not _AGENT_ASSET_RE.fullmatch(path))
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
        agent_assets = {path for path in files if _AGENT_ASSET_RE.fullmatch(path)}
        referenced = set(referenced_template_paths(manifest))
        if referenced != agent_assets or any(not path.startswith("templates/") for path in referenced):
            errors.append("manifest template references must exactly match packaged template assets")
        errors.extend(validate_module_templates(module_path, manifest))

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
