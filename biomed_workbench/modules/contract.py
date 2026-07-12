"""Strict, source-neutral contracts for independently discoverable modules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from ..models import ACCESS_MODES, KINDS, MUTABILITY_MODES


MODULE_TYPES = frozenset({"data_source", "transform", "analysis", "validation", "interpretation", "design", "delivery"})
MATURITY_LEVELS = frozenset({"experimental", "validated", "reference"})
SEVERITIES = frozenset({"info", "warning", "major", "fatal"})
ECOSYSTEMS = frozenset({"python", "r", "java", "system", "service", "database", "runtime"})
MISMATCH_POLICIES = frozenset({"block", "alternative"})
GENOME_BUILD_POLICIES = frozenset({"not_applicable", "required", "declared", "any_validated"})
REPRESENTATIONS = frozenset({"structured", "text", "binary", "sparse", "container"})
ALLOWED_CREDENTIALS = frozenset({"NCBI_API_KEY"})

_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
_VERSION_RULE_RE = re.compile(r"^(?:==|!=|>=|<=|>|<|~=)?[^\s,]+(?:,(?:==|!=|>=|<=|>|<|~=)?[^\s,]+)*$")
_FORMAT_TOKEN_RE = re.compile(r"^([a-z][a-z0-9+._-]*)@([^\s@]+)$")


@dataclass(frozen=True)
class FormatContract:
    name: str
    versions: tuple[str, ...]
    representations: tuple[str, ...]
    compression: tuple[str, ...]
    required_indexes: tuple[str, ...]
    coordinate_systems: tuple[str, ...]
    genome_build_policy: str


@dataclass(frozen=True)
class ArtifactPort:
    name: str
    artifact_type: str
    formats: tuple[FormatContract, ...]
    processing_levels: tuple[str, ...]
    required_metadata: tuple[str, ...]


@dataclass(frozen=True)
class QualityGate:
    id: str
    severity: str
    description: str
    blocks_interpretation: bool


@dataclass(frozen=True)
class ExecutionContract:
    kind: str
    timeout_seconds: int
    max_output_bytes: int


@dataclass(frozen=True)
class ToolRequirement:
    name: str
    ecosystem: str
    identity: str
    required: bool
    tested_versions: tuple[str, ...]
    allowed_versions: tuple[str, ...]
    version_source: str
    verified_at: str
    version_probe: tuple[str, ...]
    version_pattern: str
    mismatch_policy: str
    version_differences: tuple[str, ...]
    platforms: tuple[str, ...]


@dataclass(frozen=True)
class DependencyRequirement:
    name: str
    ecosystem: str
    required: bool
    tested_versions: tuple[str, ...]
    allowed_versions: tuple[str, ...]
    version_source: str
    verified_at: str
    purpose: str
    conflicts: tuple[str, ...]
    platforms: tuple[str, ...]


@dataclass(frozen=True)
class CompatibilityRow:
    id: str
    module_version: str
    tool_versions: dict[str, tuple[str, ...]]
    dependency_versions: dict[str, tuple[str, ...]]
    input_formats: dict[str, tuple[str, ...]]
    output_formats: dict[str, tuple[str, ...]]
    platforms: tuple[str, ...]


@dataclass(frozen=True)
class ProvenanceContract:
    license: str
    concept_sources: tuple[str, ...]


@dataclass(frozen=True)
class ModuleManifest:
    schema_version: int
    id: str
    version: str
    title: str
    description: str
    module_type: str
    domains: tuple[str, ...]
    intents: tuple[str, ...]
    questions: tuple[str, ...]
    entrypoint: str
    execution: ExecutionContract
    maturity: str
    input_artifacts: tuple[ArtifactPort, ...]
    output_artifacts: tuple[ArtifactPort, ...]
    preconditions: tuple[str, ...]
    assumptions: tuple[str, ...]
    quality_gates: tuple[QualityGate, ...]
    limitations: tuple[str, ...]
    evidence_effects: tuple[str, ...]
    alternatives: tuple[str, ...]
    complements: tuple[str, ...]
    tool_requirements: tuple[ToolRequirement, ...]
    dependencies: tuple[DependencyRequirement, ...]
    compatibility_matrix: tuple[CompatibilityRow, ...]
    access: str
    mutability: str
    credentials: tuple[str, ...]
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    kernel_compatibility: tuple[str, ...]
    provenance: ProvenanceContract


_MANIFEST_FIELDS = frozenset(ModuleManifest.__dataclass_fields__)
_FORMAT_FIELDS = frozenset(FormatContract.__dataclass_fields__)
_ARTIFACT_FIELDS = frozenset(ArtifactPort.__dataclass_fields__)
_QUALITY_FIELDS = frozenset(QualityGate.__dataclass_fields__)
_EXECUTION_FIELDS = frozenset(ExecutionContract.__dataclass_fields__)
_TOOL_FIELDS = frozenset(ToolRequirement.__dataclass_fields__)
_DEPENDENCY_FIELDS = frozenset(DependencyRequirement.__dataclass_fields__)
_COMPATIBILITY_FIELDS = frozenset(CompatibilityRow.__dataclass_fields__)
_PROVENANCE_FIELDS = frozenset(ProvenanceContract.__dataclass_fields__)


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{location} must be an object")
    return dict(value)


def _exact_fields(payload: Mapping[str, Any], expected: frozenset[str], location: str) -> None:
    extra = sorted(set(payload) - expected)
    missing = sorted(expected - set(payload))
    if extra:
        raise ValueError(f"unsupported {location} fields: {', '.join(extra)}")
    if missing:
        raise ValueError(f"missing {location} fields: {', '.join(missing)}")


def _text(value: Any, location: str, *, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(f"{location} must be meaningful text")
    return value.strip()


def _strings(value: Any, location: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError(f"{location} must be a {'possibly empty ' if allow_empty else 'nonempty '}list")
    result = tuple(_text(item, f"{location} item") for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{location} contains duplicate values")
    return result


def _boolean(value: Any, location: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{location} must be boolean")
    return value


def _positive_integer(value: Any, location: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{location} must be a positive integer")
    return value


def _date(value: Any, location: str) -> str:
    text = _text(value, location)
    try:
        date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{location} must be an ISO date") from None
    return text


def _version_rules(value: Any, location: str) -> tuple[str, ...]:
    rules = _strings(value, location)
    if any(not _VERSION_RULE_RE.fullmatch(rule) for rule in rules):
        raise ValueError(f"{location} contains an invalid version rule")
    return rules


def _closed_schema(value: Any, location: str) -> dict[str, object]:
    schema = _object(value, location)
    properties = schema.get("properties")
    required = schema.get("required")
    if (
        schema.get("type") != "object"
        or not isinstance(properties, dict)
        or not isinstance(required, list)
        or any(not isinstance(item, str) for item in required)
        or not set(required) <= set(properties)
        or schema.get("additionalProperties") is not False
    ):
        raise ValueError(f"{location} must be a closed object schema")
    return dict(schema)


def _format(value: Any, location: str) -> FormatContract:
    payload = _object(value, location)
    _exact_fields(payload, _FORMAT_FIELDS, location)
    name = _text(payload["name"], f"{location}.name")
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"{location}.name has an invalid identifier")
    versions = _strings(payload["versions"], f"{location} format versions")
    representations = _strings(payload["representations"], f"{location}.representations")
    if set(representations) - REPRESENTATIONS:
        raise ValueError(f"{location}.representations contains unsupported values")
    genome_policy = _text(payload["genome_build_policy"], f"{location}.genome_build_policy")
    if genome_policy not in GENOME_BUILD_POLICIES:
        raise ValueError(f"{location}.genome_build_policy is unsupported")
    return FormatContract(
        name=name,
        versions=versions,
        representations=representations,
        compression=_strings(payload["compression"], f"{location}.compression"),
        required_indexes=_strings(payload["required_indexes"], f"{location}.required_indexes", allow_empty=True),
        coordinate_systems=_strings(payload["coordinate_systems"], f"{location}.coordinate_systems", allow_empty=True),
        genome_build_policy=genome_policy,
    )


def _artifact(value: Any, location: str) -> ArtifactPort:
    payload = _object(value, location)
    _exact_fields(payload, _ARTIFACT_FIELDS, location)
    name = _text(payload["name"], f"{location}.name")
    artifact_type = _text(payload["artifact_type"], f"{location}.artifact_type")
    if not _NAME_RE.fullmatch(name) or not _NAME_RE.fullmatch(artifact_type):
        raise ValueError(f"{location} names must be source-neutral identifiers")
    if not isinstance(payload["formats"], list) or not payload["formats"]:
        raise ValueError(f"{location}.formats must be nonempty")
    formats = tuple(_format(item, f"{location}.formats[{index}]") for index, item in enumerate(payload["formats"]))
    if len({item.name for item in formats}) != len(formats):
        raise ValueError(f"{location}.formats contains duplicate names")
    return ArtifactPort(
        name=name,
        artifact_type=artifact_type,
        formats=formats,
        processing_levels=_strings(payload["processing_levels"], f"{location}.processing_levels"),
        required_metadata=_strings(payload["required_metadata"], f"{location}.required_metadata", allow_empty=True),
    )


def _artifacts(value: Any, location: str) -> tuple[ArtifactPort, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{location} must be nonempty")
    result = tuple(_artifact(item, f"{location}[{index}]") for index, item in enumerate(value))
    if len({item.name for item in result}) != len(result):
        raise ValueError(f"{location} contains duplicate port names")
    return result


def _quality_gate(value: Any, location: str) -> QualityGate:
    payload = _object(value, location)
    _exact_fields(payload, _QUALITY_FIELDS, location)
    identifier = _text(payload["id"], f"{location}.id")
    severity = _text(payload["severity"], f"{location}.severity")
    if not _ID_RE.fullmatch(identifier) or severity not in SEVERITIES:
        raise ValueError(f"{location} has invalid id or severity")
    return QualityGate(
        id=identifier,
        severity=severity,
        description=_text(payload["description"], f"{location}.description", minimum=12),
        blocks_interpretation=_boolean(payload["blocks_interpretation"], f"{location}.blocks_interpretation"),
    )


def _execution(value: Any) -> ExecutionContract:
    payload = _object(value, "execution")
    _exact_fields(payload, _EXECUTION_FIELDS, "execution")
    kind = _text(payload["kind"], "execution.kind")
    if kind not in KINDS:
        raise ValueError("execution.kind is unsupported")
    return ExecutionContract(
        kind=kind,
        timeout_seconds=_positive_integer(payload["timeout_seconds"], "execution.timeout_seconds"),
        max_output_bytes=_positive_integer(payload["max_output_bytes"], "execution.max_output_bytes"),
    )


def _tool(value: Any, location: str) -> ToolRequirement:
    payload = _object(value, location)
    _exact_fields(payload, _TOOL_FIELDS, location)
    ecosystem = _text(payload["ecosystem"], f"{location}.ecosystem")
    if ecosystem not in ECOSYSTEMS - {"runtime"}:
        raise ValueError(f"{location}.ecosystem is unsupported")
    tested = _strings(payload["tested_versions"], f"{location} tested versions")
    source = _text(payload["version_source"], f"{location}.version_source")
    if not source.startswith("https://"):
        raise ValueError(f"{location}.version_source must be an authoritative HTTPS URL")
    probe = _strings(payload["version_probe"], f"{location}.version_probe")
    pattern = _text(payload["version_pattern"], f"{location}.version_pattern")
    try:
        re.compile(pattern)
    except re.error:
        raise ValueError(f"{location}.version_pattern is invalid") from None
    mismatch_policy = _text(payload["mismatch_policy"], f"{location}.mismatch_policy")
    if mismatch_policy not in MISMATCH_POLICIES:
        raise ValueError(f"{location}.mismatch_policy is unsupported")
    return ToolRequirement(
        name=_text(payload["name"], f"{location}.name"),
        ecosystem=ecosystem,
        identity=_text(payload["identity"], f"{location}.identity"),
        required=_boolean(payload["required"], f"{location}.required"),
        tested_versions=tested,
        allowed_versions=_version_rules(payload["allowed_versions"], f"{location}.allowed_versions"),
        version_source=source,
        verified_at=_date(payload["verified_at"], f"{location}.verified_at"),
        version_probe=probe,
        version_pattern=pattern,
        mismatch_policy=mismatch_policy,
        version_differences=_strings(payload["version_differences"], f"{location}.version_differences", allow_empty=True),
        platforms=_strings(payload["platforms"], f"{location}.platforms"),
    )


def _dependency(value: Any, location: str) -> DependencyRequirement:
    payload = _object(value, location)
    _exact_fields(payload, _DEPENDENCY_FIELDS, location)
    ecosystem = _text(payload["ecosystem"], f"{location}.ecosystem")
    if ecosystem not in ECOSYSTEMS:
        raise ValueError(f"{location}.ecosystem is unsupported")
    source = _text(payload["version_source"], f"{location}.version_source")
    if not source.startswith("https://"):
        raise ValueError(f"{location}.version_source must be an authoritative HTTPS URL")
    return DependencyRequirement(
        name=_text(payload["name"], f"{location}.name"),
        ecosystem=ecosystem,
        required=_boolean(payload["required"], f"{location}.required"),
        tested_versions=_strings(payload["tested_versions"], f"{location}.tested_versions"),
        allowed_versions=_version_rules(payload["allowed_versions"], f"{location}.allowed_versions"),
        version_source=source,
        verified_at=_date(payload["verified_at"], f"{location}.verified_at"),
        purpose=_text(payload["purpose"], f"{location}.purpose", minimum=12),
        conflicts=_strings(payload["conflicts"], f"{location}.conflicts", allow_empty=True),
        platforms=_strings(payload["platforms"], f"{location}.platforms"),
    )


def _version_map(value: Any, location: str) -> dict[str, tuple[str, ...]]:
    payload = _object(value, location)
    return {str(key): _strings(item, f"{location}.{key}") for key, item in sorted(payload.items())}


def _compatibility(value: Any, location: str) -> CompatibilityRow:
    payload = _object(value, location)
    _exact_fields(payload, _COMPATIBILITY_FIELDS, location)
    return CompatibilityRow(
        id=_text(payload["id"], f"{location}.id"),
        module_version=_text(payload["module_version"], f"{location}.module_version"),
        tool_versions=_version_map(payload["tool_versions"], f"{location}.tool_versions"),
        dependency_versions=_version_map(payload["dependency_versions"], f"{location}.dependency_versions"),
        input_formats=_version_map(payload["input_formats"], f"{location}.input_formats"),
        output_formats=_version_map(payload["output_formats"], f"{location}.output_formats"),
        platforms=_strings(payload["platforms"], f"{location}.platforms"),
    )


def _provenance(value: Any) -> ProvenanceContract:
    payload = _object(value, "provenance")
    _exact_fields(payload, _PROVENANCE_FIELDS, "provenance")
    return ProvenanceContract(
        license=_text(payload["license"], "provenance.license"),
        concept_sources=_strings(payload["concept_sources"], "provenance.concept_sources"),
    )


def _validate_compatibility(manifest: ModuleManifest) -> None:
    tools = {item.name: item for item in manifest.tool_requirements}
    dependencies = {item.name: item for item in manifest.dependencies}
    inputs = {item.name: item for item in manifest.input_artifacts}
    outputs = {item.name: item for item in manifest.output_artifacts}
    if len(tools) != len(manifest.tool_requirements) or len(dependencies) != len(manifest.dependencies):
        raise ValueError("tool and dependency names must be unique")
    if not manifest.compatibility_matrix:
        raise ValueError("compatibility_matrix must be nonempty")
    row_ids = set()
    for row in manifest.compatibility_matrix:
        if row.id in row_ids:
            raise ValueError(f"duplicate compatibility row: {row.id}")
        row_ids.add(row.id)
        if row.module_version != manifest.version:
            raise ValueError(f"compatibility row {row.id} has a different module version")
        for name, versions in row.tool_versions.items():
            if name not in tools:
                raise ValueError(f"compatibility row {row.id} references unknown tool: {name}")
            if not set(versions) <= set(tools[name].tested_versions):
                raise ValueError(f"compatibility row {row.id} references untested tool versions")
        for name, versions in row.dependency_versions.items():
            if name not in dependencies:
                raise ValueError(f"compatibility row {row.id} references unknown dependency: {name}")
            if not set(versions) <= set(dependencies[name].tested_versions):
                raise ValueError(f"compatibility row {row.id} references untested dependency versions")
        missing_tools = sorted(name for name, item in tools.items() if item.required and name not in row.tool_versions)
        missing_dependencies = sorted(name for name, item in dependencies.items() if item.required and name not in row.dependency_versions)
        if missing_tools or missing_dependencies:
            raise ValueError(f"compatibility row {row.id} omits required tool or dependency versions")
        _validate_format_map(row.input_formats, inputs, row.id, "input")
        _validate_format_map(row.output_formats, outputs, row.id, "output")


def _validate_format_map(
    values: dict[str, tuple[str, ...]],
    ports: dict[str, ArtifactPort],
    row_id: str,
    direction: str,
) -> None:
    if set(values) != set(ports):
        unknown = sorted(set(values) - set(ports))
        missing = sorted(set(ports) - set(values))
        if unknown:
            raise ValueError(f"compatibility row {row_id} references unknown {direction} artifact: {unknown[0]}")
        raise ValueError(f"compatibility row {row_id} omits {direction} artifact: {missing[0]}")
    for port_name, tokens in values.items():
        supported = {f"{fmt.name}@{version}" for fmt in ports[port_name].formats for version in fmt.versions}
        for token in tokens:
            if not _FORMAT_TOKEN_RE.fullmatch(token) or token not in supported:
                raise ValueError(f"compatibility row {row_id} references unsupported {direction} format: {token}")


def parse_manifest(value: Any) -> ModuleManifest:
    payload = _object(value, "manifest")
    _exact_fields(payload, _MANIFEST_FIELDS, "manifest")
    if payload["schema_version"] != 1:
        raise ValueError("unsupported manifest schema_version")
    identifier = _text(payload["id"], "manifest.id")
    version = _text(payload["version"], "manifest.version")
    if not _ID_RE.fullmatch(identifier) or not _SEMVER_RE.fullmatch(version):
        raise ValueError("manifest id or semantic version is invalid")
    module_type = _text(payload["module_type"], "manifest.module_type")
    maturity = _text(payload["maturity"], "manifest.maturity")
    access = _text(payload["access"], "manifest.access")
    mutability = _text(payload["mutability"], "manifest.mutability")
    if module_type not in MODULE_TYPES or maturity not in MATURITY_LEVELS:
        raise ValueError("manifest module_type or maturity is unsupported")
    if access not in ACCESS_MODES or mutability not in MUTABILITY_MODES:
        raise ValueError("manifest access or mutability is unsupported")
    credentials = _strings(payload["credentials"], "manifest.credentials", allow_empty=True)
    if set(credentials) - ALLOWED_CREDENTIALS:
        raise ValueError("manifest requests an unsupported credential")
    quality_values = payload["quality_gates"]
    if not isinstance(quality_values, list) or not quality_values:
        raise ValueError("manifest.quality_gates must be nonempty")
    tool_values = payload["tool_requirements"]
    dependency_values = payload["dependencies"]
    compatibility_values = payload["compatibility_matrix"]
    if not isinstance(tool_values, list) or not isinstance(dependency_values, list) or not isinstance(compatibility_values, list):
        raise ValueError("tools, dependencies, and compatibility_matrix must be lists")
    kernel_compatibility = _version_rules(payload["kernel_compatibility"], "manifest.kernel_compatibility")
    manifest = ModuleManifest(
        schema_version=1,
        id=identifier,
        version=version,
        title=_text(payload["title"], "manifest.title"),
        description=_text(payload["description"], "manifest.description", minimum=24),
        module_type=module_type,
        domains=_strings(payload["domains"], "manifest.domains"),
        intents=_strings(payload["intents"], "manifest.intents"),
        questions=_strings(payload["questions"], "manifest.questions"),
        entrypoint=_text(payload["entrypoint"], "manifest.entrypoint"),
        execution=_execution(payload["execution"]),
        maturity=maturity,
        input_artifacts=_artifacts(payload["input_artifacts"], "manifest.input_artifacts"),
        output_artifacts=_artifacts(payload["output_artifacts"], "manifest.output_artifacts"),
        preconditions=_strings(payload["preconditions"], "manifest.preconditions"),
        assumptions=_strings(payload["assumptions"], "manifest.assumptions"),
        quality_gates=tuple(_quality_gate(item, f"manifest.quality_gates[{index}]") for index, item in enumerate(quality_values)),
        limitations=_strings(payload["limitations"], "manifest.limitations"),
        evidence_effects=_strings(payload["evidence_effects"], "manifest.evidence_effects"),
        alternatives=_strings(payload["alternatives"], "manifest.alternatives", allow_empty=True),
        complements=_strings(payload["complements"], "manifest.complements", allow_empty=True),
        tool_requirements=tuple(_tool(item, f"manifest.tool_requirements[{index}]") for index, item in enumerate(tool_values)),
        dependencies=tuple(_dependency(item, f"manifest.dependencies[{index}]") for index, item in enumerate(dependency_values)),
        compatibility_matrix=tuple(_compatibility(item, f"manifest.compatibility_matrix[{index}]") for index, item in enumerate(compatibility_values)),
        access=access,
        mutability=mutability,
        credentials=credentials,
        input_schema=_closed_schema(payload["input_schema"], "manifest.input_schema"),
        output_schema=_closed_schema(payload["output_schema"], "manifest.output_schema"),
        kernel_compatibility=kernel_compatibility,
        provenance=_provenance(payload["provenance"]),
    )
    _validate_compatibility(manifest)
    return manifest


def _format_dict(value: FormatContract) -> dict[str, object]:
    return {
        "name": value.name,
        "versions": list(value.versions),
        "representations": list(value.representations),
        "compression": list(value.compression),
        "required_indexes": list(value.required_indexes),
        "coordinate_systems": list(value.coordinate_systems),
        "genome_build_policy": value.genome_build_policy,
    }


def _artifact_dict(value: ArtifactPort) -> dict[str, object]:
    return {
        "name": value.name,
        "artifact_type": value.artifact_type,
        "formats": [_format_dict(item) for item in value.formats],
        "processing_levels": list(value.processing_levels),
        "required_metadata": list(value.required_metadata),
    }


def _quality_dict(value: QualityGate) -> dict[str, object]:
    return {
        "id": value.id,
        "severity": value.severity,
        "description": value.description,
        "blocks_interpretation": value.blocks_interpretation,
    }


def _tool_dict(value: ToolRequirement) -> dict[str, object]:
    return {
        "name": value.name,
        "ecosystem": value.ecosystem,
        "identity": value.identity,
        "required": value.required,
        "tested_versions": list(value.tested_versions),
        "allowed_versions": list(value.allowed_versions),
        "version_source": value.version_source,
        "verified_at": value.verified_at,
        "version_probe": list(value.version_probe),
        "version_pattern": value.version_pattern,
        "mismatch_policy": value.mismatch_policy,
        "version_differences": list(value.version_differences),
        "platforms": list(value.platforms),
    }


def _dependency_dict(value: DependencyRequirement) -> dict[str, object]:
    return {
        "name": value.name,
        "ecosystem": value.ecosystem,
        "required": value.required,
        "tested_versions": list(value.tested_versions),
        "allowed_versions": list(value.allowed_versions),
        "version_source": value.version_source,
        "verified_at": value.verified_at,
        "purpose": value.purpose,
        "conflicts": list(value.conflicts),
        "platforms": list(value.platforms),
    }


def _compatibility_dict(value: CompatibilityRow) -> dict[str, object]:
    return {
        "id": value.id,
        "module_version": value.module_version,
        "tool_versions": {key: list(item) for key, item in value.tool_versions.items()},
        "dependency_versions": {key: list(item) for key, item in value.dependency_versions.items()},
        "input_formats": {key: list(item) for key, item in value.input_formats.items()},
        "output_formats": {key: list(item) for key, item in value.output_formats.items()},
        "platforms": list(value.platforms),
    }


def manifest_to_dict(value: ModuleManifest) -> dict[str, object]:
    """Return a detached, canonical JSON-compatible representation."""
    return {
        "schema_version": value.schema_version,
        "id": value.id,
        "version": value.version,
        "title": value.title,
        "description": value.description,
        "module_type": value.module_type,
        "domains": list(value.domains),
        "intents": list(value.intents),
        "questions": list(value.questions),
        "entrypoint": value.entrypoint,
        "execution": {
            "kind": value.execution.kind,
            "timeout_seconds": value.execution.timeout_seconds,
            "max_output_bytes": value.execution.max_output_bytes,
        },
        "maturity": value.maturity,
        "input_artifacts": [_artifact_dict(item) for item in value.input_artifacts],
        "output_artifacts": [_artifact_dict(item) for item in value.output_artifacts],
        "preconditions": list(value.preconditions),
        "assumptions": list(value.assumptions),
        "quality_gates": [_quality_dict(item) for item in value.quality_gates],
        "limitations": list(value.limitations),
        "evidence_effects": list(value.evidence_effects),
        "alternatives": list(value.alternatives),
        "complements": list(value.complements),
        "tool_requirements": [_tool_dict(item) for item in value.tool_requirements],
        "dependencies": [_dependency_dict(item) for item in value.dependencies],
        "compatibility_matrix": [_compatibility_dict(item) for item in value.compatibility_matrix],
        "access": value.access,
        "mutability": value.mutability,
        "credentials": list(value.credentials),
        "input_schema": dict(value.input_schema),
        "output_schema": dict(value.output_schema),
        "kernel_compatibility": list(value.kernel_compatibility),
        "provenance": {"license": value.provenance.license, "concept_sources": list(value.provenance.concept_sources)},
    }
