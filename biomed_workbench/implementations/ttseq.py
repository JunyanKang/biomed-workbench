"""TT-seq abundance profiling and calibrated kinetic-rate estimation."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METHOD_DOI = "10.1126/science.aad9841"


class TTSeqExecutionError(ValueError):
    """Raised when TT-seq quantitative inputs or inferred rates are invalid."""


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise TTSeqExecutionError(f"{label} must be a local path")
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise TTSeqExecutionError(f"{label} must be a readable non-symlink file: {path}")
    return path.resolve()


def _metadata(path: Path) -> list[dict[str, Any]]:
    required = {
        "sample_id", "condition", "biological_replicate", "component",
        "labeling_minutes",
    }
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames or not required <= set(reader.fieldnames):
            raise TTSeqExecutionError("metadata lacks required TT-seq pairing and spike-in columns")
        rows = list(reader)
    if not rows:
        raise TTSeqExecutionError("metadata is empty")
    seen: set[str] = set()
    parsed: list[dict[str, Any]] = []
    for line, row in enumerate(rows, 2):
        sample = str(row["sample_id"]).strip()
        component = str(row["component"]).strip().lower()
        if not sample or sample in seen or component not in {"new", "total"}:
            raise TTSeqExecutionError(f"invalid sample identity or component at metadata line {line}")
        seen.add(sample)
        try:
            minutes = float(row["labeling_minutes"])
            spikein_reads = float(row["spikein_reads"]) if str(row.get("spikein_reads", "")).strip() else None
            spikein_amount = float(row["spikein_amount"]) if str(row.get("spikein_amount", "")).strip() else None
        except ValueError as exc:
            raise TTSeqExecutionError(f"non-numeric TT-seq metadata at line {line}") from exc
        if minutes <= 0 or (spikein_reads is not None and spikein_reads <= 0) or (spikein_amount is not None and spikein_amount <= 0):
            raise TTSeqExecutionError(f"labeling time and any declared spike-in values must be positive at line {line}")
        if (spikein_reads is None) != (spikein_amount is None):
            raise TTSeqExecutionError(f"spikein_reads and spikein_amount must be declared together at line {line}")
        parsed.append({
            "sample_id": sample,
            "condition": str(row["condition"]).strip(),
            "biological_replicate": str(row["biological_replicate"]).strip(),
            "component": component,
            "spikein_reads": spikein_reads,
            "spikein_amount": spikein_amount,
            "labeling_minutes": minutes,
        })
    pairs: dict[tuple[str, str], set[str]] = {}
    for row in parsed:
        key = (row["condition"], row["biological_replicate"])
        pairs.setdefault(key, set()).add(row["component"])
    invalid = [key for key, components in pairs.items() if components != {"new", "total"}]
    if invalid or len(parsed) != 2 * len(pairs):
        raise TTSeqExecutionError("every condition and biological replicate requires exactly one new and one total library")
    return parsed


def _median_ratio_scales(
    counts_rows: list[dict[str, str]],
    samples: list[str],
    metadata: list[dict[str, Any]],
) -> dict[str, float]:
    """Return DESeq-style median-ratio multipliers, fitted within each component."""
    scale: dict[str, float] = {}
    for component in ("new", "total"):
        component_samples = [row["sample_id"] for row in metadata if row["component"] == component]
        ratios: dict[str, list[float]] = {sample: [] for sample in component_samples}
        for raw in counts_rows:
            values = [float(raw[sample]) for sample in component_samples]
            if not values or any(value <= 0 or not math.isfinite(value) for value in values):
                continue
            geometric_mean = math.exp(sum(math.log(value) for value in values) / len(values))
            for sample, value in zip(component_samples, values, strict=True):
                ratios[sample].append(value / geometric_mean)
        for sample in component_samples:
            if not ratios[sample]:
                raise TTSeqExecutionError(
                    f"median-ratio normalization has no jointly positive features for component={component}"
                )
            size_factor = statistics.median(ratios[sample])
            if not math.isfinite(size_factor) or size_factor <= 0:
                raise TTSeqExecutionError(f"invalid median-ratio size factor for {sample}")
            scale[sample] = 1.0 / size_factor
    return scale


def execute_ttseq(request: dict[str, Any], *, output_dir: Path, report_path: Path) -> dict[str, Any]:
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-nascent-transcription":
        raise TTSeqExecutionError("request must target bulk-nascent-transcription schema version 1")
    if str(request.get("assay", "")).lower() != "tt-seq":
        raise TTSeqExecutionError("this executor accepts only assay=tt-seq")
    counts_path = _file(request.get("counts_tsv"), "counts_tsv")
    metadata_path = _file(request.get("metadata_tsv"), "metadata_tsv")
    parameters = request.get("parameters", {})
    if not isinstance(parameters, dict) or set(parameters) - {
        "analysis_mode", "normalization", "capture_efficiency", "minimum_total_count", "maximum_half_life_hours"
    }:
        raise TTSeqExecutionError("unknown TT-seq parameter")
    analysis_mode = str(parameters.get("analysis_mode", "auto")).lower()
    normalization = str(parameters.get("normalization", "auto")).lower()
    if analysis_mode not in {"auto", "relative-profile", "kinetics"}:
        raise TTSeqExecutionError("analysis_mode must be auto, relative-profile, or kinetics")
    if normalization not in {"auto", "median-ratio", "spike-in"}:
        raise TTSeqExecutionError("normalization must be auto, median-ratio, or spike-in")
    capture_efficiency = float(parameters.get("capture_efficiency", 1.0))
    minimum_total = float(parameters.get("minimum_total_count", 10))
    maximum_half_life = float(parameters.get("maximum_half_life_hours", 1000))
    if not 0 < capture_efficiency <= 1 or minimum_total < 0 or maximum_half_life <= 0:
        raise TTSeqExecutionError("TT-seq quantitative parameters are outside valid ranges")
    metadata = _metadata(metadata_path)
    samples = [row["sample_id"] for row in metadata]
    with counts_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames or reader.fieldnames[0] != "feature_id" or set(reader.fieldnames[1:]) != set(samples):
            raise TTSeqExecutionError("counts table must contain feature_id and exactly the metadata sample IDs")
        counts_rows = list(reader)
    if not counts_rows:
        raise TTSeqExecutionError("counts table is empty")
    has_spikein = all(row["spikein_reads"] is not None and row["spikein_amount"] is not None for row in metadata)
    if any(row["spikein_reads"] is not None or row["spikein_amount"] is not None for row in metadata) and not has_spikein:
        raise TTSeqExecutionError("spike-in calibration must be complete for every library or omitted for every library")
    if analysis_mode == "auto":
        analysis_mode = "kinetics" if has_spikein else "relative-profile"
    if normalization == "auto":
        normalization = "spike-in" if has_spikein else "median-ratio"
    if analysis_mode == "kinetics" and (not has_spikein or normalization != "spike-in"):
        raise TTSeqExecutionError("kinetics mode requires complete spike-in calibration and normalization=spike-in")
    if normalization == "spike-in" and not has_spikein:
        raise TTSeqExecutionError("normalization=spike-in requires spike-in reads and amount for every library")
    if normalization == "spike-in":
        ratios = [row["spikein_reads"] / row["spikein_amount"] for row in metadata]
        target_ratio = statistics.median(ratios)
        scale = {row["sample_id"]: target_ratio / (row["spikein_reads"] / row["spikein_amount"]) for row in metadata}
    else:
        scale = _median_ratio_scales(counts_rows, samples, metadata)
    metadata_by_pair = {
        (row["condition"], row["biological_replicate"], row["component"]): row
        for row in metadata
    }
    if output_dir.exists() or report_path.exists():
        raise TTSeqExecutionError("output directory and report path must not already exist")
    output_dir.mkdir(parents=True)
    scale_path = output_dir / "ttseq_scale_factors.tsv"
    with scale_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("sample_id", "condition", "biological_replicate", "component", "normalization", "spikein_reads", "spikein_amount", "scale_factor"))
        for row in metadata:
            writer.writerow((row["sample_id"], row["condition"], row["biological_replicate"], row["component"], normalization, "" if row["spikein_reads"] is None else row["spikein_reads"], "" if row["spikein_amount"] is None else row["spikein_amount"], f"{scale[row['sample_id']]:.12g}"))
    rates_path = output_dir / "ttseq_feature_estimates.tsv"
    statuses: dict[str, int] = {}
    output_rows = 0
    with rates_path.open("w", encoding="utf-8", newline="") as handle:
        fields = (
            "feature_id", "condition", "biological_replicate", "new_normalized", "total_normalized",
            "new_to_total_ratio", "new_fraction", "degradation_rate_per_hour", "synthesis_rate_per_hour", "half_life_hours", "status",
        )
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        seen_features: set[str] = set()
        for raw in counts_rows:
            feature = str(raw["feature_id"]).strip()
            if not feature or feature in seen_features:
                raise TTSeqExecutionError("feature_id values must be nonempty and unique")
            seen_features.add(feature)
            try:
                counts = {sample: float(raw[sample]) for sample in samples}
            except ValueError as exc:
                raise TTSeqExecutionError(f"non-numeric count for feature {feature}") from exc
            if any(not math.isfinite(value) or value < 0 for value in counts.values()):
                raise TTSeqExecutionError(f"counts must be finite and nonnegative for feature {feature}")
            pair_keys = sorted({(row["condition"], row["biological_replicate"]) for row in metadata})
            for condition, replicate in pair_keys:
                new_meta = metadata_by_pair[(condition, replicate, "new")]
                total_meta = metadata_by_pair[(condition, replicate, "total")]
                new_value = counts[new_meta["sample_id"]] * scale[new_meta["sample_id"]] / capture_efficiency
                total_value = counts[total_meta["sample_id"]] * scale[total_meta["sample_id"]]
                status = "estimated" if analysis_mode == "kinetics" else "relative_profile"
                fraction = degradation = synthesis = half_life = None
                ratio = None if total_value <= 0 else new_value / total_value
                if total_value < minimum_total:
                    status = "low_total_support"
                elif new_value <= 0:
                    status = "no_new_rna_signal"
                elif analysis_mode == "kinetics":
                    fraction = ratio
                    if not 0 < fraction < 1:
                        status = "new_fraction_outside_open_unit_interval"
                    else:
                        pulse_hours = new_meta["labeling_minutes"] / 60.0
                        if abs(new_meta["labeling_minutes"] - total_meta["labeling_minutes"]) > 1e-9:
                            raise TTSeqExecutionError("paired new and total libraries must declare the same labeling time")
                        degradation = -math.log1p(-fraction) / pulse_hours
                        synthesis = degradation * total_value
                        half_life = math.log(2) / degradation
                        if half_life > maximum_half_life:
                            status = "half_life_above_reporting_cap"
                statuses[status] = statuses.get(status, 0) + 1
                writer.writerow({
                    "feature_id": feature, "condition": condition, "biological_replicate": replicate,
                    "new_normalized": f"{new_value:.12g}", "total_normalized": f"{total_value:.12g}",
                    "new_to_total_ratio": "" if ratio is None else f"{ratio:.12g}",
                    "new_fraction": "" if fraction is None else f"{fraction:.12g}",
                    "degradation_rate_per_hour": "" if degradation is None else f"{degradation:.12g}",
                    "synthesis_rate_per_hour": "" if synthesis is None else f"{synthesis:.12g}",
                    "half_life_hours": "" if half_life is None else f"{half_life:.12g}", "status": status,
                })
                output_rows += 1
    implementation = Path(__file__).resolve()
    report = {
        "schema_version": 1, "module_id": "bulk-nascent-transcription", "assay": "tt-seq", "passed": True,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "method": {
            "name": "TT-seq relative abundance profiling and calibrated steady-state pulse kinetics", "doi": METHOD_DOI,
            "equations": {"degradation_rate": "-log(1-new_fraction)/pulse_hours", "synthesis_rate": "degradation_rate*total_abundance", "half_life": "log(2)/degradation_rate"},
            "assumptions": ["matched new and total libraries", "kinetic estimates additionally require steady state, spike-in proportionality, and declared capture efficiency"],
        },
        "implementation": {"path": str(implementation.relative_to(implementation.parents[2])), "sha256": sha256(implementation)},
        "inputs": {"counts": {"path": str(counts_path), "sha256": sha256(counts_path)}, "metadata": {"path": str(metadata_path), "sha256": sha256(metadata_path)}},
        "parameters": {"analysis_mode": analysis_mode, "normalization": normalization, "capture_efficiency": capture_efficiency, "minimum_total_count": minimum_total, "maximum_half_life_hours": maximum_half_life},
        "status_counts": statuses,
        "outputs": {
            "scale_factors": {"path": str(scale_path), "sha256": sha256(scale_path), "rows": len(metadata)},
            "feature_estimates": {"path": str(rates_path), "sha256": sha256(rates_path), "rows": output_rows},
            "kinetic_rates": {"path": str(rates_path), "sha256": sha256(rates_path), "rows": output_rows if analysis_mode == "kinetics" else 0},
        },
        "interpretation_scope": "Relative-profile mode reports normalized new and total RNA signal without converting it into kinetic rates. Kinetics mode reports rates only when matched spike-in calibration, labeling time, capture efficiency and steady-state assumptions are supplied.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
