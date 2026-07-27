"""Clean-room molecular design calculations with explicit limitations."""

from __future__ import annotations

import math
import re
from collections import Counter
from io import StringIO
from typing import Any

from Bio import __version__ as BIOPYTHON_VERSION
from Bio.Align import PairwiseAligner
from Bio.Data import CodonTable
from Bio.Seq import Seq
from Bio import SeqIO

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
_RESTRICTION_CUT_OFFSETS = {
    "BamHI": 1,
    "BbsI": 2,
    "BsaI": 1,
    "EcoRI": 1,
    "HindIII": 1,
    "NotI": 2,
    "PstI": 5,
    "XhoI": 1,
}
_PALINDROMIC_DIGEST_ENZYMES = frozenset({"BamHI", "EcoRI", "HindIII", "NotI", "PstI", "XhoI"})
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

_UNAMBIGUOUS_ALPHABETS = {
    "dna": frozenset("ACGT"),
    "rna": frozenset("ACGU"),
    "protein": frozenset("ACDEFGHIKLMNPQRSTVWY"),
}


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(_COMPLEMENT)[::-1]


def pairwise_sequence_alignment(
    reference: str,
    query: str,
    alphabet: str = "dna",
    mode: str = "global",
    match_score: float = 1.0,
    mismatch_score: float = -1.0,
    open_gap_score: float = -2.0,
    extend_gap_score: float = -0.5,
) -> dict[str, Any]:
    """Align two declared sequences with an explicit, versioned scoring contract.

    This is intentionally a two-sequence descriptive alignment. It does not infer
    homology, genomic placement, variants, orthology, or functional conservation.
    """
    if alphabet not in _UNAMBIGUOUS_ALPHABETS:
        raise ValueError("alphabet must be dna, rna, or protein")
    reference = normalize_sequence(reference, alphabet)
    query = normalize_sequence(query, alphabet)
    ambiguous_reference = sorted(set(reference) - _UNAMBIGUOUS_ALPHABETS[alphabet])
    ambiguous_query = sorted(set(query) - _UNAMBIGUOUS_ALPHABETS[alphabet])
    if ambiguous_reference or ambiguous_query:
        raise ValueError("pairwise alignment requires unambiguous sequences in the declared alphabet")
    if mode not in {"global", "local"}:
        raise ValueError("mode must be global or local")
    scores = (match_score, mismatch_score, open_gap_score, extend_gap_score)
    if not all(isinstance(score, (int, float)) and math.isfinite(score) for score in scores):
        raise ValueError("alignment scores must be finite numbers")
    if match_score <= mismatch_score:
        raise ValueError("match_score must be greater than mismatch_score")
    if open_gap_score > 0 or extend_gap_score > 0:
        raise ValueError("gap scores must be zero or negative")

    aligner = PairwiseAligner()
    aligner.mode = mode
    aligner.match_score = match_score
    aligner.mismatch_score = mismatch_score
    aligner.open_gap_score = open_gap_score
    aligner.extend_gap_score = extend_gap_score
    alignment = aligner.align(reference, query)[0]
    reference_aligned = str(alignment[0])
    query_aligned = str(alignment[1])
    aligned_pairs = [(left, right) for left, right in zip(reference_aligned, query_aligned, strict=True) if left != "-" and right != "-"]
    exact_match_count = sum(left == right for left, right in aligned_pairs)
    gap_count = sum(left == "-" or right == "-" for left, right in zip(reference_aligned, query_aligned, strict=True))
    coordinates = alignment.coordinates.tolist()
    blocks = [
        {
            "reference_start": int(coordinates[0][index]),
            "reference_end": int(coordinates[0][index + 1]),
            "query_start": int(coordinates[1][index]),
            "query_end": int(coordinates[1][index + 1]),
        }
        for index in range(len(coordinates[0]) - 1)
        if coordinates[0][index] != coordinates[0][index + 1] and coordinates[1][index] != coordinates[1][index + 1]
    ]
    reference_aligned_count = sum(base != "-" for base in reference_aligned)
    query_aligned_count = sum(base != "-" for base in query_aligned)
    return {
        "alphabet": alphabet,
        "mode": mode,
        "algorithm": "Biopython PairwiseAligner dynamic programming",
        "biopython_version": BIOPYTHON_VERSION,
        "scoring": {
            "match_score": float(match_score),
            "mismatch_score": float(mismatch_score),
            "open_gap_score": float(open_gap_score),
            "extend_gap_score": float(extend_gap_score),
        },
        "reference_length": len(reference),
        "query_length": len(query),
        "reference_aligned": reference_aligned,
        "query_aligned": query_aligned,
        "alignment_length": len(reference_aligned),
        "score": float(alignment.score),
        "aligned_residue_pair_count": len(aligned_pairs),
        "exact_match_count": exact_match_count,
        "mismatch_count": len(aligned_pairs) - exact_match_count,
        "gap_count": gap_count,
        "identity_fraction": round(exact_match_count / len(aligned_pairs), 8) if aligned_pairs else 0.0,
        "reference_coverage": round(reference_aligned_count / len(reference), 8),
        "query_coverage": round(query_aligned_count / len(query), 8),
        "coordinate_system": "zero-based half-open",
        "aligned_blocks": blocks,
        "limitations": [
            "This pairwise alignment does not establish homology, orthology, genomic placement, variant calls, or functional conservation.",
            "Ambiguous residues are rejected so the declared scoring contract remains interpretable; use a validated ambiguity-aware method when that is scientifically required.",
        ],
    }


