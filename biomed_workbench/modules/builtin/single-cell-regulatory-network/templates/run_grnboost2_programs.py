#!/usr/bin/env python3
"""Infer and score TF coexpression programs before motif pruning."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
from pathlib import Path

import numpy as np
import pandas as pd
from arboreto.algo import grnboost2
from dask.distributed import Client, LocalCluster
from pyscenic.aucell import aucell
from pyscenic.utils import modules_from_adjacencies


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_expression(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", index_col=0)
    if frame.shape[0] < 20 or frame.shape[1] < 10:
        raise ValueError("expression table requires at least 20 cells and 10 genes")
    if frame.index.has_duplicates or frame.columns.has_duplicates:
        raise ValueError("cell and gene identifiers must be unique")
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("expression values must be finite and nonnegative")
    if np.all(np.var(values, axis=0) == 0):
        raise ValueError("expression table has no variable genes")
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expression-tsv", type=Path, required=True)
    parser.add_argument("--tf-list", type=Path, required=True)
    parser.add_argument("--adjacencies-output", type=Path, required=True)
    parser.add_argument("--programs-output", type=Path, required=True)
    parser.add_argument("--auc-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--min-targets", type=int, default=5)
    parser.add_argument("--rho-threshold", type=float, default=0.03)
    parser.add_argument("--aucell-threshold", type=float, default=0.05)
    args = parser.parse_args()

    inputs = (args.expression_tsv, args.tf_list)
    outputs = (
        args.adjacencies_output,
        args.programs_output,
        args.auc_output,
        args.report,
    )
    if any(not path.is_file() for path in inputs):
        raise FileNotFoundError([str(path) for path in inputs if not path.is_file()])
    if any(path.exists() for path in outputs):
        raise FileExistsError([str(path) for path in outputs if path.exists()])
    if (
        args.min_targets < 3
        or not 0 < args.rho_threshold < 1
        or not 0 < args.aucell_threshold <= 1
    ):
        raise ValueError("invalid module or AUCell parameters")
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)

    source_hashes = {path.name: sha256(path) for path in inputs}
    expression = read_expression(args.expression_tsv)
    tf_names = [
        line.strip()
        for line in args.tf_list.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if (
        not tf_names
        or len(tf_names) != len(set(tf_names))
        or not set(tf_names).issubset(expression.columns)
    ):
        raise ValueError("TF list must be unique and contained in expression genes")

    cluster = LocalCluster(
        n_workers=1,
        threads_per_worker=1,
        processes=False,
        dashboard_address=None,
    )
    client = Client(cluster)
    try:
        adjacencies = grnboost2(
            expression,
            tf_names=tf_names,
            client_or_address=client,
            seed=args.seed,
            verbose=False,
        )
    finally:
        client.close()
        cluster.close()
    if adjacencies.empty or not {"TF", "target", "importance"}.issubset(
        adjacencies.columns
    ):
        raise RuntimeError("GRNBoost2 returned no adjacency evidence")
    adjacencies = adjacencies.sort_values(
        ["TF", "importance", "target"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    candidates = list(
        modules_from_adjacencies(
            adjacencies,
            expression,
            thresholds=(0.75, 0.9),
            top_n_targets=(50,),
            top_n_regulators=(5, 10, 50),
            min_genes=args.min_targets,
            absolute_thresholds=False,
            rho_dichotomize=True,
            keep_only_activating=True,
            rho_threshold=args.rho_threshold,
            rho_mask_dropouts=False,
        )
    )
    programs = {}
    for module in candidates:
        tf = module.transcription_factor
        targets = dict(module.gene2weight)
        previous = programs.get(tf)
        if previous is None or len(targets) > len(previous.gene2weight):
            programs[tf] = module
    selected = [programs[name] for name in sorted(programs)]
    if not selected:
        raise RuntimeError("no activating coexpression program passed declared gates")

    auc = aucell(
        expression,
        selected,
        auc_threshold=args.aucell_threshold,
        noweights=False,
        normalize=False,
        seed=args.seed,
        num_workers=1,
    )
    if auc.shape != (expression.shape[0], len(selected)):
        raise RuntimeError("AUCell program scoring has incomplete dimensions")
    if not np.isfinite(auc.to_numpy(dtype=float)).all():
        raise RuntimeError("AUCell program scoring contains nonfinite values")

    adjacencies.to_csv(args.adjacencies_output, sep="\t", index=False)
    records = [
        {
            "name": module.name,
            "transcription_factor": module.transcription_factor,
            "targets": dict(sorted(module.gene2weight.items())),
            "context": sorted(module.context),
            "evidence_class": "coexpression-program-not-motif-pruned-regulon",
        }
        for module in selected
    ]
    args.programs_output.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    auc.index.name = "cell_id"
    auc.to_csv(args.auc_output, sep="\t")

    reload_adj = pd.read_csv(args.adjacencies_output, sep="\t")
    reload_programs = json.loads(args.programs_output.read_text(encoding="utf-8"))
    reload_auc = pd.read_csv(args.auc_output, sep="\t", index_col=0)
    if (
        len(reload_adj) != len(adjacencies)
        or len(reload_programs) != len(selected)
        or reload_auc.shape != auc.shape
        or list(reload_auc.index) != list(expression.index)
    ):
        raise RuntimeError("reloaded GRNBoost2 program outputs failed accounting")
    if {path.name: sha256(path) for path in inputs} != source_hashes:
        raise RuntimeError("a regulatory-network input changed during analysis")

    versions = {
        name: importlib.metadata.version(name)
        for name in (
            "pyscenic",
            "arboreto",
            "numpy",
            "pandas",
            "scipy",
            "scikit-learn",
            "dask",
            "distributed",
            "setuptools",
        )
    }
    versions["python"] = platform.python_version()
    report = {
        "schema_version": 1,
        "passed": True,
        "quality_status": "passed",
        "versions": versions,
        "input": {
            "cells": expression.shape[0],
            "genes": expression.shape[1],
            "transcription_factors": len(tf_names),
            "source_sha256": source_hashes,
        },
        "parameters": {
            "seed": args.seed,
            "min_targets": args.min_targets,
            "rho_threshold": args.rho_threshold,
            "aucell_threshold": args.aucell_threshold,
        },
        "results": {
            "adjacencies": len(adjacencies),
            "candidate_modules": len(candidates),
            "scored_programs": len(selected),
            "program_targets": {
                record["transcription_factor"]: len(record["targets"])
                for record in records
            },
            "auc_shape": list(auc.shape),
        },
        "scientific_checks": {
            "grnboost2_executed": True,
            "coexpression_programs_scored": True,
            "programs_not_labeled_as_motif_pruned_regulons": True,
            "motif_pruning_not_executed": True,
            "source_expression_preserved": True,
            "outputs_reloaded": True,
        },
        "output_sha256": {
            path.name: sha256(path) for path in outputs[:-1]
        },
    }
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": True,
                "programs": len(selected),
                "tool_version": versions["pyscenic"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
