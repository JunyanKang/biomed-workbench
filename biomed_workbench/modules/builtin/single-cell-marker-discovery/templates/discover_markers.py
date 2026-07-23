#!/usr/bin/env python3
"""Discover cluster markers with donor-stratified discovery and held-out validation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

import anndata
import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-h5ad", required=True)
    parser.add_argument("--output-tsv", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--cluster-key", required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--raw-count-location", required=True)
    parser.add_argument("--validation-samples", default="")
    parser.add_argument("--method", choices=("wilcoxon", "t-test", "logreg"), default="wilcoxon")
    parser.add_argument("--top-per-cluster", type=int, default=100)
    parser.add_argument("--min-in-fraction", type=float, default=0.25)
    parser.add_argument("--max-out-fraction", type=float, default=0.5)
    parser.add_argument("--min-logfc", type=float, default=0.25)
    parser.add_argument("--max-adjusted-p", type=float, default=0.05)
    parser.add_argument("--min-sample-support", type=int, default=2)
    parser.add_argument("--min-validation-sample-support", type=int, default=1)
    parser.add_argument("--min-cells-per-sample-contrast", type=int, default=3)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def raw_counts(adata: anndata.AnnData, location: str):
    if location == "X":
        matrix = adata.X
    elif location.startswith("layers.") and location[7:] in adata.layers:
        matrix = adata.layers[location[7:]]
    else:
        raise ValueError("raw-count-location must be X or an existing layers.NAME")
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).reshape(-1)
    if (
        values.size == 0
        or not np.isfinite(values).all()
        or np.any(values < 0)
        or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8)
    ):
        raise ValueError("marker discovery requires finite nonnegative integer-like counts")
    return matrix.copy()


def parse_validation_samples(raw: str) -> list[str]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if len(values) != len(set(values)):
        raise ValueError("validation samples must be unique")
    return values


def expression_fraction(matrix, rows: np.ndarray) -> np.ndarray:
    selected = matrix[rows, :]
    if selected.shape[0] == 0:
        return np.full(matrix.shape[1], np.nan)
    return np.asarray((selected > 0).mean(axis=0)).reshape(-1)


def direction_evidence(
    matrix,
    clusters: np.ndarray,
    samples: np.ndarray,
    cluster: str,
    gene_index: int,
    sample_names: list[str],
    minimum_cells: int,
    required_positive: int,
) -> dict[str, object]:
    differences: list[float] = []
    evaluated: list[str] = []
    for sample in sample_names:
        sample_rows = samples == sample
        inside = sample_rows & (clusters == cluster)
        outside = sample_rows & (clusters != cluster)
        if int(inside.sum()) < minimum_cells or int(outside.sum()) < minimum_cells:
            continue
        inside_fraction = float(
            np.asarray((matrix[inside, gene_index] > 0).mean()).reshape(-1)[0]
        )
        outside_fraction = float(
            np.asarray((matrix[outside, gene_index] > 0).mean()).reshape(-1)[0]
        )
        differences.append(inside_fraction - outside_fraction)
        evaluated.append(sample)
    positive = sum(value > 0 for value in differences)
    negative = sum(value < 0 for value in differences)
    tied = sum(value == 0 for value in differences)
    if not evaluated:
        status = "unevaluable"
    elif negative:
        status = "discordant"
    elif positive >= required_positive:
        status = "stable-positive"
    else:
        status = "insufficient-support"
    return {
        "positive": int(positive),
        "negative": int(negative),
        "tied": int(tied),
        "evaluable": int(len(evaluated)),
        "evaluable_sample_ids": evaluated,
        "median_detection_difference": (
            float(np.median(differences)) if differences else None
        ),
        "minimum_detection_difference": (
            float(np.min(differences)) if differences else None
        ),
        "maximum_detection_difference": (
            float(np.max(differences)) if differences else None
        ),
        "status": status,
    }


def role_accounting(
    clusters: np.ndarray,
    samples: np.ndarray,
    discovery_samples: list[str],
    validation_samples: list[str],
) -> dict[str, object]:
    result: dict[str, object] = {}
    roles = {
        "discovery": discovery_samples,
        "validation": validation_samples,
    }
    for role, sample_names in roles.items():
        role_rows = np.isin(samples, sample_names)
        by_cluster = pd.Series(clusters[role_rows]).value_counts().sort_index()
        by_sample = pd.Series(samples[role_rows]).value_counts().sort_index()
        result[role] = {
            "cells": int(role_rows.sum()),
            "samples": sample_names,
            "cells_by_cluster": {
                str(key): int(value) for key, value in by_cluster.items()
            },
            "cells_by_sample": {
                str(key): int(value) for key, value in by_sample.items()
            },
        }
    return result


def main() -> int:
    args = parse_args()
    source = Path(args.input_h5ad).resolve(strict=True)
    output, report_path = Path(args.output_tsv), Path(args.report)
    if output.exists() or report_path.exists():
        raise FileExistsError("refusing to overwrite declared outputs")
    if (
        args.top_per_cluster < 5
        or args.min_sample_support < 1
        or args.min_validation_sample_support < 1
        or args.min_cells_per_sample_contrast < 2
    ):
        raise ValueError("rank, sample-support, or cell thresholds are invalid")
    if (
        not 0 <= args.min_in_fraction <= 1
        or not 0 <= args.max_out_fraction <= 1
        or not 0 < args.max_adjusted_p <= 1
    ):
        raise ValueError("fraction or adjusted-p thresholds are invalid")

    source_digest = sha256(source)
    adata = anndata.read_h5ad(source)
    for key in (args.cluster_key, args.sample_key):
        if key not in adata.obs or adata.obs[key].isna().any():
            raise ValueError(f"required observation field is absent or incomplete: {key}")
    if not adata.obs_names.is_unique or not adata.var_names.is_unique:
        raise ValueError("cell and feature identifiers must be unique")
    counts = raw_counts(adata, args.raw_count_location)
    clusters = adata.obs[args.cluster_key].astype(str).to_numpy()
    samples = adata.obs[args.sample_key].astype(str).to_numpy()
    all_samples = sorted(pd.unique(samples).tolist())
    validation_samples = parse_validation_samples(args.validation_samples)
    unknown_validation = sorted(set(validation_samples).difference(all_samples))
    if unknown_validation:
        raise ValueError(
            "validation samples are absent from the input: "
            + ",".join(unknown_validation)
        )
    discovery_samples = [
        sample for sample in all_samples if sample not in set(validation_samples)
    ]
    if len(discovery_samples) < 2:
        raise ValueError("marker discovery requires at least two discovery samples")
    if validation_samples and len(validation_samples) < args.min_validation_sample_support:
        raise ValueError("validation sample count is below the declared support threshold")
    if args.min_sample_support > len(discovery_samples):
        raise ValueError("discovery support threshold exceeds discovery sample count")

    discovery_rows = np.isin(samples, discovery_samples)
    validation_rows = np.isin(samples, validation_samples)
    cluster_sizes = pd.Series(clusters).value_counts().sort_index()
    discovery_cluster_sizes = (
        pd.Series(clusters[discovery_rows]).value_counts().reindex(cluster_sizes.index, fill_value=0)
    )
    validation_cluster_sizes = (
        pd.Series(clusters[validation_rows]).value_counts().reindex(cluster_sizes.index, fill_value=0)
    )
    if (
        cluster_sizes.size < 2
        or int(discovery_cluster_sizes.min()) < 10
        or (validation_samples and int(validation_cluster_sizes.min()) < args.min_cells_per_sample_contrast)
    ):
        raise ValueError(
            "each cluster requires at least ten discovery cells and adequate held-out validation cells"
        )

    work = anndata.AnnData(
        X=counts[discovery_rows, :].copy(),
        obs=adata.obs.loc[
            discovery_rows, [args.cluster_key, args.sample_key]
        ].copy(),
        var=adata.var.copy(),
    )
    work.obs[args.cluster_key] = pd.Categorical(clusters[discovery_rows])
    sc.pp.normalize_total(work, target_sum=10_000)
    sc.pp.log1p(work)
    np.random.seed(args.seed)
    sc.tl.rank_genes_groups(
        work,
        groupby=args.cluster_key,
        method=args.method,
        n_genes=min(args.top_per_cluster, work.n_vars),
        use_raw=False,
        pts=False,
    )

    marker_rows: list[dict[str, object]] = []
    for cluster in work.obs[args.cluster_key].cat.categories:
        ranked = sc.get.rank_genes_groups_df(work, group=str(cluster))
        discovery_inside = discovery_rows & (clusters == str(cluster))
        discovery_outside = discovery_rows & (clusters != str(cluster))
        validation_inside = validation_rows & (clusters == str(cluster))
        validation_outside = validation_rows & (clusters != str(cluster))
        discovery_in_fraction = expression_fraction(counts, discovery_inside)
        discovery_out_fraction = expression_fraction(counts, discovery_outside)
        validation_in_fraction = expression_fraction(counts, validation_inside)
        validation_out_fraction = expression_fraction(counts, validation_outside)
        for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
            gene = str(row["names"])
            gene_index = int(adata.var_names.get_loc(gene))
            discovery = direction_evidence(
                counts,
                clusters,
                samples,
                str(cluster),
                gene_index,
                discovery_samples,
                args.min_cells_per_sample_contrast,
                args.min_sample_support,
            )
            validation = direction_evidence(
                counts,
                clusters,
                samples,
                str(cluster),
                gene_index,
                validation_samples,
                args.min_cells_per_sample_contrast,
                args.min_validation_sample_support,
            )
            logfc = float(row.get("logfoldchanges", np.nan))
            adjusted = float(row.get("pvals_adj", np.nan))
            discovery_admitted = bool(
                np.isfinite(logfc)
                and np.isfinite(adjusted)
                and logfc >= args.min_logfc
                and adjusted <= args.max_adjusted_p
                and discovery_in_fraction[gene_index] >= args.min_in_fraction
                and discovery_out_fraction[gene_index] <= args.max_out_fraction
                and discovery["status"] == "stable-positive"
            )
            independently_validated = bool(
                discovery_admitted
                and validation_samples
                and validation["status"] == "stable-positive"
            )
            marker_rows.append(
                {
                    "cluster": str(cluster),
                    "rank": rank,
                    "gene": gene,
                    "score": float(row["scores"]),
                    "log2_fold_change": logfc,
                    "p_value": float(row.get("pvals", np.nan)),
                    "adjusted_p_value": adjusted,
                    "inferential_scope": "descriptive-cell-level-ranking-not-donor-level-inference",
                    "discovery_fraction_in": float(discovery_in_fraction[gene_index]),
                    "discovery_fraction_out": float(discovery_out_fraction[gene_index]),
                    "discovery_supporting_samples": discovery["positive"],
                    "discovery_discordant_samples": discovery["negative"],
                    "discovery_evaluable_samples": discovery["evaluable"],
                    "discovery_median_detection_difference": discovery[
                        "median_detection_difference"
                    ],
                    "discovery_sample_stability": discovery["status"],
                    "validation_fraction_in": (
                        float(validation_in_fraction[gene_index])
                        if validation_samples
                        else np.nan
                    ),
                    "validation_fraction_out": (
                        float(validation_out_fraction[gene_index])
                        if validation_samples
                        else np.nan
                    ),
                    "validation_supporting_samples": validation["positive"],
                    "validation_discordant_samples": validation["negative"],
                    "validation_evaluable_samples": validation["evaluable"],
                    "validation_median_detection_difference": validation[
                        "median_detection_difference"
                    ],
                    "validation_sample_stability": validation["status"],
                    "discovery_admitted_marker": discovery_admitted,
                    "independently_validated_marker": independently_validated,
                    "admitted_marker": (
                        independently_validated
                        if validation_samples
                        else discovery_admitted
                    ),
                }
            )

    markers = pd.DataFrame(marker_rows)
    if markers.empty or set(markers["cluster"]) != set(cluster_sizes.index):
        raise RuntimeError("ranked marker output does not cover every cluster")
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    markers.to_csv(output, sep="\t", index=False)
    reloaded = pd.read_csv(output, sep="\t")
    required_columns = {
        "cluster",
        "gene",
        "inferential_scope",
        "discovery_admitted_marker",
        "independently_validated_marker",
        "admitted_marker",
    }
    if (
        reloaded.shape != markers.shape
        or not required_columns <= set(reloaded.columns)
        or reloaded["gene"].isna().any()
        or not set(cluster_sizes.index) <= set(reloaded["cluster"].astype(str))
    ):
        raise RuntimeError("serialized marker table failed reload validation")
    if sha256(source) != source_digest:
        raise RuntimeError("source H5AD changed during marker discovery")

    discovery_admitted = markers["discovery_admitted_marker"]
    independently_validated = markers["independently_validated_marker"]
    all_clusters_discovered = (
        markers.loc[discovery_admitted, "cluster"].nunique() == cluster_sizes.size
    )
    all_clusters_validated = bool(
        validation_samples
        and markers.loc[independently_validated, "cluster"].nunique()
        == cluster_sizes.size
    )
    report = {
        "schema_version": 2,
        "input": {
            "filename": source.name,
            "sha256": source_digest,
            "cells": int(adata.n_obs),
            "features": int(adata.n_vars),
            "raw_count_location": args.raw_count_location,
            "cluster_key": args.cluster_key,
            "sample_key": args.sample_key,
        },
        "sample_split": {
            "selection_policy": "predeclared-sample-identifiers",
            "discovery_samples": discovery_samples,
            "validation_samples": validation_samples,
            "validation_used_for_ranking_or_threshold_selection": False,
        },
        "accounting": {
            "clusters": {str(key): int(value) for key, value in cluster_sizes.items()},
            "roles": role_accounting(
                clusters,
                samples,
                discovery_samples,
                validation_samples,
            ),
            "tested_rows": int(markers.shape[0]),
            "discovery_admitted_rows": int(discovery_admitted.sum()),
            "independently_validated_rows": int(independently_validated.sum()),
            "clusters_with_discovery_markers": int(
                markers.loc[discovery_admitted, "cluster"].nunique()
            ),
            "clusters_with_independently_validated_markers": int(
                markers.loc[independently_validated, "cluster"].nunique()
            ),
        },
        "parameters": {
            "method": args.method,
            "top_per_cluster": args.top_per_cluster,
            "min_in_fraction": args.min_in_fraction,
            "max_out_fraction": args.max_out_fraction,
            "min_logfc": args.min_logfc,
            "max_adjusted_p": args.max_adjusted_p,
            "min_sample_support": args.min_sample_support,
            "min_validation_sample_support": args.min_validation_sample_support,
            "min_cells_per_sample_contrast": args.min_cells_per_sample_contrast,
            "seed": args.seed,
        },
        "quality": {
            "integer_raw_counts_validated": True,
            "all_clusters_ranked": True,
            "all_clusters_have_discovery_markers": all_clusters_discovered,
            "independent_validation_enabled": bool(validation_samples),
            "all_clusters_have_independently_validated_markers": all_clusters_validated,
            "validation_is_posthoc_only": True,
            "cell_level_p_values_not_donor_level_inference": True,
            "source_immutable": True,
            "output_reloaded": True,
            "automatic_cell_type_assignment_performed": False,
        },
        "output": {
            "filename": output.name,
            "sha256": sha256(output),
        },
        "versions": {
            "python": platform.python_version(),
            "scanpy": importlib.metadata.version("scanpy"),
            "anndata": importlib.metadata.version("anndata"),
            "numpy": importlib.metadata.version("numpy"),
            "pandas": importlib.metadata.version("pandas"),
            "scipy": importlib.metadata.version("scipy"),
        },
        "quality_status": (
            "passed"
            if all_clusters_discovered and all_clusters_validated
            else "review-required"
        ),
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "quality_status": report["quality_status"],
                "discovery_markers": int(discovery_admitted.sum()),
                "independently_validated_markers": int(independently_validated.sum()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
