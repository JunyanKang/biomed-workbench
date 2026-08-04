#!/usr/bin/env python3
"""Add deterministic per-port observed-result contracts to workflow manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILTIN_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"
SEMANTIC_VALIDATOR = ROOT / "biomed_workbench" / "modules" / "semantic_output_validation.py"

MEDIA_TYPES = {
    "alphafold3-output": "application/zip",
    "artifact-directory": "application/zip",
    "bed": "text/tab-separated-values",
    "broadpeak": "text/tab-separated-values",
    "cellbender-h5": "application/x-hdf5",
    "count-matrix": "text/tab-separated-values",
    "csv": "text/csv",
    "fasta": "text/x-fasta",
    "h5ad": "application/x-hdf5",
    "h5mu": "application/x-hdf5",
    "html": "text/html",
    "inline-json": "application/json",
    "json": "application/json",
    "matrix-market": "text/plain",
    "metascape-result": "application/zip",
    "mmcif": "chemical/x-mmcif",
    "mofa-hdf5": "application/x-hdf5",
    "monocle-object-directory": "application/zip",
    "narrowpeak": "text/tab-separated-values",
    "newick": "text/x-newick",
    "normalized-json": "application/json",
    "paf": "text/tab-separated-values",
    "pdb": "chemical/x-pdb",
    "pdf": "application/pdf",
    "publication-figure-set": "application/zip",
    "rds": "application/octet-stream",
    "scvi-model-directory": "application/zip",
    "seurat-rds": "application/octet-stream",
    "spatialdata-zarr": "application/zip",
    "svg": "image/svg+xml",
    "tab-separated-values": "text/tab-separated-values",
    "tabular": "text/tab-separated-values",
    "tiff": "image/tiff",
    "tskit-trees": "application/octet-stream",
    "vcf": "text/x-vcf",
    "yaml": "application/yaml",
}


def _bump_patch(version: str) -> str:
    major, minor, patch = (int(value) for value in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def _contract(manifest: dict[str, object], port: dict[str, object]) -> dict[str, object]:
    formats = [
        str(item["name"])
        for item in port["formats"]  # type: ignore[index]
    ]
    media_types = sorted({MEDIA_TYPES.get(name, "application/octet-stream") for name in formats})
    semantic_profile = (
        "functional-enrichment-v1"
        if manifest["id"] == "functional-enrichment"
        else f"{manifest['id']}-{port['name']}-v1".replace("_", "-")
    )
    semantic_digest = hashlib.sha256(SEMANTIC_VALIDATOR.read_bytes()).hexdigest()
    quality_gate_ids = [item["id"] for item in manifest["quality_gates"]]  # type: ignore[index]
    return {
        "port": port["name"],
        "content_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "artifact_type": {"type": "string", "enum": [port["artifact_type"]]},
                "format": {"type": "string", "enum": formats},
                "processing_level": {"type": "string", "enum": port["processing_levels"]},
                "result_summary": {"type": "string", "minLength": 8, "maxLength": 4000},
                "record_count": {"type": "integer", "minimum": 0},
                "provenance": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "workflow": {"type": "string", "minLength": 1, "maxLength": 200},
                        "workflow_version": {"type": "string", "minLength": 1, "maxLength": 100},
                        "parameters_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "compatibility_row_id": {"type": "string", "minLength": 1, "maxLength": 200},
                    },
                    "required": ["workflow", "workflow_version", "parameters_digest", "compatibility_row_id"],
                },
            },
            "required": ["artifact_type", "format", "processing_level", "result_summary", "record_count", "provenance"],
        },
        "payloads": [
            {"role": "primary", "media_types": media_types, "minimum": 1, "maximum": 1},
            {"role": "semantic-metadata", "media_types": ["application/json"], "minimum": 1, "maximum": 1},
            {"role": "source-data", "media_types": media_types, "minimum": 0, "maximum": 1},
            {"role": "figure", "media_types": ["application/pdf", "image/svg+xml", "image/tiff", "image/png"], "minimum": 0, "maximum": 1},
            {"role": "model", "media_types": ["application/octet-stream", "application/zip", "application/x-hdf5"], "minimum": 0, "maximum": 1},
            {"role": "log", "media_types": ["application/json", "text/plain"], "minimum": 0, "maximum": 1},
        ],
        "required_postflight_gate_ids": quality_gate_ids,
        "container_reload_validator": "biomed_workbench.modules.observed_output_validation:validate_observed_output",
        "semantic_validator": "biomed_workbench.modules.semantic_output_validation:validate_observed_output_semantics",
        "semantic_validator_sha256": semantic_digest,
        "semantic_profile": semantic_profile,
        "gate_evaluators": [
            {
                "gate_id": gate_id,
                "evaluator": "biomed_workbench.modules.semantic_output_validation:evaluate_structured_gate",
                "evidence_payload_role": "semantic-metadata",
                "metric_key": gate_id,
                "metric_type": "boolean",
                "operator": "equals",
                "threshold": True,
            }
            for gate_id in quality_gate_ids
        ],
    }


def update_manifest(path: Path, *, bump_version: bool) -> bool:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("access") != "agent_generated":
        return False
    expected_contracts = [_contract(manifest, port) for port in manifest["output_artifacts"]]
    if manifest.get("observed_output_contracts") == expected_contracts:
        return False
    old_version = str(manifest["version"])
    new_version = _bump_patch(old_version) if bump_version else old_version
    manifest["version"] = new_version
    for row in manifest["compatibility_matrix"]:
        row["module_version"] = new_version
    manifest["observed_output_contracts"] = expected_contracts
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cases_path = path.parent / "tests" / "cases.json"
    if cases_path.is_file() and bump_version:
        cases = json.loads(cases_path.read_text(encoding="utf-8"))
        for case in cases.get("cases", []):
            module = case.get("expected_subset", {}).get("module")
            if isinstance(module, dict) and module.get("id") == manifest["id"] and module.get("version") == old_version:
                module["version"] = new_version
        cases_path.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-root", type=Path, default=BUILTIN_ROOT)
    parser.add_argument("--bump-module-version", action="store_true")
    args = parser.parse_args()
    changed = sum(
        update_manifest(path, bump_version=args.bump_module_version)
        for path in sorted(args.module_root.glob("*/module.json"))
    )
    print(json.dumps({"updated_agent_generated_modules": changed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