def annotate_open_reading_frames(
    sequence: str,
    min_length: int = 90,
    search_reverse: bool = True,
    filter_nested: bool = True,
    translation_table: int = 1,
) -> dict[str, Any]:
    """Find complete start-to-stop ORFs on declared DNA strands.

    The returned coordinates always address the supplied forward sequence as
    zero-based half-open intervals. The coding sequence for a reverse ORF is
    reported in its own 5'-to-3' coding orientation.
    """
    sequence = normalize_sequence(sequence, "dna")
    if set(sequence) - _UNAMBIGUOUS_ALPHABETS["dna"]:
        raise ValueError("ORF annotation requires unambiguous DNA")
    if not isinstance(min_length, int) or not 3 <= min_length <= len(sequence):
        raise ValueError("min_length must be an integer from 3 through sequence length")
    if min_length % 3:
        raise ValueError("min_length must be divisible by three")
    if not isinstance(search_reverse, bool) or not isinstance(filter_nested, bool):
        raise ValueError("search_reverse and filter_nested must be boolean")
    if not isinstance(translation_table, int):
        raise ValueError("translation_table must be an NCBI genetic-code integer")
    try:
        codon_table = CodonTable.unambiguous_dna_by_id[translation_table]
    except KeyError as exc:
        raise ValueError("translation_table is not a supported unambiguous NCBI DNA code") from exc

    def find_in_strand(strand_sequence: str, strand: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for frame_offset in range(3):
            active_starts: list[int] = []
            for codon_start in range(frame_offset, len(strand_sequence) - 2, 3):
                codon = strand_sequence[codon_start : codon_start + 3]
                if codon in codon_table.start_codons:
                    active_starts.append(codon_start)
                if codon not in codon_table.stop_codons:
                    continue
                for start in active_starts:
                    end = codon_start + 3
                    coding_sequence = strand_sequence[start:end]
                    if len(coding_sequence) < min_length:
                        continue
                    if strand == "+":
                        original_start, original_end = start, end
                    else:
                        original_start, original_end = len(sequence) - end, len(sequence) - start
                    records.append(
                        {
                            "start": original_start,
                            "end": original_end,
                            "strand": strand,
                            "frame": frame_offset + 1 if strand == "+" else -(frame_offset + 1),
                            "length": len(coding_sequence),
                            "sequence": coding_sequence,
                            "protein_sequence": str(Seq(coding_sequence).translate(table=translation_table, to_stop=True)),
                            "terminal_stop_codon": codon,
                        }
                    )
                active_starts.clear()
        return records

    records = find_in_strand(sequence, "+")
    if search_reverse:
        records.extend(find_in_strand(_reverse_complement(sequence), "-"))
    records.sort(key=lambda record: (-record["length"], record["strand"], record["start"], record["frame"]))
    if filter_nested:
        selected: list[dict[str, Any]] = []
        for record in records:
            if any(
                record["strand"] == retained["strand"]
                and record["start"] >= retained["start"]
                and record["end"] <= retained["end"]
                for retained in selected
            ):
                continue
            selected.append(record)
        records = selected
    forward_count = sum(record["strand"] == "+" for record in records)
    reverse_count = len(records) - forward_count
    return {
        "sequence_length": len(sequence),
        "translation_table": translation_table,
        "translation_table_name": codon_table.names[0],
        "search_reverse": search_reverse,
        "filter_nested": filter_nested,
        "coordinate_system": "zero-based half-open on supplied forward DNA sequence",
        "orfs": records,
        "summary": {
            "total_orf_count": len(records),
            "forward_orf_count": forward_count,
            "reverse_orf_count": reverse_count,
            "mean_orf_length": round(math.fsum(record["length"] for record in records) / len(records), 8) if records else 0.0,
        },
        "limitations": [
            "ORF discovery is not gene, transcript, promoter, operon, plasmid-feature, expression, or functional annotation.",
            "Only complete start-to-stop ORFs under the declared genetic code are reported; partial coding regions and ambiguous DNA require a separately validated analysis.",
        ],
    }


def localize_sequence_variants(
    reference: str,
    query: str,
    alphabet: str = "dna",
    reference_coordinate_offset: int = 0,
    match_score: float = 1.0,
    mismatch_score: float = -1.0,
    open_gap_score: float = -2.0,
    extend_gap_score: float = -0.5,
) -> dict[str, Any]:
    """Derive descriptive sequence substitutions and indels from one global alignment.

    Event intervals are zero-based half-open positions on the supplied reference
    sequence, shifted by ``reference_coordinate_offset``. Insertions use an empty
    interval at the reference interbase position. This is not a VCF normalizer.
    """
    if not isinstance(reference_coordinate_offset, int) or reference_coordinate_offset < 0:
        raise ValueError("reference_coordinate_offset must be a nonnegative integer")
    alignment = pairwise_sequence_alignment(
        reference=reference,
        query=query,
        alphabet=alphabet,
        mode="global",
        match_score=match_score,
        mismatch_score=mismatch_score,
        open_gap_score=open_gap_score,
        extend_gap_score=extend_gap_score,
    )
    reference_aligned = alignment["reference_aligned"]
    query_aligned = alignment["query_aligned"]
    events: list[dict[str, Any]] = []
    reference_position = 0
    index = 0
    while index < len(reference_aligned):
        ref_base = reference_aligned[index]
        query_base = query_aligned[index]
        if ref_base == query_base:
            if ref_base != "-":
                reference_position += 1
            index += 1
            continue
        event_start = reference_position
        ref_bases: list[str] = []
        query_bases: list[str] = []
        if ref_base == "-":
            kind = "insertion"
            while index < len(reference_aligned) and reference_aligned[index] == "-":
                query_bases.append(query_aligned[index])
                index += 1
        elif query_base == "-":
            kind = "deletion"
            while index < len(reference_aligned) and query_aligned[index] == "-":
                ref_bases.append(reference_aligned[index])
                reference_position += 1
                index += 1
        else:
            kind = "substitution"
            while (
                index < len(reference_aligned)
                and reference_aligned[index] != "-"
                and query_aligned[index] != "-"
                and reference_aligned[index] != query_aligned[index]
            ):
                ref_bases.append(reference_aligned[index])
                query_bases.append(query_aligned[index])
                reference_position += 1
                index += 1
        event_end = reference_position
        events.append(
            {
                "event_type": kind,
                "reference_interval": {
                    "start": reference_coordinate_offset + event_start,
                    "end": reference_coordinate_offset + event_end,
                },
                "reference_sequence": "".join(ref_bases),
                "alternate_sequence": "".join(query_bases),
            }
        )
    return {
        "alphabet": alphabet,
        "algorithm": "Biopython PairwiseAligner global dynamic programming",
        "biopython_version": BIOPYTHON_VERSION,
        "reference_coordinate_offset": reference_coordinate_offset,
        "coordinate_system": "zero-based half-open on supplied reference sequence plus declared offset",
        "scoring": alignment["scoring"],
        "alignment_score": alignment["score"],
        "reference_aligned": reference_aligned,
        "query_aligned": query_aligned,
        "events": events,
        "summary": {
            "event_count": len(events),
            "substitution_count": sum(event["event_type"] == "substitution" for event in events),
            "insertion_count": sum(event["event_type"] == "insertion" for event in events),
            "deletion_count": sum(event["event_type"] == "deletion" for event in events),
        },
        "limitations": [
            "Events are descriptive differences in the supplied sequence pair, not normalized VCF records, genomic variant calls, haplotypes, genotype calls, or clinical interpretations.",
            "Repeat contexts can admit multiple equally scored alignments; retain the aligned sequences and scoring contract before selecting a representation for downstream work.",
        ],
    }


def simulate_pcr_amplicons(
    template: str,
    forward_primer: str,
    reverse_primer: str,
    circular: bool = False,
    max_products: int = 100,
    selected_candidate_index: int | None = None,
) -> dict[str, Any]:
    """Enumerate exact-match PCR amplicons on a declared linear or circular DNA template."""
    template = normalize_sequence(template, "dna")
    forward_primer = normalize_sequence(forward_primer, "dna")
    reverse_primer = normalize_sequence(reverse_primer, "dna")
    if set(template) - _UNAMBIGUOUS_ALPHABETS["dna"] or set(forward_primer) - _UNAMBIGUOUS_ALPHABETS["dna"] or set(reverse_primer) - _UNAMBIGUOUS_ALPHABETS["dna"]:
        raise ValueError("PCR simulation requires unambiguous DNA template and primers")
    if len(forward_primer) < 10 or len(reverse_primer) < 10:
        raise ValueError("PCR simulation requires primers of at least 10 nucleotides")
    if not isinstance(circular, bool) or not isinstance(max_products, int) or not 1 <= max_products <= 1000:
        raise ValueError("circular must be boolean and max_products must be 1..1000")
    reverse_binding = _reverse_complement(reverse_primer)
    forward_sites = [index for index in range(len(template) - len(forward_primer) + 1) if template.startswith(forward_primer, index)]
    reverse_sites = [index for index in range(len(template) - len(reverse_binding) + 1) if template.startswith(reverse_binding, index)]
    products: list[dict[str, Any]] = []
    for forward_start in forward_sites:
        for reverse_start in reverse_sites:
            if reverse_start >= forward_start:
                end = reverse_start + len(reverse_binding)
                sequence = template[forward_start:end]
                wraps_origin = False
            elif circular:
                end = reverse_start + len(reverse_binding)
                sequence = template[forward_start:] + template[:end]
                wraps_origin = True
            else:
                continue
            products.append({
                "forward_binding_interval": {"start": forward_start, "end": forward_start + len(forward_primer)},
                "reverse_binding_interval": {"start": reverse_start, "end": reverse_start + len(reverse_binding)},
                "wraps_origin": wraps_origin,
                "amplicon_length": len(sequence),
                "amplicon_sequence": sequence,
            })
    products.sort(key=lambda product: (product["amplicon_length"], product["forward_binding_interval"]["start"], product["reverse_binding_interval"]["start"]))
    truncated = len(products) > max_products
    if selected_candidate_index is not None and (not isinstance(selected_candidate_index, int) or selected_candidate_index < 0):
        raise ValueError("selected_candidate_index must be a nonnegative integer when provided")
    return {
        "template_length": len(template),
        "circular": circular,
        "binding_policy": "exact full-length match; forward primer on supplied strand and reverse-primer complement on supplied strand",
        "coordinate_system": "zero-based half-open on supplied template sequence",
        "forward_binding_site_count": len(forward_sites),
        "reverse_binding_site_count": len(reverse_sites),
        "products": products[:max_products],
        "truncated": truncated,
        "selected_candidate_index": selected_candidate_index,
        "limitations": [
            "This exact-match sequence simulation does not model annealing temperature, salt, polymerase chemistry, secondary structure, primer dimers, genomic off-targets, amplification efficiency, or experimental yield.",
            "A listed in-silico amplicon is not evidence that PCR will succeed; retain template provenance and validate the chosen product experimentally.",
        ],
    }


def screen_primer_pair_specificity(
    forward_primer: str,
    reverse_primer: str,
    reference_sequences: list[dict[str, Any]],
    intended_reference_id: str,
    max_products_per_reference: int = 100,
) -> dict[str, Any]:
    """Screen one primer pair against a declared finite reference sequence set.

    This is an exact-match screen, not a genome-wide off-target prediction. It
    is useful when the reference set itself represents the relevant construct,
    paralog, amplicon, or contaminant panel.
    """
    forward_primer = normalize_sequence(forward_primer, "dna")
    reverse_primer = normalize_sequence(reverse_primer, "dna")
    if set(forward_primer) - _UNAMBIGUOUS_ALPHABETS["dna"] or set(reverse_primer) - _UNAMBIGUOUS_ALPHABETS["dna"]:
        raise ValueError("specificity screening requires unambiguous DNA primers")
    if len(forward_primer) < 10 or len(reverse_primer) < 10:
        raise ValueError("specificity screening requires primers of at least 10 nucleotides")
    if not isinstance(reference_sequences, list) or not reference_sequences:
        raise ValueError("reference_sequences must be a nonempty list")
    if not isinstance(intended_reference_id, str) or not intended_reference_id.strip():
        raise ValueError("intended_reference_id must be nonempty text")
    if not isinstance(max_products_per_reference, int) or not 1 <= max_products_per_reference <= 1000:
        raise ValueError("max_products_per_reference must be 1..1000")
    summaries = []
    identifiers = set()
    for item in reference_sequences:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("sequence"), str):
            raise ValueError("each reference sequence requires text id and sequence")
        identifier = item["id"].strip()
        if not identifier or identifier in identifiers:
            raise ValueError("reference sequence identifiers must be nonempty and unique")
        identifiers.add(identifier)
        circular = item.get("circular", False)
        if not isinstance(circular, bool):
            raise ValueError("reference circular values must be boolean")
        simulation = simulate_pcr_amplicons(item["sequence"], forward_primer, reverse_primer, circular=circular, max_products=max_products_per_reference)
        summaries.append({
            "reference_id": identifier,
            "circular": circular,
            "template_length": simulation["template_length"],
            "product_count": len(simulation["products"]),
            "products": simulation["products"],
            "truncated": simulation["truncated"],
        })
    if intended_reference_id not in identifiers:
        raise ValueError("intended_reference_id is not present in reference_sequences")
    intended = next(row for row in summaries if row["reference_id"] == intended_reference_id)
    off_targets = [row["reference_id"] for row in summaries if row["reference_id"] != intended_reference_id and row["product_count"]]
    status = "specific-within-declared-panel" if intended["product_count"] == 1 and not off_targets and not intended["truncated"] else "not-specific-within-declared-panel"
    return {
        "intended_reference_id": intended_reference_id,
        "binding_policy": "exact full-length primer matches only",
        "coordinate_system": "zero-based half-open on each declared reference sequence",
        "reference_count": len(summaries),
        "reference_summaries": summaries,
        "intended_product_count": intended["product_count"],
        "off_target_reference_ids": off_targets,
        "specificity_status": status,
        "limitations": [
            "This evaluates only the declared finite reference panel with exact full-length matches; it is not a genome-wide, transcriptome-wide, mismatch-tolerant, or thermodynamic off-target screen.",
            "A panel-specific pass does not prove experimental specificity or PCR success; use an appropriate reference-aware search and experimental validation before making such claims.",
        ],
    }


