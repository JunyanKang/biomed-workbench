"""Numerically bounded statistical primitives used by scientific capabilities."""

from __future__ import annotations

import math
from typing import Any


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    if any(not math.isfinite(float(value)) or not 0 <= float(value) <= 1 for value in p_values):
        raise ValueError("p-values must be finite and in [0, 1]")
    count = len(p_values)
    ordered = sorted(enumerate(map(float, p_values)), key=lambda item: item[1])
    adjusted = [0.0] * count
    running = 1.0
    for rank_index in range(count - 1, -1, -1):
        original_index, value = ordered[rank_index]
        rank = rank_index + 1
        running = min(running, value * count / rank)
        adjusted[original_index] = min(1.0, running)
    return adjusted


def hypergeometric_tail(population: int, successes: int, draws: int, observed: int) -> float:
    if not all(isinstance(value, int) for value in (population, successes, draws, observed)):
        raise ValueError("hypergeometric parameters must be integers")
    if population <= 0 or not 0 <= successes <= population or not 0 <= draws <= population or observed < 0:
        raise ValueError("invalid hypergeometric parameters")
    maximum = min(successes, draws)
    if observed > maximum:
        return 0.0
    denominator = math.comb(population, draws)
    minimum = max(observed, 0, draws - (population - successes))
    probability = math.fsum(
        math.comb(successes, value) * math.comb(population - successes, draws - value) / denominator
        for value in range(minimum, maximum + 1)
    )
    return min(1.0, probability)


def _beta_fraction(a: float, b: float, x: float) -> float:
    maximum_iterations = 300
    epsilon = 3e-14
    floor = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < floor:
        d = floor
    d = 1.0 / d
    result = d
    for iteration in range(1, maximum_iterations + 1):
        doubled = 2 * iteration
        coefficient = iteration * (b - iteration) * x / ((qam + doubled) * (a + doubled))
        d = 1.0 + coefficient * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + coefficient / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        result *= d * c
        coefficient = -(a + iteration) * (qab + iteration) * x / ((a + doubled) * (qap + doubled))
        d = 1.0 + coefficient * d
        if abs(d) < floor:
            d = floor
        c = 1.0 + coefficient / c
        if abs(c) < floor:
            c = floor
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < epsilon:
            return result
    raise ArithmeticError("incomplete beta fraction did not converge")


def _regularized_beta(x: float, a: float, b: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_fraction(a, b, x) / a
    return 1.0 - front * _beta_fraction(b, a, 1.0 - x) / b


def _finite_numbers(values: list[float], name: str) -> list[float]:
    numbers = [float(value) for value in values]
    if len(numbers) < 2 or any(not math.isfinite(value) for value in numbers):
        raise ValueError(f"{name} requires at least two finite observations")
    return numbers


def welch_t_test(group_a: list[float], group_b: list[float]) -> dict[str, Any]:
    a = _finite_numbers(group_a, "group_a")
    b = _finite_numbers(group_b, "group_b")
    mean_a = math.fsum(a) / len(a)
    mean_b = math.fsum(b) / len(b)
    variance_a = math.fsum((value - mean_a) ** 2 for value in a) / (len(a) - 1)
    variance_b = math.fsum((value - mean_b) ** 2 for value in b) / (len(b) - 1)
    component_a = variance_a / len(a)
    component_b = variance_b / len(b)
    standard_error_squared = component_a + component_b
    if standard_error_squared == 0:
        t_statistic = 0.0 if mean_a == mean_b else math.copysign(math.inf, mean_a - mean_b)
        p_value = 1.0 if mean_a == mean_b else 0.0
        degrees = math.inf
    else:
        t_statistic = (mean_a - mean_b) / math.sqrt(standard_error_squared)
        denominator = component_a**2 / (len(a) - 1) + component_b**2 / (len(b) - 1)
        degrees = standard_error_squared**2 / denominator if denominator else math.inf
        if math.isinf(degrees):
            p_value = math.erfc(abs(t_statistic) / math.sqrt(2.0))
        else:
            x = degrees / (degrees + t_statistic**2)
            p_value = _regularized_beta(x, degrees / 2.0, 0.5)
    return {
        "mean_a": mean_a,
        "mean_b": mean_b,
        "difference": mean_a - mean_b,
        "t_statistic": t_statistic,
        "degrees_of_freedom": degrees,
        "p_value_two_sided": min(1.0, max(0.0, p_value)),
        "method": "Welch unequal-variance two-sample t-test",
    }


def student_t_two_sided_p(t_statistic: float, degrees_of_freedom: float) -> float:
    """Return the two-sided Student t tail probability for finite inputs."""
    statistic = float(t_statistic)
    degrees = float(degrees_of_freedom)
    if not math.isfinite(statistic) or not math.isfinite(degrees) or degrees <= 0:
        raise ValueError("t statistic and positive degrees of freedom must be finite")
    x = degrees / (degrees + statistic**2)
    probability = _regularized_beta(x, degrees / 2.0, 0.5)
    return min(1.0, max(0.0, probability))
