"""One-to-one source understanding to clean-room rewrite decisions."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .assimilation import FileRecord


_TARGETS = {
    "clinical_translation": "biomed_workbench/capabilities/clinical.py",
    "codex_native_orchestration": "skills/biomed-workbench/SKILL.md",
    "data_engineering": "biomed_workbench/capabilities/data.py",
    "evidence_discovery": "biomed_workbench/capabilities/evidence.py",
    "imaging": "biomed_workbench/capabilities/imaging.py",
    "molecular_design": "biomed_workbench/capabilities/molecular.py",
    "omics": "biomed_workbench/capabilities/omics.py",
    "publication": "biomed_workbench/capabilities/publication.py",
    "runtime_orchestration": "biomed_workbench/services/compute.py",
    "scientific_assistant_core": "biomed_workbench/assistant.py",
    "statistics_modeling": "biomed_workbench/capabilities/statistics.py",
    "structural_biology": "biomed_workbench/capabilities/structure.py",
    "visualization": "biomed_workbench/capabilities/visualization.py",
    "wetlab_experiment": "biomed_workbench/capabilities/experiment.py",
}


@dataclass(frozen=True)
class DesignRecord:
    source: str
    path: str
    source_sha256: str
    purpose: str
    role: str
    capability_cluster: str
    action: str
    target: str | None
    reuse_mode: str
    rationale: str
    public_symbol_count: int
    dependency_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_design_record(record: FileRecord) -> DesignRecord:
    role = str(record.understanding.get("role", "unknown"))
    purpose = str(record.understanding.get("purpose", "")).strip()
    target = _TARGETS.get(record.capability_cluster, "biomed_workbench/assistant.py")
    reuse_mode = "concept_only"
    if record.disposition == "generated_runtime":
        action, target, reuse_mode = "exclude_generated", None, "none"
        rationale = "The file is a generated dependency or runtime object; its package role informs readiness checks but its implementation is not part of the new project."
    elif record.disposition == "sensitive":
        action, target, reuse_mode = "exclude_sensitive", None, "none"
        rationale = "Only the configuration shape is learned; credential material is redacted and never enters the new project."
    elif record.disposition == "obsolete":
        action, target, reuse_mode = "retire", None, "none"
        rationale = "The file carries no reusable behavior and is intentionally absent from the new architecture."
    elif record.disposition == "provenance_only":
        action, target, reuse_mode = "retain_provenance", "NOTICE.md", "attribution_only"
        rationale = "License and attribution obligations are retained separately from operational code."
    elif record.capability_cluster == "codex_native_orchestration":
        action, target = "rewrite_codex_native", "skills/biomed-workbench/SKILL.md"
        rationale = "The useful planning contract is redesigned for Codex; nested model clients, provider tokens, and secondary agent loops are discarded."
    elif role == "assistant_workflow":
        action, target = "rewrite_workflow", "skills/biomed-workbench/SKILL.md"
        rationale = "Workflow intent and scientific safeguards are consolidated behind the single Codex entrypoint with a new interaction contract."
    elif record.capability_cluster == "quality_assurance" or role == "verification":
        action, target = "rewrite_test", "tests/"
        rationale = "The behavior and failure case become an independent test for the redesigned capability."
    elif record.capability_cluster == "product_interface":
        action, target = "learn_product_pattern", "skills/biomed-workbench/SKILL.md"
        rationale = "Interaction and usability lessons inform the Codex experience; application-specific interface code is not retained."
    elif role == "executable_logic":
        action = "rewrite_capability"
        rationale = "Scientific purpose, inputs, outputs, and algorithmic constraints inform a fresh source-neutral implementation."
    elif role == "structured_scientific_asset":
        action = "redesign_schema"
        rationale = "The data contract and domain assumptions inform a newly validated schema without retaining serialized source artifacts."
    elif role == "binary_or_visual_asset":
        action, target = "replace_asset", "assets/"
        rationale = "The asset's communication role informs a newly produced project asset; the original bytes are not retained."
    else:
        action = "synthesize_guidance"
        rationale = "Scientific rules and operational lessons are rewritten into source-neutral capability guidance and validation criteria."
    return DesignRecord(
        source=record.source,
        path=record.path,
        source_sha256=record.sha256,
        purpose=purpose,
        role=role,
        capability_cluster=record.capability_cluster,
        action=action,
        target=target,
        reuse_mode=reuse_mode,
        rationale=rationale,
        public_symbol_count=int(record.understanding.get("public_symbol_count", 0)),
        dependency_count=int(record.understanding.get("dependency_count", 0)),
    )


def verify_design_complete(records: Iterable[FileRecord], designs: Iterable[DesignRecord]) -> None:
    source_keys = [(record.source, record.path, record.sha256) for record in records]
    design_keys = [(record.source, record.path, record.source_sha256) for record in designs]
    if len(design_keys) != len(set(design_keys)):
        raise ValueError("design ledger contains duplicate source files")
    if set(source_keys) != set(design_keys):
        raise ValueError("design ledger is not an exact one-to-one source mapping")
    if any(not record.purpose or not record.rationale or not record.action for record in designs):
        raise ValueError("design ledger contains an unexplained decision")


def summarize_design(designs: Iterable[DesignRecord]) -> dict[str, Any]:
    designs = list(designs)
    digest = hashlib.sha256()
    for record in sorted(designs, key=lambda item: (item.source, item.path)):
        digest.update(
            json.dumps(
                {
                    "source": record.source,
                    "path": record.path,
                    "source_sha256": record.source_sha256,
                    "action": record.action,
                    "target": record.target,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
        digest.update(b"\n")
    by_source = Counter(record.source for record in designs)
    return {
        "schema_version": 1,
        "learned_file_count": len(designs),
        "source_counts": dict(sorted(by_source.items())),
        "action_counts": dict(sorted(Counter(record.action for record in designs).items())),
        "capability_cluster_counts": dict(sorted(Counter(record.capability_cluster for record in designs).items())),
        "reuse_mode_counts": dict(sorted(Counter(record.reuse_mode for record in designs).items())),
        "public_symbol_count": sum(record.public_symbol_count for record in designs),
        "design_digest": digest.hexdigest(),
    }
