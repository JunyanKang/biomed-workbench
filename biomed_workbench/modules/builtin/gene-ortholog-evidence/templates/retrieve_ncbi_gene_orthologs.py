#!/usr/bin/env python3
"""Project template for bounded NCBI Gene ortholog evidence retrieval.

This is a data-source template for comparative genomics planning. It retrieves
declared source-gene to target-taxon ortholog records and preserves limitations;
it does not infer function, expression conservation, phenotype equivalence, or
experimental substitutability.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from biomed_workbench.capabilities.evidence import gene_ortholog_evidence


def read_request(path: Path) -> dict[str, Any]:
    """Load one JSON request object from disk."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"could not read input JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    return payload


def normalize_request(payload: dict[str, Any]) -> tuple[str, int, int, dict[str, Any]]:
    """Validate gene ID, target taxon ID, max records, and optional metadata."""
    gene_id = payload.get("gene_id")
    target_taxon_id = payload.get("target_taxon_id")
    max_records = payload.get("max_records", 20)
    metadata = payload.get("metadata", {})
    if not isinstance(gene_id, str) or not gene_id.isdecimal() or gene_id.startswith("0"):
        raise ValueError("gene_id must be a stable positive NCBI Gene integer string")
    if isinstance(target_taxon_id, bool) or not isinstance(target_taxon_id, int) or target_taxon_id < 1:
        raise ValueError("target_taxon_id must be a positive integer")
    if isinstance(max_records, bool) or not isinstance(max_records, int) or not 1 <= max_records <= 100:
        raise ValueError("max_records must be an integer between 1 and 100")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be an object when supplied")
    return gene_id, target_taxon_id, max_records, metadata or {}


def validate_retrieval(result: dict[str, Any], gene_id: str, target_taxon_id: int) -> list[str]:
    """Check the returned source identity, target taxon, and bounded output."""
    source = result.get("source")
    if not isinstance(source, dict) or source.get("gene_id") != gene_id:
        raise ValueError("retrieval did not preserve the requested source gene_id")
    if result.get("target_taxon_id") != str(target_taxon_id):
        raise ValueError("retrieval did not preserve the requested target_taxon_id")
    orthologs = result.get("orthologs")
    if not isinstance(orthologs, list):
        raise ValueError("orthologs must be returned as a list")
    warnings: list[str] = []
    if result.get("truncated") is True:
        warnings.append("ortholog records were truncated by max_records")
    if not orthologs:
        warnings.append("no target ortholog records were returned by the current service response")
    for index, record in enumerate(orthologs):
        if not isinstance(record, dict) or not record.get("gene_id"):
            raise ValueError(f"orthologs[{index}] lacks a stable gene_id")
    return warnings


def build_output(input_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Retrieve evidence and serialize provenance for downstream analysis."""
    gene_id, target_taxon_id, max_records, metadata = normalize_request(payload)
    result = gene_ortholog_evidence(gene_id, target_taxon_id, max_records)
    warnings = validate_retrieval(result, gene_id, target_taxon_id)
    return {
        "module_id": "gene-ortholog-evidence",
        "input_path": str(input_path),
        "metadata": metadata,
        "result": result,
        "quality": {
            "source_gene_id": gene_id,
            "target_taxon_id": target_taxon_id,
            "returned_records": len(result.get("orthologs", [])),
            "warning_count": len(warnings),
            "warnings": warnings,
            "scientific_boundary": "database ortholog evidence only; no functional or phenotype equivalence claim",
        },
        "provenance": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "template": "retrieve_ncbi_gene_orthologs.py",
            "argv": sys.argv[1:],
        },
    }


def save_json(path: Path, output: dict[str, Any]) -> None:
    """Save the bounded retrieval output."""
    if path.exists() and path.is_dir():
        raise ValueError("output path is a directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieve bounded NCBI Gene ortholog evidence")
    parser.add_argument("--input-json", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = read_request(args.input_json)
    output = build_output(args.input_json, payload)
    save_json(args.output_json, output)


if __name__ == "__main__":
    main()
