"""Clean-room omics summaries and statistical analyses."""

from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from typing import Any

from .statistics import benjamini_hochberg, hypergeometric_tail, welch_t_test


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
