#!/usr/bin/env python3
"""Import major spatial platforms and emit a coordinate-aware QC evidence bundle.

Official SpatialData-IO readers are used for vendor outputs.  Slide-seq and
generic matrices enter through an AnnData object with an explicit coordinate
key because no vendor directory contract is universal for those assays.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import inspect
import json
import math
import platform as py_platform
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


PLATFORMS = ("visium", "visium-hd", "stereoseq", "slide-seq", "xenium", "cosmx", "merfish", "generic")
IMAGING_PLATFORMS = {"xenium", "cosmx", "merfish"}
READER_NAMES = {
    "visium": "visium",
    "visium-hd": "visium_hd",
    "stereoseq": "stereoseq",
    "xenium": "xenium",
    "cosmx": "cosmx",
    "merfish": "merscope",
}


def digest_path(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
    else:
        for item in sorted(p for p in path.rglob("*") if p.is_file()):
            digest.update(item.relative_to(path).as_posix().encode())
            digest.update(b"\0")
            digest.update(item.read_bytes())
    return digest.hexdigest()


def matrix_values(matrix):
    return matrix.data if sparse.issparse(matrix) else np.asarray(matrix).ravel()


def validate_counts(adata: ad.AnnData) -> None:
    values = matrix_values(adata.X)
    if adata.n_obs == 0 or adata.n_vars == 0:
        raise ValueError("expression table is empty")
    if adata.obs_names.has_duplicates or adata.var_names.has_duplicates:
        raise ValueError("observation and feature identifiers must be unique")
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("counts must be finite and nonnegative")
    feature_types = adata.var["feature_types"].astype(str) if "feature_types" in adata.var else None
    count_mask = np.ones(adata.n_vars, dtype=bool) if feature_types is None else ~feature_types.eq("Protein Expression").to_numpy()
    count_values = matrix_values(adata[:, count_mask].X)
    if count_values.size and not np.allclose(count_values, np.rint(count_values), atol=1e-8):
        raise ValueError("transcript and control count features must be integer-valued")


def pick_table(sdata, table_name: str | None) -> tuple[str, ad.AnnData]:
    names = list(sdata.tables)
    if not names:
        raise ValueError("SpatialData object contains no expression table")
    selected = table_name or (names[0] if len(names) == 1 else None)
    if selected is None or selected not in sdata.tables:
        raise ValueError(f"declare --table-name from available tables: {names}")
    return selected, sdata.tables[selected].copy()


def spatial_elements(sdata) -> dict[str, list[str]]:
    return {
        "images": sorted(sdata.images),
        "labels": sorted(sdata.labels),
        "points": sorted(sdata.points),
        "shapes": sorted(sdata.shapes),
        "tables": sorted(sdata.tables),
    }


def load_input(args) -> tuple[ad.AnnData, object | None, dict[str, object]]:
    if args.input_h5ad:
        return ad.read_h5ad(args.input_h5ad), None, {"reader": "anndata.read_h5ad", "table": None}
    if args.platform in {"slide-seq", "generic"}:
        raise ValueError(f"{args.platform} requires --input-h5ad with explicit spatial coordinates")
    import spatialdata_io as sdio

    reader_name = READER_NAMES[args.platform]
    reader = getattr(sdio, reader_name)
    supplied = {
        "dataset_id": args.dataset_id,
        "binsize": args.bin_size,
        "load_images": args.load_images,
        "gex_only": args.gene_expression_only,
        "cells_as_circles": False,
    }
    signature = inspect.signature(reader)
    kwargs = {key: value for key, value in supplied.items() if value is not None and key in signature.parameters}
    sdata = reader(args.input_path, **kwargs)
    table_name, adata = pick_table(sdata, args.table_name)
    elements = {
        "images": sorted(sdata.images),
        "labels": sorted(sdata.labels),
        "points": sorted(sdata.points),
        "shapes": sorted(sdata.shapes),
        "tables": sorted(sdata.tables),
    }
    return adata, sdata, {"reader": f"spatialdata_io.{reader_name}", "reader_arguments": kwargs, "table": table_name, "elements": elements}


def coordinates_from(adata: ad.AnnData, key: str, sdata, provenance: dict[str, object]) -> np.ndarray:
    if key in adata.obsm:
        coords = np.asarray(adata.obsm[key], dtype=float)
        provenance["coordinate_source"] = f"table.obsm[{key!r}]"
    elif sdata is not None and "cell_boundaries" in sdata.shapes:
        boundaries = sdata.shapes["cell_boundaries"]
        observation_ids = adata.obs["cell_id"].astype(str) if "cell_id" in adata.obs else adata.obs_names.astype(str)
        matched = boundaries.reindex(observation_ids)
        if matched.geometry.isna().any():
            raise ValueError("cell-boundary identifiers do not reconcile with the expression table")
        coords = np.column_stack((matched.geometry.centroid.x, matched.geometry.centroid.y))
        provenance["coordinate_source"] = "cell_boundaries.geometry.centroid"
    else:
        raise ValueError(f"coordinate matrix is absent from obsm['{key}'] and no matched cell boundaries are available")
    if coords.ndim != 2 or coords.shape[0] != adata.n_obs or coords.shape[1] not in (2, 3):
        raise ValueError("coordinates must be observations by 2 or 3")
    if not np.isfinite(coords).all():
        raise ValueError("coordinates contain nonfinite values")
    return coords


def qc_tables(adata: ad.AnnData, coords: np.ndarray, args) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    feature_types = adata.var["feature_types"].astype(str) if "feature_types" in adata.var else None
    transcript_mask = np.ones(adata.n_vars, dtype=bool) if feature_types is None else ~feature_types.eq("Protein Expression").to_numpy()
    transcript_matrix = adata[:, transcript_mask].X
    totals = np.asarray(transcript_matrix.sum(axis=1)).ravel()
    detected = np.asarray((transcript_matrix > 0).sum(axis=1)).ravel()
    observation = pd.DataFrame({
        "observation_id": adata.obs_names.astype(str),
        "sample_id": adata.obs[args.sample_key].astype(str).to_numpy(),
        "total_counts": totals,
        "detected_features": detected,
        "x": coords[:, 0],
        "y": coords[:, 1],
    })
    if coords.shape[1] == 3:
        observation["z"] = coords[:, 2]
    control_cols = [c for c in adata.var.columns if str(c).lower() in {"negative_control", "is_negative_control", "control_type", "feature_type", "feature_types"}]
    negative_mask = np.zeros(adata.n_vars, dtype=bool)
    for column in control_cols:
        values = adata.var[column]
        if values.dtype == bool:
            negative_mask |= values.to_numpy()
        else:
            negative_mask |= values.astype(str).str.lower().str.contains("negative").to_numpy()
    if negative_mask.any():
        neg = np.asarray(adata[:, negative_mask].X.sum(axis=1)).ravel()
        observation["negative_control_counts"] = neg
        observation["negative_control_fraction"] = np.divide(neg, totals, out=np.zeros_like(neg, dtype=float), where=totals > 0)
    if feature_types is not None and feature_types.eq("Protein Expression").any():
        observation["protein_signal"] = np.asarray(adata[:, feature_types.eq("Protein Expression")].X.sum(axis=1)).ravel()
    for candidate in ("in_tissue", "cell_area", "nucleus_area", "transcript_count", "unassigned_transcript_fraction"):
        if candidate in adata.obs:
            observation[candidate] = adata.obs[candidate].to_numpy()
    samples = []
    for sample_id, part in observation.groupby("sample_id", sort=True):
        span_x = float(part["x"].max() - part["x"].min())
        span_y = float(part["y"].max() - part["y"].min())
        row = {
            "sample_id": sample_id,
            "observations": int(len(part)),
            "median_total_counts": float(part["total_counts"].median()),
            "median_detected_features": float(part["detected_features"].median()),
            "zero_count_fraction": float((part["total_counts"] == 0).mean()),
            "coordinate_span_x": span_x,
            "coordinate_span_y": span_y,
            "coordinate_unit": args.coordinate_unit,
        }
        for metric in ("negative_control_fraction", "unassigned_transcript_fraction", "cell_area", "nucleus_area"):
            if metric in part:
                row[f"median_{metric}"] = float(pd.to_numeric(part[metric], errors="coerce").median())
        samples.append(row)
    sample = pd.DataFrame(samples)
    failures = []
    if (sample["observations"] < args.minimum_observations).any():
        failures.append("minimum-observations")
    if (sample["zero_count_fraction"] > args.maximum_zero_fraction).any():
        failures.append("zero-count-fraction")
    if (sample[["coordinate_span_x", "coordinate_span_y"]] <= 0).any().any():
        failures.append("coordinate-span")
    if args.platform in IMAGING_PLATFORMS and "negative_control_fraction" not in observation:
        failures.append("negative-control-annotation-unavailable")
    summary = {
        "platform": args.platform,
        "assay_geometry": "cell-resolved-imaging" if args.platform in IMAGING_PLATFORMS else "spot-or-bead",
        "coordinate_key": args.spatial_key,
        "coordinate_unit": args.coordinate_unit,
        "observations": adata.n_obs,
        "features": adata.n_vars,
        "feature_types": feature_types.value_counts().sort_index().astype(int).to_dict() if feature_types is not None else {"unspecified-count-feature": int(adata.n_vars)},
        "samples": int(observation["sample_id"].nunique()),
        "quality_gate_failures": failures,
        "interpretation_ready": not [x for x in failures if x != "negative-control-annotation-unavailable"],
    }
    return observation, sample, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=PLATFORMS, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-path", type=Path)
    source.add_argument("--input-h5ad", type=Path)
    parser.add_argument("--table-name")
    parser.add_argument("--dataset-id")
    parser.add_argument("--bin-size", type=int)
    parser.add_argument("--load-images", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--gene-expression-only", action=argparse.BooleanOptionalAction, default=False, help="Exclude control and non-gene features when the vendor reader supports this option.")
    parser.add_argument("--sample-key", required=True)
    parser.add_argument("--sample-id", help="Explicit biological sample identifier for a single vendor directory.")
    parser.add_argument("--spatial-key", default="spatial")
    parser.add_argument("--coordinate-unit", required=True)
    parser.add_argument("--minimum-observations", type=int, default=20)
    parser.add_argument("--maximum-zero-fraction", type=float, default=0.2)
    parser.add_argument("--output-h5ad", type=Path, required=True)
    parser.add_argument("--output-zarr", type=Path)
    parser.add_argument("--observation-qc", type=Path, required=True)
    parser.add_argument("--sample-qc", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.coordinate_unit.strip() or args.minimum_observations < 1 or not 0 <= args.maximum_zero_fraction < 1:
        raise ValueError("invalid coordinate or QC thresholds")
    outputs = [args.output_h5ad, args.observation_qc, args.sample_qc, args.report] + ([args.output_zarr] if args.output_zarr else [])
    if any(path.exists() for path in outputs):
        raise FileExistsError("refusing to overwrite an existing output")
    source_path = args.input_h5ad or args.input_path
    adata, sdata, provenance = load_input(args)
    validate_counts(adata)
    if args.sample_key not in adata.obs and args.sample_id:
        adata.obs[args.sample_key] = pd.Categorical([args.sample_id] * adata.n_obs)
    if args.sample_key not in adata.obs or adata.obs[args.sample_key].isna().any():
        raise ValueError("complete biological sample identity is required")
    coords = coordinates_from(adata, args.spatial_key, sdata, provenance)
    adata.obsm[args.spatial_key] = coords
    observation, sample, summary = qc_tables(adata, coords, args)
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output_h5ad)
    if args.output_zarr:
        if sdata is None:
            raise ValueError("--output-zarr requires a vendor SpatialData-IO input")
        table_name = provenance.get("table")
        if not isinstance(table_name, str):
            raise ValueError("vendor SpatialData output has no selected table identity")
        sdata.tables[table_name] = adata
        sdata.write(args.output_zarr)
    observation.to_csv(args.observation_qc, sep="\t", index=False)
    sample.to_csv(args.sample_qc, sep="\t", index=False)
    reloaded = ad.read_h5ad(args.output_h5ad)
    if reloaded.shape != adata.shape or not args.observation_qc.stat().st_size or not args.sample_qc.stat().st_size:
        raise RuntimeError("output reload reconciliation failed")
    spatialdata_reload = None
    if args.output_zarr:
        from spatialdata import read_zarr

        spatialdata_reload = read_zarr(args.output_zarr)
        if provenance.get("table") not in spatialdata_reload.tables or spatial_elements(spatialdata_reload) != spatial_elements(sdata):
            raise RuntimeError("SpatialData output failed element-inventory reload validation")
    report = {
        "schema_version": 1,
        "passed": True,
        "module": "spatial-platform-image-foundation",
        "source": str(source_path.resolve()),
        "source_sha256": digest_path(source_path),
        "reader": provenance,
        "summary": summary,
        "parameters": {
            "platform": args.platform, "sample_key": args.sample_key, "sample_id": args.sample_id, "spatial_key": args.spatial_key,
            "gene_expression_only": args.gene_expression_only,
            "coordinate_unit": args.coordinate_unit, "minimum_observations": args.minimum_observations,
            "maximum_zero_fraction": args.maximum_zero_fraction,
        },
        "runtime": {
            "python": py_platform.python_version(),
            "anndata": importlib.metadata.version("anndata"),
            "spatialdata_io": importlib.metadata.version("spatialdata-io") if sdata is not None else None,
            "spatialdata": importlib.metadata.version("spatialdata") if sdata is not None else None,
        },
        "outputs": {
            "h5ad_sha256": digest_path(args.output_h5ad),
            "observation_qc_sha256": digest_path(args.observation_qc),
            "sample_qc_sha256": digest_path(args.sample_qc),
            "spatialdata_zarr_sha256": digest_path(args.output_zarr) if args.output_zarr else None,
            "spatialdata_reloaded": spatialdata_reload is not None,
        },
        "limitations": [
            "QC thresholds are review gates, not universal biological cutoffs.",
            "Absence of vendor negative-control annotations is reported and never imputed.",
            "Slide-seq requires a prepared AnnData object because bead-location file contracts vary by processing pipeline.",
        ],
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
