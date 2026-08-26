#!/usr/bin/env python3
"""Execute and reload bounded RNA-processing and alternative-splicing branches.

The script exposes one stable JSON request contract.  It deliberately keeps
event-level splicing, transcript usage, droplet junction screening, long-read
isoforms, and cross-assay evidence integration as distinct scientific branches.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
from typing import Any, Iterable


MODULE_ID = "rna-processing-alternative-splicing"
MODULE_VERSION = "1.0.0"
EVENT_TYPES = ("SE", "A5SS", "A3SS", "MXE", "RI")


class WorkflowError(ValueError):
    """Raised when an RNA-processing request cannot be scientifically admitted."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WorkflowError("request must be a JSON object")
    return value


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def require_file(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{field} must be a nonempty path")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise WorkflowError(f"{field} does not exist: {path}")
    return path


def require_executable(value: Any, field: str) -> Path:
    """Keep a declared environment symlink so its sibling runtime stays discoverable."""
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{field} must be a nonempty executable path")
    path = Path(value).expanduser().absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise WorkflowError(f"{field} is not executable: {path}")
    return path


def finite_float(value: str | float | int | None) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def split_numeric(value: str | None) -> list[float]:
    if value in (None, "", "NA"):
        return []
    output = []
    for item in value.split(","):
        number = finite_float(item)
        if number is not None:
            output.append(number)
    return output


def method_selection(request: dict[str, Any]) -> dict[str, Any]:
    assay = request.get("assay_class")
    question = request.get("scientific_question")
    discover_novel = bool(request.get("discover_novel_junctions", False))
    complex_events = bool(request.get("complex_local_events", False))
    if assay == "bulk-short-read" and question == "event-level-splicing":
        if complex_events:
            primary = "MAJIQ/VOILA"
            orthogonal = "rMATS"
            reason = "Complex local splice variations require a splice-graph model; rMATS provides a classical event-level check."
        elif discover_novel:
            primary = "LeafCutter or MAJIQ/VOILA"
            orthogonal = "rMATS with --novelSS where appropriate"
            reason = "Novel or annotation-incomplete junction usage should not be restricted to an annotated five-event catalogue."
        else:
            primary = "rMATS-turbo"
            orthogonal = "junction-specific RT-PCR or MAJIQ/LeafCutter for consequential events"
            reason = "Replicate-aware short-read testing of SE, A5SS, A3SS, MXE and RI directly matches the declared question."
    elif assay == "bulk-short-read" and question == "transcript-usage":
        primary = "Salmon/tximport + DRIMSeq + stageR"
        orthogonal = "DEXSeq DTU or SUPPA2"
        reason = "Transcript usage is a gene-to-transcript compositional question, not an exon-event synonym."
    elif assay == "bulk-short-read" and question == "exon-usage":
        primary = "DEXSeq"
        orthogonal = "junction/event analysis for any claimed splice mechanism"
        reason = "Differential exon usage can localize changing counting bins but does not by itself identify a complete isoform switch."
    elif assay in {"single-cell-full-length", "single-cell-droplet", "single-nucleus-three-prime"}:
        if assay == "single-cell-full-length":
            primary = "BRIE2 or sample-aware SpliZ/scQuint"
            reason = "Full-length libraries can retain event-level read evidence when biological samples remain the inferential unit."
        else:
            primary = "sample-level junction candidate screen"
            reason = "Droplet and 3-prime nuclear libraries are sparse and position-biased; junction evidence can nominate candidates but not replace replicated bulk or targeted validation."
        orthogonal = "replicated bulk RNA-seq or junction-specific RT-PCR"
    elif assay == "long-read-rna":
        primary = "FLAIR"
        orthogonal = "short-read junction support and targeted isoform validation"
        reason = "Long reads support full-length isoform discovery, correction, collapse and quantification; differential claims still require replicated sample-level inference."
    else:
        raise WorkflowError("assay_class and scientific_question do not define a supported RNA-processing branch")
    return {
        "primary_method": primary,
        "orthogonal_validation": orthogonal,
        "selection_reason": reason,
        "minimum_sufficient_rule": "one primary analysis plus one decision-relevant orthogonal validation",
    }


def _read_bam_list(path: Path) -> list[Path]:
    values = [Path(value).expanduser().resolve() for value in path.read_text(encoding="utf-8").strip().split(",") if value.strip()]
    if not values or any(not item.is_file() for item in values):
        raise WorkflowError(f"BAM list contains a missing file: {path}")
    if len(set(values)) != len(values):
        raise WorkflowError(f"BAM list contains duplicate biological inputs: {path}")
    return values


def _rmats_command(request: dict[str, Any], output_dir: Path) -> tuple[list[str], dict[str, Any]]:
    executable = require_executable(request.get("rmats_executable"), "rmats_executable")
    b1_file = require_file(request.get("b1_file"), "b1_file")
    b2_file = require_file(request.get("b2_file"), "b2_file")
    gtf = require_file(request.get("gtf"), "gtf")
    b1 = _read_bam_list(b1_file)
    b2 = _read_bam_list(b2_file)
    read_length = request.get("read_length")
    if not isinstance(read_length, int) or read_length <= 0:
        raise WorkflowError("read_length must be a positive integer measured from the admitted libraries")
    read_type = request.get("read_type", "paired")
    library_type = request.get("library_type", "fr-unstranded")
    if read_type not in {"paired", "single"}:
        raise WorkflowError("read_type must be paired or single")
    if library_type not in {"fr-unstranded", "fr-firststrand", "fr-secondstrand"}:
        raise WorkflowError("library_type is not an official rMATS library type")
    if bool(request.get("paired_stats")) and len(b1) != len(b2):
        raise WorkflowError("paired_stats requires equal, correctly ordered groups")
    work_dir = output_dir / "rmats_work"
    result_dir = output_dir / "rmats_results"
    work_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(executable), "--b1", str(b1_file), "--b2", str(b2_file), "--gtf", str(gtf),
        "--od", str(result_dir), "--tmp", str(work_dir), "-t", read_type,
        "--readLength", str(read_length), "--libType", library_type,
        "--nthread", str(int(request.get("threads", 1))), "--task", "both", "--individual-counts",
    ]
    if bool(request.get("variable_read_length")):
        command.append("--variable-read-length")
    if bool(request.get("novel_splice_sites")):
        command.append("--novelSS")
    if bool(request.get("paired_stats")):
        command.append("--paired-stats")
    cstat = finite_float(request.get("cstat", 0.0001))
    if cstat is None or not 0 <= cstat < 1:
        raise WorkflowError("cstat must satisfy 0 <= cstat < 1")
    command.extend(["--cstat", str(cstat)])
    return command, {
        "b1_replicates": len(b1), "b2_replicates": len(b2), "b1_file": b1_file,
        "b2_file": b2_file, "gtf": gtf, "result_dir": result_dir, "work_dir": work_dir,
    }


