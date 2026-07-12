"""Biochemical model fitting and sequence-aware construct design."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Callable

from .data import normalize_sequence


def _positive(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return number


def _model_function(model: str) -> tuple[list[str], Callable[[float, list[float]], float]]:
    if model == "michaelis_menten":
        return ["vmax", "km"], lambda substrate, p: p[0] * substrate / (p[1] + substrate)
    if model == "hill":
        return ["vmax", "k_half", "hill_coefficient"], lambda substrate, p: p[0] * substrate**p[2] / (p[1] ** p[2] + substrate**p[2])
    if model == "substrate_inhibition":
        return ["vmax", "km", "ki"], lambda substrate, p: p[0] * substrate / (p[1] + substrate + substrate * substrate / p[2])
    raise ValueError("model must be michaelis_menten, hill, or substrate_inhibition")


def _initial_parameters(model: str, substrates: list[float], velocities: list[float]) -> list[float]:
    x_mean = math.fsum(substrates) / len(substrates)
    transformed = [substrate / velocity for substrate, velocity in zip(substrates, velocities)]
    y_mean = math.fsum(transformed) / len(transformed)
    denominator = math.fsum((value - x_mean) ** 2 for value in substrates)
    slope = math.fsum((x - x_mean) * (y - y_mean) for x, y in zip(substrates, transformed)) / denominator if denominator else 0.0
    intercept = y_mean - slope * x_mean
    vmax = 1.0 / slope if slope > 0 else max(velocities) * 1.2
    km = intercept * vmax if intercept > 0 else median_positive(substrates)
    if model == "michaelis_menten":
        return [vmax, km]
    if model == "hill":
        return [vmax, km, 1.0]
    return [vmax, km, max(substrates)]


def median_positive(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    return ordered[midpoint] if len(ordered) % 2 else (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _weighted_sse(
    parameters: list[float],
    substrates: list[float],
    velocities: list[float],
    weights: list[float],
    predict: Callable[[float, list[float]], float],
) -> float:
    try:
        predictions = [predict(value, parameters) for value in substrates]
    except (OverflowError, ZeroDivisionError):
        return math.inf
    if any(not math.isfinite(value) or value < 0 for value in predictions):
        return math.inf
    return math.fsum(weight * (observed - fitted) ** 2 for observed, fitted, weight in zip(velocities, predictions, weights))


def _coordinate_optimize(
    initial: list[float],
    objective: Callable[[list[float]], float],
    max_iterations: int = 500,
) -> tuple[list[float], bool, int]:
    logs = [math.log(max(value, 1e-12)) for value in initial]
    steps = [0.5] * len(logs)
    best = objective([math.exp(value) for value in logs])
    for iteration in range(1, max_iterations + 1):
        improved = False
        for index in range(len(logs)):
            for direction in (-1.0, 1.0):
                candidate = logs.copy()
                candidate[index] += direction * steps[index]
                score = objective([math.exp(value) for value in candidate])
                if score < best:
                    logs, best, improved = candidate, score, True
        if not improved:
            steps = [step / 2.0 for step in steps]
            if max(steps) < 1e-10:
                return [math.exp(value) for value in logs], True, iteration
    return [math.exp(value) for value in logs], False, max_iterations


def fit_enzyme_kinetics(observations: list[dict[str, Any]], model: str = "michaelis_menten") -> dict[str, Any]:
    """Fit common steady-state kinetic models with residual diagnostics."""
    names, predict = _model_function(model)
    if len(observations) < len(names) + 2:
        raise ValueError("the selected model requires at least parameters + 2 observations")
    substrates, velocities, weights = [], [], []
    for row in observations:
        if not isinstance(row, dict):
            raise ValueError("observations must be objects")
        substrates.append(_positive(row.get("substrate"), "substrate"))
        velocities.append(_positive(row.get("velocity"), "velocity"))
        weights.append(_positive(row.get("weight", 1.0), "weight"))
    if len(set(substrates)) < len(names) + 1:
        raise ValueError("insufficient distinct substrate concentrations for the selected model")
    initial = _initial_parameters(model, substrates, velocities)
    objective = lambda parameters: _weighted_sse(parameters, substrates, velocities, weights, predict)
    parameters, converged, iterations = _coordinate_optimize(initial, objective)
    fitted = [predict(value, parameters) for value in substrates]
    residuals = [observed - prediction for observed, prediction in zip(velocities, fitted)]
    rss = math.fsum(value * value for value in residuals)
    weighted_rss = objective(parameters)
    center = math.fsum(velocities) / len(velocities)
    total = math.fsum((value - center) ** 2 for value in velocities)
    n, k = len(velocities), len(parameters)
    aic = n * math.log(max(rss / n, 1e-300)) + 2 * k
    aicc = aic + 2 * k * (k + 1) / (n - k - 1) if n > k + 1 else None
    rows = []
    for source, prediction, residual in zip(observations, fitted, residuals):
        rows.append(
            {
                "substrate": float(source["substrate"]),
                "observed_velocity": float(source["velocity"]),
                "weight": float(source.get("weight", 1.0)),
                "fitted_velocity": prediction,
                "residual": residual,
            }
        )
    return {
        "model": model,
        "parameters": dict(zip(names, parameters)),
        "diagnostics": {
            "converged": converged,
            "iterations": iterations,
            "r_squared": 1.0 - rss / total if total else 1.0,
            "rmse": math.sqrt(rss / max(1, n - k)),
            "residual_sum_squares": rss,
            "weighted_residual_sum_squares": weighted_rss,
            "aic": aic,
            "aicc": aicc,
        },
        "observations": rows,
        "quality_gates": [
            "Inspect residuals and substrate coverage rather than relying on R-squared alone.",
            "Compare biologically plausible models using AICc only when all fits use the same observations and weights.",
            "Replicate-aware uncertainty and confidence intervals require a validated nonlinear statistics workflow.",
        ],
    }


def scan_glycosylation(protein: str, context_radius: int = 5) -> dict[str, Any]:
    """Scan N-linked sequons and serine/threonine-rich local contexts."""
    sequence = normalize_sequence(protein, "protein")
    if not 0 <= context_radius <= 50:
        raise ValueError("context_radius must be 0..50")
    n_sites = []
    blocked = []
    for index in range(len(sequence) - 2):
        triplet = sequence[index : index + 3]
        if triplet[0] != "N" or triplet[2] not in "ST":
            continue
        row = {
            "start": index + 1,
            "end": index + 3,
            "asparagine": index + 1,
            "motif": triplet,
            "context": sequence[max(0, index - context_radius) : min(len(sequence), index + 3 + context_radius)],
        }
        if triplet[1] == "P":
            blocked.append(row)
        else:
            n_sites.append(row)
    o_rich = []
    window = 7
    for index in range(max(0, len(sequence) - window + 1)):
        segment = sequence[index : index + window]
        count = sum(residue in "ST" for residue in segment)
        if count >= 4:
            o_rich.append({"start": index + 1, "end": index + len(segment), "sequence": segment, "serine_threonine_count": count})
    return {
        "protein_length": len(sequence),
        "n_linked_sequons": n_sites,
        "proline_blocked_sequons": blocked,
        "serine_threonine_rich_windows": o_rich,
        "coordinate_system": "one-based inclusive",
        "limitations": [
            "N-X-S/T sequons are necessary sequence motifs, not evidence of occupancy.",
            "Serine/threonine-rich windows are descriptive and are not an O-glycosylation predictor.",
            "Topology, accessibility, expression system, and mass-spectrometry evidence are required for site assignment.",
        ],
    }


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def plan_golden_gate(fragments: list[dict[str, Any]], enzyme: str = "BsaI", circular: bool = False) -> dict[str, Any]:
    """Audit an ordered Type IIS assembly for sequence and junction risks."""
    enzymes = {"BsaI": "GGTCTC", "BbsI": "GAAGAC", "BsmBI": "CGTCTC"}
    if enzyme not in enzymes or len(fragments) < 2:
        raise ValueError("supported enzyme and at least two fragments are required")
    recognition = enzymes[enzyme]
    reverse = _reverse_complement(recognition)
    normalized = []
    findings = []
    names = set()
    for fragment in fragments:
        if not isinstance(fragment, dict):
            raise ValueError("fragments must be objects")
        name = str(fragment.get("name", "")).strip()
        sequence = normalize_sequence(str(fragment.get("sequence", "")), "dna")
        left = str(fragment.get("left_overhang", "")).strip().upper()
        right = str(fragment.get("right_overhang", "")).strip().upper()
        if not name or name in names or not re.fullmatch(r"[ACGT]{4}", left) or not re.fullmatch(r"[ACGT]{4}", right):
            raise ValueError("fragment names must be unique and each overhang must contain four DNA bases")
        names.add(name)
        for strand, motif in (("+", recognition), ("-", reverse)):
            for match in re.finditer(f"(?={motif})", sequence):
                findings.append({"fragment": name, "strand": strand, "motif": motif, "start": match.start() + 1, "end": match.start() + len(motif)})
        normalized.append({"name": name, "sequence_length": len(sequence), "left_overhang": left, "right_overhang": right})
    pairs = list(zip(normalized, normalized[1:]))
    if circular:
        pairs.append((normalized[-1], normalized[0]))
    junctions = []
    for upstream, downstream in pairs:
        junctions.append(
            {
                "upstream": upstream["name"],
                "downstream": downstream["name"],
                "overhang": upstream["right_overhang"],
                "downstream_overhang": downstream["left_overhang"],
                "compatible": upstream["right_overhang"] == downstream["left_overhang"],
            }
        )
    junction_overhangs = [row["overhang"] for row in junctions]
    risk_findings = []
    for overhang, count in sorted(Counter(junction_overhangs).items()):
        if count > 1:
            risk_findings.append({"code": "DUPLICATE_JUNCTION_OVERHANG", "overhang": overhang, "count": count})
        if overhang == _reverse_complement(overhang):
            risk_findings.append({"code": "PALINDROMIC_OVERHANG", "overhang": overhang})
    for row in junctions:
        if not row["compatible"]:
            risk_findings.append({"code": "INCOMPATIBLE_JUNCTION", "upstream": row["upstream"], "downstream": row["downstream"]})
    return {
        "enzyme": enzyme,
        "recognition_site": recognition,
        "circular": circular,
        "fragments": normalized,
        "junctions": junctions,
        "internal_site_findings": findings,
        "risk_findings": risk_findings,
        "assembly_ready": not findings and not risk_findings,
        "quality_gates": [
            "Reconstruct the complete assembled sequence and verify reading frames, scars, and regulatory context.",
            "Use empirical ligation-fidelity data when selecting overhangs for high-complexity assemblies.",
            "Confirm oligonucleotide orientation, enzyme cut geometry, and final constructs by sequencing.",
        ],
    }
