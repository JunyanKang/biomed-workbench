#!/usr/bin/env python3
"""Import validated Metascape XGMML and export quality-checked publication assets.

The scientific validation threshold is complete node/edge accounting plus a
nonempty, reloadable export; layout is explicitly treated as visualization.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def request(method: str, url: str, body: bytes | None = None, content_type: str = "application/json") -> object:
    req = Request(url, data=body, method=method, headers={"Accept": "application/json", "Content-Type": content_type})
    try:
        with urlopen(req, timeout=30) as response:
            data = response.read()
    except URLError as exc:
        raise RuntimeError("Cytoscape CyREST is unavailable; start an approved Cytoscape 3.10.x session") from exc
    return json.loads(data) if data else {}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def network_rows(base_url: str, network_suid: int, table: str) -> list[dict]:
    payload = request("GET", f"{base_url}/networks/{network_suid}/tables/{table}")
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError(f"Cytoscape {table} table is unavailable")
    return rows


def write_tsv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def apply_publication_style(base_url: str, network_suid: int, node_rows: list[dict]) -> tuple[str, int]:
    palette = ["#527AA3", "#4E9F70", "#7A5EA8", "#C07A49", "#5E8EA6", "#A66B7A", "#6E8B65", "#8B7355", "#6C6C78", "#4D9CA8"]
    groups = sorted({int(row["GROUP_ID"]) for row in node_rows if isinstance(row.get("GROUP_ID"), int)})
    style = {
        "title": f"Biomed Workbench Metascape {network_suid}",
        "defaults": [
            {"visualProperty": "NETWORK_BACKGROUND_PAINT", "value": "#FFFFFF"},
            {"visualProperty": "NODE_FILL_COLOR", "value": "#B8BEC2"},
            {"visualProperty": "NODE_SHAPE", "value": "ELLIPSE"},
            {"visualProperty": "NODE_SIZE", "value": 26.0},
            {"visualProperty": "NODE_BORDER_WIDTH", "value": 0.8},
            {"visualProperty": "NODE_BORDER_PAINT", "value": "#FFFFFF"},
            {"visualProperty": "NODE_LABEL", "value": ""},
            {"visualProperty": "NODE_LABEL_FONT_SIZE", "value": 13},
            {"visualProperty": "NODE_LABEL_COLOR", "value": "#3F464A"},
            {"visualProperty": "NODE_LABEL_POSITION", "value": "E,W,c,5.00,0.00"},
            {"visualProperty": "EDGE_WIDTH", "value": 0.55},
            {"visualProperty": "EDGE_TRANSPARENCY", "value": 100},
            {"visualProperty": "EDGE_STROKE_UNSELECTED_PAINT", "value": "#D9DEE2"},
        ],
        "mappings": [
            {"mappingType": "discreet", "mappingColumn": "GROUP_ID", "mappingColumnType": "Integer", "visualProperty": "NODE_FILL_COLOR", "map": [{"key": str(group), "value": palette[(group - 1) % len(palette)]} for group in groups]},
            {"mappingType": "continuous", "mappingColumn": "LogP", "mappingColumnType": "Double", "visualProperty": "NODE_SIZE", "points": [{"value": -30.0, "lesser": "50.0", "equal": "50.0", "greater": "50.0"}, {"value": -1.3, "lesser": "18.0", "equal": "18.0", "greater": "18.0"}]},
        ],
    }
    created = request("POST", f"{base_url}/styles", json.dumps(style).encode())
    title = created.get("title") if isinstance(created, dict) else None
    if not isinstance(title, str) or not title:
        raise RuntimeError("Cytoscape did not create the declared visual style")
    request("GET", f"{base_url}/apply/styles/{quote(title)}/{network_suid}")
    views = request("GET", f"{base_url}/networks/{network_suid}/views")
    if not isinstance(views, list) or len(views) != 1 or not isinstance(views[0], int):
        raise RuntimeError("Cytoscape did not expose one network view")
    view_suid = views[0]
    for row in node_rows:
        if not isinstance(row.get("SUID"), int):
            continue
        group = row.get("GROUP_ID") if isinstance(row.get("GROUP_ID"), int) else 1
        color_payload = {"visualProperty": "NODE_FILL_COLOR", "value": palette[(group - 1) % len(palette)]}
        request("PUT", f"{base_url}/networks/{network_suid}/views/{view_suid}/nodes/{row['SUID']}/NODE_FILL_COLOR/bypass", json.dumps(color_payload).encode())
        label = str(row.get("Description") or row.get("name") or "").strip()[:80] if row.get("FirstInGroupByLogP") == 1 else ""
        payload = {"visualProperty": "NODE_LABEL", "value": label}
        request("PUT", f"{base_url}/networks/{network_suid}/views/{view_suid}/nodes/{row['SUID']}/NODE_LABEL/bypass", json.dumps(payload).encode())
        if label:
            size_payload = {"visualProperty": "NODE_SIZE", "value": 38.0}
            request("PUT", f"{base_url}/networks/{network_suid}/views/{view_suid}/nodes/{row['SUID']}/NODE_SIZE/bypass", json.dumps(size_payload).encode())
    return title, view_suid


def apply_grouped_layout(base_url: str, network_suid: int, view_suid: int, node_rows: list[dict]) -> None:
    """Place declared functional groups deterministically without changing graph semantics."""
    grouped: dict[int, list[dict]] = {}
    for row in node_rows:
        group = row.get("GROUP_ID") if isinstance(row.get("GROUP_ID"), int) else 0
        grouped.setdefault(group, []).append(row)
    group_ids = sorted(grouped)
    columns = max(1, math.ceil(math.sqrt(len(group_ids))))
    for group_index, group in enumerate(group_ids):
        center_x = (group_index % columns) * 430.0
        center_y = (group_index // columns) * 360.0
        members = sorted(
            grouped[group],
            key=lambda row: (
                0 if row.get("FirstInGroupByLogP") == 1 else 1,
                float(row.get("LogP")) if isinstance(row.get("LogP"), (int, float)) else 0.0,
                str(row.get("name") or row.get("Description") or ""),
            ),
        )
        for member_index, row in enumerate(members):
            if not isinstance(row.get("SUID"), int):
                continue
            if member_index == 0:
                x, y = center_x, center_y
            else:
                angle = member_index * math.pi * (3.0 - math.sqrt(5.0))
                radius = 48.0 * math.sqrt(member_index)
                x = center_x + radius * math.cos(angle)
                y = center_y + radius * math.sin(angle)
            for visual_property, value in (("NODE_X_LOCATION", x), ("NODE_Y_LOCATION", y)):
                payload = {"visualProperty": visual_property, "value": value}
                request(
                    "PUT",
                    f"{base_url}/networks/{network_suid}/views/{view_suid}/nodes/{row['SUID']}/{visual_property}/bypass",
                    json.dumps(payload).encode(),
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xgmml", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--png-width", type=int, default=6000)
    parser.add_argument(
        "--layout",
        default="grouped",
        help="Use a deterministic grouped layout; choose source to preserve XGMML coordinates or name a Cytoscape layout explicitly.",
    )
    args = parser.parse_args()
    if args.png_width < 1200:
        raise ValueError("png-width must be at least 1200 pixels for a publication-oriented raster export")
    xgmml = args.xgmml.resolve()
    if not xgmml.is_file() or xgmml.suffix.lower() != ".xgmml":
        raise ValueError("xgmml must be an existing XGMML network")
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    network = request("POST", f"{args.base_url}/networks?source=url", json.dumps({"url": xgmml.as_uri()}).encode())
    if isinstance(network, list) and len(network) == 1 and isinstance(network[0], dict):
        network = network[0]
    network_suid = network.get("networkSUID") if isinstance(network, dict) else None
    if isinstance(network_suid, list) and len(network_suid) == 1:
        network_suid = network_suid[0]
    if not isinstance(network_suid, int):
        raise RuntimeError("Cytoscape did not return a network identifier")
    node_rows = network_rows(args.base_url, network_suid, "defaultnode")
    edge_rows = network_rows(args.base_url, network_suid, "defaultedge")
    node_table = output / "cytoscape_nodes.tsv"; write_tsv(node_table, node_rows)
    edge_table = output / "cytoscape_edges.tsv"; write_tsv(edge_table, edge_rows)
    style_name, view_suid = apply_publication_style(args.base_url, network_suid, node_rows)
    if args.layout == "grouped":
        apply_grouped_layout(args.base_url, network_suid, view_suid, node_rows)
    elif args.layout != "source":
        request("GET", f"{args.base_url}/apply/layouts/{quote(args.layout)}/{network_suid}")
    request(
        "POST",
        f"{args.base_url}/commands/view/fit%20content",
        json.dumps({"view": str(view_suid)}).encode(),
    )
    exports = []
    media_types = {"pdf": "image/pdf", "svg": "image/svg+xml", "png": "image/png"}
    for suffix in ("pdf", "svg", "png"):
        target = output / f"metascape_network.{suffix}"
        size_query = f"?w={args.png_width}" if suffix == "png" else ""
        url = f"{args.base_url}/networks/{network_suid}/views/{view_suid}.{suffix}{size_query}"
        req = Request(url, method="GET", headers={"Accept": media_types[suffix]})
        with urlopen(req, timeout=60) as response:
            target.write_bytes(response.read())
        if target.stat().st_size == 0:
            raise RuntimeError(f"Cytoscape exported an empty {suffix} file")
        exports.append(target)
    session = output / "metascape_network.cys"
    request("POST", f"{args.base_url}/session?file={quote(str(session))}")
    manifest = {
        "schema_version": 1, "style_version": "1.3.1", "cytoscape_network_suid": network_suid,
        "node_count": len(node_rows), "edge_count": len(edge_rows), "style": style_name, "layout": args.layout,
        "source_sha256": digest(xgmml),
        "raster_export": {"width_pixels": args.png_width, "purpose": "high-resolution publication and review export"},
        "replot_tables": [
            {"role": "nodes-and-visual-attributes", "path": node_table.name, "sha256": digest(node_table)},
            {"role": "edges-and-source-similarity", "path": edge_table.name, "sha256": digest(edge_table)},
        ],
        "exports": [{"path": path.name, "sha256": digest(path)} for path in exports],
        "session": {"path": session.name, "sha256": digest(session)} if session.is_file() else None,
        "visual_encoding": {
            "palette": "muted blue-green-purple categorical palette derived from the project publication style",
            "node_area": "term significance where LogP is available; representative terms receive a bounded emphasis",
            "labels": "one representative term per declared group",
            "edges": "thin recessed similarity links, with enough contrast to survive whole-figure reduction",
            "background": "white with weak relationships visually recessed"
        },
        "layout_semantics": "Declared functional groups use a deterministic grouped layout. Within-group proximity is a rendering choice, not an additional quantitative result."
    }
    target = output / "cytoscape_render_manifest.json"; target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(target), "network_suid": network_suid, "exports": len(exports)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
