"""Rhythm analysis with explicit fixed-period cosinor assumptions."""

from __future__ import annotations

import math
from typing import Any


def fit_fixed_period_cosinor(time: list[float], values: list[float], period: float = 24.0) -> dict[str, Any]:
    """Fit y = mesor + beta*cos(wt) + gamma*sin(wt) for one declared period."""
    try:
        import numpy as np
        from scipy.stats import f as f_distribution
        from scipy.stats import t as t_distribution
    except ImportError as exc:
        raise RuntimeError("NumPy and SciPy are required for fixed-period cosinor fitting") from exc
    if not isinstance(time, list) or not isinstance(values, list) or len(time) != len(values) or len(time) < 6:
        raise ValueError("time and values must be equal-length lists with at least six observations")
    if not isinstance(period, (int, float)) or not math.isfinite(period) or period <= 0:
        raise ValueError("period must be a finite positive number")
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (*time, *values)):
        raise ValueError("time and values must be finite numbers")
    ordered = sorted(zip((float(value) for value in time), (float(value) for value in values), strict=True))
    times = np.asarray([item[0] for item in ordered])
    observed = np.asarray([item[1] for item in ordered])
    omega = 2.0 * math.pi / float(period)
    design = np.column_stack((np.ones(len(times)), np.cos(omega * times), np.sin(omega * times)))
    coefficients, _, rank, _ = np.linalg.lstsq(design, observed, rcond=None)
    if rank != 3:
        raise ValueError("time sampling does not identify the fixed-period cosinor design")
    predicted = design @ coefficients
    residuals = observed - predicted
    sse = float(residuals @ residuals)
    centered_sse = float(((observed - observed.mean()) ** 2).sum())
    dof = len(observed) - 3
    if dof <= 0:
        raise ValueError("at least four residual degrees of freedom are required")
    covariance = np.linalg.inv(design.T @ design) * sse / dof
    beta, gamma = float(coefficients[1]), float(coefficients[2])
    amplitude = math.hypot(beta, gamma)
    acrophase = math.atan2(gamma, beta) % (2.0 * math.pi)
    acrophase_time = (acrophase / (2.0 * math.pi)) * float(period)
    model_sse = sse
    null_sse = centered_sse
    numerator = max(0.0, (null_sse - model_sse) / 2.0)
    denominator = model_sse / dof
    f_statistic = numerator / denominator if denominator > 0 else math.inf
    p_value = float(f_distribution.sf(f_statistic, 2, dof)) if math.isfinite(f_statistic) else 0.0
    critical_t = float(t_distribution.ppf(0.975, dof))
    mesor_se = math.sqrt(float(covariance[0, 0]))
    coverage = float(times[-1] - times[0])
    phase_bins = {int((item % period) / period * 8) for item in times}
    return {
        "model": "fixed-period ordinary-least-squares cosinor",
        "period": float(period),
        "observation_count": len(times),
        "parameters": {"mesor": float(coefficients[0]), "amplitude": amplitude, "acrophase_radians": acrophase, "acrophase_time": acrophase_time, "beta_cosine": beta, "gamma_sine": gamma},
        "mesor_95_ci": [float(coefficients[0] - critical_t * mesor_se), float(coefficients[0] + critical_t * mesor_se)],
        "fit_diagnostics": {"r_squared": 1.0 - model_sse / null_sse if null_sse > 0 else None, "residual_sse": model_sse, "residual_degrees_of_freedom": dof, "zero_amplitude_f_statistic": f_statistic, "zero_amplitude_p_value": p_value, "time_coverage": coverage, "occupied_eighth_period_bins": len(phase_bins), "quality_status": "passed" if coverage >= period * 0.75 and len(phase_bins) >= 4 else "review-required"},
        "predicted_values": [float(value) for value in predicted],
        "residuals": [float(value) for value in residuals],
        "limitations": ["This tests a predeclared fixed period in one series; it does not discover a period, model nonlinear trends, handle repeated-measures correlation, establish circadian causality, or replace replicate-aware inference.", "A nominal zero-amplitude p-value is conditional on the declared period, independent homoscedastic residuals, and the tested model; sampling design and multiple tested periods require separate correction and review."],
    }
