"""Clean-room molecular design calculations with explicit limitations."""

from __future__ import annotations

import math
import re
from typing import Any

from .data import normalize_sequence


_COMPLEMENT = str.maketrans("ACGTRYSWKMBDHVN", "TGCAYRSWMKVHDBN")
_ENZYMES = {
    "BamHI": "GGATCC",
    "BbsI": "GAAGAC",
    "BsaI": "GGTCTC",
    "EcoRI": "GAATTC",
    "HindIII": "AAGCTT",
    "NotI": "GCGGCCGC",
    "PstI": "CTGCAG",
    "XhoI": "CTCGAG",
}
_CODONS = {
    "human": {
        "A": "GCC", "R": "CGC", "N": "AAC", "D": "GAC", "C": "TGC", "Q": "CAG", "E": "GAG",
        "G": "GGC", "H": "CAC", "I": "ATC", "L": "CTG", "K": "AAG", "M": "ATG", "F": "TTC",
        "P": "CCC", "S": "AGC", "T": "ACC", "W": "TGG", "Y": "TAC", "V": "GTG", "*": "TGA",
    },
    "ecoli": {
        "A": "GCG", "R": "CGT", "N": "AAC", "D": "GAT", "C": "TGC", "Q": "CAG", "E": "GAA",
        "G": "GGC", "H": "CAT", "I": "ATT", "L": "CTG", "K": "AAA", "M": "ATG", "F": "TTT",
        "P": "CCG", "S": "TCT", "T": "ACC", "W": "TGG", "Y": "TAT", "V": "GTG", "*": "TAA",
    },
}


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(_COMPLEMENT)[::-1]


def _gc(sequence: str) -> float:
    return 100.0 * (sequence.count("G") + sequence.count("C")) / len(sequence)


def _tm(sequence: str) -> float:
    if len(sequence) < 14:
        return 2.0 * (sequence.count("A") + sequence.count("T")) + 4.0 * (sequence.count("G") + sequence.count("C"))
    return 64.9 + 41.0 * ((sequence.count("G") + sequence.count("C")) - 16.4) / len(sequence)


def _homopolymer(sequence: str) -> int:
    return max((len(match.group(0)) for match in re.finditer(r"(.)\1*", sequence)), default=0)


def _primer(sequence: str, start: int, strand: str) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "start": start,
        "end": start + len(sequence) - 1,
        "strand": strand,
        "length": len(sequence),
        "gc_percent": round(_gc(sequence), 3),
        "tm_c": round(_tm(sequence), 3),
        "max_homopolymer": _homopolymer(sequence),
    }


def design_primers(
    template: str,
    min_length: int = 18,
    max_length: int = 25,
    target_tm: float = 60.0,
    max_pairs: int = 10,
) -> dict[str, Any]:
    template = normalize_sequence(template, "dna")
    if set(template) - set("ACGT"):
        raise ValueError("primer design requires an unambiguous DNA template")
    if not 14 <= min_length <= max_length <= 40 or len(template) < 2 * min_length:
        raise ValueError("invalid primer lengths or template is too short")
    if not 1 <= max_pairs <= 100:
        raise ValueError("max_pairs must be 1..100")
    pairs = []
    for forward_length in range(min_length, max_length + 1):
        forward_sequence = template[:forward_length]
        forward = _primer(forward_sequence, 1, "+")
        for reverse_length in range(min_length, max_length + 1):
            reverse_sequence = _reverse_complement(template[-reverse_length:])
            reverse = _primer(reverse_sequence, len(template) - reverse_length + 1, "-")
            tm_delta = abs(forward["tm_c"] - reverse["tm_c"])
            score = (
                abs(forward["tm_c"] - target_tm)
                + abs(reverse["tm_c"] - target_tm)
                + 2.0 * tm_delta
                + max(0.0, abs(forward["gc_percent"] - 50.0) - 10.0) / 5.0
                + max(0.0, abs(reverse["gc_percent"] - 50.0) - 10.0) / 5.0
                + 4.0 * max(0, forward["max_homopolymer"] - 4)
                + 4.0 * max(0, reverse["max_homopolymer"] - 4)
            )
            pairs.append(
                {
                    "forward": forward,
                    "reverse": reverse,
                    "amplicon_length": len(template),
                    "tm_delta_c": round(tm_delta, 3),
                    "rank_score": round(score, 6),
                }
            )
    pairs.sort(key=lambda item: (item["rank_score"], item["forward"]["length"], item["reverse"]["length"]))
    return {
        "template_length": len(template),
        "tm_method": "Wallace below 14 nt; empirical GC formula otherwise",
        "pairs": pairs[:max_pairs],
        "limitations": [
            "Genomic uniqueness and off-target amplification are not assessed; verify candidates against the intended reference.",
            "Secondary structure and salt-adjusted nearest-neighbor thermodynamics require a dedicated downstream check.",
        ],
    }


