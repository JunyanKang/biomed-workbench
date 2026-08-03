"""Pre-execution tool, dependency, and scientific-format compatibility gates."""

from __future__ import annotations

import hashlib
import importlib
import json
import platform as platform_module
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..formats import FormatRegistry, FormatSnapshot, validate_format
from .contract import ArtifactPort, CompatibilityRow, FormatContract, ModuleManifest, version_is_allowed


FORMAT_REGISTRY = FormatRegistry.builtin()


@dataclass(frozen=True)
class EnvironmentSnapshot:
    tools: dict[str, str]
    dependencies: dict[str, str]
    platform: str


@dataclass(frozen=True)
class ArtifactSnapshot:
    port: str
    format: str
    format_version: str
    compression: str
    indexes: tuple[str, ...]
    coordinate_system: str | None
    genome_build: str | None
    annotation_release: str | None
    orientation: str
    metadata_fields: tuple[str, ...]
    representation: str = "structured"
    sort_order: str = "unsorted"
    reference_sequence_digest: str | None = None
    identifier_namespace: str | None = None
    sample_manifest_digest: str | None = None
    payload_roles: tuple[str, ...] = ()
    processing_level: str = "raw"


@dataclass(frozen=True)
class CompatibilityFinding:
    code: str
    severity: str
    subject: str
    message: str


@dataclass(frozen=True)
class CompatibilityDecision:
    allowed: bool
    compatibility_row_id: str | None
    findings: tuple[CompatibilityFinding, ...]
    alternatives: tuple[str, ...]


@dataclass(frozen=True)
class CompatibleInvocation:
    output: dict[str, Any]
    provenance: dict[str, Any]


class CompatibilityError(RuntimeError):
    """Raised before invocation when no validated compatibility row matches."""

    def __init__(self, decision: CompatibilityDecision):
        self.decision = decision
        codes = ", ".join(finding.code for finding in decision.findings)
        super().__init__(f"module compatibility check failed: {codes}")


ProbeRunner = Callable[[tuple[str, ...], int], str]
CallableProbeRunner = Callable[[str, int], str]
DependencyProvider = Callable[[str, str], str | None]


def _platform_name() -> str:
    system = {"darwin": "macos", "linux": "linux", "win32": "windows"}.get(sys.platform, sys.platform)
    machine = platform_module.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    return f"{system}-{machine}"


def _run_probe(command: tuple[str, ...], timeout: int) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout)
    return f"{completed.stdout}\n{completed.stderr}".strip()


def _run_callable_probe(target: str, timeout: int) -> str:
    module_name, separator, attribute_name = target.partition(":")
    if not separator or not module_name or not attribute_name or attribute_name.startswith("_"):
        raise ValueError("invalid version probe callable")
    module = importlib.import_module(module_name)
    probe = getattr(module, attribute_name)
    if not callable(probe):
        raise ValueError("version probe target is not callable")
    result = probe(timeout_seconds=timeout)
    if not isinstance(result, str) or not result.strip():
        raise ValueError("version probe callable returned no version")
    return result.strip()


