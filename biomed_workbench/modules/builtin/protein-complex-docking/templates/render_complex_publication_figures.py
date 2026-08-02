#!/usr/bin/env python3
"""Render reproducible complex-docking figures and replot tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path


CHAIN_COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_pdb(path: Path) -> list[dict]:
    atoms = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(("ATOM  ", "HETATM")) or len(line) < 54:
            continue
        try:
            atoms.append({
                "record": line[:6].strip(), "atom": line[12:16].strip(), "resname": line[17:20].strip(),
                "chain": line[21].strip() or "_", "resseq": int(line[22:26]), "icode": line[26].strip(),
                "x": float(line[30:38]), "y": float(line[38:46]), "z": float(line[46:54]),
            })
        except ValueError:
            continue
    if not atoms or len({row["chain"] for row in atoms}) < 2:
        raise ValueError("structure must contain finite coordinates for at least two chains")
    if any(not all(math.isfinite(row[key]) for key in ("x", "y", "z")) for row in atoms):
        raise ValueError("structure contains non-finite coordinates")
    return atoms


def interface_contacts(atoms: list[dict], cutoff: float) -> list[dict]:
    heavy = [row for row in atoms if not row["atom"].upper().startswith("H")]
    contacts = {}
    cutoff2 = cutoff * cutoff
    for index, left in enumerate(heavy):
        for right in heavy[index + 1:]:
            if left["chain"] == right["chain"]:
                continue
            distance2 = sum((left[key] - right[key]) ** 2 for key in ("x", "y", "z"))
            if distance2 <= cutoff2:
                a = (left["chain"], left["resseq"], left["icode"], left["resname"])
                b = (right["chain"], right["resseq"], right["icode"], right["resname"])
                if a > b:
                    a, b = b, a
                key = (a, b)
                contacts[key] = min(contacts.get(key, float("inf")), math.sqrt(distance2))
    return [
        {"chain_a": a[0], "residue_a": f"{a[3]}:{a[1]}{a[2]}", "chain_b": b[0], "residue_b": f"{b[3]}:{b[1]}{b[2]}", "minimum_distance_angstrom": round(distance, 3)}
        for (a, b), distance in sorted(contacts.items())
    ]


def write_tsv(path: Path, rows: list[dict]) -> None:
    fields = list(rows[0]) if rows else ["chain_a", "residue_a", "chain_b", "residue_b", "minimum_distance_angstrom"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader(); writer.writerows(rows)


def parse_score_table(path: Path | None) -> list[dict]:
    if path is None or not path.is_file():
        return []
    rows = []
    for rank, row in enumerate(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t"), start=1):
        if row.get("score") in {None, "", "-"}:
            continue
        normalized = {
            "model": row.get("model", ""),
            "rank": row.get("caprieval_rank") or row.get("rank") or rank,
            "cluster_id": row.get("cluster_id", ""),
            "haddock_score": row["score"],
            "dockq": row.get("dockq", ""),
            "irmsd_angstrom": row.get("irmsd", ""),
            "lrmsd_angstrom": row.get("lrmsd", ""),
            "fnat": row.get("fnat", ""),
            "buried_surface_area_angstrom2": row.get("bsa", ""),
        }
        rows.append(normalized)
    return rows


def render(structure: Path, contacts: list[dict], score_rows: list[dict], output: Path, title: str) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 6, "axes.titlesize": 7, "axes.labelsize": 7,
        "xtick.labelsize": 6, "ytick.labelsize": 6, "legend.fontsize": 6,
        "axes.linewidth": .5, "xtick.major.width": .5, "ytick.major.width": .5,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    })

    atoms = parse_pdb(structure)
    ca = [row for row in atoms if row["atom"] == "CA"] or atoms
    chains = sorted({row["chain"] for row in ca})
    fig = plt.figure(figsize=(7.2, 3.5), constrained_layout=True)
    ax = fig.add_subplot(121, projection="3d")
    for index, chain in enumerate(chains):
        rows = [row for row in ca if row["chain"] == chain]
        ax.plot([r["x"] for r in rows], [r["y"] for r in rows], [r["z"] for r in rows], lw=1.1, color=CHAIN_COLORS[index % len(CHAIN_COLORS)], label=f"Chain {chain}")
        interface_numbers = {
            int(re.search(r":(-?\d+)", contact[side]).group(1))
            for contact in contacts for side in ("residue_a", "residue_b")
            if contact[f"chain_{side[-1]}"] == chain and re.search(r":(-?\d+)", contact[side])
        }
        marked = [row for row in rows if row["resseq"] in interface_numbers]
        if marked:
            ax.scatter([r["x"] for r in marked], [r["y"] for r in marked], [r["z"] for r in marked], s=6, color=CHAIN_COLORS[index % len(CHAIN_COLORS)], edgecolor="white", linewidth=.2)
    ax.set_title("a  Complex overview", loc="left", fontsize=7, fontweight="bold")
    ax.set_axis_off(); ax.legend(frameon=False, fontsize=6, loc="upper left")

    bx = fig.add_subplot(122)
    if contacts:
        x = [int(re.search(r":(-?\d+)", row["residue_a"]).group(1)) for row in contacts]
        y = [int(re.search(r":(-?\d+)", row["residue_b"]).group(1)) for row in contacts]
        distance = [row["minimum_distance_angstrom"] for row in contacts]
        points = bx.scatter(x, y, c=distance, cmap="viridis_r", vmin=2, vmax=max(5.0, max(distance)), s=17, edgecolor="white", linewidth=.25)
        colorbar = fig.colorbar(points, ax=bx, fraction=.05, pad=.03)
        colorbar.set_label("Minimum heavy-atom distance (Å)", fontsize=6)
        colorbar.ax.tick_params(labelsize=5, width=.5)
        bx.set_xlabel(f"Chain {contacts[0]['chain_a']} residue", fontsize=7)
        bx.set_ylabel(f"Chain {contacts[0]['chain_b']} residue", fontsize=7)
    else:
        bx.text(.5, .5, "No inter-chain contacts at the declared cutoff", ha="center", va="center", fontsize=6)
        bx.set_axis_off()
    bx.set_title("b  Residue contact map", loc="left", fontsize=7, fontweight="bold")
    bx.tick_params(labelsize=6, width=.5); bx.spines[["top", "right"]].set_visible(False)
    fig.suptitle(title, fontsize=7)
    outputs = []
    for suffix in ("pdf", "svg", "png"):
        target = output / f"complex_interface.{suffix}"
        fig.savefig(target, dpi=600 if suffix == "png" else None, bbox_inches="tight")
        outputs.append(target)
    plt.close(fig)

    if score_rows:
        numeric = [(float(row["haddock_score"]), float(row["dockq"])) for row in score_rows if row.get("dockq") not in {None, "", "-"}]
        if numeric:
            fig, ax = plt.subplots(figsize=(3.5, 3.0), constrained_layout=True)
            x, y = zip(*numeric)
            ax.scatter(x, y, s=12, color="#0072B2", edgecolor="white", linewidth=.35)
            ax.set_xlabel("HADDOCK score", fontsize=7)
            ax.set_ylabel("DockQ (reference required)", fontsize=7)
            ax.set_title("Model quality landscape", loc="left", fontsize=7, fontweight="bold")
            ax.tick_params(labelsize=6, width=.5); ax.spines[["top", "right"]].set_visible(False)
            for suffix in ("pdf", "svg", "png"):
                target = output / f"docking_quality.{suffix}"
                fig.savefig(target, dpi=600 if suffix == "png" else None, bbox_inches="tight")
                outputs.append(target)
            plt.close(fig)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("structure", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--score-table", type=Path)
    parser.add_argument("--contact-cutoff", type=float, default=5.0)
    parser.add_argument("--title", default="Protein-complex structural analysis")
    args = parser.parse_args()
    if not 2.0 <= args.contact_cutoff <= 8.0:
        raise ValueError("contact cutoff must be 2..8 Angstrom")
    structure = args.structure.resolve(); output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    atoms = parse_pdb(structure); contacts = interface_contacts(atoms, args.contact_cutoff)
    table = output / "interface_contacts.tsv"; write_tsv(table, contacts)
    coordinate_table = output / "structure_residue_coordinates.tsv"
    coordinate_rows = [
        {"chain": row["chain"], "residue": f"{row['resname']}:{row['resseq']}{row['icode']}", "x_angstrom": row["x"], "y_angstrom": row["y"], "z_angstrom": row["z"]}
        for row in atoms if row["atom"] == "CA"
    ]
    write_tsv(coordinate_table, coordinate_rows)
    score_rows = parse_score_table(args.score_table.resolve() if args.score_table else None)
    score_output = output / "docking_model_scores.tsv"
    if score_rows:
        write_tsv(score_output, score_rows)
    figures = render(structure, contacts, score_rows, output, args.title)
    pymol = output / "reproduce_in_pymol.pml"
    pymol.write_text(f"load {structure.name}, complex\nhide everything\nshow cartoon, complex\ncolor marine, chain {sorted({r['chain'] for r in atoms})[0]}\nbg_color white\nset ray_opaque_background, off\n", encoding="utf-8")
    manifest = {
        "schema_version": 1, "style_version": "1.2.0", "structure_sha256": sha256(structure),
        "contact_cutoff_angstrom": args.contact_cutoff, "atom_count": len(atoms), "interface_contact_count": len(contacts),
        "replot_tables": [
            {"role": "interface-contacts", "path": table.name, "sha256": sha256(table)},
            {"role": "residue-coordinates", "path": coordinate_table.name, "sha256": sha256(coordinate_table)},
        ] + ([{"role": "model-scores", "path": score_output.name, "sha256": sha256(score_output)}] if score_rows else []),
        "figures": [{"path": path.name, "sha256": sha256(path)} for path in figures],
        "editable_scene": pymol.name,
        "semantics": "Coordinates and contacts are model-derived; only reference-backed DockQ columns evaluate agreement with a known complex.",
    }
    target = output / "figure_manifest.json"; target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(target), "figures": len(figures), "contacts": len(contacts)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
