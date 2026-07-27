"""Quantitative wet-lab assay analysis with explicit calibration and QC."""

from __future__ import annotations

import base64
from io import BytesIO
import math
import os
from pathlib import Path
from collections import defaultdict
from statistics import median
from typing import Any


def _finite(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def _sample_sd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    center = _mean(values)
    return math.sqrt(math.fsum((value - center) ** 2 for value in values) / (len(values) - 1))


def import_fcs_events(
    fcs_path: str | None = None,
    fcs_base64: str | None = None,
    max_events: int = 100_000,
) -> dict[str, Any]:
    """Parse one FCS file into a complete, JSON-safe event table.

    This deliberately refuses over-limit files rather than silently sampling
    events: downstream gate frequencies must retain their declared denominator.
    """
    supplied = int(bool(fcs_path and fcs_path.strip())) + int(bool(fcs_base64 and fcs_base64.strip()))
    if supplied != 1:
        raise ValueError("provide exactly one of fcs_path or fcs_base64")
    if isinstance(max_events, bool) or not isinstance(max_events, int) or not 1 <= max_events <= 100_000:
        raise ValueError("max_events must be an integer from 1 to 100000")

    if fcs_base64 and fcs_base64.strip():
        try:
            payload = base64.b64decode(fcs_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("fcs_base64 is not valid base64") from exc
        if not payload:
            raise ValueError("FCS payload is empty")
        source = BytesIO(payload)
        source_name = "in-memory.fcs"
    else:
        candidate = Path(os.path.expanduser(str(fcs_path))).resolve()
        if candidate.is_symlink() or not candidate.is_file() or candidate.suffix.lower() != ".fcs":
            raise ValueError("fcs_path must be a regular .fcs file")
        if candidate.stat().st_size == 0:
            raise ValueError("FCS file is empty")
        source = candidate
        source_name = candidate.name

    try:
        from flowio import FlowData
    except ImportError as exc:
        raise RuntimeError("flowio is required to import FCS files") from exc
    try:
        flow_data = FlowData(source)
    except Exception as exc:
        raise ValueError(f"could not parse FCS data: {exc}") from exc

    channel_names = [str(name).strip() for name in flow_data.pnn_labels]
    if not channel_names or len(channel_names) != flow_data.channel_count or len(set(channel_names)) != len(channel_names):
        raise ValueError("FCS channels must have unique nonempty PnN labels")
    if flow_data.event_count < 1:
        raise ValueError("FCS file contains no events")
    if flow_data.event_count > max_events:
        raise ValueError(
            f"FCS contains {flow_data.event_count} events, above the declared JSON handoff limit of {max_events}; "
            "use an external cytometry workflow that preserves all events and gate provenance"
        )
    expected_values = flow_data.event_count * flow_data.channel_count
    if len(flow_data.events) != expected_values:
        raise ValueError("FCS event payload does not match its declared event and channel counts")

    events = []
    for row_start in range(0, expected_values, flow_data.channel_count):
        row = {
            channel: _finite(flow_data.events[row_start + offset], f"FCS value for {channel}")
            for offset, channel in enumerate(channel_names)
        }
        events.append(row)
    metadata = {
        key: str(flow_data.text[key])
        for key in ("cyt", "date", "btim", "etim", "sys", "cytsn")
        if key in flow_data.text and str(flow_data.text[key]).strip()
    }
    return {
        "source_name": source_name,
        "fcs_version": str(flow_data.version),
        "event_count": flow_data.event_count,
        "channels": channel_names,
        "metadata": metadata,
        "events": events,
        "quality_gates": [
            "Input is parsed without event subsampling; event_count is the denominator for downstream gates.",
            "Apply compensation and an explicitly declared transformation before biological threshold gating when required.",
            "Retain acquisition, panel, controls, gate definitions, replicate identity, and the original FCS file outside this JSON handoff.",
        ],
    }


def summarize_dye_dilution_proliferation(
    generation_events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate CFSE/CellTrace proliferation metrics from reviewed generations.

    Peak fitting and gate assignment are intentionally external to this bounded
    calculation. A generation's observed event count is converted to a
    precursor-cell equivalent by division by ``2 ** generation``.
    """
    if not isinstance(generation_events, list) or not generation_events:
        raise ValueError("generation_events must be a nonempty array")
    generations: dict[int, int] = {}
    for row in generation_events:
        if not isinstance(row, dict):
            raise ValueError("generation events must be objects")
        generation = row.get("generation")
        event_count = row.get("event_count")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
            raise ValueError("generation must be a nonnegative integer")
        if isinstance(event_count, bool) or not isinstance(event_count, int) or event_count < 0:
            raise ValueError("event_count must be a nonnegative integer")
        if generation in generations:
            raise ValueError("each generation may be supplied only once")
        generations[generation] = event_count
    if not any(generations.values()):
        raise ValueError("at least one generation must contain events")

    rows = []
    total_events = sum(generations.values())
    precursor_equivalent = 0.0
    total_divisions = 0.0
    divided_precursors = 0.0
    for generation in sorted(generations):
        events = generations[generation]
        equivalent = events / (2 ** generation)
        precursor_equivalent += equivalent
        total_divisions += generation * equivalent
        if generation > 0:
            divided_precursors += equivalent
        rows.append(
            {
                "generation": generation,
                "event_count": events,
                "event_percent": 100.0 * events / total_events,
                "precursor_equivalent": equivalent,
            }
        )
    undivided = generations.get(0, 0)
    return {
        "generation_summary": rows,
        "total_observed_events": total_events,
        "precursor_equivalent_count": precursor_equivalent,
        "undivided_precursor_equivalent": float(undivided),
        "divided_precursor_equivalent": divided_precursors,
        "percent_divided": 100.0 * divided_precursors / precursor_equivalent,
        "division_index": total_divisions / precursor_equivalent,
        "proliferation_index": total_divisions / divided_precursors if divided_precursors else 0.0,
        "proliferation_index_status": "defined" if divided_precursors else "not-defined-no-divided-precursors",
        "quality_gates": [
            "Generation assignments must come from a reviewed dye-dilution peak model or predeclared gates, with live singlets and assay controls resolved first.",
            "All reported generations must share one sample, stain, acquisition, and parent-population denominator; missing or merged generations must be explicit.",
            "These metrics summarize proliferative history in the declared population and do not establish cell-cycle mechanism, viability, or between-condition inference without biological replicates.",
        ],
    }


def summarize_annexin_viability_quadrants(quadrant_events: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize reviewed Annexin/viability-dye quadrant event counts."""
    allowed = {"viable", "early_apoptotic", "late_apoptotic", "necrotic"}
    if not isinstance(quadrant_events, list) or not quadrant_events:
        raise ValueError("quadrant_events must be a nonempty array")
    counts: dict[str, int] = {}
    for row in quadrant_events:
        if not isinstance(row, dict):
            raise ValueError("quadrant events must be objects")
        name = str(row.get("quadrant", "")).strip()
        events = row.get("event_count")
        if name not in allowed or name in counts:
            raise ValueError("quadrants must be unique viable, early_apoptotic, late_apoptotic, or necrotic labels")
        if isinstance(events, bool) or not isinstance(events, int) or events < 0:
            raise ValueError("event_count must be a nonnegative integer")
        counts[name] = events
    missing = sorted(allowed - set(counts))
    if missing:
        raise ValueError(f"quadrant_events omit: {', '.join(missing)}")
    total = sum(counts.values())
    if total == 0:
        raise ValueError("at least one quadrant must contain events")
    percentages = {name: 100.0 * counts[name] / total for name in sorted(allowed)}
    return {
        "total_parent_events": total,
        "quadrant_counts": {name: counts[name] for name in sorted(allowed)},
        "quadrant_percentages": percentages,
        "total_apoptotic_event_count": counts["early_apoptotic"] + counts["late_apoptotic"],
        "total_apoptotic_percent": percentages["early_apoptotic"] + percentages["late_apoptotic"],
        "quality_gates": [
            "Quadrants require declared compensation, fluorescence-minus-one or equivalent threshold controls, viability-dye identity, and a reviewed live-singlet parent gate.",
            "Early and late apoptotic labels describe the declared Annexin/viability assay state; they do not independently establish mechanism, irreversible death, or necrosis.",
            "Condition comparisons require independent biological replicates and a predeclared statistical model outside this per-sample summary.",
        ],
    }


def fit_dna_content_phases(
    dna_values: list[float],
    bins: int = 128,
    minimum_peak_separation: float = 2.0,
) -> dict[str, Any]:
    """Fit a constrained DNA-content histogram with explicit admissibility checks."""
    if not isinstance(dna_values, list) or not 100 <= len(dna_values) <= 100_000:
        raise ValueError("dna_values must contain 100 to 100000 values")
    if isinstance(bins, bool) or not isinstance(bins, int) or not 32 <= bins <= 512:
        raise ValueError("bins must be an integer from 32 to 512")
    separation_limit = _finite(minimum_peak_separation, "minimum_peak_separation")
    if separation_limit <= 0:
        raise ValueError("minimum_peak_separation must be positive")
    try:
        import numpy as np
        from scipy.optimize import least_squares
    except ImportError as exc:
        raise RuntimeError("numpy and scipy are required for DNA-content fitting") from exc
    values = np.asarray([_finite(value, "DNA content") for value in dna_values], dtype=float)
    lower_q, upper_q = np.quantile(values, [0.005, 0.995])
    retained = values[(values >= lower_q) & (values <= upper_q)]
    if retained.size < 100 or not upper_q > lower_q:
        raise ValueError("DNA content lacks sufficient finite dynamic range after outlier policy")
    observed, edges = np.histogram(retained, bins=bins, range=(lower_q, upper_q))
    centers = (edges[:-1] + edges[1:]) / 2
    g1 = float(centers[int(np.argmax(observed))])
    scale = max(float(np.std(retained)), (upper_q - lower_q) / bins)

    def model(parameters):
        g1_mean, sigma, g1_amplitude, g2_amplitude, s_amplitude = parameters
        g2_mean = 2.0 * g1_mean
        g1_curve = g1_amplitude * np.exp(-0.5 * ((centers - g1_mean) / sigma) ** 2)
        g2_curve = g2_amplitude * np.exp(-0.5 * ((centers - g2_mean) / sigma) ** 2)
        s_curve = np.where((centers >= g1_mean) & (centers <= g2_mean), s_amplitude, 0.0)
        return g1_curve, g2_curve, s_curve

    initial = np.array([g1, max(scale * 0.15, 1e-6), float(observed.max()), float(observed.max()) * 0.3, float(observed.max()) * 0.1])
    lower = np.array([max(lower_q, 1e-9), (upper_q - lower_q) / 1000, 0, 0, 0])
    upper = np.array([upper_q / 2, (upper_q - lower_q) / 2, observed.max() * 4, observed.max() * 4, observed.max() * 4])

    def residuals(parameters):
        return (sum(model(parameters)) - observed) / np.sqrt(observed + 1.0)

    fit = least_squares(residuals, initial, bounds=(lower, upper), max_nfev=20_000)
    g1_curve, g2_curve, s_curve = model(fit.x)
    g1_mean, sigma, *_ = fit.x
    separation = (2.0 * g1_mean - g1_mean) / sigma
    residual = residuals(fit.x)
    reduced_chi_square = float(np.sum(residual ** 2) / max(1, len(observed) - len(fit.x)))
    admissible = bool(fit.success and separation >= separation_limit and reduced_chi_square <= 3.0)
    areas = [float(np.sum(curve)) for curve in (g1_curve, s_curve, g2_curve)]
    total_area = sum(areas)
    return {"fit_admissible": admissible, "fit_status": "admissible" if admissible else "blocked-review-required", "input_event_count": len(dna_values), "retained_event_count": int(retained.size), "g1_mean": float(g1_mean), "g2_mean": float(2.0 * g1_mean), "g2_g1_ratio": 2.0, "shared_sigma": float(sigma), "peak_separation_sigma": float(separation), "reduced_chi_square": reduced_chi_square, "phase_percentages": {"g0_g1": 100 * areas[0] / total_area, "s": 100 * areas[1] / total_area, "g2_m": 100 * areas[2] / total_area}, "quality_gates": ["Block phase interpretation unless optimization converges, G2/G1 is constrained to the DNA-content relationship, peak separation meets the declared threshold, and weighted residual fit is acceptable.", "This histogram model requires compensated, debris-, doublet-, and dead-cell-reviewed DNA events and does not replace assay controls or biological replicate inference."]}


def quantify_relative_expression(
    measurements: list[dict[str, Any]],
    target_assay: str,
    reference_assays: list[str],
    calibrator_samples: list[str],
    efficiencies: dict[str, float] | None = None,
    replicate_ct_sd_limit: float = 0.5,
) -> dict[str, Any]:
    """Perform efficiency-corrected relative qPCR quantification.

    Replicates are pooled by sample and assay. Multiple reference assays are
    combined geometrically, matching the multiplicative nature of efficiency
    correction rather than averaging final fold changes.
    """
    target = target_assay.strip()
    references = [str(value).strip() for value in reference_assays]
    calibrators = [str(value).strip() for value in calibrator_samples]
    if not measurements or not target or not references or not calibrators:
        raise ValueError("measurements, target assay, reference assays, and calibrators are required")
    if target in references or len(set(references)) != len(references) or len(set(calibrators)) != len(calibrators):
        raise ValueError("target, references, and calibrator sample names must be distinct where applicable")
    sd_limit = _finite(replicate_ct_sd_limit, "replicate_ct_sd_limit")
    if sd_limit < 0:
        raise ValueError("replicate_ct_sd_limit must be non-negative")

    required_assays = [target, *references]
    efficiency_map = {assay: 2.0 for assay in required_assays}
    for assay, value in (efficiencies or {}).items():
        if assay not in required_assays:
            raise ValueError(f"efficiency supplied for unknown assay: {assay}")
        efficiency = _finite(value, f"efficiency for {assay}")
        if not 1.0 < efficiency <= 2.5:
            raise ValueError("efficiencies must be greater than 1 and no greater than 2.5")
        efficiency_map[assay] = efficiency

    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in measurements:
        if not isinstance(row, dict):
            raise ValueError("measurements must be objects")
        sample = str(row.get("sample", "")).strip()
        assay = str(row.get("assay", "")).strip()
        ct = _finite(row.get("ct"), "Ct")
        if not sample or assay not in required_assays or not 0 <= ct <= 50:
            raise ValueError("each measurement requires a sample, a declared assay, and Ct from 0 to 50")
        grouped[sample][assay].append(ct)
    missing_calibrators = sorted(set(calibrators) - set(grouped))
    if missing_calibrators:
        raise ValueError(f"calibrator samples are absent: {', '.join(missing_calibrators)}")

    summaries: dict[str, dict[str, dict[str, Any]]] = {}
    for sample, assays in sorted(grouped.items()):
        missing = [assay for assay in required_assays if assay not in assays]
        if missing:
            raise ValueError(f"sample {sample} is missing assays: {', '.join(missing)}")
        summaries[sample] = {}
        for assay in required_assays:
            values = assays[assay]
            sd = _sample_sd(values)
            summaries[sample][assay] = {"n": len(values), "mean_ct": _mean(values), "sd_ct": sd, "ct_values": values}

    calibrator_means = {
        assay: _mean([summaries[sample][assay]["mean_ct"] for sample in calibrators])
        for assay in required_assays
    }
    rows = []
    for sample, assays in summaries.items():
        target_shift = calibrator_means[target] - assays[target]["mean_ct"]
        target_factor = efficiency_map[target] ** target_shift
        reference_factors = [
            efficiency_map[assay] ** (calibrator_means[assay] - assays[assay]["mean_ct"])
            for assay in references
        ]
        reference_factor = math.prod(reference_factors) ** (1.0 / len(reference_factors))
        flags = []
        for assay in required_assays:
            summary = assays[assay]
            if summary["n"] < 2:
                flags.append(f"SINGLE_REPLICATE:{assay}")
            elif summary["sd_ct"] is not None and summary["sd_ct"] > sd_limit:
                flags.append(f"HIGH_REPLICATE_SD:{assay}")
        rows.append(
            {
                "sample": sample,
                "assays": assays,
                "target_factor": target_factor,
                "reference_normalization_factor": reference_factor,
                "relative_expression": target_factor / reference_factor,
                "qc_flags": flags,
            }
        )
    return {
        "target_assay": target,
        "reference_assays": references,
        "calibrator_samples": calibrators,
        "calibrator_mean_ct": calibrator_means,
        "efficiencies": efficiency_map,
        "replicate_ct_sd_limit": sd_limit,
        "samples": rows,
        "method": "efficiency-corrected relative quantification with geometric reference normalization",
        "quality_gates": [
            "Inspect replicate Ct dispersion before interpreting fold changes.",
            "Validate amplification efficiency, specificity, no-template controls, and reference stability.",
            "Use biological replicates for inference; technical replicates only characterize measurement precision.",
        ],
    }


def summarize_crystal_violet_biofilm(
    observations: list[dict[str, Any]],
    replicate_level: str = "unspecified",
) -> dict[str, Any]:
    """Summarize blank-corrected crystal-violet biofilm measurements.

    This is a plate-measurement summary, not a one-observation-per-group
    significance test. It preserves every supplied read, distinguishes blanks
    from controls, and reports group-level precision and control-normalized
    effect sizes for later design-aware inference.
    """
    if not isinstance(observations, list) or len(observations) < 3:
        raise ValueError("observations must contain at least three measurements")
    if replicate_level not in {"unspecified", "technical", "biological"}:
        raise ValueError("replicate_level must be unspecified, technical, or biological")
    grouped: dict[str, list[float]] = defaultdict(list)
    raw_rows = []
    allowed_roles = {"blank", "control", "test"}
    seen = set()
    for row in observations:
        if not isinstance(row, dict):
            raise ValueError("observations must be objects")
        group = str(row.get("group", "")).strip()
        replicate_id = str(row.get("replicate_id", "")).strip()
        role = str(row.get("role", "")).strip().lower()
        absorbance = _finite(row.get("absorbance"), "absorbance")
        if not group or not replicate_id or role not in allowed_roles:
            raise ValueError("each observation requires group, replicate_id, role, and finite absorbance")
        key = (group, replicate_id)
        if key in seen:
            raise ValueError("replicate_id must be unique within each group")
        seen.add(key)
        grouped[group].append(absorbance)
        raw_rows.append({"group": group, "replicate_id": replicate_id, "role": role, "absorbance": absorbance})
    blank_rows = [row for row in raw_rows if row["role"] == "blank"]
    control_rows = [row for row in raw_rows if row["role"] == "control"]
    if not blank_rows or not control_rows:
        raise ValueError("at least one blank and one control observation are required")
    if any(row["role"] == "blank" and row["group"] != "blank" for row in raw_rows):
        raise ValueError("blank observations must use group blank")
    if any(row["role"] == "control" and row["group"] != "control" for row in raw_rows):
        raise ValueError("control observations must use group control")
    blank_mean = _mean([row["absorbance"] for row in blank_rows])
    control_corrected = [row["absorbance"] - blank_mean for row in control_rows]
    control_mean = _mean(control_corrected)
    if control_mean <= 0:
        raise ValueError("blank-corrected control mean must be positive")

    summaries = []
    for group, raw_values in sorted(grouped.items()):
        corrected = [value - blank_mean for value in raw_values]
        mean = _mean(corrected)
        sd = _sample_sd(corrected)
        role = next(row["role"] for row in raw_rows if row["group"] == group)
        flags = []
        if len(corrected) < 2:
            flags.append("SINGLE_REPLICATE")
        if mean < 0:
            flags.append("NEGATIVE_AFTER_BLANK_CORRECTION")
        if sd is not None and mean > 0 and 100.0 * sd / mean > 20.0:
            flags.append("HIGH_REPLICATE_CV")
        summaries.append(
            {
                "group": group,
                "role": role,
                "replicate_count": len(corrected),
                "raw_absorbance_values": raw_values,
                "blank_corrected_values": corrected,
                "mean_blank_corrected_absorbance": mean,
                "sd_blank_corrected_absorbance": sd,
                "cv_percent": 100.0 * sd / mean if sd is not None and mean > 0 else None,
                "fold_of_control": mean / control_mean,
                "log2_fold_of_control": math.log2(mean / control_mean) if mean > 0 else None,
                "qc_flags": flags,
            }
        )
    biological_groups = {row["group"] for row in raw_rows if row["role"] != "blank"}
    replicate_complete = all(
        next(item["replicate_count"] for item in summaries if item["group"] == group) >= 2
        for group in biological_groups
    )
    return {
        "blank_mean_absorbance": blank_mean,
        "control_mean_blank_corrected_absorbance": control_mean,
        "replicate_level": replicate_level,
        "replicate_design_status": "at-least-two-per-nonblank-group" if replicate_complete else "single-replicate-in-one-or-more-groups",
        "comparative_interpretation_status": (
            "eligible-for-design-aware-comparison"
            if replicate_level == "biological" and replicate_complete
            else "blocked-review-required"
        ),
        "groups": summaries,
        "quality_gates": [
            "Require observed blank and control wells, retained replicate identities, identical readout units, and a declared plate layout before interpreting blank-corrected absorbance.",
            "Review raw values, blank correction, replicate CV, edge effects, staining and solubilization consistency, and negative corrected values before accepting group summaries.",
            "Fold changes summarize the supplied measurements; treatment, strain, or mechanism claims require independent biological replicates and a predeclared between-group model.",
        ],
    }


def _linear_fit(xs: list[float], ys: list[float]) -> dict[str, float]:
    x_mean, y_mean = _mean(xs), _mean(ys)
    denominator = math.fsum((value - x_mean) ** 2 for value in xs)
    if denominator == 0:
        raise ValueError("standard concentrations must vary")
    slope = math.fsum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    if slope == 0:
        raise ValueError("calibration slope must be nonzero")
    intercept = y_mean - slope * x_mean
    predicted = [slope * value + intercept for value in xs]
    residual_sum = math.fsum((observed - fitted) ** 2 for observed, fitted in zip(ys, predicted))
    total_sum = math.fsum((observed - y_mean) ** 2 for observed in ys)
    return {
        "slope": slope,
        "intercept": intercept,
        "r_squared": 1.0 - residual_sum / total_sum if total_sum else 1.0,
        "rmse": math.sqrt(residual_sum / max(1, len(xs) - 2)),
        "residual_sum_squares": residual_sum,
    }


def fit_immunoassay_curve(
    standards: list[dict[str, Any]],
    unknowns: list[dict[str, Any]],
    model: str = "linear",
) -> dict[str, Any]:
    """Fit a replicate-aware calibration curve and back-calculate unknowns.

    The current validated model is linear and deliberately refuses to label a
    four-parameter logistic approximation as production-ready. The result
    carries enough residual and replicate evidence to decide whether a
    nonlinear assay-specific fit is required.
    """
    if model != "linear" or len(standards) < 3:
        raise ValueError("model must be linear and at least three standard observations are required")
    grouped: dict[float, list[float]] = defaultdict(list)
    for row in standards:
        if not isinstance(row, dict):
            raise ValueError("standards must be objects")
        concentration = _finite(row.get("concentration"), "standard concentration")
        response = _finite(row.get("response"), "standard response")
        if concentration < 0:
            raise ValueError("standard concentrations must be non-negative")
        grouped[concentration].append(response)
    if len(grouped) < 3:
        raise ValueError("at least three distinct concentrations are required")
    standard_rows = []
    for concentration, values in sorted(grouped.items()):
        center = _mean(values)
        sd = _sample_sd(values)
        standard_rows.append(
            {
                "concentration": concentration,
                "replicate_count": len(values),
                "mean_response": center,
                "sd_response": sd,
                "cv_percent": 100.0 * sd / abs(center) if sd is not None and center != 0 else None,
                "responses": values,
            }
        )
    xs = [row["concentration"] for row in standard_rows]
    ys = [row["mean_response"] for row in standard_rows]
    fit = _linear_fit(xs, ys)
    for row in standard_rows:
        predicted = fit["slope"] * row["concentration"] + fit["intercept"]
        row["fitted_response"] = predicted
        row["residual"] = row["mean_response"] - predicted
        row["back_calculated_concentration"] = (row["mean_response"] - fit["intercept"]) / fit["slope"]
    response_range = [min(ys), max(ys)]
    concentration_range = [min(xs), max(xs)]
    unknown_rows = []
    for row in unknowns:
        if not isinstance(row, dict):
            raise ValueError("unknowns must be objects")
        sample = str(row.get("sample", "")).strip()
        response = _finite(row.get("response"), "unknown response")
        dilution = _finite(row.get("dilution_factor", 1.0), "dilution_factor")
        if not sample or dilution <= 0:
            raise ValueError("unknowns require sample names and positive dilution factors")
        calculated = (response - fit["intercept"]) / fit["slope"]
        flags = []
        if not response_range[0] <= response <= response_range[1]:
            flags.append("OUTSIDE_CALIBRATED_RESPONSE_RANGE")
        if calculated < 0:
            flags.append("NEGATIVE_BACK_CALCULATION")
        unknown_rows.append(
            {
                "sample": sample,
                "response": response,
                "dilution_factor": dilution,
                "calculated_concentration": calculated,
                "reported_concentration": calculated * dilution,
                "qc_flags": flags,
            }
        )
    return {
        "model": model,
        "fit": fit,
        "standards": standard_rows,
        "unknowns": unknown_rows,
        "calibrated_concentration_range": concentration_range,
        "calibrated_response_range": response_range,
        "quality_gates": [
            "Review standard replicate CV and residual pattern before accepting the model.",
            "Do not report extrapolated unknowns without dilution and repeat measurement.",
            "Use validated 4PL or 5PL software when the working range is sigmoidal rather than linear.",
        ],
    }


def summarize_flow_cytometry(events: list[dict[str, Any]], gates: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply auditable sequential rectangular gates to event-level measurements."""
    if not events or not gates:
        raise ValueError("events and gates are required")
    normalized_events = []
    channels = set()
    for index, event in enumerate(events):
        if not isinstance(event, dict) or not event:
            raise ValueError("events must be nonempty objects")
        values = {str(channel): _finite(value, f"event {index} channel {channel}") for channel, value in event.items()}
        channels.update(values)
        normalized_events.append(values)
    populations: dict[str, list[int]] = {"all": list(range(len(normalized_events)))}
    output = []
    names = set()
    for gate in gates:
        if not isinstance(gate, dict):
            raise ValueError("gates must be objects")
        name = str(gate.get("name", "")).strip()
        parent = str(gate.get("parent", "all")).strip()
        conditions = gate.get("conditions")
        if not name or name in names or parent not in populations or not isinstance(conditions, dict) or not conditions:
            raise ValueError("gates require unique names, an existing parent, and conditions")
        names.add(name)
        normalized_conditions = {}
        for channel, bounds in conditions.items():
            if channel not in channels or not isinstance(bounds, dict) or set(bounds) - {"min", "max"} or not bounds:
                raise ValueError("gate conditions require known channels and min and/or max bounds")
            low = _finite(bounds["min"], "gate minimum") if "min" in bounds else None
            high = _finite(bounds["max"], "gate maximum") if "max" in bounds else None
            if low is not None and high is not None and low > high:
                raise ValueError("gate minimum cannot exceed maximum")
            normalized_conditions[str(channel)] = {"min": low, "max": high}
        selected = []
        for index in populations[parent]:
            event = normalized_events[index]
            keep = all(
                (bounds["min"] is None or event[channel] >= bounds["min"])
                and (bounds["max"] is None or event[channel] <= bounds["max"])
                for channel, bounds in normalized_conditions.items()
            )
            if keep:
                selected.append(index)
        populations[name] = selected
        parent_count = len(populations[parent])
        output.append(
            {
                "name": name,
                "parent": parent,
                "conditions": normalized_conditions,
                "event_count": len(selected),
                "percent_of_parent": 100.0 * len(selected) / parent_count if parent_count else None,
                "percent_of_total": 100.0 * len(selected) / len(normalized_events),
                "event_indices": selected,
            }
        )
    return {
        "input_event_count": len(normalized_events),
        "channels": sorted(channels),
        "gate_order": [row["name"] for row in output],
        "gates": output,
        "quality_gates": [
            "Apply compensation and a declared transformation before threshold gating when required.",
            "Document acquisition, debris, singlet, viability, and fluorescence-minus-one controls.",
            "Rectangular gates are descriptive; complex boundaries require validated cytometry software and retained gate provenance.",
        ],
    }


def summarize_flow_immunophenotypes(
    events: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    population_rules: list[dict[str, Any]],
    control_review: dict[str, Any],
) -> dict[str, Any]:
    """Quantify explicit marker patterns within reviewed parent-gate event sets.

    The output deliberately reports marker-rule patterns, not inferred cell
    identities. Threshold setting, compensation, and transformation remain
    declared experimental decisions with their own control evidence.
    """
    if not isinstance(events, list) or not events or not isinstance(gates, list) or not gates:
        raise ValueError("events and reviewed gates are required")
    if not isinstance(population_rules, list) or not population_rules:
        raise ValueError("population_rules must be a nonempty array")
    required_review = {
        "panel_identity",
        "sample_identity",
        "compensation_reviewed",
        "transformation_declared",
        "threshold_basis_reviewed",
    }
    if not isinstance(control_review, dict) or set(control_review) != required_review:
        raise ValueError("control_review must declare panel, sample, compensation, transformation, and threshold review")
    if not all(isinstance(control_review[field], str) and control_review[field].strip() for field in ("panel_identity", "sample_identity")):
        raise ValueError("control_review panel_identity and sample_identity must be nonempty")
    if not all(isinstance(control_review[field], bool) for field in required_review - {"panel_identity", "sample_identity"}):
        raise ValueError("control_review flags must be boolean")

    normalized_events = []
    channels = set()
    for event_index, event in enumerate(events):
        if not isinstance(event, dict) or not event:
            raise ValueError("events must contain nonempty channel objects")
        normalized = {str(channel): _finite(value, f"event {event_index} channel {channel}") for channel, value in event.items()}
        normalized_events.append(normalized)
        channels.update(normalized)

    parents: dict[str, tuple[int, ...]] = {}
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) - {"name", "event_indices", "parent", "conditions", "event_count", "percent_of_parent", "percent_of_total"}:
            raise ValueError("gates must be flow-cytometry gate summaries")
        name = gate.get("name")
        indices = gate.get("event_indices")
        if not isinstance(name, str) or not name.strip() or name in parents or not isinstance(indices, list):
            raise ValueError("each gate requires a unique name and event_indices")
        if any(isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(normalized_events) for index in indices):
            raise ValueError("gate event_indices must refer to the supplied event table")
        if len(set(indices)) != len(indices):
            raise ValueError("gate event_indices must be unique")
        parents[name] = tuple(indices)

    seen_rules = set()
    summaries = []
    for rule in population_rules:
        if not isinstance(rule, dict) or set(rule) != {"name", "parent_gate", "conditions"}:
            raise ValueError("each population rule requires name, parent_gate, and conditions")
        name, parent_name, conditions = rule["name"], rule["parent_gate"], rule["conditions"]
        if not isinstance(name, str) or not name.strip() or name in seen_rules or not isinstance(parent_name, str) or parent_name not in parents:
            raise ValueError("population rules require unique names and an existing parent_gate")
        if not isinstance(conditions, dict) or not conditions:
            raise ValueError("population rule conditions must be nonempty")
        normalized_conditions = {}
        for channel, bounds in conditions.items():
            if channel not in channels or not isinstance(bounds, dict) or not bounds or set(bounds) - {"min", "max"}:
                raise ValueError("population conditions require known channels and min and/or max bounds")
            lower = _finite(bounds["min"], f"{name} {channel} minimum") if "min" in bounds else None
            upper = _finite(bounds["max"], f"{name} {channel} maximum") if "max" in bounds else None
            if lower is not None and upper is not None and lower > upper:
                raise ValueError("population condition minimum cannot exceed maximum")
            normalized_conditions[str(channel)] = {"min": lower, "max": upper}
        parent_indices = parents[parent_name]
        matched = [
            index
            for index in parent_indices
            if all(
                (bounds["min"] is None or normalized_events[index][channel] >= bounds["min"])
                and (bounds["max"] is None or normalized_events[index][channel] <= bounds["max"])
                for channel, bounds in normalized_conditions.items()
            )
        ]
        seen_rules.add(name)
        summaries.append(
            {
                "name": name,
                "parent_gate": parent_name,
                "conditions": normalized_conditions,
                "parent_event_count": len(parent_indices),
                "event_count": len(matched),
                "percent_of_parent": 100.0 * len(matched) / len(parent_indices) if parent_indices else None,
                "percent_of_total": 100.0 * len(matched) / len(normalized_events),
                "event_indices": matched,
                "interpretation": "descriptive_marker_pattern_not_cell_identity_call",
            }
        )
    review_complete = all(control_review[field] for field in ("compensation_reviewed", "transformation_declared", "threshold_basis_reviewed"))
    return {
        "sample_identity": control_review["sample_identity"],
        "panel_identity": control_review["panel_identity"],
        "input_event_count": len(normalized_events),
        "review_status": "eligible_for_descriptive_pattern_interpretation" if review_complete else "blocked_control_review_required",
        "population_patterns": summaries,
        "quality_gates": [
            "Population patterns require reviewed compensation, transformation, threshold basis, panel identity, and sample identity.",
            "Marker-rule counts are descriptive and do not by themselves establish cell identity, disease diagnosis, function, mechanism, or condition-level inference.",
        ],
    }


def summarize_western_blot_densitometry(
    measurements: list[dict[str, Any]],
    reference_lane_ids: list[str],
    replicate_level: str = "unspecified",
) -> dict[str, Any]:
    """Normalize reviewed Western blot ROI measurements without inferring bands.

    Each row is one user-reviewed target band and, when available, its matched
    loading-control band. Background is expressed as mean intensity per pixel
    so the function can retain ROI-area-aware subtraction rather than treating
    arbitrary image pixel values as directly comparable measurements.
    """
    if not isinstance(measurements, list) or not measurements:
        raise ValueError("measurements must be a nonempty array")
    if not isinstance(reference_lane_ids, list) or not reference_lane_ids or any(
        not isinstance(value, str) or not value.strip() for value in reference_lane_ids
    ):
        raise ValueError("reference_lane_ids must be a nonempty array of lane identifiers")
    if len(set(reference_lane_ids)) != len(reference_lane_ids):
        raise ValueError("reference_lane_ids must be unique")
    if replicate_level not in {"unspecified", "technical", "biological"}:
        raise ValueError("replicate_level must be unspecified, technical, or biological")

    rows = []
    seen_lanes = set()
    for index, measurement in enumerate(measurements):
        if not isinstance(measurement, dict):
            raise ValueError("each measurement must be an object")
        required = {
            "lane_id",
            "condition",
            "target_integrated_intensity",
            "target_background_per_pixel",
            "target_area_pixels",
        }
        allowed = required | {
            "loading_control_integrated_intensity",
            "loading_control_background_per_pixel",
            "loading_control_area_pixels",
            "biological_replicate_id",
            "technical_replicate_id",
        }
        if set(measurement) - allowed or not required <= set(measurement):
            raise ValueError("measurement fields do not match the reviewed Western blot ROI contract")
        lane_id = str(measurement["lane_id"]).strip()
        condition = str(measurement["condition"]).strip()
        if not lane_id or not condition or lane_id in seen_lanes:
            raise ValueError("each measurement requires a unique nonempty lane_id and condition")
        seen_lanes.add(lane_id)
        target_raw = _finite(measurement["target_integrated_intensity"], f"lane {lane_id} target intensity")
        target_background = _finite(measurement["target_background_per_pixel"], f"lane {lane_id} target background")
        target_area = _finite(measurement["target_area_pixels"], f"lane {lane_id} target area")
        if min(target_raw, target_background, target_area) < 0:
            raise ValueError("target intensity, background, and area must be nonnegative")
        target_net = target_raw - target_background * target_area
        if target_net <= 0:
            raise ValueError(f"lane {lane_id} has nonpositive target intensity after background subtraction")
        has_control = "loading_control_integrated_intensity" in measurement
        control_fields = {
            "loading_control_integrated_intensity",
            "loading_control_background_per_pixel",
            "loading_control_area_pixels",
        }
        if has_control != all(field in measurement for field in control_fields):
            raise ValueError("loading-control intensity, background, and area must be supplied together")
        if has_control:
            control_raw = _finite(measurement["loading_control_integrated_intensity"], f"lane {lane_id} loading-control intensity")
            control_background = _finite(measurement["loading_control_background_per_pixel"], f"lane {lane_id} loading-control background")
            control_area = _finite(measurement["loading_control_area_pixels"], f"lane {lane_id} loading-control area")
            if min(control_raw, control_background, control_area) < 0:
                raise ValueError("loading-control intensity, background, and area must be nonnegative")
            control_net = control_raw - control_background * control_area
            if control_net <= 0:
                raise ValueError(f"lane {lane_id} has nonpositive loading-control intensity after background subtraction")
            normalized = target_net / control_net
        else:
            control_net = None
            normalized = target_net
        rows.append(
            {
                "lane_id": lane_id,
                "condition": condition,
                "biological_replicate_id": str(measurement.get("biological_replicate_id", "")).strip() or None,
                "technical_replicate_id": str(measurement.get("technical_replicate_id", "")).strip() or None,
                "target_net_intensity": target_net,
                "loading_control_net_intensity": control_net,
                "normalization_method": "loading-control" if has_control else "background-corrected-target-only",
                "normalized_intensity": normalized,
                "input_index": index,
            }
        )

    requested_references = set(reference_lane_ids)
    observed_references = {row["lane_id"] for row in rows} & requested_references
    missing_references = sorted(requested_references - observed_references)
    if missing_references:
        raise ValueError(f"reference_lane_ids are not present in measurements: {', '.join(missing_references)}")
    reference_values = [row["normalized_intensity"] for row in rows if row["lane_id"] in requested_references]
    reference_mean = _mean(reference_values)
    if reference_mean <= 0:
        raise ValueError("reference normalized intensity must be positive")
    for row in rows:
        row["fold_change_vs_reference"] = row["normalized_intensity"] / reference_mean
        row["is_reference_lane"] = row["lane_id"] in requested_references

    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["condition"]].append(row["fold_change_vs_reference"])
    condition_summary = [
        {
            "condition": condition,
            "lane_count": len(values),
            "mean_fold_change_vs_reference": _mean(values),
            "sample_sd_fold_change_vs_reference": _sample_sd(values),
        }
        for condition, values in sorted(grouped.items())
    ]
    return {
        "reference_lane_ids": sorted(requested_references),
        "reference_mean_normalized_intensity": reference_mean,
        "replicate_level": replicate_level,
        "lanes": rows,
        "condition_summary": condition_summary,
        "quality_gates": [
            "Each target and loading-control ROI must be manually reviewed on the original blot, with background regions, lane identity, exposure, saturation status, antibody, and sample provenance retained outside this calculation.",
            "A loading-control ratio is reported only when all three reviewed loading-control measurements are supplied for that lane; otherwise the result remains background-corrected target-only.",
            "Fold changes are normalized to the declared reference lanes. Technical lanes are not independent biological replicates, and this descriptive summary does not establish protein abundance, mechanism, or condition-level significance.",
        ],
    }


def summarize_radiotracer_biodistribution(
    measurements: list[dict[str, Any]],
    tumor_organ: str | None = None,
    blood_organ: str | None = None,
    replicate_level: str = "unspecified",
) -> dict[str, Any]:
    """Summarize declared biodistribution measurements as %ID/g and AUC.

    Activity values must already share the project's declared calibration and
    decay-correction basis. This bounded calculation does not infer organ
    kinetics from sparse observations or treat multiple organs from one animal
    as independent animals.
    """
    if not isinstance(measurements, list) or not measurements:
        raise ValueError("measurements must be a nonempty array")
    if replicate_level not in {"unspecified", "technical", "biological"}:
        raise ValueError("replicate_level must be unspecified, technical, or biological")
    tumor_name = str(tumor_organ).strip() if tumor_organ is not None else None
    blood_name = str(blood_organ).strip() if blood_organ is not None else None
    if bool(tumor_name) != bool(blood_name):
        raise ValueError("tumor_organ and blood_organ must be supplied together")
    if tumor_name and tumor_name == blood_name:
        raise ValueError("tumor_organ and blood_organ must differ")

    rows = []
    observed_keys = set()
    for index, measurement in enumerate(measurements):
        if not isinstance(measurement, dict):
            raise ValueError("each measurement must be an object")
        required = {
            "sample_id",
            "organ",
            "time_hours",
            "injected_dose_bq",
            "tissue_activity_bq",
            "tissue_mass_g",
        }
        allowed = required | {"biological_replicate_id", "technical_replicate_id"}
        if set(measurement) - allowed or not required <= set(measurement):
            raise ValueError("measurement fields do not match the biodistribution contract")
        sample_id = str(measurement["sample_id"]).strip()
        organ = str(measurement["organ"]).strip()
        if not sample_id or not organ:
            raise ValueError("each biodistribution measurement requires nonempty sample_id and organ")
        time_hours = _finite(measurement["time_hours"], f"{sample_id} time_hours")
        injected_dose = _finite(measurement["injected_dose_bq"], f"{sample_id} injected_dose_bq")
        activity = _finite(measurement["tissue_activity_bq"], f"{sample_id} tissue_activity_bq")
        mass = _finite(measurement["tissue_mass_g"], f"{sample_id} tissue_mass_g")
        if time_hours < 0 or injected_dose <= 0 or activity < 0 or mass <= 0:
            raise ValueError("time must be nonnegative, injected dose and mass positive, and activity nonnegative")
        key = (sample_id, organ, time_hours)
        if key in observed_keys:
            raise ValueError("a sample, organ, and time_hours combination may occur only once")
        observed_keys.add(key)
        rows.append(
            {
                "sample_id": sample_id,
                "organ": organ,
                "time_hours": time_hours,
                "biological_replicate_id": str(measurement.get("biological_replicate_id", "")).strip() or None,
                "technical_replicate_id": str(measurement.get("technical_replicate_id", "")).strip() or None,
                "injected_dose_bq": injected_dose,
                "tissue_activity_bq": activity,
                "tissue_mass_g": mass,
                "percent_injected_dose_per_gram": 100.0 * activity / injected_dose / mass,
            }
        )

    grouped: dict[tuple[str, float], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["organ"], row["time_hours"])].append(row["percent_injected_dose_per_gram"])
    timepoint_summary = [
        {
            "organ": organ,
            "time_hours": time_hours,
            "sample_count": len(values),
            "mean_percent_injected_dose_per_gram": _mean(values),
            "sample_sd_percent_injected_dose_per_gram": _sample_sd(values),
        }
        for (organ, time_hours), values in sorted(grouped.items())
    ]
    by_organ: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in timepoint_summary:
        by_organ[row["organ"]].append(row)
    auc_summary = []
    for organ, points in sorted(by_organ.items()):
        ordered = sorted(points, key=lambda row: row["time_hours"])
        auc = None
        if len(ordered) >= 2:
            auc = math.fsum(
                (left["mean_percent_injected_dose_per_gram"] + right["mean_percent_injected_dose_per_gram"])
                * (right["time_hours"] - left["time_hours"])
                / 2.0
                for left, right in zip(ordered, ordered[1:])
            )
        auc_summary.append(
            {
                "organ": organ,
                "observed_timepoint_count": len(ordered),
                "observed_time_range_hours": [ordered[0]["time_hours"], ordered[-1]["time_hours"]],
                "trapezoidal_auc_percent_injected_dose_per_gram_hour": auc,
                "auc_status": "observed-interval-only" if auc is not None else "not-defined-fewer-than-two-timepoints",
            }
        )

    tumor_to_blood = []
    if tumor_name and blood_name:
        values_by_organ_time = {
            (row["organ"], row["time_hours"]): row["mean_percent_injected_dose_per_gram"]
            for row in timepoint_summary
        }
        shared_times = sorted(
            time
            for organ, time in values_by_organ_time
            if organ == tumor_name and (blood_name, time) in values_by_organ_time
        )
        for time in shared_times:
            blood_value = values_by_organ_time[(blood_name, time)]
            tumor_to_blood.append(
                {
                    "time_hours": time,
                    "tumor_organ": tumor_name,
                    "blood_organ": blood_name,
                    "tumor_to_blood_ratio": values_by_organ_time[(tumor_name, time)] / blood_value if blood_value > 0 else None,
                    "ratio_status": "defined" if blood_value > 0 else "not-defined-zero-blood-mean",
                }
            )
    return {
        "replicate_level": replicate_level,
        "measurements": rows,
        "timepoint_summary": timepoint_summary,
        "organ_auc_summary": auc_summary,
        "tumor_to_blood_ratios": tumor_to_blood,
        "quality_gates": [
            "Injected-dose calibration, radionuclide identity, decay-correction reference time, counting efficiency, sample recovery, organ dissection, mass measurement, and sample identity must be retained and reviewed before interpretation.",
            "AUC is a trapezoidal integral over the observed interval only; it is not an extrapolated residence time, pharmacokinetic fit, absorbed dose, or MIRD dosimetry result.",
            "Technical measurements and multiple organs from one animal do not create independent biological replicates. Tumor-to-blood ratios require matching declared timepoints and are undefined when mean blood signal is zero.",
        ],
    }


def summarize_xenograft_tumor_growth(
    observations: list[dict[str, Any]],
    control_group: str,
    endpoint_time_days: float | None = None,
) -> dict[str, Any]:
    """Summarize animal-level xenograft volumes and endpoint TGI descriptively."""
    if not isinstance(observations, list) or not observations:
        raise ValueError("observations must be a nonempty array")
    control = str(control_group).strip()
    if not control:
        raise ValueError("control_group must be nonempty")
    endpoint = None if endpoint_time_days is None else _finite(endpoint_time_days, "endpoint_time_days")
    if endpoint is not None and endpoint < 0:
        raise ValueError("endpoint_time_days must be nonnegative")
    rows, seen = [], set()
    for row in observations:
        if not isinstance(row, dict) or set(row) != {"animal_id", "group", "time_days", "tumor_volume_mm3"}:
            raise ValueError("each observation requires animal_id, group, time_days, and tumor_volume_mm3")
        animal, group = str(row["animal_id"]).strip(), str(row["group"]).strip()
        time, volume = _finite(row["time_days"], "time_days"), _finite(row["tumor_volume_mm3"], "tumor_volume_mm3")
        if not animal or not group or time < 0 or volume < 0 or (animal, time) in seen:
            raise ValueError("animal/group must be nonempty and each animal-time measurement unique and nonnegative")
        seen.add((animal, time))
        rows.append({"animal_id": animal, "group": group, "time_days": time, "tumor_volume_mm3": volume})
    animals = {}
    for row in rows:
        current = animals.setdefault(row["animal_id"], {"group": row["group"], "rows": []})
        if current["group"] != row["group"]:
            raise ValueError("each animal must belong to exactly one group")
        current["rows"].append(row)
    if control not in {row["group"] for row in rows}:
        raise ValueError("control_group is absent from observations")
    for animal in animals.values():
        animal["rows"].sort(key=lambda value: value["time_days"])
    endpoint = endpoint if endpoint is not None else max(row["time_days"] for row in rows)
    by_group_time = defaultdict(list)
    for row in rows:
        by_group_time[(row["group"], row["time_days"])].append(row["tumor_volume_mm3"])
    trajectory = [
        {"group": group, "time_days": time, "animal_count": len(values), "mean_tumor_volume_mm3": _mean(values), "sample_sd_tumor_volume_mm3": _sample_sd(values)}
        for (group, time), values in sorted(by_group_time.items())
    ]
    changes = []
    for animal_id, animal in sorted(animals.items()):
        baseline = animal["rows"][0]
        endpoint_rows = [row for row in animal["rows"] if row["time_days"] == endpoint]
        if endpoint_rows:
            final = endpoint_rows[0]
            changes.append({"animal_id": animal_id, "group": animal["group"], "baseline_time_days": baseline["time_days"], "baseline_volume_mm3": baseline["tumor_volume_mm3"], "endpoint_time_days": endpoint, "endpoint_volume_mm3": final["tumor_volume_mm3"], "change_from_baseline_mm3": final["tumor_volume_mm3"] - baseline["tumor_volume_mm3"]})
    grouped_changes = defaultdict(list)
    for row in changes:
        grouped_changes[row["group"]].append(row["change_from_baseline_mm3"])
    control_values = grouped_changes.get(control, [])
    control_change = _mean(control_values) if control_values else None
    group_summary = []
    for group, values in sorted(grouped_changes.items()):
        mean_change = _mean(values)
        tgi = None if control_change is None or control_change <= 0 else 100.0 * (1.0 - mean_change / control_change)
        group_summary.append({"group": group, "endpoint_animal_count": len(values), "mean_change_from_baseline_mm3": mean_change, "sample_sd_change_from_baseline_mm3": _sample_sd(values), "tumor_growth_inhibition_percent_vs_control": tgi, "tgi_status": "defined" if tgi is not None else "not-defined-control-growth-not-positive-or-missing"})
    return {"control_group": control, "endpoint_time_days": endpoint, "animal_count": len(animals), "trajectory": trajectory, "animal_endpoint_changes": changes, "endpoint_group_summary": group_summary, "quality_gates": ["Each animal must retain a stable group identity and unique longitudinal measurements; exclusions, randomization, blinding, endpoint policy, volume method, treatment exposure, adverse events, and euthanasia criteria require explicit study records.", "TGI is reported only from animals with both baseline and declared endpoint measurements and positive mean control growth. It is descriptive and does not supply survival, toxicity, statistical significance, or causal drug-efficacy evidence."]}


def fit_accelerated_stability(
    observations: list[dict[str, Any]], target_temperature_c: float, specification_percent: float
) -> dict[str, Any]:
    """Fit bounded zero/first-order potency loss and Arrhenius extrapolation."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("NumPy is required for accelerated-stability fitting") from exc
    target_c = _finite(target_temperature_c, "target_temperature_c")
    specification = _finite(specification_percent, "specification_percent")
    if not 0 < specification < 100:
        raise ValueError("specification_percent must be between 0 and 100")
    if not isinstance(observations, list) or len(observations) < 6:
        raise ValueError("observations must contain at least six rows")
    grouped = defaultdict(list)
    for row in observations:
        if not isinstance(row, dict) or set(row) != {"temperature_c", "time_days", "potency_percent"}:
            raise ValueError("each row requires temperature_c, time_days, and potency_percent")
        temperature, time, potency = (_finite(row[key], key) for key in ("temperature_c", "time_days", "potency_percent"))
        if temperature <= -273.15 or time < 0 or not 0 < potency <= 100:
            raise ValueError("temperatures must exceed absolute zero, time nonnegative, and potency in (0, 100]")
        grouped[temperature].append((time, potency))
    if len(grouped) < 2:
        raise ValueError("at least two temperatures are required for Arrhenius extrapolation")
    rate_rows = []
    for temperature, pairs in sorted(grouped.items()):
        if len(pairs) < 3 or len({time for time, _ in pairs}) < 3:
            raise ValueError("each temperature requires at least three distinct timepoints")
        x = np.asarray([pair[0] for pair in pairs], dtype=float)
        y = np.asarray([pair[1] for pair in pairs], dtype=float)
        candidates = []
        for name, transformed in (("zero-order", y), ("first-order", np.log(y / 100.0))):
            slope, intercept = np.polyfit(x, transformed, 1)
            predicted = intercept + slope * x
            sse = float(np.sum((transformed - predicted) ** 2))
            aic = len(x) * math.log(max(sse / len(x), 1e-300)) + 4.0
            rate = -float(slope) if name == "zero-order" else -float(slope)
            if rate > 0:
                candidates.append((aic, name, rate, sse))
        if not candidates:
            raise ValueError(f"potency data at {temperature} C do not support a decreasing zero- or first-order model")
        aic, model, rate, sse = min(candidates)
        rate_rows.append({"temperature_c": temperature, "temperature_k": temperature + 273.15, "model": model, "degradation_rate_per_day": rate, "fit_sse": sse, "aic": aic})
    inverse_temperature = np.asarray([1.0 / row["temperature_k"] for row in rate_rows])
    log_rate = np.log(np.asarray([row["degradation_rate_per_day"] for row in rate_rows]))
    slope, intercept = np.polyfit(inverse_temperature, log_rate, 1)
    predicted_rate = float(math.exp(intercept + slope / (target_c + 273.15)))
    selected_models = {row["model"] for row in rate_rows}
    if len(selected_models) != 1:
        raise ValueError("Arrhenius extrapolation requires one selected kinetic model across all temperatures")
    model = selected_models.pop()
    shelf_days = (100.0 - specification) / predicted_rate if model == "zero-order" else -math.log(specification / 100.0) / predicted_rate
    return {"target_temperature_c": target_c, "specification_percent": specification, "temperature_fits": rate_rows, "selected_kinetic_model": model, "arrhenius_slope": float(slope), "predicted_degradation_rate_per_day": predicted_rate, "predicted_time_to_specification_days": shelf_days, "quality_gates": ["Use only potency measurements with declared assay accuracy, stability-indicating specificity, storage conditions, sampling schedule, container/closure, and acceptance criteria.", "The selected kinetic model must be the same across all temperatures; target-temperature prediction is an Arrhenius extrapolation from the observed temperature range, not a validated shelf-life claim.", "Review residuals, temperature control, excursions, batch and replicate structure, model plausibility, and regulatory stability requirements before any release, expiry, or storage decision."]}