def probe_python_runtime(*, timeout_seconds: int) -> str:
    """Return the active Python runtime version for a declared callable probe."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    return platform_module.python_version()


def detect_environment(
    manifest: ModuleManifest,
    *,
    probe_runner: ProbeRunner | None = None,
    callable_probe_runner: CallableProbeRunner | None = None,
    service_probe_runner: CallableProbeRunner | None = None,
    dependency_provider: DependencyProvider | None = None,
    platform_name: str | None = None,
) -> EnvironmentSnapshot:
    """Detect only versions explicitly declared by a module contract."""
    run_probe = probe_runner or _run_probe
    run_callable_probe = callable_probe_runner or _run_callable_probe
    run_service_probe = service_probe_runner or _run_callable_probe
    provide_dependency = dependency_provider
    tools = {}
    for requirement in manifest.tool_requirements:
        timeout = min(manifest.execution.timeout_seconds, requirement.version_probe_timeout_seconds, 30)
        try:
            if requirement.version_probe_kind == "command":
                output = run_probe(tuple(requirement.version_probe), timeout)
            elif requirement.version_probe_kind == "python_callable":
                output = run_callable_probe(requirement.version_probe[0], timeout)
            else:
                output = run_service_probe(requirement.version_probe[0], timeout)
        except (ImportError, AttributeError, OSError, RuntimeError, ValueError, subprocess.SubprocessError, TimeoutError):
            continue
        match = re.search(requirement.version_pattern, output)
        if match:
            tools[requirement.name] = match.group(1) if match.groups() else match.group(0)
    dependencies = {}
    for requirement in manifest.dependencies:
        try:
            if dependency_provider is not None:
                output = provide_dependency(requirement.name, requirement.ecosystem)
            else:
                timeout = min(manifest.execution.timeout_seconds, requirement.version_probe_timeout_seconds, 30)
                if requirement.version_probe_kind == "command":
                    output = run_probe(tuple(requirement.version_probe), timeout)
                elif requirement.version_probe_kind == "python_callable":
                    output = run_callable_probe(requirement.version_probe[0], timeout)
                else:
                    output = run_service_probe(requirement.version_probe[0], timeout)
            if not output:
                continue
            match = re.search(requirement.version_pattern, str(output))
            if match:
                dependencies[requirement.name] = match.group(1) if match.groups() else match.group(0)
        except (ImportError, AttributeError, OSError, RuntimeError, ValueError, subprocess.SubprocessError, TimeoutError):
            continue
    return EnvironmentSnapshot(tools=tools, dependencies=dependencies, platform=platform_name or _platform_name())


def _finding(code: str, subject: str, message: str) -> CompatibilityFinding:
    return CompatibilityFinding(code=code, severity="fatal", subject=subject, message=message)


def _tool_findings(manifest: ModuleManifest, row: CompatibilityRow, environment: EnvironmentSnapshot) -> list[CompatibilityFinding]:
    findings = []
    for requirement in manifest.tool_requirements:
        actual = environment.tools.get(requirement.name)
        if actual is None:
            if requirement.required:
                findings.append(_finding("MISSING_TOOL", requirement.name, "Required scientific tool was not detected by its declared probe."))
            continue
        if not version_is_allowed(actual, row.tool_versions.get(requirement.name, ())):
            findings.append(_finding("UNVALIDATED_TOOL_VERSION", requirement.name, f"Detected version {actual} is outside compatibility policy {row.id}."))
    for requirement in manifest.dependencies:
        actual = environment.dependencies.get(requirement.name)
        if actual is None:
            if requirement.required:
                findings.append(_finding("MISSING_DEPENDENCY", requirement.name, "Required dependency version was not detected."))
            continue
        if not version_is_allowed(actual, row.dependency_versions.get(requirement.name, ())):
            findings.append(_finding("UNVALIDATED_DEPENDENCY_VERSION", requirement.name, f"Detected version {actual} is outside compatibility policy {row.id}."))
    if "any" not in row.platforms and environment.platform not in row.platforms:
        findings.append(_finding("UNSUPPORTED_PLATFORM", environment.platform, f"Platform is not present in compatibility row {row.id}."))
    return findings


def _format_for(port: ArtifactPort, name: str) -> FormatContract | None:
    return next((item for item in port.formats if item.name == name), None)


def _artifact_findings(
    manifest: ModuleManifest,
    row: CompatibilityRow,
    artifacts: tuple[ArtifactSnapshot, ...],
) -> list[CompatibilityFinding]:
    findings = []
    supplied = {artifact.port: artifact for artifact in artifacts}
    for port in manifest.input_artifacts:
        artifact = supplied.get(port.name)
        if artifact is None:
            findings.append(_finding("MISSING_ARTIFACT", port.name, "Required input artifact metadata was not supplied."))
            continue
        contract = _format_for(port, artifact.format)
        token = f"{artifact.format}@{artifact.format_version}"
        if contract is None or artifact.format_version not in contract.versions or token not in row.input_formats.get(port.name, ()):
            findings.append(_finding("UNSUPPORTED_FORMAT_VERSION", port.name, f"Input format {token} is not validated by compatibility row {row.id}."))
            continue
        if artifact.compression not in contract.compression:
            findings.append(_finding("UNSUPPORTED_COMPRESSION", port.name, f"Compression {artifact.compression} is not validated for {token}."))
        missing_indexes = sorted(set(contract.required_indexes) - set(artifact.indexes))
        if missing_indexes:
            findings.append(_finding("MISSING_INDEX", port.name, f"Required companion indexes are absent: {', '.join(missing_indexes)}."))
        if contract.coordinate_systems and artifact.coordinate_system not in contract.coordinate_systems:
            findings.append(_finding("COORDINATE_SYSTEM_MISMATCH", port.name, "Coordinate system does not match the validated format contract."))
        if contract.genome_build_policy != "not_applicable" and artifact.genome_build not in contract.genome_builds:
            findings.append(_finding("GENOME_BUILD_MISMATCH", port.name, "Reference assembly is not in the validated format contract."))
        if contract.annotation_releases and artifact.annotation_release not in contract.annotation_releases:
            findings.append(_finding("ANNOTATION_RELEASE_MISMATCH", port.name, "Annotation release is not in the validated format contract."))
        if artifact.orientation not in contract.orientations:
            findings.append(_finding("ORIENTATION_MISMATCH", port.name, "Artifact orientation does not match the validated format contract."))
        missing_metadata = sorted(set(port.required_metadata) - set(artifact.metadata_fields))
        if missing_metadata:
            findings.append(_finding("MISSING_METADATA", port.name, f"Required metadata fields are absent: {', '.join(missing_metadata)}."))
        profile = FORMAT_REGISTRY.find_token(token)
        if profile is not None:
            profile_snapshot = FormatSnapshot(
                profile_id=profile.id,
                representation=artifact.representation,
                compression=artifact.compression,
                indexes=artifact.indexes,
                sort_order=artifact.sort_order,
                coordinate_system=artifact.coordinate_system,
                genome_build=artifact.genome_build,
                reference_sequence_digest=artifact.reference_sequence_digest,
                annotation_release=artifact.annotation_release,
                identifier_namespace=artifact.identifier_namespace,
                sample_manifest_digest=artifact.sample_manifest_digest,
                orientation=artifact.orientation,
                processing_level=artifact.processing_level,
                metadata_fields=artifact.metadata_fields,
                payload_roles=artifact.payload_roles,
            )
            findings.extend(
                _finding(item.code, port.name, item.message)
                for item in validate_format(profile, profile_snapshot)
            )
    unknown_ports = sorted(set(supplied) - {port.name for port in manifest.input_artifacts})
    for port_name in unknown_ports:
        findings.append(_finding("UNKNOWN_ARTIFACT_PORT", port_name, "Artifact metadata targets an undeclared input port."))
    return findings


def evaluate_compatibility(
    manifest: ModuleManifest,
    environment: EnvironmentSnapshot,
    artifacts: tuple[ArtifactSnapshot, ...],
) -> CompatibilityDecision:
    """Require one exact, complete compatibility-matrix row."""
    evaluated = []
    for row in manifest.compatibility_matrix:
        findings = tuple(_tool_findings(manifest, row, environment) + _artifact_findings(manifest, row, artifacts))
        evaluated.append((len(findings), row.id, findings))
        if not findings:
            return CompatibilityDecision(True, row.id, (), ())
    _, _row_id, best_findings = min(evaluated, key=lambda item: (item[0], item[1]))
    alternatives = ()
    if manifest.alternatives and any(
        finding.code in {"MISSING_TOOL", "UNVALIDATED_TOOL_VERSION", "MISSING_DEPENDENCY", "UNVALIDATED_DEPENDENCY_VERSION"}
        for finding in best_findings
    ):
        alternatives = manifest.alternatives
    return CompatibilityDecision(False, None, best_findings, alternatives)


def _type_matches(expected: str, value: Any) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _validate_output(schema: Mapping[str, Any], value: Any, location: str = "output") -> None:
    expected = schema.get("type")
    if expected and not _type_matches(str(expected), value):
        raise ValueError(f"{location} must be {expected}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = sorted(set(schema.get("required", ())) - set(value))
        if missing:
            raise ValueError(f"{location} is missing required fields: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise ValueError(f"{location} has unsupported fields: {', '.join(extra)}")
        for key, item in value.items():
            if key in properties and isinstance(properties[key], dict):
                _validate_output(properties[key], item, f"{location}.{key}")
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_output(schema["items"], item, f"{location}[{index}]")


def invoke_compatible(
    manifest: ModuleManifest,
    *,
    inputs: dict[str, Any],
    environment: EnvironmentSnapshot,
    artifacts: tuple[ArtifactSnapshot, ...],
    entrypoint: Callable[..., object],
) -> CompatibleInvocation:
    """Gate invocation and attach secret-free compatibility provenance."""
    decision = evaluate_compatibility(manifest, environment, artifacts)
    if not decision.allowed:
        raise CompatibilityError(decision)
    raw_output = entrypoint(**inputs)
    if not isinstance(raw_output, dict):
        raise ValueError("module output must be an object")
    output_for_contract = raw_output
    if manifest.access == "agent_generated":
        envelope = {
            "result_kind": raw_output.get("result_kind"),
            "execution_state": raw_output.get("execution_state"),
        }
        if envelope != {"result_kind": "execution_handoff", "execution_state": "prepared-not-run"}:
            raise ValueError("agent-generated output lacks the mandatory non-execution envelope")
        output_for_contract = {
            key: value
            for key, value in raw_output.items()
            if key not in {"result_kind", "execution_state"}
        }
    _validate_output(manifest.output_schema, output_for_contract)
    serialized = json.dumps(raw_output, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    if len(serialized) > manifest.execution.max_output_bytes:
        raise ValueError("module output exceeds the declared maximum size")
    declared_tools = {item.name for item in manifest.tool_requirements}
    declared_dependencies = {item.name for item in manifest.dependencies}
    provenance = {
        "module_id": manifest.id,
        "module_version": manifest.version,
        "compatibility_row_id": decision.compatibility_row_id,
        "tools": {key: value for key, value in sorted(environment.tools.items()) if key in declared_tools},
        "dependencies": {key: value for key, value in sorted(environment.dependencies.items()) if key in declared_dependencies},
        "tested_version_baseline": {
            "tools": {item.name: environment.tools.get(item.name) in item.tested_versions for item in manifest.tool_requirements if item.name in environment.tools},
            "dependencies": {item.name: environment.dependencies.get(item.name) in item.tested_versions for item in manifest.dependencies if item.name in environment.dependencies},
        },
        "compatibility_policy": {
            "tools": {key: list(value) for key, value in sorted(next(row for row in manifest.compatibility_matrix if row.id == decision.compatibility_row_id).tool_versions.items())},
            "dependencies": {key: list(value) for key, value in sorted(next(row for row in manifest.compatibility_matrix if row.id == decision.compatibility_row_id).dependency_versions.items())},
        },
        "platform": environment.platform,
        "input_formats": {artifact.port: f"{artifact.format}@{artifact.format_version}" for artifact in artifacts},
        "parameters_digest": hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest(),
        "output_digest": hashlib.sha256(serialized).hexdigest(),
    }
    return CompatibleInvocation(output=raw_output, provenance=provenance)