def _normalize_rmats(result_dir: Path) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for event_type in EVENT_TYPES:
        path = result_dir / f"{event_type}.MATS.JC.txt"
        if not path.is_file():
            raise WorkflowError(f"rMATS output is missing: {path.name}")
        for row in read_tsv(path):
            fdr = finite_float(row.get("FDR"))
            pvalue = finite_float(row.get("PValue"))
            delta = finite_float(row.get("IncLevelDifference"))
            psi1 = split_numeric(row.get("IncLevel1"))
            psi2 = split_numeric(row.get("IncLevel2"))
            ijc1, sjc1 = split_numeric(row.get("IJC_SAMPLE_1")), split_numeric(row.get("SJC_SAMPLE_1"))
            ijc2, sjc2 = split_numeric(row.get("IJC_SAMPLE_2")), split_numeric(row.get("SJC_SAMPLE_2"))
            per_replicate_support = [
                *(left + right for left, right in zip(ijc1, sjc1)),
                *(left + right for left, right in zip(ijc2, sjc2)),
            ]
            normalized.append({
                "event_type": event_type,
                "event_id": row.get("ID", ""),
                "gene_id": row.get("GeneID", "").strip('"'),
                "gene_symbol": row.get("geneSymbol", "").strip('"'),
                "chromosome": row.get("chr", ""),
                "strand": row.get("strand", ""),
                "p_value": "" if pvalue is None else f"{pvalue:.12g}",
                "fdr": "" if fdr is None else f"{fdr:.12g}",
                "delta_psi_group1_minus_group2": "" if delta is None else f"{delta:.8g}",
                "group1_psi": ",".join(f"{value:.6g}" for value in psi1),
                "group2_psi": ",".join(f"{value:.6g}" for value in psi2),
                "min_total_support": min(per_replicate_support or [0]),
            })
    return normalized


