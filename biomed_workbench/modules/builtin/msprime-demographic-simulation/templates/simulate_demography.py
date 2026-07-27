#!/usr/bin/env python3
"""Simulate a declared single-population history with msprime.

This is a reproducible forward design or method-validation simulation, not an
inference engine for real demographic history. Inputs are explicit and outputs
are new files bound to parameter and source provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import msprime


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("constant", "bottleneck", "expansion"), required=True)
    parser.add_argument("--samples", type=int, required=True)
    parser.add_argument("--sequence-length", type=float, required=True)
    parser.add_argument("--recombination-rate", type=float, required=True)
    parser.add_argument("--mutation-rate", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--parameters-json", type=Path, required=True)
    parser.add_argument("--tree-sequence", type=Path, required=True)
    parser.add_argument("--vcf", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def build_demography(model: str, parameters: dict[str, object]) -> msprime.Demography:
    required = {"constant": {"population_size"}, "bottleneck": {"population_size", "bottleneck_size", "start_time", "end_time"}, "expansion": {"current_size", "ancestral_size", "change_time"}}[model]
    if set(parameters) != required:
        raise ValueError(f"{model} parameters must be exactly: {', '.join(sorted(required))}")
    if any(not isinstance(value, (int, float)) or value <= 0 for value in parameters.values()):
        raise ValueError("all demographic parameters must be positive numbers")
    demography = msprime.Demography()
    if model == "constant":
        demography.add_population(name="pop", initial_size=parameters["population_size"])
    elif model == "bottleneck":
        if parameters["end_time"] >= parameters["start_time"]:
            raise ValueError("bottleneck end_time must be more recent than start_time")
        demography.add_population(name="pop", initial_size=parameters["population_size"])
        demography.add_population_parameters_change(time=parameters["end_time"], initial_size=parameters["bottleneck_size"], population="pop")
        demography.add_population_parameters_change(time=parameters["start_time"], initial_size=parameters["population_size"], population="pop")
    else:
        demography.add_population(name="pop", initial_size=parameters["current_size"])
        demography.add_population_parameters_change(time=parameters["change_time"], initial_size=parameters["ancestral_size"], population="pop")
    return demography


def main() -> int:
    args = parse_args()
    if not 2 <= args.samples <= 10000 or args.sequence_length <= 0 or args.recombination_rate < 0 or args.mutation_rate <= 0 or args.seed < 1:
        raise ValueError("invalid sample, sequence, rate, or seed parameter")
    if any(path.exists() or path.is_symlink() for path in (args.tree_sequence, args.vcf, args.report)):
        raise ValueError("all output paths must be new non-symlink paths")
    parameters = json.loads(args.parameters_json.read_text(encoding="utf-8"))
    if not isinstance(parameters, dict):
        raise ValueError("parameters-json must contain one object")
    demography = build_demography(args.model, parameters)
    ancestry = msprime.sim_ancestry(samples=args.samples, demography=demography, sequence_length=args.sequence_length, recombination_rate=args.recombination_rate, random_seed=args.seed)
    simulated = msprime.sim_mutations(ancestry, rate=args.mutation_rate, random_seed=args.seed + 1)
    for path in (args.tree_sequence, args.vcf, args.report): path.parent.mkdir(parents=True, exist_ok=True)
    simulated.dump(args.tree_sequence)
    with args.vcf.open("w", encoding="utf-8") as handle: simulated.write_vcf(handle)
    report = {"module_id": "msprime-demographic-simulation", "module_version": "0.1.0", "passed": True, "msprime_version": msprime.__version__, "parameters": {"model": args.model, **parameters, "samples": args.samples, "sequence_length": args.sequence_length, "recombination_rate": args.recombination_rate, "mutation_rate": args.mutation_rate, "seed": args.seed}, "inputs": {"parameters_sha256": sha256(args.parameters_json)}, "outputs": {"tree_sequence_sha256": sha256(args.tree_sequence), "vcf_sha256": sha256(args.vcf), "tree_count": simulated.num_trees, "site_count": simulated.num_sites, "diversity": simulated.diversity()}, "limitations": ["Simulation demonstrates behavior under declared assumptions and does not infer real population history, validate a demographic model, or replace empirical sequencing data."]}
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
