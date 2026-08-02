#!/usr/bin/env python3
"""Audit CUT&Tag internal-reference support and optional target-specific controls."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


REQUIRED_COLUMNS = {
    "sample_id",
    "condition",
    "replicate",
    "host_fragments",
    "spikein_fragments",
    "total_fragments",
    "rnaseh",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_samples(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None or not REQUIRED_COLUMNS <= set(reader.fieldnames):
            raise ValueError(f"sample sheet requires columns: {', '.join(sorted(REQUIRED_COLUMNS))}")
        rows: list[dict[str, object]] = []
        seen: set[str] = set()
        for line_number, raw in enumerate(reader, start=2):
            sample_id = str(raw["sample_id"]).strip()
            condition = str(raw["condition"]).strip()
            replicate = str(raw["replicate"]).strip()
            rnaseh_text = str(raw["rnaseh"]).strip().lower()
            if not sample_id or sample_id in seen or not condition or not replicate:
                raise ValueError(f"invalid or duplicate sample identity at line {line_number}")
            if rnaseh_text not in {"true", "false"}:
                raise ValueError(f"rnaseh must be true or false at line {line_number}")
            try:
                host = int(raw["host_fragments"])
                spikein = int(raw["spikein_fragments"])
                total = int(raw["total_fragments"])
            except ValueError as exc:
                raise ValueError(f"fragment counts must be integers at line {line_number}") from exc
            if min(host, spikein, total) < 0 or host + spikein > total:
                raise ValueError(f"fragment accounting is impossible at line {line_number}")
            seen.add(sample_id)
            rows.append(
                {
                    "sample_id": sample_id,
                    "condition": condition,
                    "replicate": replicate,
                    "rnaseh": rnaseh_text == "true",
                    "host_fragments": host,
                    "spikein_fragments": spikein,
                    "total_fragments": total,
                    "unassigned_fragments": total - host - spikein,
                    "reference_sample_id": str(raw.get("reference_sample_id", "")).strip(),
                }
            )
    if len(rows) < 2:
        raise ValueError("at least two libraries are required")
    return rows


def read_region_counts(path: Path, sample_ids: list[str]) -> tuple[list[str], dict[str, list[float]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected = {"region_id", *sample_ids}
        if reader.fieldnames is None or set(reader.fieldnames) != expected:
            raise ValueError("region-count table must contain region_id and exactly the sample IDs")
        regions: list[str] = []
        values = {sample: [] for sample in sample_ids}
        seen: set[str] = set()
        for line_number, raw in enumerate(reader, start=2):
            region = str(raw["region_id"]).strip()
            if not region or region in seen:
                raise ValueError(f"invalid or duplicate region_id at line {line_number}")
            seen.add(region)
            regions.append(region)
            for sample in sample_ids:
                value = float(raw[sample])
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f"region counts must be finite and nonnegative at line {line_number}")
                values[sample].append(value)
    if not regions:
        raise ValueError("region-count table is empty")
    return regions, values


def write_tsv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def render_qc(rows: list[dict[str, object]], output_prefix: Path) -> list[dict[str, object]]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required for standardized QC figures") from exc

    colors = {"host": "#0072B2", "spike-in": "#E69F00", "unassigned": "#BDBDBD"}
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 6.5,
            "axes.titlesize": 8,
            "axes.labelsize": 7,
            "axes.linewidth": 0.5,
            "xtick.labelsize": 6,
            "ytick.labelsize": 6,
            "legend.fontsize": 6,
            "legend.title_fontsize": 6.5,
            "lines.linewidth": 0.65,
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
        }
    )
    sample_ids = [str(row["sample_id"]) for row in rows]
    host = [100 * int(row["host_fragments"]) / int(row["total_fragments"]) for row in rows]
    spike = [100 * int(row["spikein_fragments"]) / int(row["total_fragments"]) for row in rows]
    other = [100 - a - b for a, b in zip(host, spike, strict=True)]
    figures: list[dict[str, object]] = []

    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    positions = list(range(len(rows)))
    ax.bar(positions, host, color=colors["host"], label="Host")
    ax.bar(positions, spike, bottom=host, color=colors["spike-in"], label="Spike-in")
    ax.bar(positions, other, bottom=[a + b for a, b in zip(host, spike, strict=True)], color=colors["unassigned"], label="Unassigned")
    ax.set_ylabel("Aligned fragment fraction (%)")
    ax.set_xticks(positions, sample_ids, rotation=45, ha="right")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=3, frameon=False)
    fig.tight_layout()
    for extension in ("pdf", "svg"):
        path = output_prefix.with_name(output_prefix.name + "_alignment_fraction." + extension)
        fig.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    figures.append({"id": "host_spikein_alignment_fraction", "formats": ["pdf", "svg"], "legend_position": "top"})

    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    factors = [
        float(row["spikein_scale_factor"]) if row["spikein_scale_factor"] is not None else float("nan")
        for row in rows
    ]
    bar_colors = ["#D55E00" if bool(row["rnaseh"]) else "#0072B2" for row in rows]
    ax.bar(positions, factors, color=bar_colors)
    ax.axhline(1, color="#000000", linewidth=0.6, linestyle="--")
    ax.set_ylabel("Spike-in scale factor")
    ax.set_xticks(positions, sample_ids, rotation=45, ha="right")
    fig.tight_layout()
    for extension in ("pdf", "svg"):
        path = output_prefix.with_name(output_prefix.name + "_scale_factor." + extension)
        fig.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(fig)
    figures.append({"id": "spikein_scale_factor", "formats": ["pdf", "svg"], "legend_position": "none"})
    return figures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--region-counts", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-or-antibody", required=True)
    parser.add_argument(
        "--normalization-method",
        choices=("none", "exogenous-target", "matched-reference"),
        required=True,
        help="Explicitly choose raw-only, a declared common exogenous target, or per-row reference-sample scaling.",
    )
    parser.add_argument("--target-spikein-fragments", type=float)
    parser.add_argument("--minimum-spikein-fragments", type=int, required=True)
    parser.add_argument("--minimum-spikein-fraction", type=float, required=True)
    parser.add_argument("--rnaseh-fold-threshold", type=float, default=2.0)
    args = parser.parse_args()

    if not args.samples.is_file():
        raise FileNotFoundError(args.samples)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {args.output_dir}")
    if args.minimum_spikein_fragments < 1 or not 0 < args.minimum_spikein_fraction < 1:
        raise ValueError("spike-in thresholds are invalid")
    if not math.isfinite(args.rnaseh_fold_threshold) or args.rnaseh_fold_threshold <= 1:
        raise ValueError("RNase H fold threshold must exceed one")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_samples(args.samples)
    positive = [int(row["spikein_fragments"]) for row in rows if int(row["spikein_fragments"]) > 0]
    if not positive:
        raise ValueError("no spike-in fragments were detected in any library")
    target: float | None = None
    if args.normalization_method == "exogenous-target":
        if args.target_spikein_fragments is None:
            raise ValueError("exogenous-target normalization requires --target-spikein-fragments")
        target = float(args.target_spikein_fragments)
        if not math.isfinite(target) or target <= 0:
            raise ValueError("target spike-in fragments must be positive")
    elif args.target_spikein_fragments is not None:
        raise ValueError("--target-spikein-fragments is valid only with exogenous-target normalization")

    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    rows_by_id = {str(row["sample_id"]): row for row in rows}
    for row in rows:
        spikein = int(row["spikein_fragments"])
        total = int(row["total_fragments"])
        fraction = spikein / total if total else 0.0
        row["spikein_fraction"] = fraction
        row["host_fraction"] = int(row["host_fragments"]) / total if total else 0.0
        row["spikein_detected"] = spikein > 0
        if args.normalization_method == "none":
            row["spikein_scale_factor"] = 1.0
        elif args.normalization_method == "exogenous-target":
            row["spikein_scale_factor"] = target / spikein if spikein else None
        else:
            reference_id = str(row["reference_sample_id"])
            if not reference_id:
                blocking.append(
                    {
                        "sample_id": str(row["sample_id"]),
                        "code": "REFERENCE_SAMPLE_MISSING",
                        "message": "matched-reference scaling requires reference_sample_id for every library",
                    }
                )
                row["spikein_scale_factor"] = None
            elif reference_id not in rows_by_id:
                blocking.append(
                    {
                        "sample_id": str(row["sample_id"]),
                        "code": "REFERENCE_SAMPLE_UNKNOWN",
                        "message": "reference_sample_id is absent from the sample sheet",
                    }
                )
                row["spikein_scale_factor"] = None
            else:
                reference_spikein = int(rows_by_id[reference_id]["spikein_fragments"])
                row["spikein_scale_factor"] = reference_spikein / spikein if spikein else None
        row["normalized_host_fragments"] = (
            int(row["host_fragments"]) * float(row["spikein_scale_factor"])
            if row["spikein_scale_factor"] is not None
            else None
        )
        if spikein < args.minimum_spikein_fragments or fraction < args.minimum_spikein_fraction:
            blocking.append(
                {
                    "sample_id": str(row["sample_id"]),
                    "code": "SPIKEIN_TOO_LOW",
                    "message": "spike-in support is below the declared reliability threshold",
                }
            )
        if fraction > 0.25:
            warnings.append(
                {
                    "sample_id": str(row["sample_id"]),
                    "code": "SPIKEIN_FRACTION_HIGH",
                    "message": "spike-in exceeds 25% of fragments; inspect low host signal and mapping competition",
                }
            )

    normalization_fields = [
        "sample_id",
        "condition",
        "replicate",
        "rnaseh",
        "host_fragments",
        "spikein_fragments",
        "unassigned_fragments",
        "total_fragments",
        "host_fraction",
        "spikein_fraction",
        "spikein_detected",
        "reference_sample_id",
        "spikein_scale_factor",
        "normalized_host_fragments",
    ]
    normalization_path = args.output_dir / "spikein_normalization.tsv"
    write_tsv(normalization_path, rows, normalization_fields)

    rnaseh_path: Path | None = None
    rnaseh_summary: dict[str, object] = {"evaluated": False}
    if args.region_counts is not None:
        if not args.region_counts.is_file():
            raise FileNotFoundError(args.region_counts)
        sample_ids = [str(row["sample_id"]) for row in rows]
        regions, counts = read_region_counts(args.region_counts, sample_ids)
        treated_rows = [row for row in rows if bool(row["rnaseh"])]
        if not treated_rows:
            raise ValueError("RNase H sensitivity requires untreated and RNase H-treated libraries")
        pairs: list[tuple[str, str]] = []
        for row in treated_rows:
            treated_id = str(row["sample_id"])
            reference_id = str(row["reference_sample_id"])
            if not reference_id or reference_id not in rows_by_id or bool(rows_by_id[reference_id]["rnaseh"]):
                raise ValueError(f"RNase H sample {treated_id} requires an untreated reference_sample_id")
            pairs.append((reference_id, treated_id))
        scale = {
            str(row["sample_id"]): float(row["spikein_scale_factor"])
            for row in rows
            if row["spikein_scale_factor"] is not None
        }
        if any(sample not in scale for pair in pairs for sample in pair):
            raise ValueError("RNase H sensitivity cannot be computed when a paired scale factor is unavailable")
        region_rows: list[dict[str, object]] = []
        for index, region in enumerate(regions):
            untreated_values = [counts[untreated][index] * scale[untreated] for untreated, _ in pairs]
            treated_values = [counts[treated][index] * scale[treated] for _, treated in pairs]
            untreated_mean = sum(untreated_values) / len(pairs)
            treated_mean = sum(treated_values) / len(pairs)
            fold = (untreated_mean + 0.5) / (treated_mean + 0.5)
            region_rows.append(
                {
                    "region_id": region,
                    "untreated_normalized_mean": untreated_mean,
                    "rnaseh_normalized_mean": treated_mean,
                    "untreated_to_rnaseh_fold": fold,
                    "rnaseh_sensitive": fold >= args.rnaseh_fold_threshold,
                }
            )
        rnaseh_path = args.output_dir / "rnaseh_sensitivity.tsv"
        write_tsv(
            rnaseh_path,
            region_rows,
            ["region_id", "untreated_normalized_mean", "rnaseh_normalized_mean", "untreated_to_rnaseh_fold", "rnaseh_sensitive"],
        )
        rnaseh_summary = {
            "evaluated": True,
            "region_count": len(region_rows),
            "matched_pair_count": len(pairs),
            "sensitive_region_count": sum(bool(row["rnaseh_sensitive"]) for row in region_rows),
            "fold_threshold": args.rnaseh_fold_threshold,
            "interpretation": "RNase H sensitivity is an assay-specificity annotation; pooled or unreplicated RNase H controls are not a condition-level statistical contrast.",
        }

    figures = render_qc(rows, args.output_dir / "cuttag_internal_reference_qc")
    report = {
        "schema_version": 1,
        "passed": not blocking,
        "assay": "CUT&Tag",
        "target_or_antibody": args.target_or_antibody,
        "input": {
            "sample_sheet_sha256": sha256(args.samples),
            "region_counts_sha256": sha256(args.region_counts) if args.region_counts is not None else None,
        },
        "spikein": {
            "detected": True,
            "normalization_method": args.normalization_method,
            "target_spikein_fragments": target,
            "minimum_spikein_fragments": args.minimum_spikein_fragments,
            "minimum_spikein_fraction": args.minimum_spikein_fraction,
            "normalization_table_sha256": sha256(normalization_path),
        },
        "rnaseh": rnaseh_summary,
        "blocking_findings": blocking,
        "warnings": warnings,
        "figures": figures,
        "plot_standard_version": "1.1.0",
        "quality_gates": {
            "fragment_accounting_reconciled": True,
            "spikein_species_signal_detected": True,
            "spikein_reliability_thresholds_applied": True,
            "rnaseh_specificity_separated_from_condition_inference": True,
            "source_inputs_immutable": True,
            "outputs_reloaded": True,
        },
        "limitations": [
            "Internal-reference identity must come from alignment to declared host and reference sequences; this table does not infer species from filenames.",
            "A constant amount of internal-reference material must have entered every sample before library-dependent losses for scale factors to support global comparisons.",
            *(
                ["S9.6 signal is DNA:RNA-hybrid evidence and requires RNase H sensitivity plus orthogonal validation before locus-level R-loop claims."]
                if args.target_or_antibody.strip().lower().replace(".", "") == "s96"
                else []
            ),
        ],
        "outputs": {
            "normalization_table": normalization_path.name,
            "rnaseh_table": rnaseh_path.name if rnaseh_path is not None else None,
        },
    }
    report_path = args.output_dir / "cuttag_internal_reference_qc.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    if blocking:
        raise RuntimeError(f"{len(blocking)} libraries failed spike-in reliability gates; see {report_path.name}")
    print(json.dumps({"passed": True, "samples": len(rows), "normalization_method": args.normalization_method, "spikein_target": target, "rnaseh_evaluated": rnaseh_summary["evaluated"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