def _svg_bulk(rows: list[dict[str, Any]], path: Path, fdr_threshold: float, delta_threshold: float) -> None:
    width, height = 1100, 430
    counts = {kind: sum(row["event_type"] == kind for row in rows) for kind in EVENT_TYPES}
    sig = {
        kind: sum(
            row["event_type"] == kind
            and finite_float(row["fdr"]) is not None and float(row["fdr"]) <= fdr_threshold
            and finite_float(row["delta_psi_group1_minus_group2"]) is not None
            and abs(float(row["delta_psi_group1_minus_group2"])) >= delta_threshold
            for row in rows
        ) for kind in EVENT_TYPES
    }
    ymax = max(counts.values(), default=1) or 1
    points = []
    for row in rows:
        delta = finite_float(row["delta_psi_group1_minus_group2"])
        fdr = finite_float(row["fdr"])
        if delta is None or fdr is None:
            continue
        points.append((delta, min(12.0, -math.log10(max(fdr, 1e-12))), row["event_type"]))
    palette = {"SE": "#3B6FB6", "A5SS": "#D9822B", "A3SS": "#4C956C", "MXE": "#8B5FBF", "RI": "#B94A48"}
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#20242A}.panel{font-size:16px;font-weight:700}.label{font-size:12px}.axis{stroke:#333;stroke-width:1.2}.grid{stroke:#D9DEE5;stroke-width:.8}</style>',
           '<text x="24" y="28" class="panel">a  Tested events</text>',
           '<text x="390" y="28" class="panel">b  Effect size and multiplicity</text>',
           '<text x="825" y="28" class="panel">c  Decision summary</text>']
    base_y, chart_h = 355, 270
    for i, kind in enumerate(EVENT_TYPES):
        x = 45 + i * 62
        bar_h = chart_h * counts[kind] / ymax
        sig_h = chart_h * sig[kind] / ymax
        svg.append(f'<rect x="{x}" y="{base_y-bar_h:.1f}" width="34" height="{bar_h:.1f}" fill="#DCE6F4"/>')
        svg.append(f'<rect x="{x}" y="{base_y-sig_h:.1f}" width="34" height="{sig_h:.1f}" fill="{palette[kind]}"/>')
        svg.append(f'<text x="{x+17}" y="374" text-anchor="middle" class="label">{kind}</text>')
        svg.append(f'<text x="{x+17}" y="{base_y-bar_h-6:.1f}" text-anchor="middle" class="label">{counts[kind]}</text>')
    svg.extend(['<line x1="38" y1="355" x2="355" y2="355" class="axis"/>', '<line x1="38" y1="78" x2="38" y2="355" class="axis"/>'])
    x0, y0, pw, ph = 425, 355, 350, 270
    svg.extend([f'<line x1="{x0}" y1="{y0}" x2="{x0+pw}" y2="{y0}" class="axis"/>', f'<line x1="{x0+pw/2}" y1="{y0-ph}" x2="{x0+pw/2}" y2="{y0}" class="grid"/>'])
    for delta, score, kind in points:
        x = x0 + (max(-1.0, min(1.0, delta)) + 1) / 2 * pw
        y = y0 - score / 12 * ph
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{palette[kind]}" fill-opacity="0.72"/>')
    svg.append(f'<text x="{x0+pw/2}" y="397" text-anchor="middle" class="label">ΔPSI (group 1 − group 2)</text>')
    formal = sum(sig.values())
    summary = [
        f"{len(rows)} events reloaded", f"{formal} pass FDR ≤ {fdr_threshold:g} and |ΔPSI| ≥ {delta_threshold:g}",
        "Biological samples remain the replicate unit", "JC results shown; JCEC retained for sensitivity",
        "Event calls do not prove a direct RNA-processing mechanism",
    ]
    for i, line in enumerate(summary):
        svg.append(f'<text x="835" y="{92+i*48}" class="label">{html.escape(line)}</text>')
    svg.append('</svg>')
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")


