#!/usr/bin/env python3
"""Build official AlphaFold 3 inputs, execute an approved local runtime, and audit outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_sequence(value: str, alphabet: str) -> str:
    sequence = re.sub(r"\s+", "", value).upper()
    if not sequence or len(sequence) > 10_000 or re.fullmatch(f"[{alphabet}]+", sequence) is None:
        raise ValueError("entity sequence is empty, too long, or contains unsupported symbols")
    return sequence


def prepare(request: dict) -> dict:
    allowed = {"name", "model_seeds", "entities", "description"}
    if not isinstance(request, dict) or set(request) - allowed:
        raise ValueError("request must be a closed AlphaFold 3 preparation object")
    name = str(request.get("name", ""))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}", name):
        raise ValueError("name must be a short printable job name")
    seeds = request.get("model_seeds", [1])
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= 20 or any(not isinstance(seed, int) or not 0 <= seed < 2**31 for seed in seeds):
        raise ValueError("model_seeds must contain 1..20 nonnegative integers")
    entities = request.get("entities")
    if not isinstance(entities, list) or not 1 <= len(entities) <= 64:
        raise ValueError("entities must contain 1..64 biomolecular entities")
    seen_ids, normalized = set(), []
    for item in entities:
        if not isinstance(item, dict) or len(item) != 1:
            raise ValueError("each entity must declare exactly one official entity type")
        kind, value = next(iter(item.items()))
        if kind not in {"protein", "rna", "dna", "ligand"} or not isinstance(value, dict):
            raise ValueError("entity type must be protein, rna, dna, or ligand")
        allowed_fields = {"id", "sequence", "modifications", "ccdCodes", "smiles", "description"}
        if set(value) - allowed_fields:
            raise ValueError("entity contains unsupported AlphaFold 3 fields")
        entity_id = value.get("id")
        ids = entity_id if isinstance(entity_id, list) else [entity_id]
        if not ids or any(not isinstance(entity, str) or not re.fullmatch(r"[A-Za-z0-9]+", entity) for entity in ids):
            raise ValueError("every entity requires one or more alphanumeric chain IDs")
        if seen_ids.intersection(ids):
            raise ValueError("chain IDs must be unique across entities")
        seen_ids.update(ids)
        clean = {"id": entity_id}
        if kind in {"protein", "rna", "dna"}:
            alphabet = "ACDEFGHIKLMNPQRSTVWYX" if kind == "protein" else "ACGUN" if kind == "rna" else "ACGTN"
            clean["sequence"] = clean_sequence(str(value.get("sequence", "")), alphabet)
            if value.get("modifications") is not None:
                if not isinstance(value["modifications"], list):
                    raise ValueError("modifications must be an array")
                clean["modifications"] = value["modifications"]
        else:
            ccd, smiles = value.get("ccdCodes"), value.get("smiles")
            if (ccd is None) == (smiles is None):
                raise ValueError("ligand must declare exactly one of ccdCodes or smiles")
            if ccd is not None:
                if not isinstance(ccd, list) or not ccd or any(not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9]{1,10}", code) for code in ccd):
                    raise ValueError("ccdCodes must be a nonempty array of CCD identifiers")
                clean["ccdCodes"] = ccd
            else:
                if not isinstance(smiles, str) or not smiles.strip() or len(smiles) > 2000:
                    raise ValueError("SMILES is invalid or too long")
                clean["smiles"] = smiles.strip()
        if value.get("description"):
            clean["description"] = str(value["description"])[:500]
        normalized.append({kind: clean})
    result = {"name": name, "modelSeeds": seeds, "sequences": normalized, "dialect": "alphafold3", "version": 4}
    return result


def parse_outputs(output_dir: Path, report_dir: Path) -> dict:
    ranking_files = sorted(output_dir.glob("*_ranking_scores.csv"))
    summary_files = sorted(output_dir.glob("*_summary_confidences.json"))
    model_files = sorted(output_dir.glob("*_model.cif"))
    if len(ranking_files) != 1 or len(summary_files) != 1 or len(model_files) != 1:
        raise RuntimeError("AlphaFold 3 output must contain one top-level ranking, summary-confidence, and model file")
    rows = list(csv.DictReader(ranking_files[0].open(encoding="utf-8")))
    if not rows:
        raise RuntimeError("AlphaFold 3 ranking table is empty")
    summary = json.loads(summary_files[0].read_text(encoding="utf-8"))
    required = {"ranking_score", "ptm", "iptm", "fraction_disordered", "has_clash"}
    if not isinstance(summary, dict) or not required <= set(summary):
        raise RuntimeError("AlphaFold 3 summary confidence lacks documented fields")
    for field in ("ranking_score", "ptm", "iptm", "fraction_disordered"):
        value = summary[field]
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise RuntimeError(f"AlphaFold 3 {field} is non-finite")
    report_dir.mkdir(parents=True, exist_ok=True)
    normalized = report_dir / "ranking_scores.tsv"
    fields = list(rows[0])
    with normalized.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t"); writer.writeheader(); writer.writerows(rows)
    return {
        "ranking_rows": len(rows), "summary_confidences": summary,
        "top_model": {"path": model_files[0].name, "sha256": digest(model_files[0])},
        "ranking_table": {"path": normalized.name, "sha256": digest(normalized)},
        "source_artifacts": [{"path": path.name, "sha256": digest(path)} for path in (*ranking_files, *summary_files)],
    }


def render_confidence(report: dict, report_dir: Path) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = report["summary_confidences"]
    labels = ["pTM", "ipTM", "ranking score", "ordered fraction"]
    values = [float(summary["ptm"]), float(summary["iptm"]), float(summary["ranking_score"]), 1 - float(summary["fraction_disordered"])]
    fig, ax = plt.subplots(figsize=(3.5, 2.8), constrained_layout=True)
    ax.bar(labels, values, color=["#0072B2", "#D55E00", "#009E73", "#7A7A7A"], width=.65)
    ax.axhline(.8, color="#B0B0B0", lw=.5, ls="--"); ax.set_ylim(0, 1.05)
    ax.set_ylabel("Model confidence summary"); ax.tick_params(axis="x", rotation=25, labelsize=6); ax.tick_params(axis="y", labelsize=6)
    ax.set_title("AlphaFold 3 complex confidence", loc="left", fontsize=7, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    outputs = []
    for suffix in ("pdf", "svg", "png"):
        target = report_dir / f"alphafold3_confidence.{suffix}"; fig.savefig(target, dpi=600 if suffix == "png" else None, bbox_inches="tight"); outputs.append(target)
    plt.close(fig)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--alphafold-executable")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--db-dir", type=Path)
    parser.add_argument("--parse-output", type=Path)
    args = parser.parse_args()
    request = prepare(json.loads(args.request.read_text(encoding="utf-8")))
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    input_path = output / "alphafold3_input.json"; input_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    prediction_dir = args.parse_output.resolve() if args.parse_output else output / "prediction"
    if args.execute:
        if not args.alphafold_executable or not args.model_dir or not args.db_dir:
            raise ValueError("local execution requires executable, approved model directory, and database directory")
        command = [args.alphafold_executable, f"--json_path={input_path}", f"--model_dir={args.model_dir.resolve()}", f"--db_dir={args.db_dir.resolve()}", f"--output_dir={prediction_dir}"]
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            raise RuntimeError(f"AlphaFold 3 exited with {completed.returncode}")
    report = {"schema_version": 1, "input": {"path": input_path.name, "sha256": digest(input_path)}, "executed": args.execute}
    if args.execute or args.parse_output:
        report.update(parse_outputs(prediction_dir, output))
        figures = render_confidence(report, output)
        report["figures"] = [{"path": path.name, "sha256": digest(path)} for path in figures]
    report["interpretation"] = [
        "ranking_score ranks samples for the full complex; chain-pair questions require chain-pair confidence metrics.",
        "pTM and ipTM are model-confidence measures, not binding affinity, kinetics, functional validation, or clinical evidence.",
    ]
    report["license_gate"] = "Local model weights and outputs must satisfy the current AlphaFold 3 terms; the workbench does not bundle weights."
    target = output / "alphafold3_manifest.json"; target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(target), "input": str(input_path), "parsed": bool(args.execute or args.parse_output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
