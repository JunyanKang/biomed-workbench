#!/usr/bin/env python3
"""Render validated STRING evidence plus quality-checked replot tables.

Scientific validation preserves the declared network type and score threshold;
the renderer never upgrades association evidence into physical interaction.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--title", default="Protein interaction evidence")
    args = parser.parse_args()
    payload = json.loads(args.result.read_text(encoding="utf-8"))
    edges = payload.get("edges")
    if not isinstance(edges, list):
        raise ValueError("result lacks STRING edge records")
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    edge_fields = ["string_id_a", "preferred_name_a", "string_id_b", "preferred_name_b", "score", "nscore", "fscore", "pscore", "ascore", "escore", "dscore", "tscore"]
    edge_table = output / "string_edges.tsv"; write_tsv(edge_table, edges, edge_fields)
    node_map = {}
    for row in edges:
        for suffix in ("a", "b"):
            node_map[row[f"string_id_{suffix}"]] = row.get(f"preferred_name_{suffix}") or row[f"string_id_{suffix}"]
    degree = {node: 0 for node in node_map}
    for row in edges:
        degree[row["string_id_a"]] += 1; degree[row["string_id_b"]] += 1
    nodes = [{"string_id": node, "label": node_map[node], "degree": degree[node]} for node in sorted(node_map)]
    node_table = output / "string_nodes.tsv"; write_tsv(node_table, nodes, ["string_id", "label", "degree"])

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5.0, 4.3), constrained_layout=True)
    ordered = sorted(node_map)
    positions = {node: (math.cos(2 * math.pi * i / max(1, len(ordered))), math.sin(2 * math.pi * i / max(1, len(ordered)))) for i, node in enumerate(ordered)}
    for row in edges:
        x1, y1 = positions[row["string_id_a"]]; x2, y2 = positions[row["string_id_b"]]
        ax.plot([x1, x2], [y1, y2], color="#9AA3A8", lw=.35 + 1.5 * float(row["score"]), alpha=.7, zorder=1)
    for node in ordered:
        x, y = positions[node]
        ax.scatter([x], [y], s=24 + 8 * degree[node], color="#0072B2", edgecolor="white", linewidth=.5, zorder=2)
        ax.text(x, y + .06, node_map[node], ha="center", va="bottom", fontsize=6)
    ax.set_aspect("equal"); ax.set_axis_off(); ax.set_title(args.title, loc="left", fontsize=7, fontweight="bold")
    subtitle = f"STRING v12.0 · {payload.get('query', {}).get('network_type', 'unknown')} network · score ≥ {payload.get('query', {}).get('required_score', 'NA')}"
    ax.text(0, -.02, subtitle, transform=ax.transAxes, fontsize=6, color="#555555")
    figures = []
    for suffix in ("pdf", "svg", "png"):
        target = output / f"string_network.{suffix}"; fig.savefig(target, dpi=600 if suffix == "png" else None, bbox_inches="tight"); figures.append(target)
    plt.close(fig)
    style = output / "cytoscape_style.json"
    style.write_text(json.dumps({
        "title": "Biomed Workbench PPI", "defaults": {"NODE_FILL_COLOR": "#0072B2", "NODE_LABEL_FONT_SIZE": 10, "EDGE_STROKE_UNSELECTED_PAINT": "#9AA3A8", "NETWORK_BACKGROUND_PAINT": "#FFFFFF"},
        "mappings": {"NODE_SIZE": {"column": "degree", "range": [24, 72]}, "EDGE_WIDTH": {"column": "score", "range": [0.5, 4.0]}},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {"schema_version": 1, "source_sha256": digest(args.result), "style_version": "1.2.0", "node_count": len(nodes), "edge_count": len(edges), "node_table": node_table.name, "edge_table": edge_table.name, "cytoscape_style": style.name, "figures": [{"path": path.name, "sha256": digest(path)} for path in figures], "edge_semantics": payload.get("query", {}).get("network_type"), "limitations": payload.get("limitations", [])}
    target = output / "ppi_figure_manifest.json"; target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(target), "nodes": len(nodes), "edges": len(edges)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
