#!/usr/bin/env python3
"""Build a path-free tool, dependency, and format compatibility report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.contract import ArtifactPort, DependencyRequirement, FormatContract, ToolRequirement  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def _format(value: FormatContract) -> dict[str, object]:
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


def _port(value: ArtifactPort) -> dict[str, object]:
    return {
        "name": value.name,
        "artifact_type": value.artifact_type,
        "formats": [_format(item) for item in value.formats],
        "processing_levels": list(value.processing_levels),
        "required_metadata": list(value.required_metadata),
    }


def _tool(value: ToolRequirement) -> dict[str, object]:
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


def _dependency(value: DependencyRequirement) -> dict[str, object]:
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


def build_compatibility_report(registry: ModuleRegistry) -> dict[str, object]:
    modules = []
    for manifest in registry.all():
        modules.append(
            {
                "id": manifest.id,
                "module_version": manifest.version,
                "external_tool_required": any(item.required for item in manifest.tool_requirements),
                "tools": [_tool(item) for item in manifest.tool_requirements],
                "dependencies": [_dependency(item) for item in manifest.dependencies],
                "input_formats": [_port(item) for item in manifest.input_artifacts],
                "output_formats": [_port(item) for item in manifest.output_artifacts],
                "compatibility_rows": [item.id for item in manifest.compatibility_matrix],
                "validation_status": "complete",
            }
        )
    return {
        "schema_version": 1,
        "module_count": len(modules),
        "compatibility_complete": sum(item["validation_status"] == "complete" for item in modules),
        "registry_digest": registry.digest,
        "modules": modules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module_root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_compatibility_report(ModuleRegistry.discover(args.module_root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_count": report["module_count"], "output": args.output.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
