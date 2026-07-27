#!/usr/bin/env python3
"""Resolve one exact gene symbol to a stable NCBI Gene ID.

The template is intentionally conservative: it writes all candidate records,
records runtime version provenance, and returns a nonzero status when the
identifier cannot pass the exact-symbol quality gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def locate_workbench_root() -> Path:
    """Locate an installed or checked-out workbench without machine-local paths."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "biomed_workbench").is_dir():
            return parent
    raise RuntimeError("Biomed Workbench package root was not found")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gene", required=True, help="Declared exact gene symbol")
    parser.add_argument("--organism", default="human", help="Declared source organism")
    parser.add_argument("--output", type=Path, required=True, help="New JSON result path")
    args = parser.parse_args()
    if not args.gene.strip() or not args.organism.strip():
        parser.error("--gene and --organism must contain non-whitespace text")
    if args.output.exists():
        parser.error("--output must be a new path so prior resolution evidence is not overwritten")
    if args.output.suffix.lower() != ".json":
        parser.error("--output must use the .json extension")
    return args


def validate_result(result: dict[str, Any]) -> list[str]:
    """Return quality-gate failures without replacing unresolved candidates."""
    failures: list[str] = []
    if result.get("resolution_status") != "resolved":
        failures.append("resolution_status is not resolved")
        return failures
    resolved = result.get("resolved")
    if not isinstance(resolved, dict):
        return ["resolved record is absent"]
    for field in ("gene_id", "symbol", "taxon_id", "scientific_name"):
        if not isinstance(resolved.get(field), str) or not resolved[field].strip():
            failures.append(f"resolved record lacks {field}")
    if not str(resolved.get("gene_id", "")).isdigit() or not str(resolved.get("taxon_id", "")).isdigit():
        failures.append("resolved identifier or taxon is not numeric")
    if not isinstance(result.get("candidates"), list) or not result["candidates"]:
        failures.append("candidate accounting is absent")
    return failures


def write_result(path: Path, result: dict[str, Any], failures: list[str]) -> None:
    """Write the reviewable result, including observed runtime provenance."""
    from biomed_workbench.version import VERSION

    payload = {
        "module": "gene-identifier-resolution",
        "runtime": {"python": sys.version.split()[0], "biomed_workbench": VERSION},
        "quality_gate_failures": failures,
        "result": result,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_arguments()
    root = locate_workbench_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from biomed_workbench.capabilities.evidence import resolve_gene_identifier

    try:
        result = resolve_gene_identifier(args.gene, args.organism)
        failures = validate_result(result)
    except (RuntimeError, ValueError) as exc:
        result = {"resolution_status": "error", "candidates": [], "error": str(exc)}
        failures = ["NCBI Gene resolution failed before a reusable identifier was produced"]
    write_result(args.output, result, failures)
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
