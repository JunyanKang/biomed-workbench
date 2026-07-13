"""Strict, source-neutral contracts for independently discoverable modules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from ..models import ACCESS_MODES, KINDS, MUTABILITY_MODES
from .scientific_command import ScientificCommand


MODULE_TYPES = frozenset({"data_source", "transform", "analysis", "validation", "interpretation", "design", "delivery"})
MATURITY_LEVELS = frozenset({"experimental", "validated", "reference"})
SEVERITIES = frozenset({"info", "warning", "major", "fatal"})
ECOSYSTEMS = frozenset({"python", "r", "java", "system", "service", "database", "runtime"})
MISMATCH_POLICIES = frozenset({"block", "alternative"})
VERSION_PROBE_KINDS = frozenset({"command", "python_callable", "service_contract", "database_contract"})
VERSION_DIFFERENCE_CATEGORIES = frozenset({"parameter", "api", "field", "default", "behavior", "input-format", "output-format"})
COMPATIBILITY_EFFECTS = frozenset({"informational", "requires-parameter", "requires-parser", "requires-format", "breaking"})
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
    genome_builds: tuple[str, ...]
    annotation_releases: tuple[str, ...]
    orientations: tuple[str, ...]


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
    command: ScientificCommand | None = None


@dataclass(frozen=True)
class VersionDifference:
    id: str
    affected_versions: tuple[str, ...]
    category: str
    description: str
    compatibility_effect: str
    required_action: str
    source: str


@dataclass(frozen=True)
class DependencyConflict:
    dependency: str
    versions: tuple[str, ...]
    reason: str
    required_action: str
    source: str


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
    version_probe_kind: str
    version_probe_timeout_seconds: int
    version_pattern: str
    mismatch_policy: str
    version_differences: tuple[VersionDifference, ...]
    platforms: tuple[str, ...]


@dataclass(frozen=True)
class DependencyRequirement:
    name: str
    ecosystem: str
    identity: str
    required: bool
    tested_versions: tuple[str, ...]
    allowed_versions: tuple[str, ...]
    version_source: str
    verified_at: str
    version_probe: tuple[str, ...]
    version_probe_kind: str
    version_probe_timeout_seconds: int
    version_pattern: str
    purpose: str
    conflicts: tuple[DependencyConflict, ...]
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
    regression_evidence_ids: tuple[str, ...]
    end_to_end_evidence_ids: tuple[str, ...]
    verified_at: str


@dataclass(frozen=True)
class ProvenanceContract:
    license: str
    concept_sources: tuple[str, ...]


@dataclass(frozen=True)
class CodeTemplate:
    path: str
    language: str
    purpose: str
    quality_gate_ids: tuple[str, ...]
    requires_adaptation: bool


@dataclass(frozen=True)
class AgentTemplateSection:
    id: str
    purpose: str
    required_logic: tuple[str, ...]
    output_artifact_types: tuple[str, ...]
    template_files: tuple[str, ...]


@dataclass(frozen=True)
class AgentParameterRule:
    id: str
    parameter: str
    decision_inputs: tuple[str, ...]
    selection_rule: str
    validation_rule: str


@dataclass(frozen=True)
class AgentProtocol:
    schema_version: int
    mode: str
    languages: tuple[str, ...]
    template_sections: tuple[AgentTemplateSection, ...]
    parameter_rules: tuple[AgentParameterRule, ...]
    preflight_checks: tuple[str, ...]
    postflight_checks: tuple[str, ...]
    provenance_fields: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    requires_observed_execution: bool


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
    code_templates: tuple[CodeTemplate, ...] = ()
    agent_protocol: AgentProtocol | None = None


_MANIFEST_FIELDS = frozenset(ModuleManifest.__dataclass_fields__)
_FORMAT_FIELDS = frozenset(FormatContract.__dataclass_fields__)
_ARTIFACT_FIELDS = frozenset(ArtifactPort.__dataclass_fields__)
_QUALITY_FIELDS = frozenset(QualityGate.__dataclass_fields__)
_EXECUTION_BASE_FIELDS = frozenset({"kind", "timeout_seconds", "max_output_bytes"})
_TOOL_FIELDS = frozenset(ToolRequirement.__dataclass_fields__)
_DEPENDENCY_FIELDS = frozenset(DependencyRequirement.__dataclass_fields__)
_VERSION_DIFFERENCE_FIELDS = frozenset(VersionDifference.__dataclass_fields__)
_DEPENDENCY_CONFLICT_FIELDS = frozenset(DependencyConflict.__dataclass_fields__)
_COMPATIBILITY_FIELDS = frozenset(CompatibilityRow.__dataclass_fields__)
_PROVENANCE_FIELDS = frozenset(ProvenanceContract.__dataclass_fields__)
_CODE_TEMPLATE_FIELDS = frozenset(CodeTemplate.__dataclass_fields__)
_AGENT_PROTOCOL_FIELDS = frozenset(AgentProtocol.__dataclass_fields__)
_AGENT_SECTION_FIELDS = frozenset(AgentTemplateSection.__dataclass_fields__)
_AGENT_PARAMETER_FIELDS = frozenset(AgentParameterRule.__dataclass_fields__)
_OPTIONAL_MANIFEST_FIELDS = frozenset({"agent_protocol", "code_templates"})


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


def _release_tuple(value: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)*)(?:[-+][0-9A-Za-z._-]+)?", value)
    return tuple(int(item) for item in match.group(1).split(".")) if match else None


def _compare_release(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    return (padded_left > padded_right) - (padded_left < padded_right)


def _matches_clause(version: str, clause: str) -> bool:
    match = re.fullmatch(r"(==|!=|>=|<=|>|<|~=)?(.+)", clause)
    if not match:
        return False
    operator, expected = match.group(1) or "==", match.group(2)
    if operator in {"==", "!="}:
        equal = version == expected
        return equal if operator == "==" else not equal
    actual_release, expected_release = _release_tuple(version), _release_tuple(expected)
    if actual_release is None or expected_release is None:
        return False
    comparison = _compare_release(actual_release, expected_release)
    if operator == ">=":
        return comparison >= 0
    if operator == "<=":
        return comparison <= 0
    if operator == ">":
        return comparison > 0
    if operator == "<":
        return comparison < 0
    if operator == "~=":
        prefix = expected_release[:-1] if len(expected_release) > 2 else expected_release[:1]
        return comparison >= 0 and actual_release[: len(prefix)] == prefix
    return False


def _version_allowed(version: str, rules: tuple[str, ...]) -> bool:
    return any(all(_matches_clause(version, clause) for clause in rule.split(",")) for rule in rules)


def _validate_tested_versions(tested: tuple[str, ...], allowed: tuple[str, ...], location: str) -> None:
    outside = [version for version in tested if not _version_allowed(version, allowed)]
    if outside:
        raise ValueError(f"{location} tested versions are outside allowed versions: {', '.join(outside)}")


def version_is_allowed(version: str, rules: tuple[str, ...]) -> bool:
    """Return whether an exact version satisfies at least one declared rule."""
    if not isinstance(version, str) or not version or not isinstance(rules, tuple) or not rules:
        return False
    return _version_allowed(version, rules)


def _rule_within_policy(rule: str, policy: tuple[str, ...]) -> bool:
    if rule in policy:
        return True
    exact = re.fullmatch(r"==(.+)", rule)
    candidate = exact.group(1) if exact else rule
    return not any(operator in candidate for operator in ("!=", ">=", "<=", ">", "<", "~=", ",")) and version_is_allowed(candidate, policy)


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
    genome_builds = _strings(payload["genome_builds"], f"{location}.genome_builds", allow_empty=True)
    coordinate_systems = _strings(payload["coordinate_systems"], f"{location}.coordinate_systems", allow_empty=True)
    if genome_policy == "not_applicable" and genome_builds:
        raise ValueError(f"{location}.genome_builds must be empty when genome builds are not applicable")
    if genome_policy != "not_applicable" and (not genome_builds or not coordinate_systems):
        raise ValueError(f"{location} must declare validated genome builds and coordinate systems")
    return FormatContract(
        name=name,
        versions=versions,
        representations=representations,
        compression=_strings(payload["compression"], f"{location}.compression"),
        required_indexes=_strings(payload["required_indexes"], f"{location}.required_indexes", allow_empty=True),
        coordinate_systems=coordinate_systems,
        genome_build_policy=genome_policy,
        genome_builds=genome_builds,
        annotation_releases=_strings(payload["annotation_releases"], f"{location}.annotation_releases", allow_empty=True),
        orientations=_strings(payload["orientations"], f"{location}.orientations"),
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
    extra = sorted(set(payload) - (_EXECUTION_BASE_FIELDS | {"command"}))
    missing = sorted(_EXECUTION_BASE_FIELDS - set(payload))
    if extra:
        raise ValueError(f"unsupported execution fields: {', '.join(extra)}")
    if missing:
        raise ValueError(f"missing execution fields: {', '.join(missing)}")
    kind = _text(payload["kind"], "execution.kind")
    if kind not in KINDS:
        raise ValueError("execution.kind is unsupported")
    if kind == "command" and "command" not in payload:
        raise ValueError("command execution requires a scientific command contract")
    if kind != "command" and "command" in payload:
        raise ValueError("scientific command contract is only valid for command execution")
    return ExecutionContract(
        kind=kind,
        timeout_seconds=_positive_integer(payload["timeout_seconds"], "execution.timeout_seconds"),
        max_output_bytes=_positive_integer(payload["max_output_bytes"], "execution.max_output_bytes"),
        command=ScientificCommand.from_dict(_object(payload["command"], "execution.command")) if kind == "command" else None,
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
    probe, probe_kind, probe_timeout, pattern = _probe_contract(payload, location, ecosystem)
    mismatch_policy = _text(payload["mismatch_policy"], f"{location}.mismatch_policy")
    if mismatch_policy not in MISMATCH_POLICIES:
        raise ValueError(f"{location}.mismatch_policy is unsupported")
    allowed = _version_rules(payload["allowed_versions"], f"{location}.allowed_versions")
    _validate_tested_versions(tested, allowed, location)
    differences = payload["version_differences"]
    if not isinstance(differences, list):
        raise ValueError(f"{location}.version_differences must be a list")
    parsed_differences = tuple(_version_difference(item, f"{location}.version_differences[{index}]") for index, item in enumerate(differences))
    if len({item.id for item in parsed_differences}) != len(parsed_differences):
        raise ValueError(f"{location}.version_differences contains duplicate ids")
    if any(any(not _rule_within_policy(rule, allowed) for rule in item.affected_versions) for item in parsed_differences):
        raise ValueError(f"{location}.version_differences references versions outside the allowed rules")
    return ToolRequirement(
        name=_text(payload["name"], f"{location}.name"),
        ecosystem=ecosystem,
        identity=_text(payload["identity"], f"{location}.identity"),
        required=_boolean(payload["required"], f"{location}.required"),
        tested_versions=tested,
        allowed_versions=allowed,
        version_source=source,
        verified_at=_date(payload["verified_at"], f"{location}.verified_at"),
        version_probe=probe,
        version_probe_kind=probe_kind,
        version_probe_timeout_seconds=probe_timeout,
        version_pattern=pattern,
        mismatch_policy=mismatch_policy,
        version_differences=parsed_differences,
        platforms=_strings(payload["platforms"], f"{location}.platforms"),
    )


def _probe_contract(payload: Mapping[str, Any], location: str, ecosystem: str) -> tuple[tuple[str, ...], str, int, str]:
    probe = _strings(payload["version_probe"], f"{location}.version_probe")
    probe_kind = _text(payload["version_probe_kind"], f"{location}.version_probe_kind")
    if probe_kind not in VERSION_PROBE_KINDS:
        raise ValueError(f"{location}.version_probe_kind is unsupported")
    if probe_kind in {"python_callable", "service_contract", "database_contract"}:
        if len(probe) != 1 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*", probe[0]):
            raise ValueError(f"{location}.version_probe must be one public module:function target")
    if probe_kind == "service_contract" and ecosystem != "service":
        raise ValueError(f"{location}.service_contract probes require the service ecosystem")
    if probe_kind == "database_contract" and ecosystem != "database":
        raise ValueError(f"{location}.database_contract probes require the database ecosystem")
    if probe_kind == "command" and ecosystem in {"service", "database"}:
        raise ValueError(f"{location}.service and database probes cannot execute as commands")
    probe_timeout = _positive_integer(payload["version_probe_timeout_seconds"], f"{location}.version_probe_timeout_seconds")
    if probe_timeout > 30:
        raise ValueError(f"{location}.version_probe_timeout_seconds must be at most 30")
    pattern = _text(payload["version_pattern"], f"{location}.version_pattern")
    try:
        re.compile(pattern)
    except re.error:
        raise ValueError(f"{location}.version_pattern is invalid") from None
    return probe, probe_kind, probe_timeout, pattern


def _version_difference(value: Any, location: str) -> VersionDifference:
    payload = _object(value, location)
    _exact_fields(payload, _VERSION_DIFFERENCE_FIELDS, location)
    identifier = _text(payload["id"], f"{location}.id")
    if not _ID_RE.fullmatch(identifier):
        raise ValueError(f"{location}.id is invalid")
    category = _text(payload["category"], f"{location}.category")
    effect = _text(payload["compatibility_effect"], f"{location}.compatibility_effect")
    if category not in VERSION_DIFFERENCE_CATEGORIES or effect not in COMPATIBILITY_EFFECTS:
        raise ValueError(f"{location} category or compatibility effect is unsupported")
    source = _text(payload["source"], f"{location}.source")
    if not source.startswith("https://"):
        raise ValueError(f"{location}.source must be an authoritative HTTPS URL")
    return VersionDifference(
        id=identifier,
        affected_versions=_version_rules(payload["affected_versions"], f"{location}.affected_versions"),
        category=category,
        description=_text(payload["description"], f"{location}.description", minimum=12),
        compatibility_effect=effect,
        required_action=_text(payload["required_action"], f"{location}.required_action", minimum=12),
        source=source,
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
    tested = _strings(payload["tested_versions"], f"{location}.tested_versions")
    allowed = _version_rules(payload["allowed_versions"], f"{location}.allowed_versions")
    _validate_tested_versions(tested, allowed, location)
    probe, probe_kind, probe_timeout, pattern = _probe_contract(payload, location, ecosystem)
    conflicts = payload["conflicts"]
    if not isinstance(conflicts, list):
        raise ValueError(f"{location}.conflicts must be a list")
    return DependencyRequirement(
        name=_text(payload["name"], f"{location}.name"),
        ecosystem=ecosystem,
        identity=_text(payload["identity"], f"{location}.identity"),
        required=_boolean(payload["required"], f"{location}.required"),
        tested_versions=tested,
        allowed_versions=allowed,
        version_source=source,
        verified_at=_date(payload["verified_at"], f"{location}.verified_at"),
        version_probe=probe,
        version_probe_kind=probe_kind,
        version_probe_timeout_seconds=probe_timeout,
        version_pattern=pattern,
        purpose=_text(payload["purpose"], f"{location}.purpose", minimum=12),
        conflicts=tuple(_dependency_conflict(item, f"{location}.conflicts[{index}]") for index, item in enumerate(conflicts)),
        platforms=_strings(payload["platforms"], f"{location}.platforms"),
    )


def _dependency_conflict(value: Any, location: str) -> DependencyConflict:
    payload = _object(value, location)
    _exact_fields(payload, _DEPENDENCY_CONFLICT_FIELDS, location)
    source = _text(payload["source"], f"{location}.source")
    if not source.startswith("https://"):
        raise ValueError(f"{location}.source must be an authoritative HTTPS URL")
    return DependencyConflict(
        dependency=_text(payload["dependency"], f"{location}.dependency"),
        versions=_version_rules(payload["versions"], f"{location}.versions"),
        reason=_text(payload["reason"], f"{location}.reason", minimum=12),
        required_action=_text(payload["required_action"], f"{location}.required_action", minimum=12),
        source=source,
    )


def _version_map(value: Any, location: str) -> dict[str, tuple[str, ...]]:
    payload = _object(value, location)
    return {str(key): _strings(item, f"{location}.{key}") for key, item in sorted(payload.items())}


def _version_rule_map(value: Any, location: str) -> dict[str, tuple[str, ...]]:
    payload = _object(value, location)
    return {str(key): _version_rules(item, f"{location}.{key}") for key, item in sorted(payload.items())}


def _compatibility(value: Any, location: str) -> CompatibilityRow:
    payload = _object(value, location)
    _exact_fields(payload, _COMPATIBILITY_FIELDS, location)
    regression_ids = _strings(payload["regression_evidence_ids"], f"{location}.regression_evidence_ids")
    end_to_end_ids = _strings(payload["end_to_end_evidence_ids"], f"{location}.end_to_end_evidence_ids")
    if any(not _ID_RE.fullmatch(item) for item in (*regression_ids, *end_to_end_ids)):
        raise ValueError(f"{location} evidence ids are invalid")
    return CompatibilityRow(
        id=_text(payload["id"], f"{location}.id"),
        module_version=_text(payload["module_version"], f"{location}.module_version"),
        tool_versions=_version_rule_map(payload["tool_versions"], f"{location}.tool_versions"),
        dependency_versions=_version_rule_map(payload["dependency_versions"], f"{location}.dependency_versions"),
        input_formats=_version_map(payload["input_formats"], f"{location}.input_formats"),
        output_formats=_version_map(payload["output_formats"], f"{location}.output_formats"),
        platforms=_strings(payload["platforms"], f"{location}.platforms"),
        regression_evidence_ids=regression_ids,
        end_to_end_evidence_ids=end_to_end_ids,
        verified_at=_date(payload["verified_at"], f"{location}.verified_at"),
    )


def _provenance(value: Any) -> ProvenanceContract:
    payload = _object(value, "provenance")
    _exact_fields(payload, _PROVENANCE_FIELDS, "provenance")
    return ProvenanceContract(
        license=_text(payload["license"], "provenance.license"),
        concept_sources=_strings(payload["concept_sources"], "provenance.concept_sources"),
    )


def _code_template(value: Any, location: str) -> CodeTemplate:
    payload = _object(value, location)
    _exact_fields(payload, _CODE_TEMPLATE_FIELDS, location)
    path = _text(payload["path"], f"{location}.path")
    if not re.fullmatch(r"templates/[a-z][a-z0-9_]*\.(?:py|R|ipynb)", path):
        raise ValueError(f"{location}.path must name a packaged code template")
    language = _text(payload["language"], f"{location}.language")
    expected_language = {"py": "python", "R": "r", "ipynb": "notebook"}[path.rsplit(".", 1)[1]]
    if language != expected_language:
        raise ValueError(f"{location}.language differs from its file extension")
    return CodeTemplate(
        path=path,
        language=language,
        purpose=_text(payload["purpose"], f"{location}.purpose", minimum=24),
        quality_gate_ids=_strings(payload["quality_gate_ids"], f"{location}.quality_gate_ids"),
        requires_adaptation=_boolean(payload["requires_adaptation"], f"{location}.requires_adaptation"),
    )


def _agent_section(value: Any, location: str) -> AgentTemplateSection:
    payload = _object(value, location)
    _exact_fields(payload, _AGENT_SECTION_FIELDS, location)
    identifier = _text(payload["id"], f"{location}.id")
    if not _ID_RE.fullmatch(identifier):
        raise ValueError(f"{location}.id is invalid")
    return AgentTemplateSection(
        id=identifier,
        purpose=_text(payload["purpose"], f"{location}.purpose", minimum=12),
        required_logic=_strings(payload["required_logic"], f"{location}.required_logic"),
        output_artifact_types=_strings(payload["output_artifact_types"], f"{location}.output_artifact_types"),
        template_files=_strings(payload["template_files"], f"{location}.template_files"),
    )


def _agent_parameter(value: Any, location: str) -> AgentParameterRule:
    payload = _object(value, location)
    _exact_fields(payload, _AGENT_PARAMETER_FIELDS, location)
    identifier = _text(payload["id"], f"{location}.id")
    parameter = _text(payload["parameter"], f"{location}.parameter")
    if not _ID_RE.fullmatch(identifier) or not _NAME_RE.fullmatch(parameter):
        raise ValueError(f"{location} has an invalid id or parameter")
    return AgentParameterRule(
        id=identifier,
        parameter=parameter,
        decision_inputs=_strings(payload["decision_inputs"], f"{location}.decision_inputs"),
        selection_rule=_text(payload["selection_rule"], f"{location}.selection_rule", minimum=12),
        validation_rule=_text(payload["validation_rule"], f"{location}.validation_rule", minimum=12),
    )


def _agent_protocol(value: Any) -> AgentProtocol:
    payload = _object(value, "manifest.agent_protocol")
    _exact_fields(payload, _AGENT_PROTOCOL_FIELDS, "manifest.agent_protocol")
    if payload["schema_version"] != 1 or payload["mode"] != "codex_generated_project_code":
        raise ValueError("manifest.agent_protocol version or mode is unsupported")
    sections = payload["template_sections"]
    parameters = payload["parameter_rules"]
    if not isinstance(sections, list) or not sections or not isinstance(parameters, list) or not parameters:
        raise ValueError("manifest.agent_protocol sections and parameter rules must be nonempty lists")
    parsed_sections = tuple(_agent_section(item, f"manifest.agent_protocol.template_sections[{index}]") for index, item in enumerate(sections))
    parsed_parameters = tuple(_agent_parameter(item, f"manifest.agent_protocol.parameter_rules[{index}]") for index, item in enumerate(parameters))
    if len({item.id for item in parsed_sections}) != len(parsed_sections) or len({item.id for item in parsed_parameters}) != len(parsed_parameters):
        raise ValueError("manifest.agent_protocol contains duplicate section or parameter rule ids")
    return AgentProtocol(
        schema_version=1,
        mode="codex_generated_project_code",
        languages=_strings(payload["languages"], "manifest.agent_protocol.languages"),
        template_sections=parsed_sections,
        parameter_rules=parsed_parameters,
        preflight_checks=_strings(payload["preflight_checks"], "manifest.agent_protocol.preflight_checks"),
        postflight_checks=_strings(payload["postflight_checks"], "manifest.agent_protocol.postflight_checks"),
        provenance_fields=_strings(payload["provenance_fields"], "manifest.agent_protocol.provenance_fields"),
        forbidden_actions=_strings(payload["forbidden_actions"], "manifest.agent_protocol.forbidden_actions"),
        requires_observed_execution=_boolean(payload["requires_observed_execution"], "manifest.agent_protocol.requires_observed_execution"),
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
            unsupported = [rule for rule in versions if not _rule_within_policy(rule, tools[name].allowed_versions)]
            if unsupported:
                raise ValueError(f"compatibility row {row.id} uses tool rules outside the declared compatibility policy")
        for name, versions in row.dependency_versions.items():
            if name not in dependencies:
                raise ValueError(f"compatibility row {row.id} references unknown dependency: {name}")
            unsupported = [rule for rule in versions if not _rule_within_policy(rule, dependencies[name].allowed_versions)]
            if unsupported:
                raise ValueError(f"compatibility row {row.id} uses dependency rules outside the declared compatibility policy")
        missing_tools = sorted(name for name, item in tools.items() if item.required and name not in row.tool_versions)
        missing_dependencies = sorted(name for name, item in dependencies.items() if item.required and name not in row.dependency_versions)
        if missing_tools or missing_dependencies:
            raise ValueError(f"compatibility row {row.id} omits required tool or dependency versions")
        _validate_format_map(row.input_formats, inputs, row.id, "input")
        _validate_format_map(row.output_formats, outputs, row.id, "output")
    for name, requirement in (*tools.items(), *dependencies.items()):
        rows = [row.tool_versions[name] if name in row.tool_versions else row.dependency_versions[name] for row in manifest.compatibility_matrix if name in row.tool_versions or name in row.dependency_versions]
        uncovered = [version for version in requirement.tested_versions if not any(version_is_allowed(version, rules) for rules in rows)]
        if uncovered:
            raise ValueError(f"tested versions are not covered by any compatibility row for {name}: {', '.join(uncovered)}")


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


def _validate_command_execution(manifest: ModuleManifest) -> None:
    command = manifest.execution.command
    if manifest.execution.kind != "command":
        if command is not None:
            raise ValueError("non-command module contains a scientific command contract")
        return
    if command is None or manifest.entrypoint != "scientific-command":
        raise ValueError("command modules must use the scientific-command entrypoint")
    if command.timeout_seconds != manifest.execution.timeout_seconds or command.max_output_bytes != manifest.execution.max_output_bytes:
        raise ValueError("scientific command limits must equal the module execution limits")
    input_ports = {port.name for port in manifest.input_artifacts}
    output_ports = {port.name for port in manifest.output_artifacts}
    if {binding.port for binding in command.inputs} != input_ports:
        raise ValueError("scientific command input bindings differ from module input ports")
    if {binding.port for binding in command.outputs} != output_ports:
        raise ValueError("scientific command output bindings differ from module output ports")
    matching_tools = [requirement for requirement in manifest.tool_requirements if requirement.name == command.tool_name]
    if len(matching_tools) != 1 or not matching_tools[0].required or matching_tools[0].identity != command.executable:
        raise ValueError("scientific command executable must match one required versioned tool")


def parse_manifest(value: Any) -> ModuleManifest:
    payload = _object(value, "manifest")
    extra = sorted(set(payload) - _MANIFEST_FIELDS)
    missing = sorted((_MANIFEST_FIELDS - _OPTIONAL_MANIFEST_FIELDS) - set(payload))
    if extra:
        raise ValueError(f"unsupported manifest fields: {', '.join(extra)}")
    if missing:
        raise ValueError(f"missing manifest fields: {', '.join(missing)}")
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
    domains = _strings(payload["domains"], "manifest.domains")
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
    code_template_values = payload.get("code_templates", [])
    if not isinstance(code_template_values, list):
        raise ValueError("manifest.code_templates must be a list")
    manifest = ModuleManifest(
        schema_version=1,
        id=identifier,
        version=version,
        title=_text(payload["title"], "manifest.title"),
        description=_text(payload["description"], "manifest.description", minimum=24),
        module_type=module_type,
        domains=domains,
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
        code_templates=tuple(
            _code_template(item, f"manifest.code_templates[{index}]")
            for index, item in enumerate(code_template_values)
        ),
        agent_protocol=_agent_protocol(payload["agent_protocol"]) if "agent_protocol" in payload else None,
    )
    if len({item.path for item in manifest.code_templates}) != len(manifest.code_templates):
        raise ValueError("manifest.code_templates contains duplicate paths")
    quality_gate_ids = {item.id for item in manifest.quality_gates}
    for template in manifest.code_templates:
        unknown = sorted(set(template.quality_gate_ids) - quality_gate_ids)
        if unknown:
            raise ValueError(f"code template references unknown quality gate: {unknown[0]}")
    if access == "agent_generated":
        if manifest.execution.kind != "workflow" or manifest.agent_protocol is None:
            raise ValueError("agent_generated modules require workflow execution and an agent_protocol")
        if not manifest.agent_protocol.requires_observed_execution:
            raise ValueError("agent_generated modules must require observed execution")
        produced_types = {port.artifact_type for port in manifest.output_artifacts}
        declared_types = {artifact_type for section in manifest.agent_protocol.template_sections for artifact_type in section.output_artifact_types}
        if not declared_types <= produced_types:
            raise ValueError("agent_protocol template sections reference undeclared output artifact types")
    elif manifest.agent_protocol is not None:
        raise ValueError("agent_protocol is only valid for agent_generated modules")
    _validate_compatibility(manifest)
    _validate_command_execution(manifest)
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
        "genome_builds": list(value.genome_builds),
        "annotation_releases": list(value.annotation_releases),
        "orientations": list(value.orientations),
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


def _agent_protocol_dict(value: AgentProtocol) -> dict[str, object]:
    return {
        "schema_version": value.schema_version,
        "mode": value.mode,
        "languages": list(value.languages),
        "template_sections": [
            {
                "id": item.id,
                "purpose": item.purpose,
                "required_logic": list(item.required_logic),
                "output_artifact_types": list(item.output_artifact_types),
                "template_files": list(item.template_files),
            }
            for item in value.template_sections
        ],
        "parameter_rules": [
            {
                "id": item.id,
                "parameter": item.parameter,
                "decision_inputs": list(item.decision_inputs),
                "selection_rule": item.selection_rule,
                "validation_rule": item.validation_rule,
            }
            for item in value.parameter_rules
        ],
        "preflight_checks": list(value.preflight_checks),
        "postflight_checks": list(value.postflight_checks),
        "provenance_fields": list(value.provenance_fields),
        "forbidden_actions": list(value.forbidden_actions),
        "requires_observed_execution": value.requires_observed_execution,
    }


def _code_template_dict(value: CodeTemplate) -> dict[str, object]:
    return {
        "path": value.path,
        "language": value.language,
        "purpose": value.purpose,
        "quality_gate_ids": list(value.quality_gate_ids),
        "requires_adaptation": value.requires_adaptation,
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
        "version_probe_kind": value.version_probe_kind,
        "version_probe_timeout_seconds": value.version_probe_timeout_seconds,
        "version_pattern": value.version_pattern,
        "mismatch_policy": value.mismatch_policy,
        "version_differences": [
            {
                "id": item.id,
                "affected_versions": list(item.affected_versions),
                "category": item.category,
                "description": item.description,
                "compatibility_effect": item.compatibility_effect,
                "required_action": item.required_action,
                "source": item.source,
            }
            for item in value.version_differences
        ],
        "platforms": list(value.platforms),
    }


def _dependency_dict(value: DependencyRequirement) -> dict[str, object]:
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
        "version_probe_kind": value.version_probe_kind,
        "version_probe_timeout_seconds": value.version_probe_timeout_seconds,
        "version_pattern": value.version_pattern,
        "purpose": value.purpose,
        "conflicts": [
            {
                "dependency": item.dependency,
                "versions": list(item.versions),
                "reason": item.reason,
                "required_action": item.required_action,
                "source": item.source,
            }
            for item in value.conflicts
        ],
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
        "regression_evidence_ids": list(value.regression_evidence_ids),
        "end_to_end_evidence_ids": list(value.end_to_end_evidence_ids),
        "verified_at": value.verified_at,
    }


def manifest_to_dict(value: ModuleManifest) -> dict[str, object]:
    """Return a detached, canonical JSON-compatible representation."""
    execution = {
        "kind": value.execution.kind,
        "timeout_seconds": value.execution.timeout_seconds,
        "max_output_bytes": value.execution.max_output_bytes,
    }
    if value.execution.command is not None:
        execution["command"] = value.execution.command.to_dict()
    payload = {
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
        "execution": execution,
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
    if value.code_templates:
        payload["code_templates"] = [_code_template_dict(item) for item in value.code_templates]
    if value.agent_protocol is not None:
        payload["agent_protocol"] = _agent_protocol_dict(value.agent_protocol)
    return payload
