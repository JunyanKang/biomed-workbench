"""Clean-room omics summaries and statistical analyses."""

from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from typing import Any

from .statistics import benjamini_hochberg, hypergeometric_tail, student_t_two_sided_p, welch_t_test


def _matrix(genes: list[str], samples: list[str], matrix: list[list[float]], *, nonnegative: bool = True) -> list[list[float]]:
    if not genes or not samples or len(matrix) != len(genes) or len(set(genes)) != len(genes) or len(set(samples)) != len(samples):
        raise ValueError("genes, samples, and matrix dimensions must be nonempty and uniquely labeled")
    normalized = []
    for row in matrix:
        values = [float(value) for value in row]
        if len(values) != len(samples) or any(not math.isfinite(value) or (nonnegative and value < 0) for value in values):
            raise ValueError("matrix must be rectangular with finite values")
        normalized.append(values)
    return normalized


def expression_qc(genes: list[str], samples: list[str], matrix: list[list[float]]) -> dict[str, Any]:
    values = _matrix(genes, samples, matrix)
    library_sizes = {sample: math.fsum(row[index] for row in values) for index, sample in enumerate(samples)}
    detected = {sample: sum(row[index] > 0 for row in values) for index, sample in enumerate(samples)}
    total_values = len(genes) * len(samples)
    zero_count = sum(value == 0 for row in values for value in row)
    return {
        "gene_count": len(genes),
        "sample_count": len(samples),
        "library_sizes": library_sizes,
        "detected_genes": detected,
        "zero_fraction": zero_count / total_values,
        "library_size_range": [min(library_sizes.values()), max(library_sizes.values())],
        "warnings": [sample for sample, total in library_sizes.items() if total == 0],
    }


def differential_expression(
    genes: list[str],
    group_a: list[list[float]],
    group_b: list[list[float]],
    pseudocount: float = 0.5,
) -> dict[str, Any]:
    if len(genes) != len(group_a) or len(genes) != len(group_b) or len(set(genes)) != len(genes):
        raise ValueError("genes and group matrices must align")
    if not math.isfinite(float(pseudocount)) or pseudocount <= 0:
        raise ValueError("pseudocount must be positive")
    rows = []
    p_values = []
    for gene, a_values, b_values in zip(genes, group_a, group_b):
        test = welch_t_test(a_values, b_values)
        mean_a = test["mean_a"]
        mean_b = test["mean_b"]
        if mean_a < 0 or mean_b < 0:
            raise ValueError("expression values must be non-negative")
        p_value = test["p_value_two_sided"]
        row = {
            "gene": gene,
            "mean_a": mean_a,
            "mean_b": mean_b,
            "log2_fold_change": math.log2((mean_a + pseudocount) / (mean_b + pseudocount)),
            "t_statistic": test["t_statistic"],
            "degrees_of_freedom": test["degrees_of_freedom"],
            "p_value": p_value,
        }
        rows.append(row)
        p_values.append(p_value)
    for row, adjusted in zip(rows, benjamini_hochberg(p_values)):
        row["adjusted_p_value"] = adjusted
    rows.sort(key=lambda row: (row["adjusted_p_value"], -abs(row["log2_fold_change"]), row["gene"]))
    return {
        "results": rows,
        "method": "Welch t-test per feature with Benjamini-Hochberg correction",
        "limitations": ["This compact method does not model count dispersion, library normalization, pairing, batches, or complex designs."],
    }


def enrichment_analysis(
    query_genes: list[str],
    gene_sets: dict[str, list[str]],
    background_genes: list[str],
) -> dict[str, Any]:
    background = set(background_genes)
    query = set(query_genes)
    if not background or not query or not query <= background:
        raise ValueError("query and background must be nonempty and query must be contained in background")
    rows = []
    p_values = []
    for term, members in sorted(gene_sets.items()):
        member_set = set(members) & background
        overlap = sorted(query & member_set)
        p_value = hypergeometric_tail(len(background), len(member_set), len(query), len(overlap))
        expected_fraction = len(member_set) / len(background) if background else 0
        observed_fraction = len(overlap) / len(query)
        row = {
            "term": term,
            "set_size": len(member_set),
            "overlap_count": len(overlap),
            "overlap_genes": overlap,
            "fold_enrichment": observed_fraction / expected_fraction if expected_fraction else None,
            "p_value": p_value,
        }
        rows.append(row)
        p_values.append(p_value)
    for row, adjusted in zip(rows, benjamini_hochberg(p_values)):
        row["adjusted_p_value"] = adjusted
    rows.sort(key=lambda row: (row["adjusted_p_value"], -row["overlap_count"], row["term"]))
    return {"results": rows, "query_size": len(query), "background_size": len(background), "method": "one-sided hypergeometric overrepresentation with BH correction"}


