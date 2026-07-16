#!/usr/bin/env python3
"""Run sample-aware Squidpy spatial statistics and joint spatial-domain discovery."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse
import squidpy as sq
from spatialdata import read_zarr


def digest_path(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    if not path.is_dir():
        raise FileNotFoundError(path)
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
    return digest.hexdigest()


def matrix_digest(matrix) -> str:
    digest = hashlib.sha256()
    if sparse.issparse(matrix):
        value = matrix.tocsr()
        digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(value.data.tobytes())
        digest.update(value.indices.tobytes())
        digest.update(value.indptr.tobytes())
    else:
        value = np.ascontiguousarray(np.asarray(matrix))
        digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(value.tobytes())
    return digest.hexdigest()


def validate_count_matrix(matrix) -> None:
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).ravel()
    if values.size == 0 or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("spatial expression counts must be nonempty, finite, and nonnegative")
    if not np.allclose(values, np.rint(values), atol=1e-8):
        raise ValueError("spatial expression source must be integer-like raw counts")


def load_input(input_h5ad: Path | None, input_spatialdata: Path | None, table_name: str | None):
    if (input_h5ad is None) == (input_spatialdata is None):
        raise ValueError("declare exactly one h5ad or SpatialData Zarr input")
    if input_h5ad is not None:
        if not input_h5ad.is_file():
            raise FileNotFoundError(input_h5ad)
        return ad.read_h5ad(input_h5ad), "h5ad", {"images": [], "labels": [], "points": [], "shapes": [], "tables": []}, input_h5ad
    if not input_spatialdata.is_dir():
        raise FileNotFoundError(input_spatialdata)
    if not table_name:
        raise ValueError("SpatialData input requires --table-name")
    spatial = read_zarr(input_spatialdata)
    if table_name not in spatial.tables:
        raise ValueError(f"SpatialData table is absent: {table_name}")
    elements = {
        "images": sorted(spatial.images), "labels": sorted(spatial.labels), "points": sorted(spatial.points),
        "shapes": sorted(spatial.shapes), "tables": sorted(spatial.tables),
    }
    return spatial.tables[table_name].copy(), "spatialdata-zarr", elements, input_spatialdata


def graph_edges(adata: ad.AnnData, sample_key: str) -> pd.DataFrame:
    connectivity = adata.obsp["spatial_connectivities"].tocsr()
    distances = adata.obsp["spatial_distances"].tocsr()
    rows = []
    for source in range(adata.n_obs):
        start, end = connectivity.indptr[source], connectivity.indptr[source + 1]
        for position in range(start, end):
            target = int(connectivity.indices[position])
            if source >= target:
                continue
            source_sample = str(adata.obs.iloc[source][sample_key])
            target_sample = str(adata.obs.iloc[target][sample_key])
            if source_sample != target_sample:
                raise RuntimeError("spatial graph contains a cross-sample edge")
            rows.append({
                "source": str(adata.obs_names[source]), "target": str(adata.obs_names[target]),
                "sample": source_sample, "connectivity": float(connectivity.data[position]),
                "distance": float(distances[source, target]),
            })
    if not rows:
        raise RuntimeError("spatial graph has no undirected edges")
    return pd.DataFrame(rows)


def neighborhood_table(result, categories: list[str]) -> pd.DataFrame:
    rows = []
    for i, source in enumerate(categories):
        for j, target in enumerate(categories):
            rows.append({"source_cluster": source, "target_cluster": target, "count": int(result.counts[i, j]), "zscore": float(result.zscore[i, j])})
    return pd.DataFrame(rows)


def cooccurrence_table(adata: ad.AnnData, sample_key: str, cluster_key: str, spatial_key: str, intervals: int) -> pd.DataFrame:
    rows = []
    categories = [str(item) for item in adata.obs[cluster_key].cat.categories]
    for sample in adata.obs[sample_key].cat.categories:
        subset = adata[adata.obs[sample_key] == sample].copy()
        subset.obs[cluster_key] = subset.obs[cluster_key].cat.remove_unused_categories()
        present = [str(item) for item in subset.obs[cluster_key].cat.categories]
        occurrence, bounds = sq.gr.co_occurrence(subset, cluster_key=cluster_key, spatial_key=spatial_key, interval=intervals, copy=True, n_jobs=1, show_progress_bar=False)
        if occurrence.shape != (len(present), len(present), len(bounds) - 1):
            raise RuntimeError("Squidpy co-occurrence output has unexpected dimensions")
        for i, source in enumerate(present):
            for j, target in enumerate(present):
                for interval_index in range(len(bounds) - 1):
                    rows.append({
                        "sample": str(sample), "source_cluster": source, "target_cluster": target,
                        "distance_lower": float(bounds[interval_index]), "distance_upper": float(bounds[interval_index + 1]),
                        "cooccurrence": float(occurrence[i, j, interval_index]),
                    })
    if not rows or not set(categories).issubset({row["source_cluster"] for row in rows}):
        raise RuntimeError("sample-aware co-occurrence omitted a declared cluster")
    return pd.DataFrame(rows)


def spatial_domains(adata: ad.AnnData, sample_key: str, spatial_key: str, *, hvgs: int, pcs: int, neighbors: int, resolution: float, coordinate_weight: float, seed: int) -> dict[str, object]:
    working = adata.copy()
    working.X = working.layers["counts"].copy()
    working.uns.pop("log1p", None)
    sc.pp.normalize_total(working, target_sum=1e4)
    sc.pp.log1p(working)
    sc.pp.highly_variable_genes(working, n_top_genes=min(hvgs, working.n_vars), flavor="seurat")
    selected = int(working.var["highly_variable"].sum())
    if selected < 10:
        raise RuntimeError("fewer than ten variable genes are available for spatial domains")
    model = working[:, working.var["highly_variable"]].copy()
    sc.pp.scale(model, zero_center=True, max_value=10)
    sc.tl.pca(model, n_comps=min(pcs, selected - 1, model.n_obs - 1), random_state=seed)
    coordinates = np.asarray(working.obsm[spatial_key], dtype=float)
    standardized = np.zeros_like(coordinates)
    for sample in working.obs[sample_key].cat.categories:
        mask = np.asarray(working.obs[sample_key] == sample)
        center = coordinates[mask].mean(axis=0)
        scale = coordinates[mask].std(axis=0)
        if (scale <= 0).any():
            raise ValueError(f"sample {sample} has a constant spatial coordinate axis")
        standardized[mask] = (coordinates[mask] - center) / scale
    joint = np.hstack([np.asarray(model.obsm["X_pca"], dtype=float), standardized * coordinate_weight])
    if not np.isfinite(joint).all():
        raise RuntimeError("joint expression-spatial representation is nonfinite")
    working.obsm["X_spatial_domain"] = joint
    sc.pp.neighbors(working, n_neighbors=min(neighbors, working.n_obs - 1), use_rep="X_spatial_domain", random_state=seed, key_added="spatial_domain")
    sc.tl.leiden(working, adjacency=working.obsp["spatial_domain_connectivities"], resolution=resolution, key_added="spatial_domain", random_state=seed, flavor="igraph", n_iterations=2, directed=False)
    if working.obs["spatial_domain"].isna().any() or working.obs["spatial_domain"].nunique() < 2:
        raise RuntimeError("joint expression-spatial Leiden did not produce reviewable domains")
    adata.obsm["X_spatial_domain"] = working.obsm["X_spatial_domain"].copy()
    adata.obsp["spatial_domain_connectivities"] = working.obsp["spatial_domain_connectivities"].copy()
    adata.obsp["spatial_domain_distances"] = working.obsp["spatial_domain_distances"].copy()
    adata.obs["spatial_domain"] = working.obs["spatial_domain"].copy()
    adata.uns["spatial_domain"] = dict(working.uns["spatial_domain"])
    return {"highly_variable_genes": selected, "principal_components": model.obsm["X_pca"].shape[1], "domains": int(working.obs["spatial_domain"].nunique())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input-h5ad", type=Path)
    inputs.add_argument("--input-spatialdata-zarr", type=Path)
    parser.add_argument("--table-name")
    parser.add_argument("--output-h5ad", type=Path, required=True)
    parser.add_argument("--observation-output", type=Path, required=True)
    parser.add_argument("--graph-output", type=Path, required=True)
    parser.add_argument("--neighborhood-output", type=Path, required=True)
    parser.add_argument("--cooccurrence-output", type=Path, required=True)
    parser.add_argument("--moran-output", type=Path, required=True)
    parser.add_argument("--spatial-genes-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--cluster-key", required=True)
    parser.add_argument("--spatial-key", default="spatial")
    parser.add_argument("--coordinate-unit", required=True)
    parser.add_argument("--genes", required=True, help="Comma-separated genes for spatial autocorrelation.")
    parser.add_argument("--n-spatial-neighbors", type=int, default=6)
    parser.add_argument("--radius", type=float)
    parser.add_argument("--delaunay", action="store_true")
    parser.add_argument("--permutations", type=int, default=1000)
    parser.add_argument("--cooccurrence-intervals", type=int, default=25)
    parser.add_argument("--svg-fdr", type=float, default=0.05)
    parser.add_argument("--minimum-moran", type=float, default=0.1)
    parser.add_argument("--minimum-supporting-samples", type=int, default=2)
    parser.add_argument("--domain-hvgs", type=int, default=2000)
    parser.add_argument("--domain-pcs", type=int, default=30)
    parser.add_argument("--domain-neighbors", type=int, default=15)
    parser.add_argument("--domain-resolution", type=float, required=True)
    parser.add_argument("--coordinate-weight", type=float, default=2.0)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()

    outputs = (args.output_h5ad, args.observation_output, args.graph_output, args.neighborhood_output, args.cooccurrence_output, args.moran_output, args.spatial_genes_output, args.report)
    if any(path.exists() for path in outputs):
        raise FileExistsError([str(path) for path in outputs if path.exists()])
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    if args.n_spatial_neighbors < 2 or args.permutations < 99 or args.cooccurrence_intervals < 3 or not 0 < args.svg_fdr < 1 or not -1 <= args.minimum_moran <= 1 or args.minimum_supporting_samples < 1 or args.domain_hvgs < 10 or args.domain_pcs < 2 or args.domain_neighbors < 2 or args.domain_resolution <= 0 or args.coordinate_weight < 0 or not args.coordinate_unit.strip():
        raise ValueError("invalid spatial graph, permutation, SVG, domain, or coordinate parameters")
    if args.radius is not None and (not math.isfinite(args.radius) or args.radius <= 0):
        raise ValueError("radius must be a finite positive distance in the declared coordinate unit")

    adata, input_kind, spatial_elements, source_path = load_input(args.input_h5ad, args.input_spatialdata_zarr, args.table_name)
    source_digest = digest_path(source_path)
    if adata.n_obs < 40 or adata.n_vars < 20 or adata.obs_names.has_duplicates or adata.var_names.has_duplicates:
        raise ValueError("spatial input requires at least 40 unique observations and 20 unique genes")
    validate_count_matrix(adata.X)
    source_count_digest = matrix_digest(adata.X)
    source_cells = list(adata.obs_names)
    source_genes = list(adata.var_names)
    for key in (args.sample_key, args.cluster_key):
        if key not in adata.obs or adata.obs[key].isna().any():
            raise ValueError(f"complete observation metadata is required: {key}")
        adata.obs[key] = adata.obs[key].astype(str).astype("category")
    if args.spatial_key not in adata.obsm:
        raise ValueError(f"spatial coordinates are absent from obsm: {args.spatial_key}")
    coordinates = np.asarray(adata.obsm[args.spatial_key], dtype=float)
    if coordinates.shape != (adata.n_obs, 2) or not np.isfinite(coordinates).all():
        raise ValueError("spatial coordinates must be a finite observations-by-two matrix")
    sample_sizes = adata.obs[args.sample_key].value_counts().sort_index()
    if (sample_sizes < 20).any():
        raise ValueError("every spatial biological sample requires at least 20 observations")
    if args.minimum_supporting_samples > len(sample_sizes):
        raise ValueError("minimum supporting samples exceeds available biological samples")
    genes = [item.strip() for item in args.genes.split(",") if item.strip()]
    if len(genes) != len(set(genes)) or not genes or not set(genes).issubset(adata.var_names):
        raise ValueError("spatial autocorrelation genes must be unique, nonempty, and present")

    adata.layers["counts"] = adata.X.copy()
    sq.gr.spatial_neighbors(adata, spatial_key=args.spatial_key, library_key=args.sample_key, coord_type="generic", n_neighs=args.n_spatial_neighbors, radius=args.radius, delaunay=args.delaunay, key_added="spatial")
    edges = graph_edges(adata, args.sample_key)
    neighborhood = sq.gr.nhood_enrichment(adata, cluster_key=args.cluster_key, library_key=args.sample_key, connectivity_key=None, n_perms=args.permutations, seed=args.seed, copy=True, n_jobs=1, show_progress_bar=False)
    neighborhood_frame = neighborhood_table(neighborhood, [str(item) for item in adata.obs[args.cluster_key].cat.categories])
    cooccurrence_frame = cooccurrence_table(adata, args.sample_key, args.cluster_key, args.spatial_key, args.cooccurrence_intervals)

    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    moran = sq.gr.spatial_autocorr(adata, connectivity_key="spatial_connectivities", genes=genes, mode="moran", n_perms=args.permutations, corr_method="fdr_bh", seed=args.seed, copy=True, n_jobs=1, show_progress_bar=False)
    if moran is None or moran.empty or "I" not in moran.columns or not np.isfinite(moran["I"]).all():
        raise RuntimeError("Moran's I output is empty or nonfinite")
    q_columns = [column for column in moran.columns if "pval" in column and column.endswith("_fdr_bh")]
    if not q_columns:
        raise RuntimeError("Moran's I output lacks multiplicity-adjusted p values")
    q_column = "pval_sim_fdr_bh" if "pval_sim_fdr_bh" in q_columns else q_columns[0]
    moran.index.name = "gene"
    global_moran = moran.reset_index()
    global_moran.insert(0, "sample", "all")
    global_moran.insert(0, "scope", "global")
    sample_moran_frames = []
    for sample_index, sample in enumerate(adata.obs[args.sample_key].cat.categories):
        subset = adata[adata.obs[args.sample_key] == sample].copy()
        sample_moran = sq.gr.spatial_autocorr(subset, connectivity_key="spatial_connectivities", genes=genes, mode="moran", n_perms=args.permutations, corr_method="fdr_bh", seed=args.seed + sample_index + 1, copy=True, n_jobs=1, show_progress_bar=False)
        if sample_moran is None or sample_moran.empty or not np.isfinite(sample_moran["I"]).all():
            raise RuntimeError(f"sample-level Moran's I failed: {sample}")
        sample_moran.index.name = "gene"
        frame = sample_moran.reset_index()
        frame.insert(0, "sample", str(sample))
        frame.insert(0, "scope", "sample")
        sample_moran_frames.append(frame)
    sample_moran_frame = pd.concat(sample_moran_frames, ignore_index=True)
    support = sample_moran_frame.assign(supported=sample_moran_frame["I"] >= args.minimum_moran).groupby("gene")["supported"].sum().astype(int)
    global_moran["supporting_samples"] = global_moran["gene"].map(support).astype(int)
    global_moran["admitted_spatial_gene"] = (global_moran["I"] >= args.minimum_moran) & (global_moran[q_column] <= args.svg_fdr) & (global_moran["supporting_samples"] >= args.minimum_supporting_samples)
    sample_moran_frame["supporting_samples"] = sample_moran_frame["gene"].map(support).astype(int)
    sample_moran_frame["admitted_spatial_gene"] = sample_moran_frame["gene"].isin(global_moran.loc[global_moran["admitted_spatial_gene"], "gene"])
    moran_frame = pd.concat([global_moran, sample_moran_frame], ignore_index=True, sort=False)
    spatial_gene_frame = global_moran.loc[global_moran["admitted_spatial_gene"]].copy()

    domain_summary = spatial_domains(adata, args.sample_key, args.spatial_key, hvgs=args.domain_hvgs, pcs=args.domain_pcs, neighbors=args.domain_neighbors, resolution=args.domain_resolution, coordinate_weight=args.coordinate_weight, seed=args.seed)
    adata.uns["spatial_analysis_contract"] = {
        "coordinate_unit": args.coordinate_unit, "sample_key": args.sample_key, "cluster_key": args.cluster_key,
        "spatial_key": args.spatial_key, "source_digest": source_digest, "source_count_digest": source_count_digest,
        "input_kind": input_kind, "spatial_elements": spatial_elements,
    }

    observation = adata.obs[[args.sample_key, args.cluster_key, "spatial_domain"]].copy()
    observation.insert(0, "cell_id", adata.obs_names)
    observation["spatial_x"] = coordinates[:, 0]
    observation["spatial_y"] = coordinates[:, 1]
    edges.to_csv(args.graph_output, sep="\t", index=False)
    neighborhood_frame.to_csv(args.neighborhood_output, sep="\t", index=False)
    cooccurrence_frame.to_csv(args.cooccurrence_output, sep="\t", index=False)
    moran_frame.to_csv(args.moran_output, sep="\t", index=False)
    spatial_gene_frame.to_csv(args.spatial_genes_output, sep="\t", index=False)
    observation.to_csv(args.observation_output, sep="\t", index=False)
    adata.write_h5ad(args.output_h5ad, compression="gzip")

    reloaded = ad.read_h5ad(args.output_h5ad)
    reload_observation = pd.read_csv(args.observation_output, sep="\t")
    reload_edges = pd.read_csv(args.graph_output, sep="\t")
    reload_neighborhood = pd.read_csv(args.neighborhood_output, sep="\t")
    reload_cooccurrence = pd.read_csv(args.cooccurrence_output, sep="\t")
    reload_moran = pd.read_csv(args.moran_output, sep="\t")
    if list(reloaded.obs_names) != source_cells or list(reloaded.var_names) != source_genes or matrix_digest(reloaded.layers["counts"]) != source_count_digest:
        raise RuntimeError("reloaded spatial object changed source cells, genes, or counts")
    if len(reload_observation) != adata.n_obs or len(reload_edges) != len(edges) or len(reload_neighborhood) != len(neighborhood_frame) or len(reload_cooccurrence) != len(cooccurrence_frame) or len(reload_moran) != len(moran_frame):
        raise RuntimeError("reloaded spatial tables failed accounting")
    if digest_path(source_path) != source_digest:
        raise RuntimeError("spatial source changed during analysis")

    package_names = ("squidpy", "spatialdata", "scanpy", "anndata", "numpy", "pandas", "scipy", "scikit-learn", "igraph", "zarr")
    versions = {name: importlib.metadata.version(name) for name in package_names}
    versions["python"] = platform.python_version()
    report = {
        "schema_version": 1, "passed": True, "quality_status": "passed", "versions": versions,
        "input": {"kind": input_kind, "observations": adata.n_obs, "genes": adata.n_vars, "samples": int(adata.obs[args.sample_key].nunique()), "sample_sizes": {str(key): int(value) for key, value in sample_sizes.items()}, "clusters": int(adata.obs[args.cluster_key].nunique()), "coordinate_unit": args.coordinate_unit, "source_digest": source_digest, "source_count_digest": source_count_digest, "spatial_elements": spatial_elements},
        "parameters": {"n_spatial_neighbors": args.n_spatial_neighbors, "radius": args.radius, "delaunay": args.delaunay, "permutations": args.permutations, "cooccurrence_intervals": args.cooccurrence_intervals, "svg_fdr": args.svg_fdr, "minimum_moran": args.minimum_moran, "minimum_supporting_samples": args.minimum_supporting_samples, "domain_hvgs": args.domain_hvgs, "domain_pcs": args.domain_pcs, "domain_neighbors": args.domain_neighbors, "domain_resolution": args.domain_resolution, "coordinate_weight": args.coordinate_weight, "seed": args.seed},
        "results": {"spatial_edges": len(edges), "cross_sample_edges": 0, "neighborhood_rows": len(neighborhood_frame), "cooccurrence_rows": len(cooccurrence_frame), "moran_genes": len(global_moran), "moran_rows": len(moran_frame), "admitted_spatial_genes": spatial_gene_frame["gene"].tolist(), "spatial_gene_support": {str(row.gene): int(row.supporting_samples) for row in spatial_gene_frame.itertuples(index=False)}, "moran_q_column": q_column, **domain_summary},
        "scientific_checks": {"h5ad_or_spatialdata_input_validated": True, "coordinate_units_declared": True, "spatialdata_elements_recorded": True, "sample_isolated_spatial_graph": True, "neighborhood_enrichment_executed": True, "sample_aware_cooccurrence_executed": True, "moran_permutation_test_executed": True, "spatial_gene_multiplicity_control_applied": True, "spatial_gene_sample_replication_required": True, "joint_expression_spatial_domains_executed": True, "raw_counts_cells_genes_and_coordinates_preserved": True, "outputs_reloaded": True, "spots_not_used_as_condition_replicates": True, "no_environment_or_compute_infrastructure_managed": True},
        "output_sha256": {path.name: digest_path(path) for path in outputs[:-1]},
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "spatial_genes": len(spatial_gene_frame), "domains": domain_summary["domains"], "tool_version": versions["squidpy"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