def summarize_rna_secondary_structure(dot_bracket: str, sequence: str | None = None) -> dict[str, Any]:
    """Validate one RNA dot-bracket structure and summarize its observed topology."""
    if not isinstance(dot_bracket, str) or not dot_bracket:
        raise ValueError("dot_bracket must be nonempty text")
    structure = "".join(dot_bracket.split())
    brackets = {"(": ")", "[": "]", "{": "}"}
    closers = {close: opening for opening, close in brackets.items()}
    stacks = {opening: [] for opening in brackets}
    pairs: list[tuple[int, int, str]] = []
    for index, token in enumerate(structure):
        if token in brackets:
            stacks[token].append(index)
        elif token in closers:
            opening = closers[token]
            if not stacks[opening]:
                raise ValueError("dot_bracket has an unmatched closing bracket")
            pairs.append((stacks[opening].pop(), index, opening + token))
        elif token != ".":
            raise ValueError("dot_bracket supports only ., (), [], and {} characters")
    if any(stacks.values()):
        raise ValueError("dot_bracket has an unmatched opening bracket")
    pairs.sort()
    normalized_sequence = None
    pair_classes: dict[str, int] = {"AU": 0, "UA": 0, "GC": 0, "CG": 0, "GU": 0, "UG": 0, "noncanonical": 0}
    if sequence is not None:
        normalized_sequence = normalize_sequence(sequence, "rna")
        if len(normalized_sequence) != len(structure):
            raise ValueError("RNA sequence length must match dot_bracket length")
        for left, right, _ in pairs:
            key = normalized_sequence[left] + normalized_sequence[right]
            pair_classes[key if key in pair_classes else "noncanonical"] += 1
    stems: list[list[tuple[int, int, str]]] = []
    for pair in pairs:
        if stems and pair[0] == stems[-1][-1][0] + 1 and pair[1] == stems[-1][-1][1] - 1:
            stems[-1].append(pair)
        else:
            stems.append([pair])
    return {
        "length": len(structure),
        "dot_bracket": structure,
        "sequence": normalized_sequence,
        "coordinate_system": "zero-based nucleotide positions",
        "base_pairs": [{"left": left, "right": right, "bracket_class": kind} for left, right, kind in pairs],
        "stems": [{"start_pair": {"left": stem[0][0], "right": stem[0][1]}, "end_pair": {"left": stem[-1][0], "right": stem[-1][1]}, "pair_count": len(stem)} for stem in stems],
        "summary": {"base_pair_count": len(pairs), "paired_nucleotide_fraction": round((2 * len(pairs)) / len(structure), 8), "stem_count": len(stems), "pair_classes": pair_classes if normalized_sequence else None},
        "limitations": ["This validates and summarizes a supplied secondary-structure representation; it does not predict folding, calculate thermodynamic free energy, infer kinetics, or validate structure experimentally.", "Pseudoknot bracket classes are preserved as supplied notation, not independently inferred structural evidence."],
    }