def _guide_record(guide: str, pam: str, start: int, strand: str) -> dict[str, Any]:
    gc = _gc(guide)
    homopolymer = _homopolymer(guide)
    score = 100.0 - abs(gc - 50.0) * 1.5 - max(0, homopolymer - 3) * 12.0
    return {
        "guide": guide,
        "pam": pam,
        "strand": strand,
        "start": start,
        "end": start + len(guide) - 1,
        "gc_percent": round(gc, 3),
        "max_homopolymer": homopolymer,
        "heuristic_score": round(max(0.0, score), 3),
    }


def crispr_guides(sequence: str, guide_length: int = 20, max_guides: int = 50) -> dict[str, Any]:
    sequence = normalize_sequence(sequence, "dna")
    if set(sequence) - set("ACGT"):
        raise ValueError("guide discovery requires unambiguous DNA")
    if not 15 <= guide_length <= 25 or not 1 <= max_guides <= 500:
        raise ValueError("invalid guide_length or max_guides")
    guides = []
    for index in range(0, len(sequence) - guide_length - 2):
        guide = sequence[index : index + guide_length]
        pam = sequence[index + guide_length : index + guide_length + 3]
        if len(pam) == 3 and pam[1:] == "GG":
            guides.append(_guide_record(guide, pam, index + 1, "+"))
    for pam_index in range(0, len(sequence) - guide_length - 2):
        pam_forward = sequence[pam_index : pam_index + 3]
        downstream = sequence[pam_index + 3 : pam_index + 3 + guide_length]
        if pam_forward[:2] == "CC" and len(downstream) == guide_length:
            guides.append(_guide_record(_reverse_complement(downstream), _reverse_complement(pam_forward), pam_index + 4, "-"))
    guides.sort(key=lambda item: (-item["heuristic_score"], item["start"], item["strand"]))
    return {
        "nuclease": "SpCas9",
        "pam_rule": "NGG",
        "guides": guides[:max_guides],
        "limitations": [
            "Heuristic ranking is not an activity model.",
            "Genome-wide off-targets, variant overlap, chromatin accessibility, and delivery constraints require reference-aware validation.",
        ],
    }


def restriction_sites(sequence: str, enzymes: list[str] | None = None) -> dict[str, Any]:
    sequence = normalize_sequence(sequence, "dna")
    selected = enzymes or sorted(_ENZYMES)
    unknown = sorted(set(selected) - set(_ENZYMES))
    if unknown:
        raise ValueError(f"unknown enzymes: {', '.join(unknown)}")
    sites = []
    for enzyme in selected:
        motif = _ENZYMES[enzyme]
        for match in re.finditer(f"(?={motif})", sequence):
            sites.append({"enzyme": enzyme, "motif": motif, "start": match.start() + 1, "end": match.start() + len(motif)})
    sites.sort(key=lambda item: (item["start"], item["enzyme"]))
    return {"sequence_length": len(sequence), "sites": sites, "site_count": len(sites), "coordinate_system": "one-based inclusive"}


def back_translate(protein: str, organism: str = "human") -> dict[str, Any]:
    protein = normalize_sequence(protein, "protein")
    if set(protein) - set(_CODONS.get(organism, {})):
        if organism not in _CODONS:
            raise ValueError(f"unsupported organism: {organism}")
        raise ValueError("protein contains ambiguous or unsupported residues")
    codons = _CODONS[organism]
    dna = "".join(codons[residue] for residue in protein)
    return {
        "protein": protein,
        "organism": organism,
        "dna": dna,
        "gc_percent": round(_gc(dna), 3),
        "method": "deterministic preferred-codon back translation",
        "limitations": ["Codon-pair bias, RNA structure, motifs, repeats, and expression context are not optimized."],
    }
