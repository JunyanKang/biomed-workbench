"""Two-layer, file-verifiable scientific evidence maps for project reporting."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Mapping

from .identity import digest_value, validate_identifier
from .execution_chain import delivery_slice_digest
from .scientific_dependency import (
    AnalysisAdmission,
    ArtifactReview,
    ScientificDecision,
    ScientificDependencyBundle,
)
from .hypotheses import Hypothesis
if TYPE_CHECKING:
    from .state import ProjectState


FILE_ROLES = frozenset(
    {
        "registered-data",
        "plot-data",
        "analysis-script",
        "renderer",
        "final-data",
        "final-pdf",
        "final-png",
        "caption",
    }
)
SOURCE_ROLES = frozenset({"original-study", "dataset", "method", "background", "claim"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
CHANGE_TYPES = frozenset({"initial", "major", "minor", "patch"})
_ROLE_STAGES = (
    ("registered-data",),
    ("plot-data",),
    ("analysis-script",),
    ("renderer",),
    ("final-data", "final-pdf", "final-png"),
    ("caption",),
)


@dataclass(frozen=True)
class EvidenceMapVersion:
    version: str
    revision: int
    parent_map_digest: str | None
    change_type: str
    change_summary_zh: str
    change_summary_en: str
    map_kind: str = "project-snapshot"

    def __post_init__(self) -> None:
        if not _SEMVER.fullmatch(self.version):
            raise ValueError("evidence map version must use semantic versioning")
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("evidence map revision must be positive")
        if self.change_type not in CHANGE_TYPES:
            raise ValueError("evidence map change_type is unsupported")
        if self.map_kind not in {"project-snapshot", "validated-delivery"}:
            raise ValueError("evidence map kind is unsupported")
        if self.parent_map_digest is not None and not _SHA256.fullmatch(self.parent_map_digest):
            raise ValueError("evidence map parent digest must be SHA-256")
        if self.revision == 1:
            if self.parent_map_digest is not None or self.change_type != "initial":
                raise ValueError("initial evidence maps require revision 1, no parent, and initial change type")
        elif self.parent_map_digest is None or self.change_type == "initial":
            raise ValueError("revised evidence maps require a parent and non-initial change type")
        for field in ("change_summary_zh", "change_summary_en"):
            value = getattr(self, field)
            if not isinstance(value, str) or len(value.strip()) < 12:
                raise ValueError(f"evidence map {field} must be meaningful")

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "revision": self.revision,
            "parent_map_digest": self.parent_map_digest,
            "change_type": self.change_type,
            "change_summary_zh": self.change_summary_zh,
            "change_summary_en": self.change_summary_en,
            "map_kind": self.map_kind,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceMapVersion":
        return cls(**dict(payload))


@dataclass(frozen=True)
class EvidenceMapPublication:
    """Append-only project-state reference to one validated evidence map version."""

    id: str
    version: EvidenceMapVersion
    map_digest: str
    edge_table_digest: str
    source_state_digest: str
    dependency_bundle_digest: str
    map_kind: str
    delivery_slice_digest: str
    active_artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "evidence_map_publication.id"))
        if not isinstance(self.version, EvidenceMapVersion):
            raise ValueError("evidence map publication requires a version contract")
        for field in ("map_digest", "edge_table_digest", "source_state_digest", "dependency_bundle_digest", "delivery_slice_digest"):
            if not _SHA256.fullmatch(getattr(self, field)):
                raise ValueError(f"evidence map publication {field} must be SHA-256")
        if self.map_kind != self.version.map_kind:
            raise ValueError("evidence map publication kind differs from its version contract")
        active = tuple(validate_identifier(value, "evidence_map_publication.active_artifact_id") for value in self.active_artifact_ids)
        if len(set(active)) != len(active):
            raise ValueError("evidence map publication active artifact IDs must be unique")
        object.__setattr__(self, "active_artifact_ids", active)

    @classmethod
    def from_map(cls, evidence_map: "ScientificEvidenceMap") -> "EvidenceMapPublication":
        evidence_map.validate_integrity()
        return cls(
            id=f"evidence-map-{evidence_map.version.revision}-{evidence_map.digest[:16]}",
            version=evidence_map.version,
            map_digest=evidence_map.digest,
            edge_table_digest=evidence_map.edge_table_digest,
            source_state_digest=evidence_map.state_digest,
            dependency_bundle_digest=evidence_map.dependency_bundle_digest,
            map_kind=evidence_map.version.map_kind,
            delivery_slice_digest=evidence_map.delivery_slice_digest,
            active_artifact_ids=evidence_map.active_evidence_artifact_ids,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceMapPublication":
        values = dict(payload)
        values["version"] = EvidenceMapVersion.from_dict(values["version"])
        values.setdefault("map_kind", values["version"].map_kind)
        values.setdefault("delivery_slice_digest", values["source_state_digest"])
        values["active_artifact_ids"] = tuple(values.get("active_artifact_ids", ()))
        return cls(**values)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "version": self.version.to_dict(),
            "map_digest": self.map_digest,
            "edge_table_digest": self.edge_table_digest,
            "source_state_digest": self.source_state_digest,
            "dependency_bundle_digest": self.dependency_bundle_digest,
            "map_kind": self.map_kind,
            "delivery_slice_digest": self.delivery_slice_digest,
            "active_artifact_ids": list(self.active_artifact_ids),
        }


def _relative_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("evidence file path must be nonempty")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or str(path) != value:
        raise ValueError("evidence file path must be normalized and workspace-relative")
    return value


@dataclass(frozen=True)
class EvidenceFile:
    id: str
    role: str
    path: str
    sha256: str
    media_type: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "evidence_file.id"))
        if self.role not in FILE_ROLES:
            raise ValueError("evidence_file.role is unsupported")
        object.__setattr__(self, "path", _relative_path(self.path))
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("evidence_file.sha256 must be an exact SHA-256")
        if not isinstance(self.media_type, str) or "/" not in self.media_type:
            raise ValueError("evidence_file.media_type is invalid")

    @classmethod
    def from_workspace(
        cls,
        *,
        id: str,
        role: str,
        path: str,
        media_type: str,
        workspace_root: Path,
    ) -> "EvidenceFile":
        relative = _relative_path(path)
        target = workspace_root / relative
        if not target.is_file():
            raise ValueError(f"evidence file does not exist: {relative}")
        return cls(
            id=id,
            role=role,
            path=relative,
            sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            media_type=media_type,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "role": self.role,
            "path": self.path,
            "sha256": self.sha256,
            "media_type": self.media_type,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceFile":
        return cls(**dict(payload))


@dataclass(frozen=True)
class NarrativeSource:
    id: str
    role: str
    title: str
    doi: str
    url: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", validate_identifier(self.id, "narrative_source.id"))
        if self.role not in SOURCE_ROLES:
            raise ValueError("narrative_source.role is unsupported")
        if not isinstance(self.title, str) or len(self.title.strip()) < 8:
            raise ValueError("narrative_source.title must be meaningful")
        if not _DOI.fullmatch(self.doi):
            raise ValueError("narrative_source.doi must be a canonical DOI")
        if self.url != f"https://doi.org/{self.doi}":
            raise ValueError("narrative_source.url must be the canonical DOI URL")

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "role": self.role,
            "title": self.title,
            "doi": self.doi,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NarrativeSource":
        return cls(**dict(payload))


@dataclass(frozen=True)
class EvidenceUnitSpec:
    id: str
    group_id: str
    artifact_id: str
    panel_id: str | None
    analysis_admission_ids: tuple[str, ...]
    predecessor_unit_ids: tuple[str, ...]
    prerequisite_conclusion_zh: str
    prerequisite_conclusion_en: str
    files: tuple[EvidenceFile, ...]
    narrative_sources: tuple[NarrativeSource, ...]

    def __post_init__(self) -> None:
        for field in ("id", "group_id", "artifact_id"):
            object.__setattr__(self, field, validate_identifier(getattr(self, field), f"evidence_unit.{field}"))
        if self.panel_id is not None:
            object.__setattr__(self, "panel_id", validate_identifier(self.panel_id, "evidence_unit.panel_id"))
        admissions = tuple(
            validate_identifier(value, "evidence_unit.analysis_admission_ids")
            for value in self.analysis_admission_ids
        )
        if not admissions or len(set(admissions)) != len(admissions):
            raise ValueError("evidence unit analysis admissions must be nonempty and unique")
        object.__setattr__(self, "analysis_admission_ids", admissions)
        predecessors = tuple(validate_identifier(value, "evidence_unit.predecessor_unit_ids") for value in self.predecessor_unit_ids)
        if self.id in predecessors or len(set(predecessors)) != len(predecessors):
            raise ValueError("evidence unit predecessors must be unique and cannot include itself")
        object.__setattr__(self, "predecessor_unit_ids", predecessors)
        for field in ("prerequisite_conclusion_zh", "prerequisite_conclusion_en"):
            value = getattr(self, field)
            if not isinstance(value, str) or len(value.strip()) < 12:
                raise ValueError(f"evidence_unit.{field} must be meaningful")
        files = tuple(self.files)
        sources = tuple(self.narrative_sources)
        if len({item.id for item in files}) != len(files) or len({item.id for item in sources}) != len(sources):
            raise ValueError("evidence unit file and source IDs must be unique")
        if not sources or not any(item.role == "original-study" for item in sources):
            raise ValueError("each evidence unit requires at least one original-study DOI")
        object.__setattr__(self, "files", files)
        object.__setattr__(self, "narrative_sources", sources)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvidenceUnitSpec":
        values = dict(payload)
        values["analysis_admission_ids"] = tuple(values["analysis_admission_ids"])
        values["predecessor_unit_ids"] = tuple(values["predecessor_unit_ids"])
        values["files"] = tuple(EvidenceFile.from_dict(item) for item in values["files"])
        values["narrative_sources"] = tuple(NarrativeSource.from_dict(item) for item in values["narrative_sources"])
        return cls(**values)


@dataclass(frozen=True)
class EvidenceMapUnit:
    spec: EvidenceUnitSpec
    artifact_type: str
    admissions: tuple[AnalysisAdmission, ...]
    review: ArtifactReview
    decision: ScientificDecision
    evidence_origin: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.spec.id,
            "group_id": self.spec.group_id,
            "artifact_id": self.spec.artifact_id,
            "artifact_type": self.artifact_type,
            "panel_id": self.spec.panel_id,
            "analysis_admission_ids": list(self.spec.analysis_admission_ids),
            "predecessor_unit_ids": list(self.spec.predecessor_unit_ids),
            "prerequisite_conclusion_zh": self.spec.prerequisite_conclusion_zh,
            "prerequisite_conclusion_en": self.spec.prerequisite_conclusion_en,
            "files": [item.to_dict() for item in self.spec.files],
            "narrative_sources": [item.to_dict() for item in self.spec.narrative_sources],
            "analysis_admissions": [item.to_dict() for item in self.admissions],
            "review": self.review.to_dict(),
            "decision": self.decision.to_dict(),
            "evidence_origin": self.evidence_origin,
        }


@dataclass(frozen=True)
class EvidenceMapEdge:
    layer: str
    group_id: str
    source: str
    target: str
    relation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "layer": self.layer,
            "group_id": self.group_id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
        }


@dataclass(frozen=True)
class ScientificEvidenceMap:
    schema_version: int
    project_id: str
    scientific_question: str
    version: EvidenceMapVersion
    state_digest: str
    dependency_bundle_digest: str
    delivery_slice_digest: str
    active_evidence_artifact_ids: tuple[str, ...]
    hypotheses: tuple[Hypothesis, ...]
    units: tuple[EvidenceMapUnit, ...]
    edges: tuple[EvidenceMapEdge, ...]
    edge_table_digest: str
    digest: str

    def _basis(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "scientific_question": self.scientific_question,
            "version": self.version.to_dict(),
            "state_digest": self.state_digest,
            "dependency_bundle_digest": self.dependency_bundle_digest,
            "delivery_slice_digest": self.delivery_slice_digest,
            "active_evidence_artifact_ids": list(self.active_evidence_artifact_ids),
            "hypotheses": [hypothesis.to_dict() for hypothesis in self.hypotheses],
            "units": [unit.to_dict() for unit in self.units],
            "edges": [edge.to_dict() for edge in self.edges],
            "edge_table_digest": self.edge_table_digest,
        }

    def validate_integrity(self) -> None:
        if self.schema_version != 1:
            raise ValueError("scientific evidence map schema is unsupported")
        expected_edge_digest = digest_value([edge.to_dict() for edge in self.edges])
        if self.edge_table_digest != expected_edge_digest:
            raise ValueError("scientific evidence map edge table was modified")
        if self.digest != digest_value(self._basis()):
            raise ValueError("scientific evidence map digest does not match its content")

    @property
    def story_edges(self) -> tuple[EvidenceMapEdge, ...]:
        return tuple(edge for edge in self.edges if edge.layer == "story")

    @property
    def detail_edges(self) -> tuple[EvidenceMapEdge, ...]:
        return tuple(edge for edge in self.edges if edge.layer == "detail")

    def to_dict(self) -> dict[str, object]:
        self.validate_integrity()
        return {**self._basis(), "digest": self.digest}


def _validate_files(unit: EvidenceUnitSpec, review: ArtifactReview, workspace_root: Path) -> None:
    roles = {item.role for item in unit.files}
    required = {"registered-data", "analysis-script", "caption"}
    if review.artifact_kind == "figure":
        required |= {"plot-data", "renderer"}
        if not roles & {"final-pdf", "final-png"}:
            raise ValueError("figure evidence units require a final PDF or PNG")
    else:
        required.add("final-data")
    if not required <= roles:
        raise ValueError(f"evidence unit omits required file roles: {', '.join(sorted(required - roles))}")
    for item in unit.files:
        target = workspace_root / item.path
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != item.sha256:
            raise ValueError(f"evidence file is missing or checksum-mismatched: {item.path}")


def validate_evidence_map_files(
    evidence_map: ScientificEvidenceMap,
    *,
    workspace_root: Path,
) -> None:
    """Recheck every file immediately before rendering or version publication."""
    evidence_map.validate_integrity()
    for unit in evidence_map.units:
        _validate_files(unit.spec, unit.review, workspace_root)


def _validate_acyclic(units: tuple[EvidenceMapUnit, ...]) -> None:
    dependencies = {unit.spec.id: set(unit.spec.predecessor_unit_ids) for unit in units}
    ready = sorted(key for key, values in dependencies.items() if not values)
    visited: list[str] = []
    while ready:
        value = ready.pop(0)
        visited.append(value)
        for target in sorted(dependencies):
            if value in dependencies[target]:
                dependencies[target].remove(value)
                if not dependencies[target] and target not in visited and target not in ready:
                    ready.append(target)
                    ready.sort()
    if len(visited) != len(units):
        raise ValueError("scientific evidence story contains a dependency cycle")


def build_scientific_evidence_map(
    state: ProjectState,
    bundle: ScientificDependencyBundle,
    unit_specs: tuple[EvidenceUnitSpec, ...],
    *,
    workspace_root: Path,
    version: EvidenceMapVersion,
) -> ScientificEvidenceMap:
    if bundle.map_kind != version.map_kind:
        raise ValueError("evidence map version and dependency bundle kinds differ")
    bundle._validate(state)
    specs = tuple(unit_specs)
    if len({item.id for item in specs}) != len(specs):
        raise ValueError("evidence map unit IDs must be unique")
    resource_ids = [
        resource.id
        for spec in specs
        for resource in (*spec.files, *spec.narrative_sources)
    ]
    if len(set(resource_ids)) != len(resource_ids):
        raise ValueError("evidence map file and narrative-source IDs must be globally unique")
    spec_ids = {item.id for item in specs}
    if any(not set(item.predecessor_unit_ids) <= spec_ids for item in specs):
        raise ValueError("evidence map unit references an unknown predecessor")
    artifacts = {item.id: item for item in state.artifacts}
    reviews = {item.artifact_id: item for item in bundle.reviews}
    decisions = {item.artifact_id: item for item in bundle.decisions}
    admissions = {item.id: item for item in bundle.admissions}
    if {item.artifact_id for item in specs} != set(artifacts):
        raise ValueError("scientific evidence map must cover every registered artifact")
    units: list[EvidenceMapUnit] = []
    for spec in specs:
        artifact = artifacts.get(spec.artifact_id)
        if artifact is None:
            raise ValueError("evidence map references an unknown artifact")
        review = reviews[spec.artifact_id]
        if review.artifact_kind == "figure":
            panel_ids = {panel.panel_id for panel in review.panels}
            if spec.panel_id not in panel_ids:
                raise ValueError("figure evidence unit references an unknown panel")
        elif spec.panel_id is not None:
            raise ValueError("non-figure evidence units cannot declare a panel")
        if not set(spec.analysis_admission_ids) <= set(admissions):
            raise ValueError("evidence map references an unknown analysis admission")
        unit_admissions = tuple(admissions[item] for item in spec.analysis_admission_ids)
        relevant_hypotheses = set(decisions[spec.artifact_id].hypothesis_ids)
        if relevant_hypotheses and not any(
            relevant_hypotheses & set(item.hypothesis_ids) for item in unit_admissions
        ):
            raise ValueError("evidence unit admissions do not address the artifact decision hypotheses")
        _validate_files(spec, review, workspace_root)
        units.append(
            EvidenceMapUnit(
                spec,
                artifact.artifact_type,
                unit_admissions,
                review,
                decisions[spec.artifact_id],
                "input-qualification" if artifact.producing_module_id is None else "observed-analysis",
            )
        )
    for artifact_id, review in reviews.items():
        covered = [unit.spec.panel_id for unit in units if unit.spec.artifact_id == artifact_id]
        if review.artifact_kind == "figure":
            if set(covered) != {panel.panel_id for panel in review.panels} or len(covered) != len(set(covered)):
                raise ValueError("evidence map panel coverage differs from the figure review")
        elif covered != [None]:
            raise ValueError("each non-figure artifact requires exactly one evidence unit")
    ordered_units = tuple(sorted(units, key=lambda item: item.spec.id))
    _validate_acyclic(ordered_units)
    unit_by_id = {unit.spec.id: unit for unit in ordered_units}
    edges: set[tuple[str, str, str, str, str]] = set()
    for unit in ordered_units:
        spec = unit.spec
        for predecessor in spec.predecessor_unit_ids:
            edges.add(("detail", spec.group_id, predecessor, spec.id, "precedes"))
            if spec.panel_id is not None and unit_by_id[predecessor].spec.panel_id is not None:
                edges.add(("story", "global-panel-story", predecessor, spec.id, "panel-depends-on"))
        previous = [spec.id]
        for stage in _ROLE_STAGES:
            current = sorted(
                (item for item in spec.files if item.role in stage),
                key=lambda item: item.id,
            )
            if not current:
                continue
            for source in previous:
                for target in current:
                    edges.add(
                        (
                            "detail",
                            spec.group_id,
                            source,
                            target.id,
                            f"to-{target.role}",
                        )
                    )
            previous = [item.id for item in current]
        for source in previous:
            for narrative in spec.narrative_sources:
                edges.add(("detail", spec.group_id, source, narrative.id, "caption-supported-by-doi"))
    ordered_edges = tuple(EvidenceMapEdge(*value) for value in sorted(edges))
    edge_digest = digest_value([edge.to_dict() for edge in ordered_edges])
    provisional = ScientificEvidenceMap(
        1,
        state.context.project_id,
        state.context.scientific_question,
        version,
        state.state_digest,
        bundle.digest,
        delivery_slice_digest(state),
        tuple(sorted(item.artifact_id for item in bundle.decisions if item.active_evidence)),
        tuple(sorted(state.hypotheses, key=lambda item: item.id)),
        ordered_units,
        ordered_edges,
        edge_digest,
        "0" * 64,
    )
    result = ScientificEvidenceMap(**{**provisional.__dict__, "digest": digest_value(provisional._basis())})
    result.validate_integrity()
    return result