def summarize_aligned_protein_conservation(sequences: list[str], identifiers: list[str] | None = None) -> dict[str, Any]:
    """Summarize per-column conservation in a pre-aligned protein sequence set."""
    if not isinstance(sequences, list) or len(sequences) < 2:
        raise ValueError("sequences must contain at least two aligned protein sequences")
    normalized = []
    for sequence in sequences:
        if not isinstance(sequence, str):
            raise ValueError("every sequence must be text")
        value = "".join(sequence.split()).upper()
        if not value or set(value) - set("ACDEFGHIKLMNPQRSTVWY-"):
            raise ValueError("aligned protein sequences may contain canonical residues and gaps only")
        normalized.append(value)
    alignment_length = len(normalized[0])
    if not alignment_length or any(len(sequence) != alignment_length for sequence in normalized):
        raise ValueError("all aligned protein sequences must have one nonzero common length")
    if identifiers is None:
        identifiers = [f"sequence_{index + 1}" for index in range(len(normalized))]
    if not isinstance(identifiers, list) or len(identifiers) != len(normalized) or len(set(identifiers)) != len(identifiers):
        raise ValueError("identifiers must be unique and match the sequence count")
    columns = []
    for index in range(alignment_length):
        residues = [sequence[index] for sequence in normalized if sequence[index] != "-"]
        counts = Counter(residues)
        coverage = len(residues) / len(normalized)
        consensus, consensus_count = (counts.most_common(1)[0] if counts else (None, 0))
        frequencies = [count / len(residues) for count in counts.values()] if residues else []
        entropy = -sum(value * math.log2(value) for value in frequencies)
        columns.append({"alignment_position": index, "coverage_fraction": round(coverage, 8), "consensus_residue": consensus, "consensus_fraction": round(consensus_count / len(residues), 8) if residues else 0.0, "shannon_entropy_bits": round(entropy, 8), "residue_counts": dict(sorted(counts.items()))})
    return {"sequence_count": len(normalized), "identifiers": identifiers, "alignment_length": alignment_length, "coordinate_system": "zero-based alignment columns", "columns": columns, "summary": {"mean_coverage_fraction": round(sum(column["coverage_fraction"] for column in columns) / alignment_length, 8), "mean_consensus_fraction": round(sum(column["consensus_fraction"] for column in columns) / alignment_length, 8), "fully_conserved_column_count": sum(column["consensus_fraction"] == 1.0 and column["coverage_fraction"] == 1.0 for column in columns)}, "limitations": ["This summarizes an already aligned input and does not establish homology, orthology, evolutionary selection, functional importance or structural conservation.", "Gap handling and any upstream alignment settings remain part of the scientific contract and must be retained with this summary."]}


