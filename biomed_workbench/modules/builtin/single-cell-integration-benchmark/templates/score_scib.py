#!/usr/bin/env python3
"""Compute the complete official scIB metric family and retain N/A reasons."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import scanpy as sc

from biomed_workbench.capabilities.single_cell_integration import (
    SCIB_BATCH_METRICS,
    SCIB_BIOLOGY_METRICS,
    integration_diagnostics,
)


ALIASES = {
    "ASW_label": "label_asw",
    "ASW_label/batch": "batch_asw",
    "PCR_batch": "pcr_comparison",
    "cell_cycle_conservation": "cell_cycle_conservation",
    "graph_conn": "graph_connectivity",
    "hvg_overlap": "hvg_conservation",
    "iLISI": "ilisi",
    "cLISI": "clisi",
    "isolated_label_ASW": "isolated_label_asw",
    "isolated_label_F1": "isolated_label_f1",
    "kBET": "kbet",
    "NMI_cluster/label": "nmi",
    "ARI_cluster/label": "ari",
    "trajectory": "trajectory_conservation",
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-h5ad", required=True)
    parser.add_argument("--integrated-h5ad", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--batch-key", required=True)
    parser.add_argument("--label-key", required=True)
    parser.add_argument("--embedding-key", required=True)
    parser.add_argument("--cluster-key")
    parser.add_argument("--organism", default="mouse")
    parser.add_argument("--subsample", type=float, default=0.5)
    parser.add_argument("--cores", type=int, default=1)
    parser.add_argument("--neighbors", type=int, default=30)
    return parser.parse_args()


def scalar(value):
    if value is None:
        return None
    array = np.asarray(value)
    if array.size != 1:
        return None
    result = float(array.reshape(-1)[0])
    return result if np.isfinite(result) else None


def main() -> int:
    args = arguments()
    import scib

    baseline = sc.read_h5ad(args.baseline_h5ad)
    integrated = sc.read_h5ad(args.integrated_h5ad)
    if not baseline.obs_names.equals(integrated.obs_names):
        raise ValueError("baseline and integrated cells differ")
    for key in (args.batch_key, args.label_key):
        if key not in baseline.obs or key not in integrated.obs:
            raise ValueError(f"required metadata field is absent: {key}")
    if args.embedding_key not in integrated.obsm:
        raise ValueError("integrated embedding is absent")
    if not 0 < args.subsample <= 1 or args.cores < 1:
        raise ValueError("subsample and core parameters are invalid")

    official = scib.metrics.metrics(
        baseline,
        integrated,
        batch_key=args.batch_key,
        label_key=args.label_key,
        embed=args.embedding_key,
        cluster_key=args.cluster_key or "_scib_cluster",
        ari_=True,
        nmi_=True,
        silhouette_=True,
        pcr_=True,
        cell_cycle_=True,
        organism=args.organism,
        hvg_score_=True,
        isolated_labels_f1_=True,
        isolated_labels_asw_=True,
        graph_conn_=True,
        trajectory_=True,
        kBET_=True,
        ilisi_=True,
        clisi_=True,
        subsample=args.subsample,
        n_cores=args.cores,
        type_="embed",
    )
    if isinstance(official, pd.DataFrame):
        raw = official.iloc[:, 0].to_dict() if official.shape[1] == 1 else official.stack().to_dict()
    elif isinstance(official, pd.Series):
        raw = official.to_dict()
    elif isinstance(official, dict):
        raw = official
    else:
        raise TypeError("unsupported scIB metric result")
    canonical = {name: None for name in SCIB_BATCH_METRICS + SCIB_BIOLOGY_METRICS}
    for key, value in raw.items():
        canonical_key = ALIASES.get(str(key), str(key).lower())
        if canonical_key in canonical:
            canonical[canonical_key] = scalar(value)

    clusters = integrated.obs[args.cluster_key] if args.cluster_key else None
    aligned = integration_diagnostics(
        integrated.obsm[args.embedding_key],
        batch=integrated.obs[args.batch_key],
        labels=integrated.obs[args.label_key],
        clusters=clusters,
        n_neighbors=args.neighbors,
    )
    not_applicable = {
        key: "official scIB returned no finite value for the supplied data and prerequisites"
        for key, value in canonical.items() if value is None
    }
    payload = {
        "schema_version": 1,
        "passed": True,
        "official_scib_metrics": canonical,
        "official_raw_keys": sorted(map(str, raw)),
        "not_applicable_reasons": not_applicable,
        "aligned_diagnostics": aligned,
        "parameters": {
            "batch_key": args.batch_key,
            "label_key": args.label_key,
            "embedding_key": args.embedding_key,
            "cluster_key": args.cluster_key,
            "organism": args.organism,
            "subsample": args.subsample,
            "cores": args.cores,
            "neighbors": args.neighbors,
        },
        "versions": {
            "scib": version("scib"),
            "scanpy": sc.__version__,
        },
        "scientific_boundary": [
            "No method is ranked by UMAP appearance.",
            "Missing trajectory, cell-cycle, or isolated-label prerequisites remain explicit N/A values.",
            "Integration metrics do not authorize corrected-expression differential testing.",
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
