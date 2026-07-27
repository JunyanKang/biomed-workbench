"""Transparent biophysical fitting routines with explicit data boundaries."""

from __future__ import annotations

import math
import statistics
from typing import Any


def _one_site_injection_heats(
    injection_volumes_ul: list[float],
    cell_macromolecule_um: float,
    syringe_ligand_um: float,
    cell_volume_ul: float,
    log10_kd_m: float,
    enthalpy_kcal_per_mol: float,
    stoichiometry: float,
    dilution_intercept_ucal: float,
    dilution_slope_ucal_per_um: float,
) -> list[float]:
    """Predict per-injection integrated heats for a dilution-aware one-site model."""
    kd_um = 10.0 ** log10_kd_m * 1_000_000.0
    macromolecule = float(cell_macromolecule_um)
    ligand = 0.0
    complex_um = 0.0
    predicted: list[float] = []
    volume = float(cell_volume_ul)
    for injection_ul in injection_volumes_ul:
        dilution = 1.0 - injection_ul / volume
        macromolecule *= dilution
        ligand = ligand * dilution + syringe_ligand_um * injection_ul / volume
        binding_sites = stoichiometry * macromolecule
        discriminant = max(0.0, (binding_sites + ligand + kd_um) ** 2 - 4.0 * binding_sites * ligand)
        next_complex = (binding_sites + ligand + kd_um - math.sqrt(discriminant)) / 2.0
        bound_moles_delta = (next_complex - complex_um * dilution) * volume * 1e-12
        binding_heat = enthalpy_kcal_per_mol * 1e6 * bound_moles_delta
        dilution_heat = dilution_intercept_ucal + dilution_slope_ucal_per_um * ligand
        predicted.append(binding_heat + dilution_heat)
        complex_um = next_complex
    return predicted


def fit_itc_single_site_binding(
    injection_volumes_ul: list[float],
    integrated_heats_ucal: list[float],
    cell_macromolecule_um: float,
    syringe_ligand_um: float,
    cell_volume_ul: float,
    temperature_k: float = 298.15,
) -> dict[str, Any]:
    """Fit a dilution-aware one-site ITC model to observed integrated heats.

    Inputs must be integrated per-injection heats, not a raw thermogram. The
    model is intentionally bounded to one experiment and one-site binding;
    complex stoichiometry, global fits, baseline integration, and model
    selection remain separate scientific decisions.
    """
    try:
        import numpy as np
        from scipy.optimize import least_squares
    except ImportError as exc:
        raise RuntimeError("SciPy and NumPy are required for ITC single-site fitting") from exc
    values = (cell_macromolecule_um, syringe_ligand_um, cell_volume_ul, temperature_k)
    if not all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0 for value in values):
        raise ValueError("concentrations, cell_volume_ul, and temperature_k must be finite positive numbers")
    if not isinstance(injection_volumes_ul, list) or not isinstance(integrated_heats_ucal, list):
        raise ValueError("injection_volumes_ul and integrated_heats_ucal must be lists")
    if len(injection_volumes_ul) != len(integrated_heats_ucal) or len(injection_volumes_ul) < 8:
        raise ValueError("ITC fitting requires equal-length injection volumes and heats with at least eight injections")
    if not all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0 for value in injection_volumes_ul):
        raise ValueError("injection volumes must be finite positive numbers")
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in integrated_heats_ucal):
        raise ValueError("integrated heats must be finite numbers")
    if any(volume >= cell_volume_ul * 0.1 for volume in injection_volumes_ul):
        raise ValueError("each injection must be less than 10 percent of the cell volume for this dilution model")
    observed = np.asarray(integrated_heats_ucal, dtype=float)
    volumes = [float(value) for value in injection_volumes_ul]

    def residuals(parameters):
        return np.asarray(
            _one_site_injection_heats(
                volumes, float(cell_macromolecule_um), float(syringe_ligand_um), float(cell_volume_ul), *parameters
            ),
            dtype=float,
        ) - observed

    amplitude = max(float(np.ptp(observed)), 1.0)
    initial_enthalpy = max(
        -499.0,
        min(499.0, -amplitude / (float(cell_macromolecule_um) * float(cell_volume_ul) * 1e-6)),
    )
    initial = np.asarray([-6.0, initial_enthalpy, 1.0, 0.0, 0.0])
    fitted = least_squares(
        residuals,
        initial,
        bounds=([-12.0, -500.0, 0.1, -amplitude * 5, -amplitude * 5], [-2.0, 500.0, 10.0, amplitude * 5, amplitude * 5]),
        max_nfev=20000,
    )
    predicted = residuals(fitted.x) + observed
    residual = observed - predicted
    sse = float(np.sum(residual**2))
    dof = len(observed) - len(fitted.x)
    rmse = math.sqrt(sse / dof) if dof > 0 else None
    covariance = None
    parameter_se: list[float] = []
    if dof > 0 and fitted.jac.shape[0] >= fitted.jac.shape[1]:
        try:
            covariance = np.linalg.inv(fitted.jac.T @ fitted.jac) * sse / dof
            parameter_se = [float(value) for value in np.sqrt(np.diag(covariance))]
        except np.linalg.LinAlgError:
            pass
    log_kd, enthalpy, stoichiometry, dilution_intercept, dilution_slope = (float(value) for value in fitted.x)
    kd_m = 10.0 ** log_kd
    delta_g = 0.00198720425864083 * float(temperature_k) * math.log(kd_m)
    delta_s = (enthalpy - delta_g) / float(temperature_k)
    boundary_hits = [
        name
        for name, value, lower, upper in zip(
            ("log10_kd_m", "enthalpy_kcal_per_mol", "stoichiometry", "dilution_intercept_ucal", "dilution_slope_ucal_per_um"),
            fitted.x,
            (-12.0, -500.0, 0.1, -amplitude * 5, -amplitude * 5),
            (-2.0, 500.0, 10.0, amplitude * 5, amplitude * 5),
            strict=True,
        )
        if abs(value - lower) < 1e-6 or abs(value - upper) < 1e-6
    ]
    quality_status = "passed" if fitted.success and not boundary_hits and rmse is not None else "review-required"
    return {
        "model": "dilution-aware one-site equilibrium binding fit",
        "temperature_k": float(temperature_k),
        "injection_count": len(volumes),
        "parameters": {"kd_m": kd_m, "ka_per_m": 1.0 / kd_m, "enthalpy_kcal_per_mol": enthalpy, "stoichiometry": stoichiometry, "dilution_intercept_ucal": dilution_intercept, "dilution_slope_ucal_per_um": dilution_slope, "delta_g_kcal_per_mol": delta_g, "delta_s_kcal_per_mol_k": delta_s},
        "parameter_standard_errors": parameter_se,
        "predicted_heats_ucal": [float(value) for value in predicted],
        "residuals_ucal": [float(value) for value in residual],
        "fit_diagnostics": {"converged": bool(fitted.success), "message": str(fitted.message), "sse_ucal2": sse, "rmse_ucal": rmse, "degrees_of_freedom": dof, "boundary_hits": boundary_hits, "quality_status": quality_status},
        "limitations": ["This fits one supplied integrated-heat experiment under a one-site equilibrium model; it does not integrate raw thermograms, select among binding models, perform global or Bayesian fitting, correct concentration errors, establish stoichiometry, or validate a biological interaction.", "Blank and replicate experiments, injection anomalies, concentration uncertainty, buffer ionization, and residual structure must be reviewed before interpreting fitted thermodynamic parameters."],
    }