def summarize_cd_thermal_transition(temperatures_c: list[float], signals: list[float]) -> dict[str, Any]:
    """Summarize a monotonic circular-dichroism thermal transition without structural deconvolution."""
    if not isinstance(temperatures_c, list) or not isinstance(signals, list) or len(temperatures_c) < 4 or len(temperatures_c) != len(signals):
        raise ValueError("temperatures_c and signals must be equal-length lists with at least four observations")
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (*temperatures_c, *signals)):
        raise ValueError("temperatures and signals must be finite numbers")
    temperatures = [float(value) for value in temperatures_c]
    values = [float(value) for value in signals]
    if any(right <= left for left, right in zip(temperatures, temperatures[1:])):
        raise ValueError("temperatures_c must be strictly increasing")
    low, high = values[0], values[-1]
    span = high - low
    if span == 0:
        raise ValueError("signals must have nonzero endpoint span")
    fractions = [(value - low) / span for value in values]
    direction = "increasing" if span > 0 else "decreasing"
    monotonic_violations = sum(
        (right < left if span > 0 else right > left)
        for left, right in zip(values, values[1:])
    )
    def crossing(target: float) -> float | None:
        for index, (left, right) in enumerate(zip(fractions, fractions[1:])):
            if (left <= target <= right) or (right <= target <= left):
                if right == left:
                    return temperatures[index]
                return temperatures[index] + (target - left) * (temperatures[index + 1] - temperatures[index]) / (right - left)
        return None
    t10, tm, t90 = crossing(0.1), crossing(0.5), crossing(0.9)
    return {"temperature_unit": "C", "signal_direction": direction, "normalized_fraction": [round(value, 8) for value in fractions], "summary": {"observation_count": len(temperatures), "temperature_start_c": temperatures[0], "temperature_end_c": temperatures[-1], "transition_midpoint_c": round(tm, 8) if tm is not None else None, "transition_10_percent_c": round(t10, 8) if t10 is not None else None, "transition_90_percent_c": round(t90, 8) if t90 is not None else None, "transition_width_c": round(t90 - t10, 8) if t10 is not None and t90 is not None else None, "monotonicity_violation_count": monotonic_violations}, "limitations": ["This is a descriptive endpoint-normalized transition summary, not a thermodynamic unfolding fit, van't Hoff analysis, reversibility assessment, aggregation assessment, or calibrated secondary-structure deconvolution.", "Interpretation requires declared wavelength, blank/baseline processing, concentration, path length, replicate design and appropriate experimental controls."]}


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
    """Design facing PCR primer pairs with Primer3's thermodynamic backend."""
    template = normalize_sequence(template, "dna")
    if set(template) - set("ACGT"):
        raise ValueError("primer design requires an unambiguous DNA template")
    if not 14 <= min_length <= max_length <= 40 or len(template) < 2 * min_length:
        raise ValueError("invalid primer lengths or template is too short")
    if not 1 <= max_pairs <= 100:
        raise ValueError("max_pairs must be 1..100")
    try:
        import primer3
    except ImportError as exc:
        raise RuntimeError("Primer3 is required for primer design; install the module's declared primer3-py dependency") from exc
    tm_window = 5.0
    result = primer3.bindings.design_primers(
        {"SEQUENCE_TEMPLATE": template},
        {
            "PRIMER_TASK": "generic",
            "PRIMER_PICK_LEFT_PRIMER": 1,
            "PRIMER_PICK_RIGHT_PRIMER": 1,
            "PRIMER_NUM_RETURN": max_pairs,
            "PRIMER_MIN_SIZE": min_length,
            "PRIMER_OPT_SIZE": min(max(min_length, 20), max_length),
            "PRIMER_MAX_SIZE": max_length,
            "PRIMER_MIN_TM": max(0.0, target_tm - tm_window),
            "PRIMER_OPT_TM": target_tm,
            "PRIMER_MAX_TM": target_tm + tm_window,
            "PRIMER_PRODUCT_SIZE_RANGE": [[max(2 * min_length, 40), len(template)]],
        },
    )
    pairs = []
    for index in range(int(result.get("PRIMER_PAIR_NUM_RETURNED", 0))):
        forward_sequence = result[f"PRIMER_LEFT_{index}_SEQUENCE"]
        reverse_sequence = result[f"PRIMER_RIGHT_{index}_SEQUENCE"]
        forward_position, forward_length = result[f"PRIMER_LEFT_{index}"]
        reverse_end, reverse_length = result[f"PRIMER_RIGHT_{index}"]
        reverse_position = reverse_end - reverse_length + 1
        forward = _primer(forward_sequence, forward_position + 1, "+")
        reverse = _primer(reverse_sequence, reverse_position + 1, "-")
        forward.update({
            "tm_c": round(float(result[f"PRIMER_LEFT_{index}_TM"]), 3),
            "gc_percent": round(float(result[f"PRIMER_LEFT_{index}_GC_PERCENT"]), 3),
            "penalty": round(float(result[f"PRIMER_LEFT_{index}_PENALTY"]), 6),
            "self_any_th": round(float(result[f"PRIMER_LEFT_{index}_SELF_ANY_TH"]), 6),
            "self_end_th": round(float(result[f"PRIMER_LEFT_{index}_SELF_END_TH"]), 6),
            "hairpin_th": round(float(result[f"PRIMER_LEFT_{index}_HAIRPIN_TH"]), 6),
        })
        reverse.update({
            "tm_c": round(float(result[f"PRIMER_RIGHT_{index}_TM"]), 3),
            "gc_percent": round(float(result[f"PRIMER_RIGHT_{index}_GC_PERCENT"]), 3),
            "penalty": round(float(result[f"PRIMER_RIGHT_{index}_PENALTY"]), 6),
            "self_any_th": round(float(result[f"PRIMER_RIGHT_{index}_SELF_ANY_TH"]), 6),
            "self_end_th": round(float(result[f"PRIMER_RIGHT_{index}_SELF_END_TH"]), 6),
            "hairpin_th": round(float(result[f"PRIMER_RIGHT_{index}_HAIRPIN_TH"]), 6),
        })
        pairs.append({
            "forward": forward,
            "reverse": reverse,
            "amplicon_length": int(result[f"PRIMER_PAIR_{index}_PRODUCT_SIZE"]),
            "tm_delta_c": round(abs(forward["tm_c"] - reverse["tm_c"]), 3),
            "rank_score": round(float(result[f"PRIMER_PAIR_{index}_PENALTY"]), 6),
        })
    return {
        "template": template,
        "template_length": len(template),
        "tm_method": "Primer3 nearest-neighbor thermodynamics",
        "primer3_version": primer3.__version__,
        "pairs": pairs,
        "limitations": [
            "Genomic uniqueness and off-target amplification are not assessed; verify candidates against the intended reference.",
            "Primer3 candidate thermodynamics do not establish target specificity, genomic uniqueness, sample-template integrity, polymerase compatibility, or PCR success.",
        ],
    }


