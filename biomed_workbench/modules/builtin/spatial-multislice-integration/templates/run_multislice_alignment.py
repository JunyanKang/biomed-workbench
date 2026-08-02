#!/usr/bin/env python3
"""Align ordered spatial sections with PASTE/PASTE2 and emit 3D coordinates."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_section_contract(sections: list[str], spacings: list[float], inputs: list[Path], overlap: float, alpha: float) -> None:
    """Validate ordered sections, calibrated spacing and model parameters."""
    if len(sections) != len(inputs) or len(spacings) != len(sections) - 1:
        raise ValueError("section ids and inter-section spacing must match the ordered inputs")
    if len(set(sections)) != len(sections):
        raise ValueError("section identifiers must be unique and ordered")
    if any(x <= 0 or not np.isfinite(x) for x in spacings) or not 0 < overlap <= 1 or not 0 <= alpha <= 1:
        raise ValueError("invalid spacing, overlap or alpha")


def common_genes(slices: list[ad.AnnData]) -> list[str]:
    """Return genes shared across every section in stable first-section order."""
    shared = slices[0].var_names
    for value in slices[1:]:
        shared = shared.intersection(value.var_names)
    if len(shared) < 100:
        raise ValueError("fewer than 100 common genes")
    return list(shared)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("paste", "paste2"), required=True)
    parser.add_argument("--input-h5ad", type=Path, nargs="+", required=True)
    parser.add_argument("--section-ids", required=True)
    parser.add_argument("--section-spacing", required=True, help="Comma-separated z spacing after each section, in coordinate units.")
    parser.add_argument("--coordinate-unit", required=True)
    parser.add_argument("--spatial-key", default="spatial")
    parser.add_argument("--alpha", type=float, default=0.1)
    parser.add_argument("--overlap-fraction", type=float, default=1.0)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--coordinates-output", type=Path, required=True)
    parser.add_argument("--couplings-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output_directory.exists() or args.coordinates_output.exists() or args.couplings_output.exists() or args.report.exists():
        raise FileExistsError("refusing to overwrite output")
    sections = args.section_ids.split(",")
    spacings = [float(x) for x in args.section_spacing.split(",")]
    validate_section_contract(sections, spacings, args.input_h5ad, args.overlap_fraction, args.alpha)
    slices = [ad.read_h5ad(path) for path in args.input_h5ad]
    common = common_genes(slices)
    slices = [value[:, common].copy() for value in slices]
    for value in slices:
        if args.spatial_key not in value.obsm:
            raise ValueError("spatial coordinates are absent")
        value.obsm["spatial"] = np.asarray(value.obsm[args.spatial_key], dtype=float)
    couplings = []
    np.random.seed(args.seed)
    if args.backend == "paste":
        import paste as pst
        for left, right in zip(slices[:-1], slices[1:]):
            couplings.append(pst.pairwise_align(left, right, alpha=args.alpha, dissimilarity="kl", use_rep=None, norm=True, verbose=False))
        aligned = pst.stack_slices_pairwise(slices, couplings)
    else:
        import paste2 as pst2
        for left, right in zip(slices[:-1], slices[1:]):
            couplings.append(pst2.partial_pairwise_align(left, right, s=args.overlap_fraction, alpha=args.alpha, dissimilarity="kl"))
        import paste as pst
        aligned = pst.stack_slices_pairwise(slices, couplings)
    args.output_directory.mkdir(parents=True)
    args.coordinates_output.parent.mkdir(parents=True, exist_ok=True)
    args.couplings_output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    z = 0.0
    coordinate_rows = []
    coupling_rows = []
    for i, (section, value) in enumerate(zip(sections, aligned)):
        value.write_h5ad(args.output_directory / f"{i:03d}-{section}.h5ad")
        coords = np.asarray(value.obsm["spatial"], dtype=float)
        coordinate_rows.extend({"section_id": section, "observation_id": obs, "x": xy[0], "y": xy[1], "z": z, "coordinate_unit": args.coordinate_unit} for obs, xy in zip(value.obs_names.astype(str), coords))
        if i < len(spacings):
            z += spacings[i]
    for pair, coupling in enumerate(couplings):
        matrix = coupling.toarray() if hasattr(coupling, "toarray") else np.asarray(coupling)
        sources, targets = np.nonzero(matrix)
        coupling_rows.extend({"source_section": sections[pair], "target_section": sections[pair + 1], "source_index": int(s), "target_index": int(t), "weight": float(matrix[s, t])} for s, t in zip(sources, targets))
    coordinate_frame = pd.DataFrame(coordinate_rows)
    coupling_frame = pd.DataFrame(coupling_rows)
    coordinate_frame.to_csv(args.coordinates_output, sep="\t", index=False)
    coupling_frame.to_csv(args.couplings_output, sep="\t", index=False)
    reloaded_sections = [ad.read_h5ad(args.output_directory / f"{i:03d}-{section}.h5ad") for i, section in enumerate(sections)]
    reloaded_coordinates = pd.read_csv(args.coordinates_output, sep="\t")
    reloaded_couplings = pd.read_csv(args.couplings_output, sep="\t")
    if [item.n_obs for item in reloaded_sections] != [item.n_obs for item in aligned]:
        raise RuntimeError("aligned section outputs failed observation reconciliation")
    if len(reloaded_coordinates) != sum(item.n_obs for item in aligned) or not np.isfinite(reloaded_coordinates[["x", "y", "z"]].to_numpy()).all():
        raise RuntimeError("3D coordinate output failed reload reconciliation")
    if reloaded_couplings.empty or (reloaded_couplings["weight"] <= 0).any() or not np.isfinite(reloaded_couplings["weight"]).all():
        raise RuntimeError("pairwise coupling output failed reload validation")
    report = {
        "schema_version": 1,
        "passed": True,
        "backend": args.backend,
        "backend_version": importlib.metadata.version("paste-bio") if args.backend == "paste" else importlib.metadata.version("paste2"),
        "pot_version": importlib.metadata.version("POT"),
        "section_order": sections,
        "section_observations": [int(item.n_obs) for item in aligned],
        "inter_section_spacing": spacings,
        "coordinate_unit": args.coordinate_unit,
        "common_genes": len(common),
        "alpha": args.alpha,
        "overlap_fraction": args.overlap_fraction,
        "seed": args.seed,
        "coupling_nonzero_entries": int(len(reloaded_couplings)),
        "coupling_weight_sum": float(reloaded_couplings["weight"].sum()),
        "outputs": {
            "coordinates_sha256": digest(args.coordinates_output),
            "couplings_sha256": digest(args.couplings_output),
            "aligned_h5ad_sha256": {section: digest(args.output_directory / f"{i:03d}-{section}.h5ad") for i, section in enumerate(sections)},
        },
        "interpretation_scope": "The coupling is model-based spatial correspondence. Section order, physical spacing and partial-overlap assumptions remain explicit project inputs.",
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
