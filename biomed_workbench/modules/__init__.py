"""Scientific module contracts and dynamic registry support."""

from .contract import (
    ArtifactPort,
    CompatibilityRow,
    DependencyRequirement,
    ExecutionContract,
    FormatContract,
    ModuleManifest,
    ProvenanceContract,
    QualityGate,
    ToolRequirement,
    manifest_to_dict,
    parse_manifest,
)

__all__ = [
    "ArtifactPort",
    "CompatibilityRow",
    "DependencyRequirement",
    "ExecutionContract",
    "FormatContract",
    "ModuleManifest",
    "ProvenanceContract",
    "QualityGate",
    "ToolRequirement",
    "manifest_to_dict",
    "parse_manifest",
]