def select_pcr_primer_pair(template: str, pairs: list[dict[str, Any]], selected_candidate_index: int = 0) -> dict[str, Any]:
    """Bind one ranked primer-design candidate to an explicit PCR simulation request."""
    template = normalize_sequence(template, "dna")
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("pairs must contain at least one ranked primer-design candidate")
    if not isinstance(selected_candidate_index, int) or not 0 <= selected_candidate_index < len(pairs):
        raise ValueError("selected_candidate_index is outside the available candidate list")
    pair = pairs[selected_candidate_index]
    if not isinstance(pair, dict) or not isinstance(pair.get("forward"), dict) or not isinstance(pair.get("reverse"), dict):
        raise ValueError("selected candidate lacks forward and reverse primer records")
    forward, reverse = pair["forward"].get("sequence"), pair["reverse"].get("sequence")
    if not isinstance(forward, str) or not isinstance(reverse, str):
        raise ValueError("selected candidate primer sequences are missing")
    forward, reverse = normalize_sequence(forward, "dna"), normalize_sequence(reverse, "dna")
    if len(forward) < 10 or len(reverse) < 10:
        raise ValueError("selected primers are too short for PCR simulation")
    return {"template": template, "forward_primer": forward, "reverse_primer": reverse, "selected_candidate_index": selected_candidate_index}


