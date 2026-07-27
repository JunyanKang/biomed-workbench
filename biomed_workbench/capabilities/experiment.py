"""Auditable calculations for common experimental planning and analysis."""

from __future__ import annotations

import math
from typing import Any


def _positive(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return value


def serial_dilution(
    initial_concentration: float,
    dilution_factor: float,
    steps: int,
    final_volume_ul: float,
) -> dict[str, Any]:
    concentration = _positive(initial_concentration, "initial_concentration")
    factor = _positive(dilution_factor, "dilution_factor")
    volume = _positive(final_volume_ul, "final_volume_ul")
    if factor <= 1 or not 1 <= steps <= 100:
        raise ValueError("dilution_factor must exceed 1 and steps must be 1..100")
    transfer = volume / factor
    diluent = volume - transfer
    result = []
    for step in range(1, steps + 1):
        concentration /= factor
        result.append(
            {
                "step": step,
                "concentration": concentration,
                "transfer_ul": transfer,
                "diluent_ul": diluent,
                "final_volume_ul": volume,
            }
        )
    return {"steps": result, "dilution_factor": factor, "assumption": "Each transfer is made from the immediately preceding dilution."}


def pcr_mix(
    reactions: int,
    reaction_volume_ul: float,
    components: dict[str, float],
    overage_percent: float = 10.0,
) -> dict[str, Any]:
    if not isinstance(reactions, int) or not 1 <= reactions <= 100_000:
        raise ValueError("reactions must be an integer from 1 to 100000")
    reaction_volume = _positive(reaction_volume_ul, "reaction_volume_ul")
    if not isinstance(components, dict) or not components:
        raise ValueError("components must be a nonempty object")
    normalized = {str(name): float(value) for name, value in components.items()}
    if any(not math.isfinite(value) or value < 0 for value in normalized.values()):
        raise ValueError("component volumes must be finite and non-negative")
    if not 0 <= overage_percent <= 100:
        raise ValueError("overage_percent must be 0..100")
    water = reaction_volume - math.fsum(normalized.values())
    if water < -1e-9:
        raise ValueError("component volumes exceed reaction volume")
    water = max(0.0, water)
    equivalents = reactions * (1.0 + overage_percent / 100.0)
    master_mix = {name: value * equivalents for name, value in normalized.items()}
    master_mix["water"] = water * equivalents
    return {
        "reactions": reactions,
        "prepared_reaction_equivalents": equivalents,
        "reaction_volume_ul": reaction_volume,
        "water_per_reaction_ul": water,
        "per_reaction": {**normalized, "water": water},
        "master_mix": master_mix,
    }


def dose_response_summary(
    concentrations: list[float],
    responses: list[float],
    direction: str = "decreasing",
) -> dict[str, Any]:
    if len(concentrations) != len(responses) or len(concentrations) < 3:
        raise ValueError("concentrations and responses require at least three paired values")
    if direction not in {"decreasing", "increasing"}:
        raise ValueError("direction must be decreasing or increasing")
    pairs = sorted((_positive(concentration, "concentration"), float(response)) for concentration, response in zip(concentrations, responses))
    if any(not math.isfinite(response) for _concentration, response in pairs):
        raise ValueError("responses must be finite")
    ordered_responses = [response for _concentration, response in pairs]
    monotonic = all(
        (right <= left if direction == "decreasing" else right >= left)
        for left, right in zip(ordered_responses, ordered_responses[1:])
    )
    lower, upper = min(ordered_responses), max(ordered_responses)
    half = (lower + upper) / 2.0
    half_concentration = None
    for (left_concentration, left_response), (right_concentration, right_response) in zip(pairs, pairs[1:]):
        if (left_response - half) * (right_response - half) <= 0 and left_response != right_response:
            fraction = (half - left_response) / (right_response - left_response)
            log_value = math.log10(left_concentration) + fraction * (math.log10(right_concentration) - math.log10(left_concentration))
            half_concentration = 10**log_value
            break
    return {
        "direction": direction,
        "monotonic": monotonic,
        "response_min": lower,
        "response_max": upper,
        "half_max_response": half,
        "half_max_concentration": half_concentration,
        "method": "log-concentration interpolation between observations bracketing the empirical half range",
        "limitations": ["This is not a nonlinear four-parameter logistic fit and does not estimate confidence intervals."],
    }


def _slope(xs: list[float], ys: list[float]) -> float:
    x_mean = math.fsum(xs) / len(xs)
    y_mean = math.fsum(ys) / len(ys)
    denominator = math.fsum((value - x_mean) ** 2 for value in xs)
    if denominator == 0:
        raise ValueError("time values must not be identical")
    return math.fsum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator


def growth_curve_summary(
    times: list[float] | None = None,
    values: list[float] | None = None,
    window: int = 3,
    observations: list[dict[str, Any]] | None = None,
    blank_od: float | None = None,
    replicate_level: str = "unspecified",
) -> dict[str, Any]:
    """Fit a bacterial growth curve while preserving replicate-level measurements.

    The legacy times/values pair remains a supported shorthand for a
    single-series descriptive fit. New requests should supply observations
    with stable replicate identifiers. Both logistic and modified Gompertz
    curves are fitted to every retained observation, then compared by AICc.
    The selected model is a measurement summary, not evidence of viability,
    strain fitness, or a condition effect.
    """
    try:
        import numpy as np
        from scipy.optimize import curve_fit
    except ImportError as exc:
        raise RuntimeError("numpy and scipy are required for bacterial growth-curve fitting") from exc

    if observations is not None and (times is not None or values is not None):
        raise ValueError("provide observations or the legacy times/values pair, not both")
    rows: list[dict[str, Any]] = []
    if observations is not None:
        if not isinstance(observations, list) or len(observations) < 6:
            raise ValueError("observations must contain at least six replicate-level measurements")
        for index, row in enumerate(observations):
            if not isinstance(row, dict):
                raise ValueError("each observation must be an object")
            time = float(row.get("time_hours"))
            od = float(row.get("od"))
            replicate_id = str(row.get("replicate_id", "")).strip()
            if not math.isfinite(time) or not math.isfinite(od) or not replicate_id:
                raise ValueError("each observation requires finite time_hours, finite od, and replicate_id")
            rows.append({"time_hours": time, "od": od, "replicate_id": replicate_id, "source_index": index})
    else:
        if not isinstance(times, list) or not isinstance(values, list) or len(times) != len(values) or len(times) < 3:
            raise ValueError("times and values require at least three equal-length pairs")
        for index, (time, od) in enumerate(zip(times, values)):
            time_value = float(time)
            od_value = float(od)
            if not math.isfinite(time_value) or not math.isfinite(od_value):
                raise ValueError("times and values must be finite")
            rows.append({"time_hours": time_value, "od": od_value, "replicate_id": f"legacy-{index + 1}", "source_index": index})

    if replicate_level not in {"unspecified", "technical", "biological"}:
        raise ValueError("replicate_level must be unspecified, technical, or biological")
    if not isinstance(window, int) or isinstance(window, bool) or not 2 <= window <= len(rows):
        raise ValueError("window must be an integer from 2 to the observation count")
    blank = 0.0 if blank_od is None else float(blank_od)
    if not math.isfinite(blank) or blank < 0:
        raise ValueError("blank_od must be a nonnegative finite number when supplied")

    seen = set()
    by_time: dict[float, list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["time_hours"], row["replicate_id"])
        if key in seen:
            raise ValueError("replicate_id may occur only once at each time_hours value")
        seen.add(key)
        corrected = row["od"] - blank
        if corrected < 0:
            raise ValueError("blank correction produced a negative OD; review blank identity and units")
        row["blank_corrected_od"] = corrected
        by_time.setdefault(row["time_hours"], []).append(row)
    if len(by_time) < 4:
        raise ValueError("at least four distinct time_hours values are required for curve-model comparison")

    ordered_rows = sorted(rows, key=lambda item: (item["time_hours"], item["replicate_id"]))
    x_absolute = np.asarray([row["time_hours"] for row in ordered_rows], dtype=float)
    y = np.asarray([row["blank_corrected_od"] for row in ordered_rows], dtype=float)
    time_origin = float(x_absolute.min())
    x = x_absolute - time_origin
    span = float(x.max())
    dynamic_range = float(y.max() - y.min())
    if span <= 0 or dynamic_range <= max(1e-8, 0.01 * max(float(y.max()), 1e-8)):
        raise ValueError("measurements lack time or OD dynamic range after blank correction")

    def logistic(time, baseline, amplitude, rate, inflection):
        argument = np.clip(-rate * (time - inflection), -700.0, 700.0)
        return baseline + amplitude / (1.0 + np.exp(argument))

    def gompertz(time, baseline, amplitude, maximum_rate, lag):
        argument = np.clip((maximum_rate * math.e / amplitude) * (lag - time) + 1.0, -700.0, 700.0)
        return baseline + amplitude * np.exp(-np.exp(argument))

    baseline_lower = float(y.min() - dynamic_range)
    baseline_upper = float(y.max())
    amplitude_upper = max(dynamic_range * 100.0, 1e-6)
    rate_upper = max(1.0, 100.0 / span)
    shared_bounds = (
        [baseline_lower, max(dynamic_range * 1e-7, 1e-10), 1e-10, -span],
        [baseline_upper, amplitude_upper, rate_upper, 2.0 * span],
    )
    initial = [float(y.min()), max(dynamic_range, 1e-6), min(1.0 / span, rate_upper / 2.0), span / 2.0]

    def fit_candidate(name: str, model) -> dict[str, Any]:
        try:
            parameters, covariance = curve_fit(model, x, y, p0=initial, bounds=shared_bounds, maxfev=50_000)
            fitted = model(x, *parameters)
            residuals = y - fitted
            rss = float(np.sum(residuals ** 2))
            total_sum_squares = float(np.sum((y - float(np.mean(y))) ** 2))
            r_squared = 1.0 - rss / total_sum_squares if total_sum_squares > 0 else None
            parameter_count = len(parameters)
            observation_count = int(y.size)
            aic = observation_count * math.log(max(rss / observation_count, 1e-300)) + 2.0 * parameter_count
            aicc = (
                aic + (2.0 * parameter_count * (parameter_count + 1)) / (observation_count - parameter_count - 1)
                if observation_count > parameter_count + 1
                else None
            )
            standard_errors = np.sqrt(np.clip(np.diag(covariance), 0.0, None))
            parameter_names = (
                ("baseline_od", "amplitude_od", "maximum_growth_rate_per_hour", "lag_time_hours")
                if name == "modified_gompertz"
                else ("baseline_od", "amplitude_od", "rate_constant_per_hour", "inflection_time_hours")
            )
            fitted_parameters = {
                parameter_name: float(value + time_origin if parameter_name in {"lag_time_hours", "inflection_time_hours"} else value)
                for parameter_name, value in zip(parameter_names, parameters)
            }
            parameter_uncertainty = {
                parameter_name: float(error)
                for parameter_name, error in zip(parameter_names, standard_errors)
            }
            maximum_rate = float(parameters[2]) if name == "modified_gompertz" else float(parameters[1] * parameters[2] / 4.0)
            return {
                "model": name,
                "fit_success": True,
                "parameters": fitted_parameters,
                "parameter_standard_errors": parameter_uncertainty,
                "maximum_growth_rate_per_hour": maximum_rate,
                "rss": rss,
                "r_squared": r_squared,
                "aic": float(aic),
                "aicc": float(aicc) if aicc is not None else None,
                "residual_mean": float(np.mean(residuals)),
                "residual_root_mean_square": float(math.sqrt(rss / observation_count)),
            }
        except (RuntimeError, ValueError, FloatingPointError) as exc:
            return {"model": name, "fit_success": False, "failure_reason": str(exc)}

    candidates = [fit_candidate("logistic", logistic), fit_candidate("modified_gompertz", gompertz)]
    successful = [candidate for candidate in candidates if candidate["fit_success"]]
    if not successful:
        raise ValueError("neither logistic nor modified Gompertz model converged; inspect the raw measurements")
    selected = min(
        successful,
        key=lambda candidate: candidate["aicc"] if candidate["aicc"] is not None else candidate["aic"],
    )

    timepoint_summary = []
    for time in sorted(by_time):
        corrected = [row["blank_corrected_od"] for row in by_time[time]]
        mean = math.fsum(corrected) / len(corrected)
        sd = math.sqrt(math.fsum((value - mean) ** 2 for value in corrected) / (len(corrected) - 1)) if len(corrected) > 1 else None
        timepoint_summary.append(
            {
                "time_hours": time,
                "replicate_count": len(corrected),
                "mean_blank_corrected_od": mean,
                "standard_deviation_od": sd,
                "coefficient_of_variation_percent": 100.0 * sd / mean if sd is not None and mean > 0 else None,
            }
        )
    legacy_pairs = sorted((row["time_hours"], row["blank_corrected_od"]) for row in ordered_rows)
    legacy_window = min(window, len(legacy_pairs))
    slopes = [
        (_slope([time for time, _ in legacy_pairs[start : start + legacy_window]], [math.log(value) for _, value in legacy_pairs[start : start + legacy_window]]), start)
        for start in range(len(legacy_pairs) - legacy_window + 1)
        if all(value > 0 for _, value in legacy_pairs[start : start + legacy_window])
    ]
    max_slope, start = max(slopes) if slopes else (None, None)
    replicate_complete = all(row["replicate_count"] >= 2 for row in timepoint_summary)
    residual_quality = selected["r_squared"] is not None and selected["r_squared"] >= 0.8
    fit_admissible = bool(residual_quality)
    interpretation_status = (
        "eligible-for-growth-curve-interpretation"
        if fit_admissible and replicate_complete and replicate_level == "biological"
        else "blocked-review-required"
    )
    return {
        "fit_admissible": fit_admissible,
        "fit_status": "admissible" if fit_admissible else "blocked-review-required",
        "interpretation_status": interpretation_status,
        "selected_model": selected["model"],
        "model_candidates": candidates,
        "selected_model_summary": selected,
        "replicate_level": replicate_level,
        "replicate_design_status": "complete-at-every-timepoint" if replicate_complete else "incomplete-at-one-or-more-timepoints",
        "blank_correction": {"blank_od": blank, "applied": blank_od is not None},
        "input_observation_count": len(ordered_rows),
        "distinct_timepoint_count": len(timepoint_summary),
        "timepoint_summary": timepoint_summary,
        "max_growth_rate_per_time": max_slope,
        "doubling_time": math.log(2) / max_slope if max_slope and max_slope > 0 else None,
        "log_phase_start_time": legacy_pairs[start][0] if start is not None else None,
        "log_phase_end_time": legacy_pairs[start + legacy_window - 1][0] if start is not None else None,
        "window": legacy_window,
        "method": "replicate-preserving logistic and modified Gompertz model comparison by AICc; legacy log-window summary retained for continuity",
        "quality_gates": [
            "Require a declared blank, OD units, plate layout, instrument settings, and raw replicate-level measurements before accepting model parameters.",
            "Review model residuals and both candidate fits; AICc selects only between the declared empirical curves and cannot prove a biological mechanism.",
            "Condition or strain claims require independently cultured biological replicates, randomization or plate-position review, and a predeclared between-condition model outside this per-curve summary.",
        ],
    }


def enumerate_cfu_from_dilution_plates(
    plates: list[dict[str, Any]],
    countable_minimum: int = 25,
    countable_maximum: int = 250,
    replicate_level: str = "unspecified",
) -> dict[str, Any]:
    """Estimate CFU per mL from declared, observed serial-dilution plate counts.

    Each plate contributes an exposure equal to plated volume divided by the
    cumulative dilution factor. Countable plates are pooled with the Poisson
    likelihood estimator rather than averaging dilution-specific back
    calculations. TNTC and low-count plates remain visible as censored or
    excluded observations; they are never replaced by simulated colony counts.
    """
    try:
        from scipy.stats import chi2
    except ImportError as exc:
        raise RuntimeError("scipy is required for CFU confidence intervals and heterogeneity diagnostics") from exc
    if not isinstance(plates, list) or not plates:
        raise ValueError("plates must be a nonempty array")
    if (
        isinstance(countable_minimum, bool)
        or isinstance(countable_maximum, bool)
        or not isinstance(countable_minimum, int)
        or not isinstance(countable_maximum, int)
        or countable_minimum < 1
        or countable_maximum <= countable_minimum
    ):
        raise ValueError("countable_minimum and countable_maximum must be ordered positive integers")
    if replicate_level not in {"unspecified", "technical", "biological"}:
        raise ValueError("replicate_level must be unspecified, technical, or biological")

    normalized = []
    seen = set()
    for index, plate in enumerate(plates):
        if not isinstance(plate, dict):
            raise ValueError("each plate must be an object")
        plate_id = str(plate.get("plate_id", "")).strip()
        replicate_id = str(plate.get("replicate_id", "")).strip()
        status = str(plate.get("count_status", "")).strip().lower()
        if not plate_id or not replicate_id or plate_id in seen:
            raise ValueError("each plate requires a unique plate_id and nonempty replicate_id")
        seen.add(plate_id)
        try:
            dilution_factor = float(plate.get("dilution_factor"))
            plated_volume = float(plate.get("plated_volume_ml"))
        except (TypeError, ValueError) as exc:
            raise ValueError("dilution_factor and plated_volume_ml must be numeric") from exc
        if not math.isfinite(dilution_factor) or dilution_factor < 1:
            raise ValueError("dilution_factor must be a finite cumulative reciprocal dilution of at least 1")
        if not math.isfinite(plated_volume) or plated_volume <= 0:
            raise ValueError("plated_volume_ml must be a positive finite number")
        colony_count = plate.get("colony_count")
        if status not in {"counted", "tntc", "invalid"}:
            raise ValueError("count_status must be counted, tntc, or invalid")
        if status == "counted":
            if isinstance(colony_count, bool) or not isinstance(colony_count, int) or colony_count < 0:
                raise ValueError("counted plates require a nonnegative integer colony_count")
        elif colony_count is not None:
            raise ValueError("tntc and invalid plates must not supply colony_count")
        normalized.append(
            {
                "plate_id": plate_id,
                "replicate_id": replicate_id,
                "dilution_factor": dilution_factor,
                "plated_volume_ml": plated_volume,
                "count_status": status,
                "colony_count": colony_count,
                "source_index": index,
            }
        )

    countable = []
    plate_results = []
    for plate in normalized:
        result = dict(plate)
        if plate["count_status"] == "tntc":
            result["selection_status"] = "excluded-tntc"
            result["estimated_cfu_per_ml"] = None
        elif plate["count_status"] == "invalid":
            result["selection_status"] = "excluded-invalid"
            result["estimated_cfu_per_ml"] = None
        elif plate["colony_count"] < countable_minimum:
            result["selection_status"] = "excluded-below-countable-range"
            result["estimated_cfu_per_ml"] = plate["colony_count"] * plate["dilution_factor"] / plate["plated_volume_ml"]
        elif plate["colony_count"] > countable_maximum:
            result["selection_status"] = "excluded-above-countable-range"
            result["estimated_cfu_per_ml"] = plate["colony_count"] * plate["dilution_factor"] / plate["plated_volume_ml"]
        else:
            result["selection_status"] = "countable"
            result["estimated_cfu_per_ml"] = plate["colony_count"] * plate["dilution_factor"] / plate["plated_volume_ml"]
            countable.append(result)
        plate_results.append(result)

    quality_gates = [
        "Use observed colony counts from declared dilution, plated volume, medium, incubation, and plate identity; this module never simulates a plate count.",
        "TNTC, invalid, and outside-range plates remain in the report but are not pooled into the primary CFU estimate.",
        "Between-condition, strain-fitness, or treatment claims require independently cultured biological replicates and a design-aware comparison outside this single-sample enumeration.",
    ]
    if not countable:
        return {
            "estimate_admissible": False,
            "enumeration_status": "blocked-no-countable-plates",
            "comparative_interpretation_status": "blocked-review-required",
            "cfu_per_ml": None,
            "confidence_interval_95": None,
            "countable_plate_count": 0,
            "total_plate_count": len(plate_results),
            "replicate_level": replicate_level,
            "replicate_design_status": "not-assessable-no-countable-plates",
            "heterogeneity": None,
            "plate_results": plate_results,
            "quality_gates": quality_gates,
        }

    total_colonies = sum(item["colony_count"] for item in countable)
    total_exposure_ml = math.fsum(item["plated_volume_ml"] / item["dilution_factor"] for item in countable)
    estimate = total_colonies / total_exposure_ml
    alpha = 0.05
    interval = {
        "lower_cfu_per_ml": 0.5 * float(chi2.ppf(alpha / 2, 2 * total_colonies)) / total_exposure_ml if total_colonies else 0.0,
        "upper_cfu_per_ml": 0.5 * float(chi2.ppf(1 - alpha / 2, 2 * (total_colonies + 1))) / total_exposure_ml,
        "method": "exact Poisson interval for pooled countable-plate exposure",
    }
    expected = [estimate * item["plated_volume_ml"] / item["dilution_factor"] for item in countable]
    chi_square = math.fsum(
        (item["colony_count"] - expected_count) ** 2 / expected_count
        for item, expected_count in zip(countable, expected)
        if expected_count > 0
    )
    degrees_of_freedom = len(countable) - 1
    heterogeneity = (
        {
            "pearson_chi_square": chi_square,
            "degrees_of_freedom": degrees_of_freedom,
            "p_value": float(chi2.sf(chi_square, degrees_of_freedom)),
            "status": "heterogeneous-review-required" if chi2.sf(chi_square, degrees_of_freedom) < 0.01 else "no-strong-evidence-of-extra-poisson-heterogeneity",
        }
        if degrees_of_freedom > 0
        else {
            "pearson_chi_square": None,
            "degrees_of_freedom": 0,
            "p_value": None,
            "status": "not-assessable-single-countable-plate",
        }
    )
    heterogeneity_blocks = heterogeneity["status"] == "heterogeneous-review-required"
    countable_replicates = {item["replicate_id"] for item in countable}
    replicate_status = (
        "multiple-replicates-retained"
        if len(countable_replicates) >= 2
        else "single-replicate-retained"
    )
    return {
        "estimate_admissible": not heterogeneity_blocks,
        "enumeration_status": "estimated" if not heterogeneity_blocks else "blocked-heterogeneous-countable-plates",
        "comparative_interpretation_status": (
            "eligible-for-design-aware-comparison"
            if not heterogeneity_blocks and replicate_level == "biological" and len(countable_replicates) >= 2
            else "blocked-review-required"
        ),
        "cfu_per_ml": estimate,
        "confidence_interval_95": interval,
        "countable_plate_count": len(countable),
        "total_plate_count": len(plate_results),
        "replicate_level": replicate_level,
        "replicate_design_status": replicate_status,
        "heterogeneity": heterogeneity,
        "plate_results": plate_results,
        "quality_gates": quality_gates,
    }


def simulate_bacterial_population_scenario(
    initial_population: float,
    growth_rate_per_hour: float,
    clearance_rate_per_hour: float,
    carrying_capacity: float,
    duration_hours: float,
    output_steps: int = 241,
) -> dict[str, Any]:
    """Integrate a declared logistic-growth-with-clearance scenario using RK4.

    Parameters are supplied by the user and are never estimated from the
    resulting trajectory. The output is explicitly simulated context for
    experimental design or sensitivity discussion, not measured population
    evidence.
    """
    initial = _positive(initial_population, "initial_population")
    growth = _positive(growth_rate_per_hour, "growth_rate_per_hour")
    clearance = float(clearance_rate_per_hour)
    capacity = _positive(carrying_capacity, "carrying_capacity")
    duration = _positive(duration_hours, "duration_hours")
    if not math.isfinite(clearance) or clearance < 0:
        raise ValueError("clearance_rate_per_hour must be a nonnegative finite number")
    if initial > capacity * 100:
        raise ValueError("initial_population is implausibly above carrying_capacity; review units")
    if isinstance(output_steps, bool) or not isinstance(output_steps, int) or not 2 <= output_steps <= 10_001:
        raise ValueError("output_steps must be an integer from 2 to 10001")

    def derivative(population: float) -> float:
        return growth * population * (1.0 - population / capacity) - clearance * population

    step = duration / (output_steps - 1)
    population = initial
    trajectory = [{"time_hours": 0.0, "simulated_population": population}]
    for index in range(1, output_steps):
        k1 = derivative(population)
        k2 = derivative(max(0.0, population + step * k1 / 2.0))
        k3 = derivative(max(0.0, population + step * k2 / 2.0))
        k4 = derivative(max(0.0, population + step * k3))
        population = max(0.0, population + step * (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0)
        trajectory.append({"time_hours": index * step, "simulated_population": population})
    net_low_density_rate = growth - clearance
    equilibrium = capacity * net_low_density_rate / growth if net_low_density_rate > 0 else 0.0
    return {
        "simulation_status": "completed",
        "population_is_simulated": True,
        "parameters": {
            "initial_population": initial,
            "growth_rate_per_hour": growth,
            "clearance_rate_per_hour": clearance,
            "carrying_capacity": capacity,
            "duration_hours": duration,
            "output_steps": output_steps,
        },
        "net_low_density_rate_per_hour": net_low_density_rate,
        "deterministic_equilibrium_population": equilibrium,
        "equilibrium_status": "positive-equilibrium" if equilibrium > 0 else "extinction-attractor",
        "trajectory": trajectory,
        "quality_gates": [
            "All parameters are user-supplied scenario assumptions and must retain units, source rationale, and plausible bounds outside this calculation.",
            "Numerical integration is checked for finite nonnegative states, but it does not validate parameter identifiability or model adequacy.",
            "Do not represent this trajectory as measured growth, a treatment effect, colonization, clearance mechanism, or population prediction without fitted and independently validated parameters.",
        ],
    }