def single_cell_qc(
    genes: list[str],
    cells: list[str],
    matrix: list[list[float]],
    mitochondrial_prefixes: list[str] | None = None,
    min_counts: float = 500,
    min_genes: int = 200,
    max_mito_percent: float = 20,
) -> dict[str, Any]:
    values = _matrix(genes, cells, matrix)
    prefixes = tuple(mitochondrial_prefixes or ["MT-", "mt-"])
    mitochondrial = [any(gene.startswith(prefix) for prefix in prefixes) for gene in genes]
    rows = []
    for index, cell in enumerate(cells):
        counts = math.fsum(row[index] for row in values)
        detected = sum(row[index] > 0 for row in values)
        mito_counts = math.fsum(row[index] for row, is_mito in zip(values, mitochondrial) if is_mito)
        mito_percent = 100.0 * mito_counts / counts if counts else 0.0
        flags = []
        if counts < min_counts:
            flags.append("low_counts")
        if detected < min_genes:
            flags.append("low_detected_genes")
        if mito_percent > max_mito_percent:
            flags.append("high_mitochondrial_fraction")
        rows.append({"cell": cell, "total_counts": counts, "detected_genes": detected, "mitochondrial_counts": mito_counts, "mitochondrial_percent": mito_percent, "flags": flags})
    return {
        "cells": rows,
        "thresholds": {"min_counts": min_counts, "min_genes": min_genes, "max_mito_percent": max_mito_percent},
        "flagged_cell_count": sum(bool(row["flags"]) for row in rows),
        "limitations": ["Threshold flags are descriptive and must be adapted to assay chemistry, tissue, depth, and expected biology."],
    }


def variant_summary(variants: list[dict[str, Any]]) -> dict[str, Any]:
    type_counts: Counter[str] = Counter()
    filter_counts: Counter[str] = Counter()
    chromosome_counts: Counter[str] = Counter()
    transitions = 0
    transversions = 0
    transition_pairs = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}
    for variant in variants:
        if not isinstance(variant, dict):
            raise ValueError("variants must be objects")
        chrom = str(variant.get("chrom", "")).strip()
        ref = str(variant.get("ref", "")).upper()
        alt = str(variant.get("alt", "")).upper()
        filter_value = str(variant.get("filter", "PASS") or "PASS")
        if not chrom or not ref or not alt or any(base not in "ACGT" for base in ref + alt):
            raise ValueError("variant chrom, ref, and alt must be present and use unambiguous DNA")
        chromosome_counts[chrom] += 1
        filter_counts[filter_value] += 1
        if len(ref) == len(alt) == 1:
            type_counts["snv"] += 1
            if (ref, alt) in transition_pairs:
                transitions += 1
            else:
                transversions += 1
        elif len(ref) != len(alt):
            type_counts["indel"] += 1
        else:
            type_counts["mnv"] += 1
    return {
        "variant_count": len(variants),
        "type_counts": dict(sorted(type_counts.items())),
        "filter_counts": dict(sorted(filter_counts.items())),
        "chromosome_counts": dict(sorted(chromosome_counts.items())),
        "transition_count": transitions,
        "transversion_count": transversions,
        "ti_tv_ratio": transitions / transversions if transversions else None,
    }


