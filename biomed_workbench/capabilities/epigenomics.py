"""Executable epigenomic evidence functions with explicit scientific boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..implementations.motif_enrichment import known_motif_enrichment
from ..implementations.cool_contact_evidence import cool_contact_candidates


def sequence_motif_enrichment(
    foreground_sequences: list[str], background_sequences: list[str], motifs: list[dict[str, Any]], threshold: float = 0.8
) -> dict[str, Any]:
    """Test declared known PWMs against declared foreground and background sequences."""
    return known_motif_enrichment(foreground_sequences, background_sequences, motifs, threshold)


def cool_contact_evidence(cool_path: str, regulatory_elements_path: str, max_candidates: int = 10000) -> dict[str, Any]:
    """Extract bounded descriptive enhancer-promoter contact evidence from .cool."""
    return cool_contact_candidates(Path(cool_path), Path(regulatory_elements_path), max_candidates=max_candidates)
