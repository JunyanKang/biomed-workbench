#!/usr/bin/env python3
"""Run GRNBoost2, cisTarget motif pruning, regulon construction, and AUCell."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
from arboreto.algo import grnboost2
from ctxcore.rnkdb import RankingDatabase
from dask.distributed import Client, LocalCluster
from pyscenic.aucell import aucell
from pyscenic.prune import df2regulons
from pyscenic.transform import module2features_auc1st_impl, modules2df
from pyscenic.utils import load_motif_annotations, modules_from_adjacencies


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TableRankingDatabase(RankingDatabase):
    def __init__(self, rankings: pd.DataFrame, name: str):
        self.rankings = rankings
        super().__init__(name=name)

    @property
    def total_genes(self) -> int:
        return self.rankings.shape[1]

    @property
    def genes(self) -> tuple:
        return tuple(self.rankings.columns)

    def load_full(self) -> pd.DataFrame:
        return self.rankings

    def load(self, signature) -> pd.DataFrame:
        return self.rankings.loc[:, self.rankings.columns.isin(signature.genes)]


def read_expression(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", index_col=0)
    if frame.empty or frame.shape[0] < 20 or frame.shape[1] < 10:
        raise ValueError("expression table requires at least 20 cells and 10 genes")
    if frame.index.has_duplicates or frame.columns.has_duplicates or frame.index.isna().any() or frame.columns.isna().any():
        raise ValueError("expression cell and gene identifiers must be unique and nonmissing")
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("expression values must be finite and nonnegative")
    if np.all(np.var(values, axis=0) == 0):
        raise ValueError("expression table has no variable genes")
    return frame


def read_ranking(path: Path, genes: pd.Index) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", index_col=0)
    if frame.empty or frame.index.has_duplicates or frame.columns.has_duplicates:
        raise ValueError("ranking table requires unique motifs and genes")
    if set(frame.columns) != set(genes):
        raise ValueError("ranking database gene universe must exactly match expression genes")
    frame = frame.loc[:, genes]
    values = frame.to_numpy(dtype=float)
    expected = np.arange(frame.shape[1])
    if not np.isfinite(values).all() or not np.equal(values, np.floor(values)).all():
        raise ValueError("ranking values must be finite integers")
    if any(not np.array_equal(np.sort(row.astype(int)), expected) for row in values):
        raise ValueError("each motif ranking row must be a complete zero-based permutation of genes")
    return frame.astype(np.int32)


def serialize_enrichment(frame: pd.DataFrame) -> pd.DataFrame:
    flat = frame.reset_index()
    flat.columns = ["_".join(str(part) for part in column if str(part)) if isinstance(column, tuple) else str(column) for column in flat.columns]
    for column in flat.columns:
        flat[column] = flat[column].map(
            lambda value: json.dumps(dict(value), sort_keys=True) if isinstance(value, (list, tuple)) and value and isinstance(value[0], tuple)
            else json.dumps(sorted(value)) if isinstance(value, (set, frozenset)) else value
        )
    return flat


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expression-tsv", type=Path, required=True)
    parser.add_argument("--tf-list", type=Path, required=True)
    parser.add_argument("--ranking-tsv", type=Path, required=True)
    parser.add_argument("--motif-annotations", type=Path, required=True)
    parser.add_argument("--adjacencies-output", type=Path, required=True)
    parser.add_argument("--motif-enrichment-output", type=Path, required=True)
    parser.add_argument("--regulons-output", type=Path, required=True)
    parser.add_argument("--auc-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--min-targets", type=int, default=5)
    parser.add_argument("--rank-threshold", type=int, required=True)
    parser.add_argument("--cis-auc-threshold", type=float, default=0.2)
    parser.add_argument("--nes-threshold", type=float, default=3.0)
    parser.add_argument("--rho-threshold", type=float, default=0.03)
    parser.add_argument("--aucell-threshold", type=float, default=0.05)
    args = parser.parse_args()

    inputs = (args.expression_tsv, args.tf_list, args.ranking_tsv, args.motif_annotations)
    outputs = (args.adjacencies_output, args.motif_enrichment_output, args.regulons_output, args.auc_output, args.report)
    if any(not path.is_file() for path in inputs):
        raise FileNotFoundError([str(path) for path in inputs if not path.is_file()])
    if any(path.exists() for path in outputs):
        raise FileExistsError([str(path) for path in outputs if path.exists()])
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    if args.min_targets < 3 or args.rank_threshold < 5 or not 0 < args.cis_auc_threshold <= 1 or not math.isfinite(args.nes_threshold) or not 0 < args.rho_threshold < 1 or not 0 < args.aucell_threshold <= 1:
        raise ValueError("invalid regulon, cisTarget, correlation, or AUCell parameter")

    source_hashes = {path.name: sha256(path) for path in inputs}
    expression = read_expression(args.expression_tsv)
    tf_names = [line.strip() for line in args.tf_list.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not tf_names or len(tf_names) != len(set(tf_names)) or not set(tf_names).issubset(expression.columns):
        raise ValueError("TF list must be unique, nonempty, and contained in expression genes")
    rankings = read_ranking(args.ranking_tsv, expression.columns)
    if args.rank_threshold > rankings.shape[1]:
        raise ValueError("rank threshold exceeds ranking gene universe")
    annotations = load_motif_annotations(str(args.motif_annotations))
    if annotations.empty or not set(tf_names).intersection(annotations.index.get_level_values("TF")):
        raise ValueError("motif annotations contain no eligible declared TF")

    cluster = LocalCluster(n_workers=1, threads_per_worker=1, processes=False, dashboard_address=None)
    client = Client(cluster)
    try:
        adjacencies = grnboost2(expression, tf_names=tf_names, client_or_address=client, seed=args.seed, verbose=False)
    finally:
        client.close()
        cluster.close()
    if adjacencies.empty or not {"TF", "target", "importance"}.issubset(adjacencies.columns):
        raise RuntimeError("GRNBoost2 returned no reloadable adjacency evidence")
    adjacencies = adjacencies.sort_values(["TF", "importance", "target"], ascending=[True, False, True]).reset_index(drop=True)

    modules = list(modules_from_adjacencies(
        adjacencies, expression, thresholds=(0.75, 0.9), top_n_targets=(50,), top_n_regulators=(5, 10, 50),
        min_genes=args.min_targets, absolute_thresholds=False, rho_dichotomize=True, keep_only_activating=True,
        rho_threshold=args.rho_threshold, rho_mask_dropouts=False,
    ))
    if not modules:
        raise RuntimeError("no coexpression module passed the declared target and correlation gates")
    database = TableRankingDatabase(rankings, name=args.ranking_tsv.stem)
    pruning = partial(
        module2features_auc1st_impl, rank_threshold=args.rank_threshold, auc_threshold=args.cis_auc_threshold,
        nes_threshold=args.nes_threshold, filter_for_annotation=True,
    )
    enrichment = modules2df(database, modules, annotations, weighted_recovery=False, module2features_func=pruning)
    target_column = ("Enrichment", "TargetGenes")
    if enrichment.empty or target_column not in enrichment.columns:
        raise RuntimeError("cisTarget motif pruning returned no target evidence")
    enrichment = enrichment[enrichment[target_column].map(lambda value: bool(value))]
    if enrichment.empty:
        raise RuntimeError("all motif-pruned modules had empty target sets")
    regulons = list(df2regulons(enrichment))
    if not regulons:
        raise RuntimeError("no regulon survived motif pruning")
    auc = aucell(expression, regulons, auc_threshold=args.aucell_threshold, noweights=False, normalize=False, seed=args.seed, num_workers=1)
    if auc.shape != (expression.shape[0], len(regulons)) or not np.isfinite(auc.to_numpy()).all():
        raise RuntimeError("AUCell output is incomplete or nonfinite")

    adjacencies.to_csv(args.adjacencies_output, sep="\t", index=False)
    serialize_enrichment(enrichment).to_csv(args.motif_enrichment_output, sep="\t", index=False)
    regulon_records = [{
        "name": regulon.name, "transcription_factor": regulon.transcription_factor,
        "targets": dict(sorted(regulon.gene2weight.items())), "context": sorted(regulon.context), "score": float(regulon.score),
    } for regulon in regulons]
    args.regulons_output.write_text(json.dumps(regulon_records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    auc.index.name = "cell_id"
    auc.to_csv(args.auc_output, sep="\t")

    reload_adj = pd.read_csv(args.adjacencies_output, sep="\t")
    reload_enrichment = pd.read_csv(args.motif_enrichment_output, sep="\t")
    reload_regulons = json.loads(args.regulons_output.read_text(encoding="utf-8"))
    reload_auc = pd.read_csv(args.auc_output, sep="\t", index_col=0)
    if len(reload_adj) != len(adjacencies) or len(reload_enrichment) != len(enrichment) or len(reload_regulons) != len(regulons) or reload_auc.shape != auc.shape or list(reload_auc.index) != list(expression.index):
        raise RuntimeError("reloaded pySCENIC outputs failed accounting")
    if {path.name: sha256(path) for path in inputs} != source_hashes:
        raise RuntimeError("a pySCENIC input changed during analysis")

    versions = {name: importlib.metadata.version(name) for name in ("pyscenic", "arboreto", "ctxcore", "numpy", "pandas", "scipy", "scikit-learn", "dask", "distributed", "setuptools")}
    versions["python"] = platform.python_version()
    report = {
        "schema_version": 1, "passed": True, "quality_status": "passed", "versions": versions,
        "input": {"cells": expression.shape[0], "genes": expression.shape[1], "transcription_factors": len(tf_names), "motifs": rankings.shape[0], "source_sha256": source_hashes},
        "parameters": {"seed": args.seed, "min_targets": args.min_targets, "rank_threshold": args.rank_threshold, "cis_auc_threshold": args.cis_auc_threshold, "nes_threshold": args.nes_threshold, "rho_threshold": args.rho_threshold, "aucell_threshold": args.aucell_threshold},
        "results": {"adjacencies": len(adjacencies), "coexpression_modules": len(modules), "motif_enrichment_rows": len(enrichment), "regulons": len(regulons), "regulon_targets": {record["name"]: len(record["targets"]) for record in regulon_records}, "auc_shape": list(auc.shape)},
        "scientific_checks": {"grnboost2_executed": True, "cistarget_motif_pruning_executed": True, "regulons_constructed": True, "aucell_executed": True, "motif_and_ranking_resources_hashed": True, "source_expression_preserved": True, "outputs_reloaded": True, "no_environment_or_compute_infrastructure_managed": True},
        "output_sha256": {path.name: sha256(path) for path in outputs[:-1]},
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "regulons": len(regulons), "tool_version": versions["pyscenic"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
