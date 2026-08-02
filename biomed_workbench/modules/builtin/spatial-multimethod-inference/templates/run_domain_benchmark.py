#!/usr/bin/env python3
"""Run BayesSpace/SpaGCN/STAGATE as separate spatial-domain benchmark arms.

This controller freezes a benchmark manifest, launches project-adapted native
backends, and scores only label-blind stability/coherence/fragmentation metrics.
Reviewed biological labels may be added after fitting solely as post-hoc ARI.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score


def score_labels(adata: ad.AnnData, labels: pd.Series, spatial_key: str, k: int) -> dict[str, float]:
    from sklearn.neighbors import NearestNeighbors
    coords = np.asarray(adata.obsm[spatial_key], dtype=float)
    nn = NearestNeighbors(n_neighbors=min(k + 1, len(coords))).fit(coords)
    indices = nn.kneighbors(return_distance=False)[:, 1:]
    values = labels.astype(str).to_numpy()
    agreement = float(np.mean(values[:, None] == values[indices]))
    fragments = 0
    for label in np.unique(values):
        members = set(np.flatnonzero(values == label))
        components = 0
        while members:
            components += 1
            stack = [members.pop()]
            while stack:
                node = stack.pop()
                adjacent = [x for x in indices[node] if x in members and values[x] == label]
                for x in adjacent:
                    members.remove(x)
                    stack.append(x)
        fragments += components
    return {"neighbor_label_agreement": agreement, "connected_fragments": float(fragments)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-h5ad", type=Path, required=True)
    parser.add_argument("--spatial-key", default="spatial")
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--methods", default="bayesspace,spagcn,stagate")
    parser.add_argument("--clusters", type=int, required=True)
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--neighbor-k", type=int, default=6)
    parser.add_argument("--reviewed-label-key")
    parser.add_argument("--results-directory", type=Path, required=True)
    parser.add_argument("--metrics-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--backend-command-template", required=True, help="Command with {method}, {seed}, {clusters}, {input}, {output} placeholders.")
    args = parser.parse_args()
    if args.results_directory.exists() or args.metrics_output.exists() or args.report.exists():
        raise FileExistsError("refusing to overwrite output")
    adata = ad.read_h5ad(args.input_h5ad)
    if args.sample_key not in adata.obs or args.spatial_key not in adata.obsm:
        raise ValueError("sample identity or spatial coordinates are absent")
    methods = [x.strip() for x in args.methods.split(",") if x.strip()]
    if not methods or not set(methods) <= {"bayesspace", "spagcn", "stagate"}:
        raise ValueError("methods must be bayesspace, spagcn and/or stagate")
    seeds = [int(x) for x in args.seeds.split(",")]
    if len(seeds) < 3 or len(set(seeds)) != len(seeds):
        raise ValueError("at least three unique seeds are required")
    args.results_directory.mkdir(parents=True)
    rows = []
    label_runs = {}
    for method in methods:
        label_runs[method] = []
        for seed in seeds:
            output = args.results_directory / f"{method}-seed-{seed}.tsv"
            command = args.backend_command_template.format(method=method, seed=seed, clusters=args.clusters, input=args.input_h5ad, output=output)
            started = time.monotonic()
            completed = subprocess.run(shlex.split(command), check=False, capture_output=True, text=True)
            elapsed = time.monotonic() - started
            if completed.returncode:
                raise RuntimeError(f"{method} seed {seed} failed: {completed.stderr[-2000:]}")
            frame = pd.read_csv(output, sep="\t")
            if list(frame.columns) != ["observation_id", "domain"] or frame["observation_id"].tolist() != adata.obs_names.astype(str).tolist():
                raise RuntimeError("backend output violates observation/domain contract")
            labels = frame["domain"].astype(str)
            label_runs[method].append(labels)
            metrics = score_labels(adata, labels, args.spatial_key, args.neighbor_k)
            rows.append({"method": method, "seed": seed, "runtime_seconds": elapsed, **metrics})
    for method, runs in label_runs.items():
        for i in range(len(runs)):
            pair_ari = [adjusted_rand_score(runs[i], runs[j]) for j in range(len(runs)) if j != i]
            rows[[r["method"] == method and r["seed"] == seeds[i] for r in rows].index(True)]["seed_stability_ari"] = float(np.mean(pair_ari))
    metrics = pd.DataFrame(rows)
    if args.reviewed_label_key:
        if args.reviewed_label_key not in adata.obs:
            raise ValueError("reviewed label key is absent")
        reviewed = adata.obs[args.reviewed_label_key].astype(str)
        metrics["posthoc_reviewed_label_ari"] = [adjusted_rand_score(reviewed, label_runs[row.method][seeds.index(row.seed)]) for row in metrics.itertuples()]
    args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(args.metrics_output, sep="\t", index=False)
    args.report.write_text(json.dumps({"schema_version": 1, "methods": methods, "seeds": seeds, "clusters": args.clusters, "label_blind_selection": True, "automatic_winner": None, "claim_boundary": "No single method is declared universally best; review stability, coherence, fragmentation, runtime and discordant anatomy without tuning on reviewed labels."}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
