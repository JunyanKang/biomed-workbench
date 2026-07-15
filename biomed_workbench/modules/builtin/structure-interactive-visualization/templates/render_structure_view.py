#!/usr/bin/env python3
"""Render a selected coordinate model as provenance-bound py3Dmol HTML."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

import py3Dmol
from Bio.PDB import MMCIFIO, MMCIFParser, PDBIO, PDBParser, Select


MODULE_ID = "structure-interactive-visualization"
MODULE_VERSION = "1.0.0"
CHAIN_COLORS = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000")


class ChainSelect(Select):
    def __init__(self, chain_ids: list[str]):
        self.chain_ids = frozenset(chain_ids)

    def accept_chain(self, chain) -> bool:
        return chain.id in self.chain_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--format", required=True, choices=("pdb", "mmcif"))
    parser.add_argument("--model-index", required=True, type=int)
    parser.add_argument("--chains", required=True, help="Comma-separated chain identifiers")
    parser.add_argument("--style", required=True, choices=("cartoon", "stick", "sphere", "line"))
    parser.add_argument("--color-semantics", required=True, choices=("chain", "alphafold-plddt", "uniform"))
    parser.add_argument("--confidence-provenance", required=True, choices=("alphafold-b-column-plddt", "not-applicable", "unknown"))
    parser.add_argument("--html-output", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--width", type=int, default=1000)
    parser.add_argument("--height", type=int, default=720)
    return parser.parse_args()


def stable_input(path: Path) -> tuple[Path, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("coordinate input must be a stable regular file")
    content = path.read_bytes()
    if not content:
        raise ValueError("coordinate input is empty")
    return path.resolve(), hashlib.sha256(content).hexdigest()


def load_scope(path: Path, structure_format: str, model_index: int, requested_chains: list[str]):
    parser = PDBParser(QUIET=True) if structure_format == "pdb" else MMCIFParser(QUIET=True)
    try:
        structure = parser.get_structure("input", str(path))
    except Exception as exc:
        raise ValueError(f"unable to parse declared {structure_format} coordinate input") from exc
    models = list(structure.get_models())
    if model_index < 0 or model_index >= len(models):
        raise ValueError(f"model index {model_index} is absent from {len(models)} observed models")
    if not requested_chains or len(requested_chains) != len(set(requested_chains)):
        raise ValueError("one or more unique chain identifiers are required")
    model = models[model_index]
    observed_chains = {chain.id for chain in model}
    missing = sorted(set(requested_chains) - observed_chains)
    if missing:
        raise ValueError(f"requested chains are absent: {', '.join(missing)}")
    atom_count = sum(1 for chain in model if chain.id in requested_chains for _atom in chain.get_atoms())
    if atom_count == 0:
        raise ValueError("selected model and chains contain no atoms")
    return structure, models, model, sorted(observed_chains), atom_count


def serialize_model(model, structure_format: str, requested_chains: list[str]) -> str:
    suffix = ".pdb" if structure_format == "pdb" else ".cif"
    descriptor, temporary_name = tempfile.mkstemp(prefix="structure-view-model-", suffix=suffix)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        writer = PDBIO() if structure_format == "pdb" else MMCIFIO()
        writer.set_structure(model)
        writer.save(str(temporary_path), select=ChainSelect(requested_chains))
        text = temporary_path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError("selected coordinate model serialized to an empty document")
        return text
    finally:
        temporary_path.unlink(missing_ok=True)


def style_spec(style: str, color: str | None = None, colorscheme: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if color is not None:
        payload["color"] = color
    if colorscheme is not None:
        payload["colorscheme"] = colorscheme
    if style == "cartoon":
        return {"cartoon": payload}
    if style == "stick":
        return {"stick": {**payload, "radius": 0.18}}
    if style == "sphere":
        return {"sphere": {**payload, "scale": 0.28}}
    return {"line": {**payload, "linewidth": 1.5}}


def configure_view(view, model_text: str, structure_format: str, requested_chains: list[str], style: str, color_semantics: str) -> dict[str, Any]:
    viewer_format = "pdb" if structure_format == "pdb" else "cif"
    view.addModel(model_text, viewer_format)
    view.setStyle({}, {})
    legend: dict[str, Any]
    if color_semantics == "chain":
        mapping = {}
        for index, chain_id in enumerate(requested_chains):
            color = CHAIN_COLORS[index % len(CHAIN_COLORS)]
            mapping[chain_id] = color
            view.setStyle({"chain": chain_id}, style_spec(style, color=color))
        legend = {"type": "categorical-chain", "mapping": mapping}
    elif color_semantics == "alphafold-plddt":
        colorscheme = {"prop": "b", "gradient": "roygb", "min": 0, "max": 100}
        for chain_id in requested_chains:
            view.setStyle({"chain": chain_id}, style_spec(style, colorscheme=colorscheme))
        legend = {
            "type": "alphafold-plddt",
            "property": "B-column",
            "range": [0, 100],
            "bins": {"very_low": [0, 50], "low": [50, 70], "confident": [70, 90], "very_high": [90, 100]},
        }
    else:
        for chain_id in requested_chains:
            view.setStyle({"chain": chain_id}, style_spec(style, color="#0072B2"))
        legend = {"type": "uniform", "color": "#0072B2"}
    view.setBackgroundColor("white")
    view.zoomTo()
    return legend


def write_html(view, output: Path, forbidden_path: str) -> tuple[str, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        raise ValueError(f"refusing to overwrite HTML output: {output}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".html", dir=output.parent)
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        view.write_html(str(temporary_path))
        content = temporary_path.read_text(encoding="utf-8")
        if len(content.encode("utf-8")) < 1000 or "3Dmol" not in content:
            raise ValueError("py3Dmol produced blank or unrecognized HTML")
        if forbidden_path in content:
            raise ValueError("HTML leaked the local source path")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        size = len(content.encode("utf-8"))
        os.replace(temporary_path, output)
        return digest, size
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite manifest output: {path}")
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def build(args: argparse.Namespace) -> tuple[dict[str, Any], Any, str]:
    if args.width < 320 or args.width > 4000 or args.height < 240 or args.height > 3000:
        raise ValueError("viewer dimensions are outside the validated bounds")
    if args.color_semantics == "alphafold-plddt" and args.confidence_provenance != "alphafold-b-column-plddt":
        raise ValueError("pLDDT coloring requires declared AlphaFold B-column pLDDT provenance")
    if args.color_semantics != "alphafold-plddt" and args.confidence_provenance == "alphafold-b-column-plddt":
        confidence_note = "AlphaFold confidence provenance is retained but not encoded by the selected color semantics."
    else:
        confidence_note = None
    input_path, input_digest = stable_input(args.input)
    requested_chains = [value.strip() for value in args.chains.split(",") if value.strip()]
    _structure, models, model, all_chains, atom_count = load_scope(input_path, args.format, args.model_index, requested_chains)
    if args.color_semantics == "alphafold-plddt":
        b_values = [float(atom.bfactor) for chain in model if chain.id in requested_chains for atom in chain.get_atoms()]
        if not b_values or any(not math.isfinite(value) or value < 0 or value > 100 for value in b_values):
            raise ValueError("AlphaFold pLDDT coloring requires finite selected-atom B values within 0 through 100")
    model_text = serialize_model(model, args.format, requested_chains)
    view = py3Dmol.view(width=args.width, height=args.height)
    legend = configure_view(view, model_text, args.format, requested_chains, args.style, args.color_semantics)
    manifest = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "input": {
            "sha256": input_digest,
            "format": args.format,
            "model_index": args.model_index,
            "model_count": len(models),
            "selected_chains": requested_chains,
            "all_chain_ids_in_selected_model": all_chains,
            "selected_atom_count": atom_count,
        },
        "view": {
            "style": args.style,
            "color_semantics": args.color_semantics,
            "confidence_provenance": args.confidence_provenance,
            "width": args.width,
            "height": args.height,
            "legend": legend,
        },
        "warnings": [confidence_note] if confidence_note else [],
        "quality_status": "passed",
        "versions": {"python": platform.python_version(), "biopython": version("biopython"), "py3dmol": version("py3Dmol")},
        "interpretation_boundary": "The HTML artifact is a communication and inspection view, not evidence of structural quality, affinity, dynamics, biological state, or function.",
    }
    return manifest, view, str(input_path)


def main() -> int:
    args = parse_args()
    manifest, view, forbidden_path = build(args)
    html_digest, html_size = write_html(view, args.html_output, forbidden_path)
    manifest["html_output"] = {"sha256": html_digest, "bytes": html_size}
    manifest["result_digest"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    atomic_json(args.manifest_output, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
