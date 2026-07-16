#!/usr/bin/env python3
"""Validate evidence-backed eRegulons and score paired RNA/ATAC signatures with SCENIC+."""

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
from scenicplus.eregulon_enrichment import score_eRegulons


REQUIRED_COLUMNS = (
    "TF", "Gene", "Region", "Gene_signature_name", "Region_signature_name", "motif_id",
    "motif_evidence", "region_gene_score", "region_gene_pvalue", "tf_gene_score",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_matrix(path: Path, label: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", index_col=0)
    if frame.empty or frame.index.has_duplicates or frame.columns.has_duplicates:
        raise ValueError(f"{label} matrix requires unique cells and features")
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError(f"{label} matrix must contain finite nonnegative values")
    return frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expression-tsv", type=Path, required=True)
    parser.add_argument("--accessibility-tsv", type=Path, required=True)
    parser.add_argument("--eregulons-tsv", type=Path, required=True)
    parser.add_argument("--gene-auc-output", type=Path, required=True)
    parser.add_argument("--region-auc-output", type=Path, required=True)
    parser.add_argument("--concordance-output", type=Path, required=True)
    parser.add_argument("--validated-eregulons-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--auc-threshold", type=float, default=0.05)
    parser.add_argument("--minimum-targets", type=int, default=5)
    args = parser.parse_args()

    inputs = (args.expression_tsv, args.accessibility_tsv, args.eregulons_tsv)
    outputs = (args.gene_auc_output, args.region_auc_output, args.concordance_output, args.validated_eregulons_output, args.report)
    if any(not path.is_file() for path in inputs):
        raise FileNotFoundError([str(path) for path in inputs if not path.is_file()])
    if any(path.exists() for path in outputs):
        raise FileExistsError([str(path) for path in outputs if path.exists()])
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    if not 0 < args.auc_threshold <= 1 or args.minimum_targets < 3:
        raise ValueError("invalid SCENIC+ AUC or target-count parameter")

    source_hashes = {path.name: sha256(path) for path in inputs}
    expression = read_matrix(args.expression_tsv, "expression")
    accessibility = read_matrix(args.accessibility_tsv, "accessibility")
    if list(expression.index) != list(accessibility.index):
        raise ValueError("RNA and ATAC cells must be identical and in the same order")
    eregulons = pd.read_csv(args.eregulons_tsv, sep="\t")
    if eregulons.empty or not set(REQUIRED_COLUMNS).issubset(eregulons.columns):
        raise ValueError(f"eRegulon table requires columns: {', '.join(REQUIRED_COLUMNS)}")
    if eregulons[list(REQUIRED_COLUMNS[:6])].isna().any().any() or eregulons.duplicated(["TF", "Gene", "Region", "Gene_signature_name", "Region_signature_name"]).any():
        raise ValueError("eRegulon identities must be nonmissing and unique")
    if not set(eregulons["Gene"]).issubset(expression.columns) or not set(eregulons["Region"]).issubset(accessibility.columns):
        raise ValueError("eRegulon genes and regions must exist in their paired matrices")
    if not eregulons["motif_evidence"].astype(str).str.len().gt(0).all():
        raise ValueError("every eRegulon row requires explicit motif evidence")
    numeric = eregulons[["region_gene_score", "region_gene_pvalue", "tf_gene_score"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy()).all() or not numeric["region_gene_pvalue"].between(0, 1).all():
        raise ValueError("eRegulon evidence scores must be finite and p values must be bounded")
    eregulons[["region_gene_score", "region_gene_pvalue", "tf_gene_score"]] = numeric

    pair_groups = eregulons.groupby(["Gene_signature_name", "Region_signature_name"], sort=True)
    pair_summary = pair_groups.agg(TF=("TF", lambda values: ";".join(sorted(set(values)))), genes=("Gene", "nunique"), regions=("Region", "nunique"), rows=("TF", "size")).reset_index()
    if pair_summary["TF"].str.contains(";").any():
        raise ValueError("each gene/region signature pair must belong to exactly one TF")
    if (pair_summary[["genes", "regions"]] < args.minimum_targets).any().any():
        raise ValueError("every eRegulon signature requires the declared minimum genes and regions")

    scores = score_eRegulons(eregulons, expression, accessibility, auc_threshold=args.auc_threshold, normalize=False, n_cpu=1)
    gene_auc = scores["Gene_based"]
    region_auc = scores["Region_based"]
    if set(gene_auc.index) != set(expression.index) or set(region_auc.index) != set(expression.index):
        raise RuntimeError("SCENIC+ omitted or added cells")
    gene_auc = gene_auc.reindex(expression.index)
    region_auc = region_auc.reindex(expression.index)
    if not np.isfinite(gene_auc.to_numpy()).all() or not np.isfinite(region_auc.to_numpy()).all():
        raise RuntimeError("SCENIC+ AUC contains nonfinite values")

    concordance_records = []
    for row in pair_summary.itertuples(index=False):
        gene_values = gene_auc[row.Gene_signature_name]
        region_values = region_auc[row.Region_signature_name]
        concordance_records.append({
            "TF": row.TF, "Gene_signature_name": row.Gene_signature_name, "Region_signature_name": row.Region_signature_name,
            "genes": int(row.genes), "regions": int(row.regions), "rows": int(row.rows),
            "pearson": float(gene_values.corr(region_values, method="pearson")),
            "spearman": float(gene_values.corr(region_values, method="spearman")),
        })
    concordance = pd.DataFrame(concordance_records)
    if concordance[["pearson", "spearman"]].isna().any().any():
        raise RuntimeError("eRegulon concordance is undefined; inspect constant signatures")

    gene_auc.index.name = region_auc.index.name = "cell_id"
    gene_auc.to_csv(args.gene_auc_output, sep="\t")
    region_auc.to_csv(args.region_auc_output, sep="\t")
    concordance.to_csv(args.concordance_output, sep="\t", index=False)
    eregulons.sort_values(["TF", "Gene_signature_name", "Region_signature_name", "Gene", "Region"]).to_csv(args.validated_eregulons_output, sep="\t", index=False)
    reload_gene = pd.read_csv(args.gene_auc_output, sep="\t", index_col=0)
    reload_region = pd.read_csv(args.region_auc_output, sep="\t", index_col=0)
    reload_concordance = pd.read_csv(args.concordance_output, sep="\t")
    reload_eregulons = pd.read_csv(args.validated_eregulons_output, sep="\t")
    if reload_gene.shape != gene_auc.shape or reload_region.shape != region_auc.shape or len(reload_concordance) != len(concordance) or len(reload_eregulons) != len(eregulons) or list(reload_gene.index) != list(expression.index):
        raise RuntimeError("reloaded SCENIC+ outputs failed accounting")
    if {path.name: sha256(path) for path in inputs} != source_hashes:
        raise RuntimeError("a SCENIC+ input changed during scoring")

    packages = ("scenicplus", "pyscenic", "pycistopic", "numpy", "pandas", "scipy", "scikit-learn", "tables")
    versions = {name: importlib.metadata.version(name) for name in packages}
    versions["python"] = platform.python_version()
    report = {
        "schema_version": 1, "passed": True, "quality_status": "passed", "versions": versions,
        "input": {"cells": len(expression), "genes": expression.shape[1], "regions": accessibility.shape[1], "eregulon_rows": len(eregulons), "signature_pairs": len(pair_summary), "source_sha256": source_hashes},
        "parameters": {"auc_threshold": args.auc_threshold, "minimum_targets": args.minimum_targets},
        "results": {"gene_auc_shape": list(gene_auc.shape), "region_auc_shape": list(region_auc.shape), "concordance": concordance.to_dict(orient="records")},
        "scientific_checks": {"motif_and_region_gene_evidence_required": True, "paired_cells_preserved": True, "scenicplus_gene_auc_executed": True, "scenicplus_region_auc_executed": True, "gene_region_concordance_retained": True, "method_specific_evidence_preserved": True, "outputs_reloaded": True, "no_environment_or_compute_infrastructure_managed": True},
        "output_sha256": {path.name: sha256(path) for path in outputs[:-1]},
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "signature_pairs": len(pair_summary), "tool_version": versions["scenicplus"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
