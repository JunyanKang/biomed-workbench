"""Deterministic known-PWM sequence motif enrichment primitives."""

from __future__ import annotations

import math
from typing import Any


DNA = frozenset("ACGTN")
COMPLEMENT = str.maketrans("ACGT", "TGCA")


class MotifEnrichmentError(ValueError):
    """Raised when sequence or PWM evidence is not scientifically interpretable."""


def validate_sequences(values: list[str], label: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise MotifEnrichmentError(f"{label} must contain at least one sequence")
    normalized = []
    for index, value in enumerate(values, start=1):
        sequence = str(value).upper().replace(" ", "").replace("\n", "")
        if not sequence or any(base not in DNA for base in sequence):
            raise MotifEnrichmentError(f"{label} sequence {index} is empty or contains non-DNA characters")
        normalized.append(sequence)
    return normalized


def normalize_motifs(motifs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(motifs, list) or not motifs:
        raise MotifEnrichmentError("at least one motif PWM is required")
    normalized = []
    seen = set()
    for item in motifs:
        if not isinstance(item, dict):
            raise MotifEnrichmentError("motifs must be objects")
        identifier = str(item.get("id", "")).strip()
        matrix = item.get("matrix")
        if not identifier or identifier in seen or not isinstance(matrix, dict) or set(matrix) != {"A", "C", "G", "T"}:
            raise MotifEnrichmentError("each motif requires a unique id and A/C/G/T matrix rows")
        rows = []
        widths = set()
        for base in "ACGT":
            row = matrix[base]
            if not isinstance(row, list) or not row:
                raise MotifEnrichmentError(f"motif {identifier} has an empty {base} row")
            try:
                numeric = [float(value) for value in row]
            except (TypeError, ValueError) as exc:
                raise MotifEnrichmentError(f"motif {identifier} has nonnumeric PWM values") from exc
            if any(value < 0 or not math.isfinite(value) for value in numeric):
                raise MotifEnrichmentError(f"motif {identifier} has invalid PWM values")
            rows.append(numeric)
            widths.add(len(numeric))
        if len(widths) != 1 or next(iter(widths)) < 3:
            raise MotifEnrichmentError(f"motif {identifier} must have one A/C/G/T width of at least three")
        for column in zip(*rows):
            if sum(column) <= 0:
                raise MotifEnrichmentError(f"motif {identifier} contains an all-zero PWM column")
        normalized.append({"id": identifier, "matrix": {base: rows[index] for index, base in enumerate("ACGT")}, "width": next(iter(widths))})
        seen.add(identifier)
    return normalized


def reverse_complement(sequence: str) -> str:
    return sequence.translate(COMPLEMENT)[::-1]


def normalized_window_score(window: str, motif: dict[str, Any], pseudocount: float = 0.1) -> float | None:
    if "N" in window:
        return None
    matrix = motif["matrix"]
    observed = minimum = maximum = 0.0
    for position, base in enumerate(window):
        column = {letter: matrix[letter][position] + pseudocount for letter in "ACGT"}
        total = sum(column.values())
        scores = {letter: math.log2((value / total) / 0.25) for letter, value in column.items()}
        observed += scores[base]
        minimum += min(scores.values())
        maximum += max(scores.values())
    return (observed - minimum) / (maximum - minimum) if maximum > minimum else 0.0


def sequence_has_motif(sequence: str, motif: dict[str, Any], threshold: float) -> bool:
    width = motif["width"]
    if len(sequence) < width:
        return False
    reverse = reverse_complement(sequence)
    for candidate in (sequence, reverse):
        for start in range(len(candidate) - width + 1):
            score = normalized_window_score(candidate[start : start + width], motif)
            if score is not None and score >= threshold:
                return True
    return False


def log_choose(total: int, selected: int) -> float:
    if selected < 0 or selected > total:
        return float("-inf")
    return math.lgamma(total + 1) - math.lgamma(selected + 1) - math.lgamma(total - selected + 1)


def fisher_enrichment_pvalue(foreground_total: int, foreground_hits: int, background_total: int, background_hits: int) -> float:
    total = foreground_total + background_total
    hit_total = foreground_hits + background_hits
    upper = min(foreground_total, hit_total)
    observed = foreground_hits
    log_denominator = log_choose(total, foreground_total)
    terms = [log_choose(hit_total, hits) + log_choose(total - hit_total, foreground_total - hits) - log_denominator for hits in range(observed, upper + 1)]
    maximum = max(terms)
    return min(1.0, math.exp(maximum) * sum(math.exp(term - maximum) for term in terms))


def benjamini_hochberg(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    adjusted = [1.0] * len(values)
    running = 1.0
    for rank, (index, value) in reversed(list(enumerate(ordered, start=1))):
        running = min(running, value * len(values) / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


def known_motif_enrichment(
    foreground_sequences: list[str], background_sequences: list[str], motifs: list[dict[str, Any]], threshold: float = 0.8
) -> dict[str, Any]:
    if not isinstance(threshold, (float, int)) or not 0 < float(threshold) <= 1:
        raise MotifEnrichmentError("threshold must be within (0, 1]")
    foreground = validate_sequences(foreground_sequences, "foreground")
    background = validate_sequences(background_sequences, "background")
    normalized_motifs = normalize_motifs(motifs)
    rows = []
    p_values = []
    for motif in normalized_motifs:
        foreground_hits = sum(sequence_has_motif(sequence, motif, float(threshold)) for sequence in foreground)
        background_hits = sum(sequence_has_motif(sequence, motif, float(threshold)) for sequence in background)
        p_value = fisher_enrichment_pvalue(len(foreground), foreground_hits, len(background), background_hits)
        odds_numerator = (foreground_hits + 0.5) * (len(background) - background_hits + 0.5)
        odds_denominator = (len(foreground) - foreground_hits + 0.5) * (background_hits + 0.5)
        rows.append({"motif_id": motif["id"], "motif_width": motif["width"], "foreground_hits": foreground_hits, "foreground_total": len(foreground), "background_hits": background_hits, "background_total": len(background), "odds_ratio": odds_numerator / odds_denominator, "p_value": p_value})
        p_values.append(p_value)
    for row, adjusted in zip(rows, benjamini_hochberg(p_values)):
        row["adjusted_p_value"] = adjusted
    rows.sort(key=lambda row: (row["adjusted_p_value"], -row["odds_ratio"], row["motif_id"]))
    return {"method": "bidirectional PWM scan followed by one-sided Fisher exact enrichment and Benjamini-Hochberg correction", "threshold": float(threshold), "foreground_sequence_count": len(foreground), "background_sequence_count": len(background), "motif_count": len(normalized_motifs), "results": rows, "limitations": ["PWM sequence matches are not direct transcription-factor occupancy evidence.", "Enrichment depends on the declared sequence universe, background composition, PWM collection, score threshold, and multiple-testing family."]}
