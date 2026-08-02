#!/usr/bin/env python3
"""Evaluate spatial deconvolution outputs without treating consensus as truth."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from biomed_workbench.capabilities.single_cell_integration import projection_jsd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--method",
        action="append",
        required=True,
        help="Repeated METHOD=abundance.tsv arguments.",
    )
    parser.add_argument("--truth-tsv", type=Path)
    parser.add_argument(
        "--truth-semantics",
        choices=("independent", "simulation", "none"),
        default="none",
    )
    parser.add_argument("--location-id-column", default="location_id")
    parser.add_argument("--minimum-cell-types", type=int, default=2)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def parse_method(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError("method inputs must use METHOD=path")
    name, raw_path = value.split("=", 1)
    if not name.strip() or not raw_path.strip():
        raise ValueError("method name and path must be nonempty")
    return name.strip(), Path(raw_path)


def read_abundance(
    path: Path,
    location_column: str,
    minimum_cell_types: int,
) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t")
    if location_column not in frame:
        raise ValueError(f"{path.name}: location identifier column is absent")
    if frame[location_column].isna().any() or frame[location_column].astype(str).duplicated().any():
        raise ValueError(f"{path.name}: location identifiers must be complete and unique")
    matrix = frame.set_index(location_column)
    matrix = matrix.select_dtypes(include=[np.number])
    if matrix.shape[1] < minimum_cell_types:
        raise ValueError(f"{path.name}: too few numeric cell-type columns")
    values = matrix.to_numpy(dtype=float)
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError(f"{path.name}: abundance values must be finite and nonnegative")
    totals = values.sum(axis=1)
    if np.any(totals <= 0):
        raise ValueError(f"{path.name}: every location must have positive abundance mass")
    return matrix.div(totals, axis=0)


def matched(left: pd.DataFrame, right: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    locations = left.index.intersection(right.index, sort=False)
    cell_types = left.columns.intersection(right.columns, sort=False)
    if len(locations) < 2 or len(cell_types) < 2:
        raise ValueError("comparison requires at least two shared locations and cell types")
    return left.loc[locations, cell_types], right.loc[locations, cell_types]


def pair_summary(left: pd.DataFrame, right: pd.DataFrame) -> dict[str, object]:
    left_match, right_match = matched(left, right)
    result = projection_jsd(left_match, right_match)
    left_top = left_match.idxmax(axis=1)
    right_top = right_match.idxmax(axis=1)
    return {
        "locations": len(left_match),
        "cell_types": len(left_match.columns),
        "mean_jsd": result["mean_spot_jsd"],
        "median_jsd": result["median_spot_jsd"],
        "top_cell_type_agreement": float(np.mean(left_top == right_top)),
        "interpretation": "method concordance, not accuracy",
    }


def truth_summary(
    estimate: pd.DataFrame,
    truth: pd.DataFrame,
    truth_semantics: str,
) -> dict[str, object]:
    estimate_match, truth_match = matched(estimate, truth)
    result = projection_jsd(estimate_match, truth_match)
    absolute = np.abs(estimate_match.to_numpy() - truth_match.to_numpy())
    return {
        "locations": len(estimate_match),
        "cell_types": len(estimate_match.columns),
        "mean_jsd": result["mean_spot_jsd"],
        "median_jsd": result["median_spot_jsd"],
        "mean_absolute_error": float(np.mean(absolute)),
        "truth_semantics": truth_semantics,
        "interpretation": "distributional accuracy against declared truth",
    }


def main() -> int:
    args = parse_args()
    if args.report.exists():
        raise FileExistsError("refusing to overwrite report")
    parsed = [parse_method(value) for value in args.method]
    names = [name for name, _ in parsed]
    if len(set(names)) != len(names):
        raise ValueError("method names must be unique")
    matrices = {
        name: read_abundance(path, args.location_id_column, args.minimum_cell_types)
        for name, path in parsed
    }
    pairwise = {
        f"{left}__vs__{right}": pair_summary(matrices[left], matrices[right])
        for left, right in combinations(names, 2)
    }
    accuracy: dict[str, object] = {}
    if args.truth_tsv is not None:
        if args.truth_semantics == "none":
            raise ValueError("truth semantics must be independent or simulation when truth is provided")
        truth = read_abundance(
            args.truth_tsv,
            args.location_id_column,
            args.minimum_cell_types,
        )
        accuracy = {
            name: truth_summary(matrix, truth, args.truth_semantics)
            for name, matrix in matrices.items()
        }
    elif args.truth_semantics != "none":
        raise ValueError("truth semantics were declared but no truth matrix was supplied")
    payload = {
        "schema_version": 1,
        "passed": True,
        "methods": names,
        "pairwise_concordance": pairwise,
        "truth_based_accuracy": accuracy,
        "scientific_validation": {
            "accuracy_available": bool(accuracy),
            "consensus_is_not_truth": True,
            "selection_rule": (
                "Do not select a method because it reproduces desired anatomy. Review held-out "
                "genes, simulations or independent labels, residuals, reference sensitivity, "
                "runtime and between-sample reproducibility."
            ),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    reloaded = json.loads(args.report.read_text())
    if not reloaded.get("passed"):
        raise RuntimeError("report reload failed scientific validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
