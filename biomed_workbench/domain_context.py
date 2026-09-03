"""Validate project-owned biological context without turning it into a claim engine."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Mapping, Sequence


_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.I)


def _nonempty_list(payload: Mapping[str, object], field: str) -> list[object]:
    value = payload.get(field, [])
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _strings(payload: Mapping[str, object], field: str) -> list[str]:
    values = _nonempty_list(payload, field)
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(f"{field} must contain non-empty strings")
    return [str(item).strip() for item in values]


def _validate_literature_claims(rows: Sequence[object]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"established_knowledge row {index} must be an object")
        statement = str(row.get("statement", "")).strip()
        doi = str(row.get("doi", "")).strip()
        scope = str(row.get("scope", "")).strip()
        if len(statement) < 12 or len(scope) < 5 or not _DOI.match(doi):
            raise ValueError(
                f"established_knowledge row {index} requires a specific statement, scope, and DOI"
            )
        normalized.append({"statement": statement, "scope": scope, "doi": doi})
    return normalized


def _validate_project_observations(rows: Sequence[object]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"project_observations row {index} must be an object")
        statement = str(row.get("statement", "")).strip()
        artifact_ids = row.get("artifact_ids", [])
        status = str(row.get("status", "CANDIDATE")).strip().upper()
        if len(statement) < 12:
            raise ValueError(f"project_observations row {index} requires a specific observation")
        if not isinstance(artifact_ids, list) or not artifact_ids or any(
            not isinstance(item, str) or not item.strip() for item in artifact_ids
        ):
            raise ValueError(f"project_observations row {index} requires artifact_ids")
        if status not in {"FORMAL", "CANDIDATE", "SENSITIVITY", "DEPRECATED"}:
            raise ValueError(f"project_observations row {index} has an unsupported status")
        normalized.append({
            "statement": statement,
            "artifact_ids": [str(item).strip() for item in artifact_ids],
            "status": status,
        })
    return normalized


def validate_domain_context(payload: Mapping[str, object]) -> dict[str, object]:
    """Return a normalized, digest-bound biological context for expert review.

    Literature knowledge and project observations remain separate by construction.
    The function checks provenance and inference boundaries; it does not certify that
    a biological statement is true.
    """
    profile_id = str(payload.get("profile_id", "")).strip()
    version = str(payload.get("version", "")).strip()
    organism = str(payload.get("organism", "")).strip()
    tissue_or_system = str(payload.get("tissue_or_system", "")).strip()
    if not all((profile_id, version, organism, tissue_or_system)):
        raise ValueError("profile_id, version, organism, and tissue_or_system are required")

    established = _validate_literature_claims(_nonempty_list(payload, "established_knowledge"))
    observations = _validate_project_observations(_nonempty_list(payload, "project_observations"))
    forbidden = _strings(payload, "forbidden_inferences")
    alternatives = _strings(payload, "competing_explanations")
    discriminators = _strings(payload, "discriminating_observations")
    if not established:
        raise ValueError("at least one DOI-bound established_knowledge statement is required")
    if not forbidden:
        raise ValueError("at least one project-specific forbidden inference is required")
    if alternatives and not discriminators:
        raise ValueError("competing explanations require discriminating observations")

    normalized: dict[str, object] = {
        "schema_version": 1,
        "profile_id": profile_id,
        "version": version,
        "organism": organism,
        "tissue_or_system": tissue_or_system,
        "developmental_or_disease_context": _strings(payload, "developmental_or_disease_context"),
        "cell_types_or_compartments": _strings(payload, "cell_types_or_compartments"),
        "established_knowledge": established,
        "project_observations": observations,
        "forbidden_inferences": forbidden,
        "competing_explanations": alternatives,
        "discriminating_observations": discriminators,
        "scientific_review_required": True,
        "interpretation": (
            "This profile supplies project-specific biological context and inference boundaries. "
            "It does not replace literature verification or expert scientific review."
        ),
    }
    normalized["profile_digest"] = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return normalized
