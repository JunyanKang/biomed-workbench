"""Quantitative wet-lab assay analysis with explicit calibration and QC."""

from __future__ import annotations

import math
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
