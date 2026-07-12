"""Versioned, deeply immutable scientific artifacts for module exchange."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .artifact_store import ArtifactPayload
from .identity import FrozenMapping, digest_value, freeze_mapping, thaw, validate_identifier


QUALITY_STATUSES = frozenset({"unassessed", "passed", "warning", "major", "fatal"})
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z+._-]*$")


def _token(value: str, location: str, pattern: re.Pattern[str] = _TOKEN_RE) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{location} must be an explicit versioned token")
    return value


def _optional_token(value: str | None, location: str) -> str | None:
    return None if value is None else _token(value, location)


@dataclass(frozen=True)
class ScientificArtifact:
    id: str
    artifact_type: str
    schema_version: str
    format_name: str
    format_version: str
    compression: str
    orientation: str
    indexes: tuple[str, ...]
    producing_module_id: str | None
    producing_module_version: str | None
    source_artifact_ids: tuple[str, ...]
    scientific_scope: Mapping[str, Any]
    experimental_unit: str
    denominator: str
    processing_level: str
    quality_status: str
    coordinate_system: str | None
    genome_build: str | None
    annotation_release: str | None
    identifier_namespace: str | None
    producer_tool_versions: Mapping[str, str]
    content: Mapping[str, Any]
    content_digest: str
    payloads: tuple[ArtifactPayload, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "artifact.id"))
        object.__setattr__(self, "artifact_type", validate_identifier(self.artifact_type, "artifact.artifact_type"))
        object.__setattr__(self, "schema_version", _token(self.schema_version, "artifact.schema_version", _VERSION_RE))
        object.__setattr__(self, "format_name", _token(self.format_name, "artifact.format_name"))
        object.__setattr__(self, "format_version", _token(self.format_version, "artifact.format_version", _VERSION_RE))
        object.__setattr__(self, "compression", _token(self.compression, "artifact.compression"))
        object.__setattr__(self, "orientation", _token(self.orientation, "artifact.orientation"))
        indexes = tuple(_token(value, "artifact.indexes") for value in self.indexes)
        if len(set(indexes)) != len(indexes):
            raise ValueError("artifact.indexes contains duplicates")
        object.__setattr__(self, "indexes", indexes)
        if (self.producing_module_id is None) != (self.producing_module_version is None):
            raise ValueError("producing module ID and version must be declared together")
        if self.producing_module_id is not None:
            object.__setattr__(self, "producing_module_id", validate_identifier(self.producing_module_id, "artifact.producing_module_id"))
            object.__setattr__(self, "producing_module_version", _token(self.producing_module_version, "artifact.producing_module_version", _VERSION_RE))
        source_ids = tuple(validate_identifier(value, "artifact.source_artifact_ids") for value in self.source_artifact_ids)
        if self.id in source_ids or len(set(source_ids)) != len(source_ids):
            raise ValueError("artifact sources must be unique and cannot include the artifact itself")
        object.__setattr__(self, "source_artifact_ids", source_ids)
        object.__setattr__(self, "scientific_scope", freeze_mapping(self.scientific_scope))
        object.__setattr__(self, "experimental_unit", validate_identifier(self.experimental_unit, "artifact.experimental_unit"))
        if not isinstance(self.denominator, str) or not self.denominator.strip():
            raise ValueError("artifact.denominator must explicitly identify the inference denominator")
        freeze_mapping({"denominator": self.denominator})
        object.__setattr__(self, "denominator", self.denominator.strip())
        object.__setattr__(self, "processing_level", validate_identifier(self.processing_level, "artifact.processing_level"))
        if self.quality_status not in QUALITY_STATUSES:
            raise ValueError("artifact.quality_status is unsupported")
        object.__setattr__(self, "coordinate_system", _optional_token(self.coordinate_system, "artifact.coordinate_system"))
        object.__setattr__(self, "genome_build", _optional_token(self.genome_build, "artifact.genome_build"))
        object.__setattr__(self, "annotation_release", _optional_token(self.annotation_release, "artifact.annotation_release"))
        object.__setattr__(self, "identifier_namespace", _optional_token(self.identifier_namespace, "artifact.identifier_namespace"))
        if self.genome_build is not None and self.coordinate_system is None:
            raise ValueError("genome-build artifacts require an explicit coordinate system")
        versions = freeze_mapping(self.producer_tool_versions)
        if any(not _TOKEN_RE.fullmatch(name) or not isinstance(version, str) or not _VERSION_RE.fullmatch(version) for name, version in versions.items()):
            raise ValueError("producer tool names and versions must be explicit tokens")
        object.__setattr__(self, "producer_tool_versions", versions)
        content = freeze_mapping(self.content)
        object.__setattr__(self, "content", content)
        payloads = tuple(self.payloads)
        if any(not isinstance(payload, ArtifactPayload) for payload in payloads):
            raise ValueError("artifact payloads must be ArtifactPayload values")
        if len({payload.role for payload in payloads}) != len(payloads):
            raise ValueError("artifact payload roles must be unique")
        object.__setattr__(self, "payloads", payloads)
        expected = self._content_digest(content, payloads)
        if self.content_digest != expected:
            raise ValueError("artifact content digest does not match canonical content")

    @staticmethod
    def _content_digest(content: Mapping[str, Any], payloads: tuple[ArtifactPayload, ...]) -> str:
        if not payloads:
            return digest_value(content)
        return digest_value({"content": thaw(content), "payloads": [payload.to_dict() for payload in payloads]})

    @classmethod
    def create(cls, **values: Any) -> "ScientificArtifact":
        if "content_digest" in values:
            raise ValueError("create computes content_digest automatically")
        content = values.get("content")
        if not isinstance(content, Mapping):
            raise ValueError("artifact.content must be an object")
        payloads = tuple(values.get("payloads", ()))
        values["payloads"] = payloads
        return cls(**values, content_digest=cls._content_digest(content, payloads))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificArtifact":
        values = dict(payload)
        values["source_artifact_ids"] = tuple(values["source_artifact_ids"])
        values["indexes"] = tuple(values["indexes"])
        values["payloads"] = tuple(ArtifactPayload.from_dict(item) for item in values.get("payloads", ()))
        return cls(**values)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "id": self.id,
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "format_name": self.format_name,
            "format_version": self.format_version,
            "compression": self.compression,
            "orientation": self.orientation,
            "indexes": list(self.indexes),
            "producing_module_id": self.producing_module_id,
            "producing_module_version": self.producing_module_version,
            "source_artifact_ids": list(self.source_artifact_ids),
            "scientific_scope": thaw(self.scientific_scope),
            "experimental_unit": self.experimental_unit,
            "denominator": self.denominator,
            "processing_level": self.processing_level,
            "quality_status": self.quality_status,
            "coordinate_system": self.coordinate_system,
            "genome_build": self.genome_build,
            "annotation_release": self.annotation_release,
            "identifier_namespace": self.identifier_namespace,
            "producer_tool_versions": thaw(self.producer_tool_versions),
            "content": thaw(self.content),
            "content_digest": self.content_digest,
        }
        if self.payloads:
            payload["payloads"] = [value.to_dict() for value in self.payloads]
        return payload