def network_summary(edges: list[list[str]], directed: bool = False) -> dict[str, Any]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    normalized_edges = set()
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise ValueError("each edge must contain exactly two node labels")
        left, right = map(str, edge)
        if not left or not right or left == right:
            raise ValueError("network edges require two distinct nonempty nodes")
        key = (left, right) if directed else tuple(sorted((left, right)))
        normalized_edges.add(key)
        adjacency[left].add(right)
        if not directed:
            adjacency[right].add(left)
        else:
            adjacency.setdefault(right, set())
    visited = set()
    components = []
    undirected_neighbors = {node: set(neighbors) for node, neighbors in adjacency.items()}
    if directed:
        for left, right in normalized_edges:
            undirected_neighbors[left].add(right)
            undirected_neighbors[right].add(left)
    for node in sorted(adjacency):
        if node in visited:
            continue
        queue = deque([node])
        visited.add(node)
        component = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(undirected_neighbors[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    degree = {node: len(neighbors) for node, neighbors in sorted(adjacency.items())}
    hubs = [{"node": node, "degree": value} for node, value in sorted(degree.items(), key=lambda item: (-item[1], item[0]))]
    return {"directed": directed, "node_count": len(adjacency), "edge_count": len(normalized_edges), "degree": degree, "hubs": hubs, "component_count": len(components), "components": components}


def multi_sample_variant_concordance(
    samples: list[str],
    variants: list[dict[str, Any]],
    reference_build: str,
    reference_sequence_digest: str,
    normalization: str,
) -> dict[str, Any]:
    """Compare explicit per-sample variant states without confusing missingness with reference."""
    sample_ids = [str(value).strip() for value in samples]
    if len(sample_ids) < 2 or any(not value for value in sample_ids) or len(set(sample_ids)) != len(sample_ids):
        raise ValueError("samples must contain at least two unique nonempty identifiers")
    build = str(reference_build).strip()
    digest = str(reference_sequence_digest).strip().lower()
    if not build or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("reference build and a SHA-256 reference sequence digest are required")
    if normalization != "split-left-normalized-biallelic":
        raise ValueError("normalization must be split-left-normalized-biallelic")
    if not variants:
        raise ValueError("variants must be nonempty")

    loci: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()
    allowed_states = {"alternate", "reference", "not_callable"}
    alternate_by_sample = {sample: set() for sample in sample_ids}
    callable_by_sample = {sample: set() for sample in sample_ids}
    phase_blocks: dict[tuple[str, str], list[tuple[str, int, str, str, int]]] = defaultdict(list)
    for raw in variants:
        if not isinstance(raw, dict):
            raise ValueError("each variant must be an object")
        chrom = str(raw.get("chrom", "")).strip().removeprefix("chr")
        position = raw.get("position")
        ref = str(raw.get("ref", "")).upper()
        alt = str(raw.get("alt", "")).upper()
        states = raw.get("states")
        if not chrom or not isinstance(position, int) or isinstance(position, bool) or position <= 0:
            raise ValueError("variant chromosome and one-based positive integer position are required")
        if not ref or not alt or ref == alt or any(base not in "ACGT" for base in ref + alt):
            raise ValueError("variants require distinct nonempty DNA REF and ALT alleles")
        locus = (chrom, position, ref, alt)
        if locus in seen:
            raise ValueError("duplicate normalized variant locus")
        seen.add(locus)
        if not isinstance(states, dict) or set(states) != set(sample_ids):
            raise ValueError("every variant must declare exactly one state for every sample")
        normalized_states = {sample: str(states[sample]) for sample in sample_ids}
        if any(state not in allowed_states for state in normalized_states.values()):
            raise ValueError("variant states must be alternate, reference, or not_callable")
        locus_id = f"{chrom}:{position}:{ref}:{alt}"
        for sample, state in normalized_states.items():
            if state != "not_callable":
                callable_by_sample[sample].add(locus_id)
            if state == "alternate":
                alternate_by_sample[sample].add(locus_id)

        phases = raw.get("phases", {})
        if phases is None:
            phases = {}
        if not isinstance(phases, dict) or not set(phases) <= set(sample_ids):
            raise ValueError("phases must be keyed only by declared samples")
        normalized_phases: dict[str, dict[str, Any]] = {}
        for sample, phase in phases.items():
            if normalized_states[sample] == "not_callable" or not isinstance(phase, dict):
                raise ValueError("phase data require a callable sample and structured phase record")
            phase_set = str(phase.get("phase_set", "")).strip()
            haplotypes = phase.get("haplotypes")
            if not phase_set or not isinstance(haplotypes, list) or not haplotypes or len(set(haplotypes)) != len(haplotypes) or not set(haplotypes) <= {1, 2}:
                raise ValueError("phase records require a phase_set and unique haplotypes drawn from 1 and 2")
            if normalized_states[sample] != "alternate":
                raise ValueError("only alternate calls may carry ALT haplotype phase")
            normalized_phases[sample] = {"phase_set": phase_set, "haplotypes": sorted(haplotypes)}
            for haplotype in sorted(haplotypes):
                phase_blocks[(sample, phase_set)].append((*locus, haplotype))
        loci.append({"locus_id": locus_id, "chrom": chrom, "position": position, "ref": ref, "alt": alt, "states": normalized_states, "phases": normalized_phases})

    pairwise = []
    for left_index, left in enumerate(sample_ids):
        for right in sample_ids[left_index + 1:]:
            jointly_callable = callable_by_sample[left] & callable_by_sample[right]
            left_alt = alternate_by_sample[left] & jointly_callable
            right_alt = alternate_by_sample[right] & jointly_callable
            shared = left_alt & right_alt
            union = left_alt | right_alt
            concordant_reference = jointly_callable - union
            pairwise.append({
                "sample_a": left,
                "sample_b": right,
                "jointly_callable_count": len(jointly_callable),
                "shared_alternate_count": len(shared),
                "sample_a_private_count": len(left_alt - right_alt),
                "sample_b_private_count": len(right_alt - left_alt),
                "concordant_reference_count": len(concordant_reference),
                "alternate_jaccard": len(shared) / len(union) if union else None,
                "genotype_state_concordance": (len(shared) + len(concordant_reference)) / len(jointly_callable) if jointly_callable else None,
                "not_jointly_callable_count": len(loci) - len(jointly_callable),
            })

    haplotype_signatures = []
    for (sample, phase_set), calls in sorted(phase_blocks.items()):
        ordered = sorted(calls, key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
        haplotype_signatures.append({
            "sample": sample,
            "phase_set": phase_set,
            "haplotype_1_alt_loci": [f"{c}:{p}:{r}:{a}" for c, p, r, a, h in ordered if h == 1],
            "haplotype_2_alt_loci": [f"{c}:{p}:{r}:{a}" for c, p, r, a, h in ordered if h == 2],
        })
    return {
        "reference_build": build,
        "reference_sequence_digest": digest,
        "normalization": normalization,
        "sample_count": len(sample_ids),
        "variant_count": len(loci),
        "sample_summaries": [{
            "sample": sample,
            "alternate_count": len(alternate_by_sample[sample]),
            "reference_count": len(callable_by_sample[sample] - alternate_by_sample[sample]),
            "not_callable_count": len(loci) - len(callable_by_sample[sample]),
        } for sample in sample_ids],
        "pairwise": pairwise,
        "haplotype_signatures": haplotype_signatures,
        "loci": loci,
        "quality_gates": [
            "All samples share one declared reference build and exact reference sequence digest.",
            "Every sample-locus state is explicit; not_callable is never treated as reference.",
            "Only split, left-normalized, biallelic variants are accepted.",
            "Haplotype signatures require explicit phase sets and do not estimate ancestry or divergence time.",
        ],
        "limitations": ["Set concordance does not establish variant-call accuracy, population structure, phylogeny, selection, pathogenicity, or causal effect."],
    }


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        average = (cursor + 1 + end) / 2.0
        for index in order[cursor:end]:
            ranks[index] = average
        cursor = end
    return ranks


def _correlation(left: list[float], right: list[float]) -> tuple[float, float]:
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    covariance = math.fsum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_ss = math.fsum((value - left_mean) ** 2 for value in left)
    right_ss = math.fsum((value - right_mean) ** 2 for value in right)
    if left_ss == 0 or right_ss == 0:
        raise ValueError("correlation is undefined for a constant vector")
    correlation = max(-1.0, min(1.0, covariance / math.sqrt(left_ss * right_ss)))
    if abs(correlation) == 1:
        return correlation, 0.0
    statistic = correlation * math.sqrt((len(left) - 2) / (1 - correlation**2))
    return correlation, student_t_two_sided_p(statistic, len(left) - 2)


def ddr_coexpression_hypothesis_network(
    sample_ids: list[str],
    expression: dict[str, list[float | None]],
    ddr_genes: list[str],
    mutated_samples: dict[str, list[str]],
    method: str = "spearman",
    minimum_paired_samples: int = 8,
    minimum_absolute_correlation: float = 0.5,
    false_discovery_rate: float = 0.05,
) -> dict[str, Any]:
    """Build an FDR-controlled DDR coexpression hypothesis network."""
    samples = [str(value).strip() for value in sample_ids]
    if len(samples) < 3 or any(not value for value in samples) or len(set(samples)) != len(samples):
        raise ValueError("sample_ids must contain at least three unique identifiers")
    if method not in {"pearson", "spearman"}:
        raise ValueError("method must be pearson or spearman")
    if not isinstance(minimum_paired_samples, int) or minimum_paired_samples < 3:
        raise ValueError("minimum_paired_samples must be an integer of at least three")
    if not 0 <= float(minimum_absolute_correlation) <= 1 or not 0 < float(false_discovery_rate) <= 1:
        raise ValueError("correlation and false-discovery thresholds are out of range")
    genes = sorted(str(gene).strip().upper() for gene in expression)
    if len(genes) < 2 or any(not gene for gene in genes) or len(set(genes)) != len(genes):
        raise ValueError("expression requires at least two unique gene symbols")
    values_by_gene: dict[str, list[float | None]] = {}
    for original_gene, raw_values in expression.items():
        gene = str(original_gene).strip().upper()
        if not isinstance(raw_values, list) or len(raw_values) != len(samples):
            raise ValueError("each expression vector must align exactly to sample_ids")
        values: list[float | None] = []
        for value in raw_values:
            if value is None:
                values.append(None)
            else:
                number = float(value)
                if not math.isfinite(number):
                    raise ValueError("expression values must be finite numbers or null")
                values.append(number)
        values_by_gene[gene] = values
    declared_ddr = sorted({str(gene).strip().upper() for gene in ddr_genes if str(gene).strip()})
    if not declared_ddr or not set(declared_ddr) <= set(genes):
        raise ValueError("ddr_genes must be a nonempty subset of expression genes")
    sample_set = set(samples)
    normalized_mutations = {}
    for gene, raw_samples in mutated_samples.items():
        symbol = str(gene).strip().upper()
        listed = [str(sample).strip() for sample in raw_samples]
        if symbol not in genes or len(set(listed)) != len(listed) or not set(listed) <= sample_set:
            raise ValueError("mutated_samples must use expression genes and declared samples without duplicates")
        normalized_mutations[symbol] = sorted(listed)

    tested = []
    for index, left_gene in enumerate(genes):
        for right_gene in genes[index + 1:]:
            paired = [(left, right) for left, right in zip(values_by_gene[left_gene], values_by_gene[right_gene]) if left is not None and right is not None]
            if len(paired) < minimum_paired_samples:
                continue
            left_values = [pair[0] for pair in paired]
            right_values = [pair[1] for pair in paired]
            if method == "spearman":
                left_values = _average_ranks(left_values)
                right_values = _average_ranks(right_values)
            try:
                correlation, p_value = _correlation(left_values, right_values)
            except ValueError:
                continue
            tested.append({"gene_a": left_gene, "gene_b": right_gene, "paired_sample_count": len(paired), "correlation": correlation, "p_value": p_value})
    if not tested:
        raise ValueError("no gene pair had sufficient nonconstant paired observations")
    adjusted = benjamini_hochberg([row["p_value"] for row in tested])
    for row, q_value in zip(tested, adjusted):
        row["adjusted_p_value"] = q_value
    edges = [row for row in tested if abs(row["correlation"]) >= minimum_absolute_correlation and row["adjusted_p_value"] <= false_discovery_rate]
    edges.sort(key=lambda row: (row["adjusted_p_value"], -abs(row["correlation"]), row["gene_a"], row["gene_b"]))
    degree = Counter()
    for row in edges:
        degree[row["gene_a"]] += 1
        degree[row["gene_b"]] += 1
    hypotheses = []
    for row in edges:
        mutated = [gene for gene in (row["gene_a"], row["gene_b"]) if normalized_mutations.get(gene)]
        if mutated and ({row["gene_a"], row["gene_b"]} & set(declared_ddr)):
            hypotheses.append({
                "gene_a": row["gene_a"],
                "gene_b": row["gene_b"],
                "correlation": row["correlation"],
                "adjusted_p_value": row["adjusted_p_value"],
                "mutation_context_genes": mutated,
                "interpretation": "functional_dependency_hypothesis_requires_independent_perturbation_evidence",
            })
    return {
        "method": f"{method} correlation with pairwise-complete observations and Benjamini-Hochberg correction",
        "sample_count": len(samples),
        "gene_count": len(genes),
        "ddr_genes": declared_ddr,
        "tested_pair_count": len(tested),
        "edge_count": len(edges),
        "thresholds": {"minimum_paired_samples": minimum_paired_samples, "minimum_absolute_correlation": minimum_absolute_correlation, "false_discovery_rate": false_discovery_rate},
        "edges": edges,
        "node_degree": dict(sorted(degree.items())),
        "mutation_frequencies": {gene: len(sample_list) / len(samples) for gene, sample_list in sorted(normalized_mutations.items())},
        "functional_dependency_hypotheses": hypotheses,
        "quality_gates": [
            "Gene pairs are tested only with the declared minimum number of paired finite observations.",
            "Network edges satisfy both an absolute-correlation threshold and BH-adjusted false-discovery threshold.",
            "Mutation annotations add context but do not convert coexpression into genetic interaction evidence.",
        ],
        "limitations": ["Coexpression is not synthetic lethality, causal regulation, physical interaction, or clinical actionability; hypotheses require independent perturbation and replication evidence."],
    }
