#!/usr/bin/env python3
"""Build and audit a one-to-one, one-to-many and many-to-many orthology ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from biomed_workbench.capabilities.single_cell_integration import (
    build_orthology_ledger,
    orthology_coverage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-tsv", type=Path, required=True)
    parser.add_argument(
        "--feature-tsv",
        action="append",
        required=True,
        help="Repeated SPECIES=one-column-feature.tsv arguments.",
    )
    parser.add_argument("--minimum-confidence", type=float, default=0)
    parser.add_argument("--output-tsv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_feature_sets(values: list[str]) -> tuple[dict[str, list[str]], dict[str, str]]:
    features: dict[str, list[str]] = {}
    digests: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("feature inputs must use SPECIES=path")
        species, raw_path = value.split("=", 1)
        species = species.strip()
        path = Path(raw_path)
        if not species or species in features:
            raise ValueError("species feature inputs must be unique and nonempty")
        frame = pd.read_csv(path, sep="\t", header=None)
        genes = frame.iloc[:, 0].astype(str).str.strip()
        if genes.eq("").any() or genes.duplicated().any():
            raise ValueError(f"{species}: feature identifiers must be unique and nonempty")
        features[species] = genes.tolist()
        digests[species] = sha256(path)
    return features, digests


def main() -> int:
    args = parse_args()
    if args.output_tsv.exists() or args.report.exists():
        raise FileExistsError("refusing to overwrite output")
    if not 0 <= args.minimum_confidence <= 1:
        raise ValueError("minimum confidence must be between zero and one")
    raw = pd.read_csv(args.input_tsv, sep="\t")
    ledger = build_orthology_ledger(raw)
    ledger = ledger.loc[ledger["confidence"] >= args.minimum_confidence].copy()
    if ledger.empty:
        raise ValueError("no orthology rows remain after confidence filtering")
    features, feature_digests = read_feature_sets(args.feature_tsv)
    species_in_ledger = set(ledger["source_species"]) | set(ledger["target_species"])
    if set(features) - species_in_ledger:
        raise ValueError("feature inputs contain species absent from the orthology ledger")
    coverage = orthology_coverage(ledger, features)
    pair_counts = (
        ledger.groupby(["source_species", "target_species"], observed=True)
        .size()
        .rename("pairs")
        .reset_index()
        .to_dict(orient="records")
    )
    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(args.output_tsv, sep="\t", index=False)
    payload = {
        "schema_version": 1,
        "passed": True,
        "input_sha256": sha256(args.input_tsv),
        "feature_sha256": feature_digests,
        "rows": len(ledger),
        "orthogroups": int(ledger["orthogroup_id"].nunique()),
        "relations": ledger["relation"].value_counts().to_dict(),
        "species_pairs": pair_counts,
        "coverage": coverage,
        "minimum_confidence": args.minimum_confidence,
        "scientific_validation": [
            "The ledger preserves one-to-one, one-to-many and many-to-many relations rather than silently collapsing them.",
            "Resource name, release and confidence remain attached to every relation.",
            "Feature coverage is reported per species before any shared-space method is selected.",
        ],
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    reloaded = pd.read_csv(args.output_tsv, sep="\t")
    if len(reloaded) != len(ledger) or reloaded.isna().any().any():
        raise RuntimeError("orthology ledger failed reload validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