def run_bulk_rmats(request: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    command, context = _rmats_command(request, output_dir)
    env = os.environ.copy()
    env["PATH"] = f"{Path(command[0]).parent}:{env.get('PATH', '')}"
    completed = subprocess.run(command, text=True, capture_output=True, env=env, check=False)
    (output_dir / "rmats.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (output_dir / "rmats.stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise WorkflowError(f"rMATS failed with exit code {completed.returncode}; see retained logs")
    rows = _normalize_rmats(context["result_dir"])
    fields = ["event_type", "event_id", "gene_id", "gene_symbol", "chromosome", "strand", "p_value", "fdr", "delta_psi_group1_minus_group2", "group1_psi", "group2_psi", "min_total_support"]
    normalized_path = output_dir / "alternative_splicing_events.tsv"
    write_tsv(normalized_path, rows, fields)
    fdr_threshold = float(request.get("fdr_threshold", 0.05))
    delta_threshold = float(request.get("delta_psi_threshold", 0.1))
    figure_path = output_dir / "alternative_splicing_overview.svg"
    _svg_bulk(rows, figure_path, fdr_threshold, delta_threshold)
    formal_design = context["b1_replicates"] >= 3 and context["b2_replicates"] >= 3
    return {
        "branch": "bulk-rmats", "execution_status": "completed", "scientific_status": "formal-eligible" if formal_design else "candidate",
        "formal_design_gate": formal_design, "event_count": len(rows), "group1_replicates": context["b1_replicates"],
        "group2_replicates": context["b2_replicates"], "backend": "rMATS-turbo", "backend_version": _probe_version(command[0], env),
        "command": command, "outputs": [str(normalized_path), str(figure_path), str(context["result_dir"])],
        "input_digests": {"b1_file": sha256(context["b1_file"]), "b2_file": sha256(context["b2_file"]), "gtf": sha256(context["gtf"])},
        "limitations": ["An rMATS event is not equivalent to a full-length isoform switch.", "Association with binding, chromatin, R-loop or protein-interaction evidence does not establish direct causality."],
    }


def _probe_version(executable: str, env: dict[str, str]) -> str:
    completed = subprocess.run([executable, "--version"], text=True, capture_output=True, env=env, check=False)
    value = (completed.stdout or completed.stderr).strip().splitlines()
    return value[0] if value else "unresolved"


def run_junction_screen(request: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    counts_path = require_file(request.get("junction_counts_tsv"), "junction_counts_tsv")
    rows = read_tsv(counts_path)
    required = {"sample_id", "biological_unit", "condition", "cell_state", "event_id", "event_type", "gene_id", "junction_count", "event_count"}
    if not rows or not required <= set(rows[0]):
        raise WorkflowError(f"junction_counts_tsv must contain: {', '.join(sorted(required))}")
    seen_units: dict[str, str] = {}
    event_rows: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        sample = row["sample_id"]
        unit = row["biological_unit"]
        condition = row["condition"]
        if sample in seen_units and seen_units[sample] != unit:
            raise WorkflowError(f"sample {sample} maps to more than one biological unit")
        seen_units[sample] = unit
        if finite_float(row["junction_count"]) is None or finite_float(row["event_count"]) is None:
            raise WorkflowError("junction_count and event_count must be finite numbers")
        if float(row["junction_count"]) < 0 or float(row["event_count"]) <= 0 or float(row["junction_count"]) > float(row["event_count"]):
            raise WorkflowError("junction counts must satisfy 0 <= junction_count <= event_count")
        key = (row["event_id"], sample)
        if key in event_rows:
            raise WorkflowError(f"duplicate event-by-sample row: {key}")
        event_rows[key] = row
    conditions = sorted({row["condition"] for row in rows})
    if len(conditions) != 2:
        raise WorkflowError("the bounded junction screen currently requires exactly two conditions")
    samples_by_condition = {condition: sorted({row["sample_id"] for row in rows if row["condition"] == condition}) for condition in conditions}
    min_event = int(request.get("min_event_count_per_sample", 20))
    min_junction = int(request.get("min_junction_count_per_sample", 3))
    max_range = float(request.get("max_within_condition_psi_range", 0.2))
    min_delta = float(request.get("min_abs_delta_psi", 0.1))
    output: list[dict[str, Any]] = []
    for event_id in sorted({row["event_id"] for row in rows}):
        event = [row for row in rows if row["event_id"] == event_id]
        by_sample = {row["sample_id"]: row for row in event}
        complete = all(sample in by_sample for sample in samples_by_condition[conditions[0]] + samples_by_condition[conditions[1]])
        psi = {sample: float(row["junction_count"]) / float(row["event_count"]) for sample, row in by_sample.items()}
        values = {condition: [psi[sample] for sample in samples_by_condition[condition] if sample in psi] for condition in conditions}
        means = {condition: statistics.mean(values[condition]) if values[condition] else math.nan for condition in conditions}
        ranges = {condition: max(values[condition]) - min(values[condition]) if values[condition] else math.nan for condition in conditions}
        delta = means[conditions[1]] - means[conditions[0]]
        coverage = complete and all(float(row["event_count"]) >= min_event and float(row["junction_count"]) >= min_junction for row in event)
        repeatability = all(ranges[condition] <= max_range for condition in conditions)
        passed = coverage and repeatability and abs(delta) >= min_delta
        first = event[0]
        output.append({
            "event_id": event_id, "event_type": first["event_type"], "gene_id": first["gene_id"], "cell_state": first["cell_state"],
            f"mean_psi_{conditions[0]}": f"{means[conditions[0]]:.8g}", f"mean_psi_{conditions[1]}": f"{means[conditions[1]]:.8g}",
            f"range_psi_{conditions[0]}": f"{ranges[conditions[0]]:.8g}", f"range_psi_{conditions[1]}": f"{ranges[conditions[1]]:.8g}",
            f"delta_psi_{conditions[1]}_minus_{conditions[0]}": f"{delta:.8g}", "coverage_gate": str(coverage).lower(),
            "repeatability_gate": str(repeatability).lower(), "candidate_pass": str(passed).lower(),
        })
    output.sort(key=lambda row: abs(float(row[f"delta_psi_{conditions[1]}_minus_{conditions[0]}"])), reverse=True)
    fields = list(output[0]) if output else []
    candidate_path = output_dir / "junction_candidate_events.tsv"
    write_tsv(candidate_path, output, fields)
    summary = {
        "branch": "single-cell-junction-screen", "execution_status": "completed", "scientific_status": "candidate",
        "event_count": len(output), "candidate_count": sum(row["candidate_pass"] == "true" for row in output),
        "conditions": conditions, "samples_by_condition": samples_by_condition,
        "claim_boundary": "junction-supported candidate discovery; no cell-level or formal differential-splicing claim",
        "outputs": [str(candidate_path)], "input_digests": {"junction_counts_tsv": sha256(counts_path)},
        "limitations": ["Cells or nuclei are not biological replicates.", "Three-prime coverage and nuclear pre-mRNA can bias junction and intronic evidence.", "Spliced/unspliced velocity layers are not alternative-splicing event evidence."],
    }
    return summary


def run_evidence_integration(request: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    splice_path = require_file(request.get("splicing_events_tsv"), "splicing_events_tsv")
    ledger_path = require_file(request.get("evidence_ledger_tsv"), "evidence_ledger_tsv")
    splice_rows = read_tsv(splice_path)
    ledger = read_tsv(ledger_path)
    if not splice_rows or "gene_id" not in splice_rows[0]:
        raise WorkflowError("splicing event table must contain gene_id")
    required = {"gene_id", "evidence_type", "evidence_status", "source_artifact_id"}
    if not ledger or not required <= set(ledger[0]):
        raise WorkflowError(f"evidence ledger must contain: {', '.join(sorted(required))}")
    by_gene: dict[str, list[dict[str, str]]] = {}
    for row in ledger:
        by_gene.setdefault(row["gene_id"], []).append(row)
    output = []
    for event in splice_rows:
        linked = by_gene.get(event["gene_id"], [])
        evidence_types = sorted({row["evidence_type"] for row in linked})
        output.append({
            **event,
            "linked_evidence_types": ";".join(evidence_types),
            "linked_source_artifacts": ";".join(sorted({row["source_artifact_id"] for row in linked})),
            "integration_class": "multi-assay-candidate" if linked else "splicing-only",
            "causal_status": "unresolved",
        })
    path = output_dir / "rna_processing_evidence_integration.tsv"
    fields = list(output[0]) if output else list(splice_rows[0]) + ["linked_evidence_types", "linked_source_artifacts", "integration_class", "causal_status"]
    write_tsv(path, output, fields)
    return {
        "branch": "evidence-integration", "execution_status": "completed", "scientific_status": "candidate",
        "event_count": len(output), "linked_event_count": sum(row["integration_class"] == "multi-assay-candidate" for row in output),
        "outputs": [str(path)], "input_digests": {"splicing_events_tsv": sha256(splice_path), "evidence_ledger_tsv": sha256(ledger_path)},
        "claim_boundary": "co-located or gene-linked evidence only; direct RNA-processing causality remains unresolved",
    }


def run_design(request: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    selection = method_selection(request)
    return {
        "branch": "design", "execution_status": "completed", "scientific_status": "design-only", **selection,
        "required_design_fields": ["biological sample", "condition", "pairing", "library layout", "strandedness", "read length", "reference genome", "annotation release"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    request = read_json(args.request.resolve())
    if request.get("schema_version") != 1 or request.get("module_id") != MODULE_ID:
        raise WorkflowError(f"request must target {MODULE_ID} schema version 1")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    branch = request.get("analysis_branch")
    if branch == "design":
        report = run_design(request, output_dir)
    elif branch == "bulk-rmats":
        report = run_bulk_rmats(request, output_dir)
    elif branch == "single-cell-junction-screen":
        report = run_junction_screen(request, output_dir)
    elif branch == "evidence-integration":
        report = run_evidence_integration(request, output_dir)
    else:
        raise WorkflowError("analysis_branch must be design, bulk-rmats, single-cell-junction-screen, or evidence-integration")
    report.update({
        "schema_version": 1, "module_id": MODULE_ID, "module_version": MODULE_VERSION,
        "request_sha256": sha256(args.request.resolve()),
    })
    report_path = output_dir / "rna_processing_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    reloaded = read_json(report_path)
    if reloaded.get("module_id") != MODULE_ID or reloaded.get("execution_status") != "completed":
        raise WorkflowError("written report failed independent reload")
    print(json.dumps({"report": str(report_path), "branch": branch, "scientific_status": report["scientific_status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
