#!/usr/bin/env python3
"""Score projection distributions with Jensen-Shannon divergence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[5]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from biomed_workbench.capabilities.single_cell_integration import projection_jsd


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observed-tsv", required=True)
    parser.add_argument("--expected-tsv", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--row-id-column", required=True)
    parser.add_argument(
        "--comparison-semantics",
        choices=("held-out-truth", "simulation-truth", "method-concordance", "reference-concordance"),
        required=True,
    )
    return parser.parse_args()


def read_matrix(path: str, row_id: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t")
    if row_id not in frame:
        raise ValueError(f"row identifier column is absent: {row_id}")
    if frame[row_id].isna().any() or frame[row_id].astype(str).duplicated().any():
        raise ValueError("row identifiers must be complete and unique")
    return frame.set_index(row_id)


def main() -> int:
    args = arguments()
    observed = read_matrix(args.observed_tsv, args.row_id_column)
    expected = read_matrix(args.expected_tsv, args.row_id_column)
    result = projection_jsd(observed, expected)
    location_values = np.asarray(list(result["spot_jsd"].values()), dtype=float)
    if location_values.size == 0 or not np.isfinite(location_values).all():
        raise ValueError("scientific validation failed: JSD values are absent or non-finite")
    if (location_values < 0).any() or (location_values > 1).any():
        raise ValueError("scientific validation failed: normalized JSD must be in [0, 1]")
    accuracy_semantics = args.comparison_semantics in {"held-out-truth", "simulation-truth"}
    payload = {
        "schema_version": 1,
        "passed": True,
        "comparison_semantics": args.comparison_semantics,
        "jsd": result,
        "interpretation": (
            "Independent truth is available; lower JSD supports distributional accuracy."
            if accuracy_semantics
            else "No independent truth is available; JSD measures concordance, not accuracy."
        ),
        "scientific_boundary": [
            "JSD compares probability or abundance distributions and is not a batch-correction method.",
            "JSD does not establish cell identity, spatial causality, or cell-cell signaling.",
        ],
    }
    output = Path(args.report)
    if output.exists():
        raise FileExistsError("refusing to overwrite report")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
