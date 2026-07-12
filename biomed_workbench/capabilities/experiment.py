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


def growth_curve_summary(times: list[float], values: list[float], window: int = 3) -> dict[str, Any]:
    if len(times) != len(values) or len(times) < 3:
        raise ValueError("times and values require at least three pairs")
    if not 2 <= window <= len(times):
        raise ValueError("window must be between 2 and the number of observations")
    pairs = sorted((float(time), _positive(value, "growth value")) for time, value in zip(times, values))
    if any(not math.isfinite(time) for time, _value in pairs) or len({time for time, _value in pairs}) != len(pairs):
        raise ValueError("times must be finite and unique")
    candidates = []
    for start in range(len(pairs) - window + 1):
        segment = pairs[start : start + window]
        slope = _slope([time for time, _value in segment], [math.log(value) for _time, value in segment])
        candidates.append((slope, start, start + window - 1))
    max_slope, start, end = max(candidates)
    return {
        "max_growth_rate_per_time": max_slope,
        "doubling_time": math.log(2) / max_slope if max_slope > 0 else None,
        "log_phase_start_time": pairs[start][0],
        "log_phase_end_time": pairs[end][0],
        "window": window,
        "method": "maximum sliding-window linear slope of log-transformed positive measurements",
    }
