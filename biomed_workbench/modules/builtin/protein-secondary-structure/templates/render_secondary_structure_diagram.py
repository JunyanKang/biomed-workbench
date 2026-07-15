#!/usr/bin/env python3
"""Render a digest-bound SVG track from validated residue-level DSSP rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import tempfile
import xml.etree.ElementTree as ET
from importlib.metadata import version
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.hashsalt"] = "biomed-workbench-secondary-structure-v1"
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrow, FancyBboxPatch  # noqa: E402


MODULE_ID = "protein-secondary-structure"
MODULE_VERSION = "1.0.0"
COMPATIBILITY_ROW_ID = "structure-analysis-2026-07-15-protein-secondary-structure"
EXPECTED_COLUMNS = (
    "chain_id",
    "hetero_flag",
    "residue_number",
    "insertion_code",
    "dssp_index",
    "amino_acid",
    "secondary_structure",
    "relative_accessibility",
    "phi_degrees",
    "psi_degrees",
)
DSSP_TO_CATEGORY = {
    "H": "helix",
    "G": "helix",
    "I": "helix",
    "E": "sheet",
    "B": "sheet",
    "T": "coil",
    "S": "coil",
    "-": "coil",
}
CATEGORY_COLORS = {"helix": "#C53B3B", "sheet": "#2676B8", "coil": "#6F7780"}
MAX_ROWS = 100_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--residue-table", required=True, type=Path)
    parser.add_argument("--chain", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--show-residue-numbers", action="store_true")
    parser.add_argument("--svg-output", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    return parser.parse_args()


def stable_input(path: Path) -> tuple[bytes, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("residue table must be a stable regular file")
    content = path.read_bytes()
    if not content:
        raise ValueError("residue table is empty")
    return content, hashlib.sha256(content).hexdigest()


def parse_rows(content: bytes, chain_id: str) -> tuple[list[dict[str, Any]], int]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("residue table must be UTF-8 text") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter="\t")
    if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
        raise ValueError("residue table columns and order differ from the validated DSSP contract")
    source_rows = list(reader)
    if not source_rows or len(source_rows) > MAX_ROWS:
        raise ValueError(f"residue table must contain between 1 and {MAX_ROWS} rows")
    observed_ids: set[tuple[str, int, str]] = set()
    observed_dssp: set[int] = set()
    selected: list[dict[str, Any]] = []
    for row_number, source in enumerate(source_rows, start=2):
        try:
            residue_number = int(source["residue_number"])
            dssp_index = int(source["dssp_index"])
            accessibility = float(source["relative_accessibility"])
            phi = float(source["phi_degrees"])
            psi = float(source["psi_degrees"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"row {row_number} contains a malformed numeric field") from exc
        if not all(math.isfinite(value) for value in (accessibility, phi, psi)):
            raise ValueError(f"row {row_number} contains non-finite DSSP values")
        code = source["secondary_structure"]
        if code not in DSSP_TO_CATEGORY:
            raise ValueError(f"row {row_number} contains an unsupported DSSP code")
        identity = (source["chain_id"], residue_number, source["insertion_code"])
        if identity in observed_ids or dssp_index in observed_dssp:
            raise ValueError(f"row {row_number} duplicates a residue identity or DSSP index")
        observed_ids.add(identity)
        observed_dssp.add(dssp_index)
        if source["chain_id"] == chain_id:
            selected.append(
                {
                    "chain_id": chain_id,
                    "residue_number": residue_number,
                    "insertion_code": source["insertion_code"],
                    "dssp_index": dssp_index,
                    "amino_acid": source["amino_acid"],
                    "dssp_code": code,
                    "category": DSSP_TO_CATEGORY[code],
                }
            )
    if not selected:
        raise ValueError("selected chain has no rows in the validated DSSP table")
    selected.sort(key=lambda row: row["dssp_index"])
    return selected, len(source_rows)


def build_segments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    start = 0
    for index in range(1, len(rows) + 1):
        boundary = index == len(rows)
        if not boundary:
            previous, current = rows[index - 1], rows[index]
            boundary = current["category"] != previous["category"] or current["dssp_index"] != previous["dssp_index"] + 1
        if boundary:
            first, last = rows[start], rows[index - 1]
            segments.append(
                {
                    "category": first["category"],
                    "start_row_index": start,
                    "end_row_index": index - 1,
                    "residue_count": index - start,
                    "start_residue": {"number": first["residue_number"], "insertion_code": first["insertion_code"]},
                    "end_residue": {"number": last["residue_number"], "insertion_code": last["insertion_code"]},
                    "start_dssp_index": first["dssp_index"],
                    "end_dssp_index": last["dssp_index"],
                }
            )
            start = index
    if sum(segment["residue_count"] for segment in segments) != len(rows):
        raise ValueError("secondary-structure segments do not reconcile to selected residues")
    return segments


def render_svg(rows: list[dict[str, Any]], segments: list[dict[str, Any]], title: str, show_numbers: bool) -> bytes:
    width = min(24.0, max(8.0, 0.075 * len(rows) + 4.0))
    figure, axis = plt.subplots(figsize=(width, 2.3))
    y = 0.5
    for segment in segments:
        start = segment["start_row_index"]
        count = segment["residue_count"]
        category = segment["category"]
        color = CATEGORY_COLORS[category]
        if category == "helix":
            patch = FancyBboxPatch((start, y - 0.20), count, 0.40, boxstyle="round,pad=0.08", facecolor=color, edgecolor="white", linewidth=0.6)
            axis.add_patch(patch)
        elif category == "sheet":
            body = max(0.0, count - min(0.8, count * 0.4))
            patch = FancyArrow(start, y, body, 0, width=0.36, head_width=0.62, head_length=count - body, length_includes_head=True, facecolor=color, edgecolor="white", linewidth=0.6)
            axis.add_patch(patch)
        else:
            axis.plot([start, start + count], [y, y], color=color, linewidth=4.0, solid_capstyle="butt")
    axis.set_xlim(-0.5, len(rows) + 0.5)
    axis.set_ylim(0, 1)
    axis.set_yticks([])
    axis.set_xlabel("Residue position in validated DSSP row order")
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    if title:
        axis.set_title(title)
    handles = [plt.Line2D([0], [0], color=CATEGORY_COLORS[name], linewidth=6, label=name.title()) for name in ("helix", "sheet", "coil")]
    axis.legend(handles=handles, loc="upper right", frameon=False, ncol=3)
    if show_numbers:
        step = max(1, math.ceil(len(rows) / 20))
        ticks = list(range(0, len(rows), step))
        labels = [f"{rows[index]['residue_number']}{rows[index]['insertion_code']}" for index in ticks]
        axis.set_xticks(ticks, labels, rotation=45, ha="right")
    else:
        axis.set_xticks([])
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="svg", metadata={"Date": None, "Creator": "Biomed Workbench"})
    plt.close(figure)
    content = buffer.getvalue()
    if len(content) < 1_000:
        raise ValueError("rendered SVG is unexpectedly small")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("rendered SVG is not parseable XML") from exc
    if not root.tag.endswith("svg"):
        raise ValueError("rendered document root is not SVG")
    return content


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite output: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
        os.replace(temporary_name, path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def build(args: argparse.Namespace) -> tuple[bytes, dict[str, Any]]:
    if not args.chain or len(args.chain) > 8 or len(args.title) > 256:
        raise ValueError("chain or title is outside the bounded diagram contract")
    content, source_digest = stable_input(args.residue_table)
    rows, source_row_count = parse_rows(content, args.chain)
    segments = build_segments(rows)
    svg = render_svg(rows, segments, args.title, args.show_residue_numbers)
    category_counts = {category: sum(row["category"] == category for row in rows) for category in CATEGORY_COLORS}
    code_counts = {code: sum(row["dssp_code"] == code for row in rows) for code in DSSP_TO_CATEGORY}
    manifest = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "module_version": MODULE_VERSION,
        "compatibility_row_id": COMPATIBILITY_ROW_ID,
        "input": {"sha256": source_digest, "source_row_count": source_row_count, "selected_chain": args.chain},
        "diagram": {
            "title": args.title,
            "show_residue_numbers": args.show_residue_numbers,
            "selected_residue_count": len(rows),
            "segment_count": len(segments),
            "category_counts": category_counts,
            "dssp_code_counts": code_counts,
            "segments": segments,
            "category_colors": CATEGORY_COLORS,
            "svg_sha256": hashlib.sha256(svg).hexdigest(),
            "svg_bytes": len(svg),
        },
        "versions": {"matplotlib": version("matplotlib")},
        "quality_gates": {
            "source_schema_validated": True,
            "selected_residues_accounted": sum(category_counts.values()) == len(rows),
            "segments_accounted": sum(segment["residue_count"] for segment in segments) == len(rows),
            "dssp_alphabet_retained": set(code_counts) == set(DSSP_TO_CATEGORY),
            "svg_nonblank_and_parseable": True,
        },
        "interpretation_boundary": "The diagram visualizes observed DSSP assignments from one supplied coordinate model; it is not evidence of dynamics, stability, occupancy, function, or experimental state.",
    }
    return svg, manifest


def main() -> int:
    args = parse_args()
    if args.svg_output.suffix.lower() != ".svg":
        raise ValueError("diagram output must use the .svg suffix")
    if args.svg_output.exists() or args.manifest_output.exists() or args.svg_output.is_symlink() or args.manifest_output.is_symlink():
        raise ValueError("refusing to overwrite diagram outputs")
    svg, manifest = build(args)
    atomic_write(args.svg_output, svg)
    atomic_write(args.manifest_output, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    print(json.dumps({"passed": True, "residue_count": manifest["diagram"]["selected_residue_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
