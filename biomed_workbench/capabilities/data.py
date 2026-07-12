"""Deterministic data inspection primitives for scientific workflows."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable


DNA_ALPHABET = frozenset("ACGTRYSWKMBDHVN")
RNA_ALPHABET = frozenset("ACGURYSWKMBDHVN")
PROTEIN_ALPHABET = frozenset("ACDEFGHIKLMNPQRSTVWYBXZJUO*")
_DNA_COMPLEMENT = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")
_RNA_COMPLEMENT = str.maketrans("ACGURYSWKMBDHVN", "UGCAYRSWMKVHDBN")


def normalize_sequence(sequence: str, alphabet: str) -> str:
    if not isinstance(sequence, str):
        raise ValueError("sequence must be text")
    normalized = "".join(sequence.split()).upper()
    if not normalized:
        raise ValueError("sequence must not be empty")
    allowed = {"dna": DNA_ALPHABET, "rna": RNA_ALPHABET, "protein": PROTEIN_ALPHABET}.get(alphabet)
    if allowed is None:
        raise ValueError("alphabet must be dna, rna, or protein")
    invalid = sorted(set(normalized) - allowed)
    if invalid:
        raise ValueError(f"sequence contains invalid {alphabet} symbols: {''.join(invalid)}")
    return normalized


def sequence_inspect(sequence: str, alphabet: str = "dna") -> dict[str, Any]:
    normalized = normalize_sequence(sequence, alphabet)
    composition = dict(sorted(Counter(normalized).items()))
    if alphabet in {"dna", "rna"}:
        canonical = "ACGT" if alphabet == "dna" else "ACGU"
        canonical_length = sum(composition.get(base, 0) for base in canonical)
        gc_count = composition.get("G", 0) + composition.get("C", 0)
        ambiguous_positions = [index for index, base in enumerate(normalized, start=1) if base not in canonical]
        reverse_complement = normalized.translate(_DNA_COMPLEMENT if alphabet == "dna" else _RNA_COMPLEMENT)[::-1]
        return {
            "alphabet": alphabet,
            "normalized_sequence": normalized,
            "length": len(normalized),
            "canonical_length": canonical_length,
            "composition": composition,
            "gc_percent": round(100.0 * gc_count / canonical_length, 6) if canonical_length else None,
            "ambiguous_positions": ambiguous_positions,
            "reverse_complement": reverse_complement,
        }
    return {
        "alphabet": alphabet,
        "normalized_sequence": normalized,
        "length": len(normalized),
        "composition": composition,
        "ambiguous_positions": [index for index, residue in enumerate(normalized, start=1) if residue in "BXZJUO"],
        "stop_positions": [index for index, residue in enumerate(normalized, start=1) if residue == "*"],
    }


def _inferred_type(values: Iterable[Any]) -> str:
    observed = {type(value) for value in values if value is not None and value != ""}
    if not observed:
        return "empty"
    if observed <= {bool}:
        return "boolean"
    if observed <= {int}:
        return "integer"
    if observed <= {int, float} and bool not in observed:
        return "number"
    if observed <= {str}:
        return "string"
    return "mixed"


def profile_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("rows must be a list of objects")
    column_order: list[str] = []
    for row in rows:
        for column in row:
            if column not in column_order:
                column_order.append(str(column))
    columns: dict[str, Any] = {}
    for column in column_order:
        values = [row.get(column) for row in rows]
        present = [value for value in values if value is not None and value != ""]
        inferred = _inferred_type(values)
        unique = {jsonable_key(value) for value in present}
        details: dict[str, Any] = {
            "inferred_type": inferred,
            "missing_count": len(values) - len(present),
            "missing_fraction": round((len(values) - len(present)) / len(values), 6) if values else 0.0,
            "unique_count": len(unique),
        }
        if inferred in {"integer", "number"} and present:
            numbers = [float(value) for value in present]
            details["minimum"] = min(numbers)
            details["maximum"] = max(numbers)
            details["mean"] = math.fsum(numbers) / len(numbers)
        columns[column] = details
    return {
        "row_count": len(rows),
        "column_count": len(column_order),
        "column_order": column_order,
        "columns": columns,
    }


def jsonable_key(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return f"{type(value).__name__}:{value}"
    return f"{type(value).__name__}:{repr(value)}"
