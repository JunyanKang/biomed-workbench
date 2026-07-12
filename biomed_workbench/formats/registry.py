"""Declarative, exact-version omics format registry and metadata validator."""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Mapping

from ..kernel.artifacts import ScientificArtifact


_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
_POLICIES = frozenset({"required", "declared", "not_applicable"})
_REPRESENTATIONS = frozenset({"text", "binary", "sparse", "container", "structured"})


def _tokens(value: Any, location: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{location} must be a {'possibly empty ' if allow_empty else 'non-empty '}list")
    result = tuple(value)
    if any(not isinstance(item, str) or not _TOKEN_RE.fullmatch(item) for item in result):
        raise ValueError(f"{location} contains an invalid token")
    if len(set(result)) != len(result):
        raise ValueError(f"{location} contains duplicates")
    return result


def _policy(value: Any, location: str) -> str:
    if value not in _POLICIES:
        raise ValueError(f"{location} must be required, declared, or not_applicable")
    return value


@dataclass(frozen=True)
class IndexRequirement:
    when_compression: tuple[str, ...]
    one_of: tuple[str, ...]
    all_of: tuple[str, ...]


@dataclass(frozen=True)
class FormatProfile:
    id: str
    name: str
    specification_version: str
    specification_source: str
    authority: str
    representations: tuple[str, ...]
    compression: tuple[str, ...]
    index_requirements: tuple[IndexRequirement, ...]
    sort_orders: tuple[str, ...]
    coordinate_systems: tuple[str, ...]
    reference_policy: str
    annotation_policy: str
    identifier_namespace_policy: str
    sample_manifest_policy: str
    orientations: tuple[str, ...]
    processing_levels: tuple[str, ...]
    required_metadata: tuple[str, ...]
    required_payload_roles: tuple[str, ...]

    @property
    def token(self) -> str:
        return f"{self.name}@{self.specification_version}"


@dataclass(frozen=True)
class FormatSnapshot:
    profile_id: str
    representation: str
    compression: str
    indexes: tuple[str, ...]
    sort_order: str
    coordinate_system: str | None
    genome_build: str | None
    reference_sequence_digest: str | None
    annotation_release: str | None
    identifier_namespace: str | None
    sample_manifest_digest: str | None
    orientation: str
    processing_level: str
    metadata_fields: tuple[str, ...]
    payload_roles: tuple[str, ...]

    @classmethod
    def from_artifact(cls, artifact: ScientificArtifact, profile_id: str) -> "FormatSnapshot":
        return cls(
            profile_id=profile_id,
            representation=artifact.representation,
            compression=artifact.compression,
            indexes=artifact.indexes,
            sort_order=artifact.sort_order or "unsorted",
            coordinate_system=artifact.coordinate_system,
            genome_build=artifact.genome_build,
            reference_sequence_digest=artifact.reference_sequence_digest,
            annotation_release=artifact.annotation_release,
            identifier_namespace=artifact.identifier_namespace,
            sample_manifest_digest=artifact.sample_manifest_digest,
            orientation=artifact.orientation,
            processing_level=artifact.processing_level,
            metadata_fields=artifact.metadata_fields,
            payload_roles=tuple(payload.role for payload in artifact.payloads),
        )


@dataclass(frozen=True)
class FormatFinding:
    code: str
    field: str
    message: str


def _parse_profile(payload: Mapping[str, Any]) -> FormatProfile:
    required = {
        "id", "name", "specification_version", "specification_source", "authority",
        "representations", "compression", "index_requirements", "sort_orders",
        "coordinate_systems", "reference_policy", "annotation_policy",
        "identifier_namespace_policy", "sample_manifest_policy", "orientations",
        "processing_levels", "required_metadata", "required_payload_roles",
    }
    if set(payload) != required:
        raise ValueError(f"format profile fields differ: missing={sorted(required - set(payload))}, extra={sorted(set(payload) - required)}")
    identifier = payload["id"]
    if not isinstance(identifier, str) or not _ID_RE.fullmatch(identifier):
        raise ValueError("format profile id is invalid")
    source = payload["specification_source"]
    if not isinstance(source, str) or not (source.startswith("https://") or source.startswith("docs/")):
        raise ValueError(f"format profile {identifier} has an invalid specification source")
    representations = _tokens(payload["representations"], f"{identifier}.representations")
    if set(representations) - _REPRESENTATIONS:
        raise ValueError(f"format profile {identifier} has an unsupported representation")
    raw_indexes = payload["index_requirements"]
    if not isinstance(raw_indexes, list):
        raise ValueError(f"{identifier}.index_requirements must be a list")
    index_requirements = []
    for index, item in enumerate(raw_indexes):
        if not isinstance(item, dict) or set(item) != {"when_compression", "one_of", "all_of"}:
            raise ValueError(f"{identifier}.index_requirements[{index}] is invalid")
        requirement = IndexRequirement(
            when_compression=_tokens(item["when_compression"], f"{identifier}.index.when_compression", allow_empty=True),
            one_of=_tokens(item["one_of"], f"{identifier}.index.one_of", allow_empty=True),
            all_of=_tokens(item["all_of"], f"{identifier}.index.all_of", allow_empty=True),
        )
        if not requirement.one_of and not requirement.all_of:
            raise ValueError(f"{identifier}.index requirement must require at least one index")
        index_requirements.append(requirement)
    return FormatProfile(
        id=identifier,
        name=str(payload["name"]),
        specification_version=str(payload["specification_version"]),
        specification_source=source,
        authority=str(payload["authority"]),
        representations=representations,
        compression=_tokens(payload["compression"], f"{identifier}.compression"),
        index_requirements=tuple(index_requirements),
        sort_orders=_tokens(payload["sort_orders"], f"{identifier}.sort_orders"),
        coordinate_systems=_tokens(payload["coordinate_systems"], f"{identifier}.coordinate_systems", allow_empty=True),
        reference_policy=_policy(payload["reference_policy"], f"{identifier}.reference_policy"),
        annotation_policy=_policy(payload["annotation_policy"], f"{identifier}.annotation_policy"),
        identifier_namespace_policy=_policy(payload["identifier_namespace_policy"], f"{identifier}.identifier_namespace_policy"),
        sample_manifest_policy=_policy(payload["sample_manifest_policy"], f"{identifier}.sample_manifest_policy"),
        orientations=_tokens(payload["orientations"], f"{identifier}.orientations"),
        processing_levels=_tokens(payload["processing_levels"], f"{identifier}.processing_levels"),
        required_metadata=_tokens(payload["required_metadata"], f"{identifier}.required_metadata", allow_empty=True),
        required_payload_roles=_tokens(payload["required_payload_roles"], f"{identifier}.required_payload_roles"),
    )


class FormatRegistry:
    """Immutable lookup for the project-owned format catalog."""

    def __init__(self, profiles: tuple[FormatProfile, ...]):
        if len({item.id for item in profiles}) != len(profiles):
            raise ValueError("format registry contains duplicate ids")
        if len({item.token for item in profiles}) != len(profiles):
            raise ValueError("format registry contains duplicate format-version tokens")
        self._profiles = tuple(sorted(profiles, key=lambda item: item.id))
        self._by_id = {item.id: item for item in self._profiles}
        self._by_token = {item.token: item for item in self._profiles}
        self._digest = hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @classmethod
    def builtin(cls) -> "FormatRegistry":
        payload = json.loads(files("biomed_workbench.formats").joinpath("catalog.json").read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1 or not isinstance(payload.get("profiles"), list):
            raise ValueError("format catalog root is invalid")
        return cls(tuple(_parse_profile(item) for item in payload["profiles"]))

    def all(self) -> tuple[FormatProfile, ...]:
        return self._profiles

    @property
    def digest(self) -> str:
        return self._digest

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "profiles": [
                {
                    "id": item.id,
                    "name": item.name,
                    "specification_version": item.specification_version,
                    "specification_source": item.specification_source,
                    "authority": item.authority,
                    "representations": list(item.representations),
                    "compression": list(item.compression),
                    "index_requirements": [
                        {
                            "when_compression": list(requirement.when_compression),
                            "one_of": list(requirement.one_of),
                            "all_of": list(requirement.all_of),
                        }
                        for requirement in item.index_requirements
                    ],
                    "sort_orders": list(item.sort_orders),
                    "coordinate_systems": list(item.coordinate_systems),
                    "reference_policy": item.reference_policy,
                    "annotation_policy": item.annotation_policy,
                    "identifier_namespace_policy": item.identifier_namespace_policy,
                    "sample_manifest_policy": item.sample_manifest_policy,
                    "orientations": list(item.orientations),
                    "processing_levels": list(item.processing_levels),
                    "required_metadata": list(item.required_metadata),
                    "required_payload_roles": list(item.required_payload_roles),
                }
                for item in self._profiles
            ],
        }

    def get(self, profile_id: str) -> FormatProfile:
        try:
            return self._by_id[profile_id]
        except KeyError:
            raise KeyError(f"unknown format profile: {profile_id}") from None

    def find_token(self, token: str) -> FormatProfile | None:
        return self._by_token.get(token)


def validate_format(profile: FormatProfile, snapshot: FormatSnapshot) -> tuple[FormatFinding, ...]:
    """Return every format-contract mismatch without guessing compatibility."""
    findings: list[FormatFinding] = []

    def mismatch(condition: bool, code: str, field: str, message: str) -> None:
        if condition:
            findings.append(FormatFinding(code, field, message))

    mismatch(snapshot.profile_id != profile.id, "PROFILE_MISMATCH", "profile_id", "Artifact profile does not match the selected format contract.")
    mismatch(snapshot.representation not in profile.representations, "REPRESENTATION_MISMATCH", "representation", "Representation is not validated for this format version.")
    mismatch(snapshot.compression not in profile.compression, "COMPRESSION_MISMATCH", "compression", "Compression is not validated for this format version.")
    mismatch(snapshot.sort_order not in profile.sort_orders, "SORT_ORDER_MISMATCH", "sort_order", "Sort order is not validated for this format version.")
    mismatch(bool(profile.coordinate_systems) and snapshot.coordinate_system not in profile.coordinate_systems, "COORDINATE_SYSTEM_MISMATCH", "coordinate_system", "Coordinate convention is absent or incompatible.")
    mismatch(snapshot.orientation not in profile.orientations, "ORIENTATION_MISMATCH", "orientation", "Matrix or record orientation is incompatible.")
    mismatch(snapshot.processing_level not in profile.processing_levels, "PROCESSING_LEVEL_MISMATCH", "processing_level", "Processing level is not supported by this profile.")

    indexes = set(snapshot.indexes)
    for requirement in profile.index_requirements:
        if requirement.when_compression and snapshot.compression not in requirement.when_compression:
            continue
        mismatch(bool(requirement.one_of) and not indexes.intersection(requirement.one_of), "MISSING_INDEX", "indexes", f"One companion index is required from: {', '.join(requirement.one_of)}.")
        missing = sorted(set(requirement.all_of) - indexes)
        mismatch(bool(missing), "MISSING_INDEX", "indexes", f"Required companion indexes are absent: {', '.join(missing)}.")

    reference_missing = not snapshot.genome_build or not snapshot.reference_sequence_digest
    mismatch(profile.reference_policy == "required" and reference_missing, "REFERENCE_METADATA_MISSING", "reference", "Genome build and reference sequence digest are required.")
    mismatch(profile.reference_policy == "not_applicable" and bool(snapshot.genome_build or snapshot.reference_sequence_digest), "UNEXPECTED_REFERENCE_METADATA", "reference", "Reference metadata is not applicable to this format.")
    mismatch(profile.annotation_policy == "required" and not snapshot.annotation_release, "ANNOTATION_RELEASE_MISSING", "annotation_release", "Annotation release is required.")
    mismatch(profile.identifier_namespace_policy == "required" and not snapshot.identifier_namespace, "IDENTIFIER_NAMESPACE_MISSING", "identifier_namespace", "Identifier namespace is required.")
    mismatch(profile.sample_manifest_policy == "required" and not snapshot.sample_manifest_digest, "SAMPLE_MANIFEST_MISSING", "sample_manifest_digest", "A content digest for the sample manifest is required.")

    missing_metadata = sorted(set(profile.required_metadata) - set(snapshot.metadata_fields))
    mismatch(bool(missing_metadata), "REQUIRED_METADATA_MISSING", "metadata_fields", f"Required metadata fields are absent: {', '.join(missing_metadata)}.")
    missing_roles = sorted(set(profile.required_payload_roles) - set(snapshot.payload_roles))
    mismatch(bool(missing_roles), "PAYLOAD_ROLE_MISSING", "payload_roles", f"Required payload roles are absent: {', '.join(missing_roles)}.")
    return tuple(findings)