def plan_sanger_verification_coverage(
    template: str,
    target_start: int,
    target_end: int,
    existing_primers: list[dict[str, str]] | None = None,
    read_length: int = 700,
    primer_length: int = 20,
    coverage_overlap: int = 100,
    max_new_primers: int = 12,
) -> dict[str, Any]:
    """Plan explicit Sanger-read coverage for one non-wrapping linear target interval.

    Existing primers are only considered when they exactly bind the declared
    template. New candidates use simple composition heuristics and retain both
    their binding and expected read-coverage intervals for review.
    """
    template = normalize_sequence(template, "dna")
    if set(template) - _UNAMBIGUOUS_ALPHABETS["dna"]:
        raise ValueError("verification planning requires unambiguous DNA")
    if not isinstance(target_start, int) or not isinstance(target_end, int) or not 0 <= target_start < target_end <= len(template):
        raise ValueError("target_start and target_end must be a nonempty zero-based half-open interval within template")
    if not all(isinstance(value, int) for value in (read_length, primer_length, coverage_overlap, max_new_primers)):
        raise ValueError("read_length, primer_length, coverage_overlap, and max_new_primers must be integers")
    if not 100 <= read_length <= 2000 or not 14 <= primer_length <= 40 or not 0 <= coverage_overlap < read_length:
        raise ValueError("read_length must be 100..2000, primer_length 14..40, and coverage_overlap smaller than read_length")
    if not 1 <= max_new_primers <= 100:
        raise ValueError("max_new_primers must be 1..100")
    if len(template) < primer_length:
        raise ValueError("template is shorter than primer_length")
    if existing_primers is not None and not isinstance(existing_primers, list):
        raise ValueError("existing_primers must be a list when provided")

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    def add_candidate(name: str, sequence: str, start: int, strand: str, source: str) -> None:
        key = (sequence, start, strand)
        if key in seen:
            return
        seen.add(key)
        end = start + len(sequence)
        coverage = {"start": start, "end": min(len(template), start + read_length)} if strand == "+" else {"start": max(0, end - read_length), "end": end}
        primer = _primer(sequence, start + 1, strand)
        candidates.append({
            "name": name,
            "source": source,
            "sequence": sequence,
            "binding_interval": {"start": start, "end": end},
            "expected_read_coverage": coverage,
            "strand": strand,
            "gc_percent": primer["gc_percent"],
            "tm_c": primer["tm_c"],
            "max_homopolymer": primer["max_homopolymer"],
        })

    for index, item in enumerate(existing_primers or []):
        if not isinstance(item, dict) or not isinstance(item.get("sequence"), str):
            raise ValueError("each existing primer must have a text sequence")
        sequence = normalize_sequence(item["sequence"], "dna")
        if set(sequence) - _UNAMBIGUOUS_ALPHABETS["dna"] or len(sequence) < 14:
            raise ValueError("existing primers must be unambiguous DNA of at least 14 nucleotides")
        name = str(item.get("name") or f"existing_{index + 1}")
        reverse = _reverse_complement(sequence)
        for start in range(len(template) - len(sequence) + 1):
            if template.startswith(sequence, start):
                add_candidate(name, sequence, start, "+", "existing")
            if template.startswith(reverse, start):
                add_candidate(name, sequence, start, "-", "existing")

    scan_start = max(0, target_start - read_length + coverage_overlap)
    scan_end = min(len(template) - primer_length, target_end - 1)
    for start in range(scan_start, scan_end + 1):
        sequence = template[start : start + primer_length]
        primer = _primer(sequence, start + 1, "+")
        if 35.0 <= primer["gc_percent"] <= 65.0 and 50.0 <= primer["tm_c"] <= 70.0 and primer["max_homopolymer"] <= 4:
            add_candidate(f"design_f_{start}", sequence, start, "+", "designed")
        reverse_template = template[start : start + primer_length]
        reverse_sequence = _reverse_complement(reverse_template)
        primer = _primer(reverse_sequence, start + 1, "-")
        if 35.0 <= primer["gc_percent"] <= 65.0 and 50.0 <= primer["tm_c"] <= 70.0 and primer["max_homopolymer"] <= 4:
            add_candidate(f"design_r_{start}", reverse_sequence, start, "-", "designed")

    selected: list[dict[str, Any]] = []
    cursor = target_start
    new_count = 0
    while cursor < target_end:
        eligible = [candidate for candidate in candidates if candidate["expected_read_coverage"]["start"] <= cursor < candidate["expected_read_coverage"]["end"] and (candidate["source"] == "existing" or new_count < max_new_primers)]
        if not eligible:
            break
        eligible.sort(key=lambda candidate: (
            candidate["expected_read_coverage"]["end"],
            candidate["source"] == "existing",
            -abs(candidate["tm_c"] - 60.0),
            -candidate["gc_percent"],
        ), reverse=True)
        chosen = eligible[0]
        if chosen["source"] == "designed":
            new_count += 1
        selected.append(chosen)
        next_cursor = chosen["expected_read_coverage"]["end"] - coverage_overlap
        if next_cursor <= cursor:
            next_cursor = chosen["expected_read_coverage"]["end"]
        cursor = next_cursor
    coverage_intervals = sorted(
        ({"start": max(target_start, candidate["expected_read_coverage"]["start"]), "end": min(target_end, candidate["expected_read_coverage"]["end"])} for candidate in selected),
        key=lambda interval: (interval["start"], interval["end"]),
    )
    merged: list[dict[str, int]] = []
    for interval in coverage_intervals:
        if interval["end"] <= interval["start"]:
            continue
        if merged and interval["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], interval["end"])
        else:
            merged.append(dict(interval))
    uncovered: list[dict[str, int]] = []
    position = target_start
    for interval in merged:
        if interval["start"] > position:
            uncovered.append({"start": position, "end": interval["start"]})
        position = max(position, interval["end"])
    if position < target_end:
        uncovered.append({"start": position, "end": target_end})
    return {
        "template_length": len(template),
        "target_interval": {"start": target_start, "end": target_end},
        "coordinate_system": "zero-based half-open on supplied linear template",
        "read_length": read_length,
        "coverage_overlap": coverage_overlap,
        "recommended_primers": selected,
        "merged_target_coverage": merged,
        "uncovered_intervals": uncovered,
        "target_fully_covered": not uncovered,
        "candidate_count": len(candidates),
        "limitations": [
            "This plans expected read reach from exact primer binding on a supplied linear template; it does not support targets crossing a circular origin.",
            "Read length, primer thermodynamics, secondary structure, base-calling quality, template quality, primer uniqueness and experimental sequencing success are not predicted or validated.",
            "Review primer uniqueness against the intended construct or genomic background and inspect chromatograms before treating coverage as sequence confirmation.",
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


def _restriction_cut_positions(sequence: str, enzyme: str, circular: bool) -> list[int]:
    motif = _ENZYMES[enzyme]
    offset = _RESTRICTION_CUT_OFFSETS[enzyme]
    if circular:
        searchable = sequence + sequence[: len(motif) - 1]
        starts = [index for index in range(len(sequence)) if searchable.startswith(motif, index)]
    else:
        starts = [match.start() for match in re.finditer(f"(?={motif})", sequence)]
    return sorted({(start + offset) % len(sequence) if circular else start + offset for start in starts})


def simulate_restriction_digest(sequence: str, enzymes: list[str], circular: bool = False) -> dict[str, Any]:
    """Predict exact-motif restriction fragments on a declared DNA sequence."""
    sequence = normalize_sequence(sequence, "dna")
    if set(sequence) - _UNAMBIGUOUS_ALPHABETS["dna"]:
        raise ValueError("restriction digest requires unambiguous DNA")
    if not isinstance(enzymes, list) or not enzymes or not all(isinstance(enzyme, str) for enzyme in enzymes):
        raise ValueError("enzymes must be a nonempty list of supported enzyme names")
    if not isinstance(circular, bool):
        raise ValueError("circular must be boolean")
    selected = list(dict.fromkeys(enzymes))
    unknown = sorted(set(selected) - set(_ENZYMES))
    if unknown:
        raise ValueError(f"unknown enzymes: {', '.join(unknown)}")
    unsupported_digest_enzymes = sorted(set(selected) - _PALINDROMIC_DIGEST_ENZYMES)
    if unsupported_digest_enzymes:
        raise ValueError(
            "restriction digest supports palindromic Type II cutters only; use golden-gate-plan for Type IIS assembly enzymes: "
            + ", ".join(unsupported_digest_enzymes)
        )

    cuts = []
    for enzyme in selected:
        for cut in _restriction_cut_positions(sequence, enzyme, circular):
            cuts.append({"enzyme": enzyme, "motif": _ENZYMES[enzyme], "cut_position": cut})
    cuts.sort(key=lambda item: (item["cut_position"], item["enzyme"]))
    unique_positions = sorted({item["cut_position"] for item in cuts})
    length = len(sequence)

    def fragment(start: int, end: int, wraps_origin: bool) -> dict[str, Any]:
        fragment_sequence = sequence[start:] + sequence[:end] if wraps_origin else sequence[start:end]
        return {"start": start, "end": end, "wraps_origin": wraps_origin, "length": len(fragment_sequence), "sequence": fragment_sequence}

    if not unique_positions:
        fragments = [fragment(0, length, False)]
        digestion_state = "uncut"
    elif circular:
        fragments = [
            fragment(start, end % length, end >= length)
            for start, end in zip(unique_positions, unique_positions[1:] + [unique_positions[0] + length], strict=True)
        ]
        digestion_state = "linearized" if len(unique_positions) == 1 else "fragmented"
    else:
        boundaries = [0, *unique_positions, length]
        fragments = [fragment(start, end, False) for start, end in zip(boundaries, boundaries[1:]) if end > start]
        digestion_state = "fragmented"
    fragments.sort(key=lambda item: (-item["length"], item["start"], item["end"]))
    return {
        "sequence_length": length,
        "circular": circular,
        "coordinate_system": "zero-based interbase cut positions and zero-based half-open fragment intervals on the supplied sequence",
        "enzymes": selected,
        "cut_sites": cuts,
        "unique_cut_count": len(unique_positions),
        "digestion_state": digestion_state,
        "fragments": fragments,
        "limitations": [
            "This predicts cuts only for exact supported recognition motifs on the supplied sequence; it does not model methylation, star activity, partial digestion, enzyme buffer compatibility, DNA topology, gel migration, or fragment recovery.",
            "A predicted fragment pattern is not evidence of construct identity or successful digestion; retain sequence provenance and verify experimentally.",
        ],
    }


def extract_genbank_coding_sequences(genbank_record: str, identifier: str) -> dict[str, Any]:
    """Extract exact annotated CDS records matching one declared identifier.

    Matching is deliberately exact and limited to standard GenBank CDS
    qualifiers (gene, locus_tag, and protein_id); the function does not
    resolve aliases, infer genes from coordinates, or search remote databases.
    """
    if not isinstance(genbank_record, str) or not genbank_record.strip():
        raise ValueError("genbank_record must be nonempty GenBank text")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("identifier must be nonempty text")
    requested = identifier.strip()
    try:
        records = list(SeqIO.parse(StringIO(genbank_record), "genbank"))
    except Exception as exc:
        raise ValueError("genbank_record could not be parsed") from exc
    if len(records) != 1:
        raise ValueError("genbank_record must contain exactly one parseable record")
    record = records[0]
    candidates: list[dict[str, Any]] = []
    for feature in record.features:
        if feature.type != "CDS":
            continue
        qualifiers = {key: [str(value) for value in values] for key, values in feature.qualifiers.items()}
        aliases = {
            value
            for key in ("gene", "locus_tag", "protein_id")
            for value in qualifiers.get(key, [])
        }
        if requested not in aliases:
            continue
        codon_start = int(qualifiers.get("codon_start", ["1"])[0])
        if codon_start not in {1, 2, 3}:
            raise ValueError("matched CDS has an invalid codon_start qualifier")
        translation_table = int(qualifiers.get("transl_table", ["1"])[0])
        try:
            CodonTable.unambiguous_dna_by_id[translation_table]
        except KeyError as exc:
            raise ValueError("matched CDS has an unsupported transl_table qualifier") from exc
        extracted = str(feature.extract(record.seq)).upper()
        coding_sequence = extracted[codon_start - 1 :]
        intervals = [
            {"start": int(part.start), "end": int(part.end)}
            for part in feature.location.parts
        ]
        translated = None
        translation_status = "not-divisible-by-three"
        if len(coding_sequence) % 3 == 0:
            translated = str(Seq(coding_sequence).translate(table=translation_table, to_stop=True))
            translation_status = "translated"
        supplied_translation = qualifiers.get("translation", [None])[0]
        if supplied_translation is not None:
            supplied_translation = supplied_translation.replace(" ", "").replace("\n", "")
        translation_match = (
            translated == supplied_translation.rstrip("*")
            if translated is not None and supplied_translation is not None
            else None
        )
        candidates.append(
            {
                "record_id": record.id,
                "record_description": record.description,
                "matched_identifier": requested,
                "matched_qualifiers": {
                    key: values
                    for key, values in qualifiers.items()
                    if key in {"gene", "locus_tag", "protein_id"}
                },
                "location_intervals": intervals,
                "strand": "+" if feature.location.strand == 1 else "-" if feature.location.strand == -1 else None,
                "coding_sequence": coding_sequence,
                "coding_sequence_length": len(coding_sequence),
                "codon_start": codon_start,
                "translation_table": translation_table,
                "translated_protein": translated,
                "supplied_translation": supplied_translation,
                "translation_match": translation_match,
                "translation_status": translation_status,
                "partial": "<" in str(feature.location) or ">" in str(feature.location),
            }
        )
    return {
        "record_id": record.id,
        "requested_identifier": requested,
        "match_policy": "exact match against CDS gene, locus_tag, or protein_id qualifiers",
        "coordinate_system": "zero-based half-open intervals on the supplied GenBank record",
        "matched_cds_count": len(candidates),
        "coding_sequences": candidates,
        "limitations": [
            "This extracts only CDS features already annotated in one supplied GenBank record; it does not resolve aliases, infer coding regions, choose among transcript isoforms, validate assembly identity, or search NCBI.",
            "A translation agreement checks the submitted annotation against the locally extracted sequence under the declared translation table; it does not validate gene identity, expression, function, or biological consequence.",
        ],
    }


def restriction_sites(
    sequence: str,
    enzymes: list[str] | None = None,
    include_digest: bool = False,
    circular: bool = False,
) -> dict[str, Any]:
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
    result = {"sequence_length": len(sequence), "sites": sites, "site_count": len(sites), "coordinate_system": "one-based inclusive"}
    if include_digest:
        result["digest"] = simulate_restriction_digest(sequence, selected, circular=circular)
    return result


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