def electrophysiology_trace_summary(
    time_ms: list[float],
    signal: list[float],
    baseline_window_ms: float | None = None,
    threshold: float | None = None,
    polarity: str = "positive",
) -> dict[str, Any]:
    """Summarize one declared electrophysiology trace without inferring cell state."""
    if polarity not in {"positive", "negative"}:
        raise ValueError("polarity must be positive or negative")
    if not isinstance(time_ms, list) or not isinstance(signal, list) or len(time_ms) != len(signal) or len(time_ms) < 5:
        raise ValueError("time_ms and signal must be equal-length lists with at least five observations")
    pairs = [(float(time), float(value)) for time, value in zip(time_ms, signal, strict=True)]
    if any(not math.isfinite(time) or not math.isfinite(value) for time, value in pairs):
        raise ValueError("time_ms and signal values must be finite")
    pairs = sorted(pairs)
    if any(right <= left for (left, _), (right, _) in zip(pairs, pairs[1:])):
        raise ValueError("time_ms values must be unique after sorting")
    times = [time for time, _value in pairs]
    values = [value for _time, value in pairs]
    intervals = [right - left for left, right in zip(times, times[1:])]
    median_interval = statistics.median(intervals)
    jitter = max(abs(interval - median_interval) for interval in intervals) / median_interval if median_interval > 0 else math.inf
    if baseline_window_ms is None:
        baseline_cutoff = times[0] + max(median_interval, (times[-1] - times[0]) * 0.1)
    else:
        baseline_window = float(baseline_window_ms)
        if not math.isfinite(baseline_window) or baseline_window <= 0:
            raise ValueError("baseline_window_ms must be positive when supplied")
        baseline_cutoff = times[0] + baseline_window
    baseline_values = [value for time, value in pairs if time <= baseline_cutoff]
    if len(baseline_values) < 2:
        raise ValueError("baseline window contains fewer than two observations")
    baseline = statistics.median(baseline_values)
    centered = [value - baseline for value in values]
    if polarity == "positive":
        peak_index, peak_value = max(enumerate(centered), key=lambda item: item[1])
        threshold_value = 0.5 * peak_value if threshold is None else float(threshold)
        above = [value >= threshold_value for value in centered]
    else:
        peak_index, peak_value = min(enumerate(centered), key=lambda item: item[1])
        threshold_value = 0.5 * peak_value if threshold is None else float(threshold)
        above = [value <= threshold_value for value in centered]
    if not math.isfinite(threshold_value):
        raise ValueError("threshold must be finite when supplied")
    crossings = [
        {"time_ms": times[index], "direction": "enter"}
        for index in range(1, len(above))
        if above[index] and not above[index - 1]
    ]
    return {
        "trace_count": 1,
        "observation_count": len(values),
        "time_start_ms": times[0],
        "time_end_ms": times[-1],
        "median_sampling_interval_ms": median_interval,
        "sampling_jitter_fraction": jitter,
        "baseline": baseline,
        "polarity": polarity,
        "peak_amplitude_from_baseline": peak_value,
        "time_to_peak_ms": times[peak_index] - times[0],
        "threshold": threshold_value,
        "threshold_crossing_count": len(crossings),
        "threshold_crossings": crossings,
        "quality_status": "passed" if jitter <= 0.05 and abs(peak_value) > 0 else "review-required",
        "limitations": [
            "This summarizes one supplied trace; it does not detect action-potential classes, model membrane properties, correct series resistance, infer synaptic physiology, or diagnose cell state.",
            "Filtering, event detection rules, clamp mode, units, stimulation protocol, replicate identity, and acquisition metadata must be reviewed before biological interpretation.",
        ],
    }
