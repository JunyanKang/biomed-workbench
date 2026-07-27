#!/usr/bin/env python3
"""Run a bounded MAFFT and IQ-TREE comparative sequence workflow.

This project template intentionally requires already installed MAFFT and IQ-TREE.
It validates and preserves the actual input records, commands, versions, alignment,
tree, and report. It never manufactures a fallback alignment, tree, haplotype, or
evolutionary estimate when an external method is unavailable or fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from Bio import Phylo, SeqIO


DNA = frozenset("ACGTRYSWKMBDHVN-")
RNA = frozenset("ACGURYSWKMBDHVN-")
PROTEIN = frozenset("ABCDEFGHIKLMNPQRSTVWXYZ*-")


class ComparativeSequenceError(ValueError):
    """Raised when a comparative sequence analysis contract is violated."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-fasta", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sequence-type", required=True, choices=("dna", "rna", "protein"))
    parser.add_argument("--substitution-model", required=True)
    parser.add_argument("--support-method", required=True, choices=("ultrafast-bootstrap", "standard-bootstrap", "none-exploratory"))
    parser.add_argument("--support-replicates", required=True, type=int)
    parser.add_argument("--outgroup-id", action="append", default=[])
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--mafft", default="mafft")
    parser.add_argument("--iqtree", default="iqtree3")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_version(command: str) -> str:
    executable = shutil.which(command)
    if executable is None:
        raise ComparativeSequenceError(f"required executable is unavailable: {command}")
    completed = subprocess.run([executable, "--version"], text=True, capture_output=True, check=False, timeout=30)
    output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0 or not re.search(r"\d+\.\d+", output):
        raise ComparativeSequenceError(f"could not establish version for {command}")
    return output


def allowed_alphabet(sequence_type: str) -> frozenset[str]:
    return {"dna": DNA, "rna": RNA, "protein": PROTEIN}[sequence_type]


def load_records(path: Path, sequence_type: str) -> list:
    if path.is_symlink() or not path.is_file():
        raise ComparativeSequenceError("input FASTA must be a stable regular file")
    records = list(SeqIO.parse(path, "fasta"))
    if len(records) < 4:
        raise ComparativeSequenceError("at least four declared homologous records are required")
    seen: set[str] = set()
    alphabet = allowed_alphabet(sequence_type)
    for record in records:
        identifier = record.id.strip()
        sequence = str(record.seq).upper().replace(" ", "")
        if not identifier or identifier in seen:
            raise ComparativeSequenceError("FASTA record identifiers must be nonempty and unique")
        if not sequence or any(letter not in alphabet for letter in sequence):
            raise ComparativeSequenceError(f"record {identifier} violates the declared {sequence_type} alphabet")
        seen.add(identifier)
    return records


def metadata_ids(path: Path) -> set[str]:
    if path.is_symlink() or not path.is_file():
        raise ComparativeSequenceError("metadata must be a stable regular tab-separated file")
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ComparativeSequenceError("metadata is empty")
    header = lines[0].split("\t")
    if "record_id" not in header:
        raise ComparativeSequenceError("metadata must contain a record_id column")
    position = header.index("record_id")
    values = set()
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) != len(header) or not fields[position].strip() or fields[position] in values:
            raise ComparativeSequenceError("metadata rows must be complete and have unique record_id values")
        values.add(fields[position])
    return values


def run_checked(command: list[str], *, stdout_path: Path | None = None) -> dict[str, object]:
    try:
        if stdout_path is None:
            completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=7200)
        else:
            with stdout_path.open("x", encoding="utf-8") as handle:
                completed = subprocess.run(command, text=True, stdout=handle, stderr=subprocess.PIPE, check=False, timeout=7200)
    except subprocess.TimeoutExpired as exc:
        raise ComparativeSequenceError(f"scientific command timed out: {Path(command[0]).name}") from exc
    if completed.returncode != 0:
        raise ComparativeSequenceError(f"scientific command failed: {Path(command[0]).name}: {completed.stderr[-1000:]}")
    return {"argv": command, "stderr": completed.stderr[-4000:], "returncode": completed.returncode}


def run_mafft_safely(command: argparse.Namespace, input_fasta: Path, alignment: Path) -> dict[str, object]:
    """Run MAFFT with sandbox-friendly defaults, then provide fallback compatibility.

    MaFFT's shell launcher may emit progress to /dev/stderr, which is blocked in some
    constrained Codex environments. Prefer quiet mode first, then fallback to legacy
    behavior only when quiet is unavailable.
    """

    quiet_command = [command.mafft, "--quiet", "--auto", "--thread", str(command.threads), str(input_fasta)]
    try:
        return run_checked(quiet_command, stdout_path=alignment)
    except ComparativeSequenceError as exc:
        if "error" in str(exc) and "unknown option" in str(exc).lower():
            return run_checked([command.mafft, "--auto", "--thread", str(command.threads), str(input_fasta)], stdout_path=alignment)
        raise


def validate_alignment(path: Path, input_ids: set[str]) -> dict[str, object]:
    records = list(SeqIO.parse(path, "fasta"))
    identifiers = [record.id for record in records]
    if set(identifiers) != input_ids or len(identifiers) != len(input_ids):
        raise ComparativeSequenceError("aligned records do not exactly match the input record set")
    lengths = {len(record.seq) for record in records}
    if len(lengths) != 1 or next(iter(lengths), 0) == 0:
        raise ComparativeSequenceError("alignment does not have one nonempty common aligned length")
    columns = next(iter(lengths))
    gap_count = sum(str(record.seq).count("-") for record in records)
    return {"record_count": len(records), "aligned_columns": columns, "gap_fraction": gap_count / (len(records) * columns)}


def validate_tree(path: Path, input_ids: set[str], outgroup_ids: set[str]) -> dict[str, object]:
    try:
        tree = Phylo.read(path, "newick")
    except Exception as exc:
        raise ComparativeSequenceError("treefile is not reloadable Newick") from exc
    tips = {tip.name for tip in tree.get_terminals()}
    if tips != input_ids or len(tips) != len(input_ids):
        raise ComparativeSequenceError("tree tips do not exactly match aligned record identifiers")
    missing_outgroups = sorted(outgroup_ids - tips)
    if missing_outgroups:
        raise ComparativeSequenceError(f"declared outgroups are absent from tree: {', '.join(missing_outgroups)}")
    return {"tip_count": len(tips), "outgroups_present": sorted(outgroup_ids), "rooted_in_template": False}


def iqtree_command(args: argparse.Namespace, alignment: Path, prefix: Path) -> list[str]:
    command = [args.iqtree, "-s", str(alignment), "-m", args.substitution_model, "-pre", str(prefix), "-seed", str(args.seed), "-nt", str(args.threads), "-redo"]
    if args.support_method == "ultrafast-bootstrap":
        command.extend(["-B", str(args.support_replicates)])
    elif args.support_method == "standard-bootstrap":
        command.extend(["-b", str(args.support_replicates)])
    elif args.support_replicates != 0:
        raise ComparativeSequenceError("none-exploratory support requires support-replicates=0")
    if args.support_method == "ultrafast-bootstrap" and args.support_replicates < 1000:
        raise ComparativeSequenceError("IQ-TREE ultrafast bootstrap requires at least 1000 replicates")
    if args.support_method == "standard-bootstrap" and args.support_replicates < 100:
        raise ComparativeSequenceError("standard bootstrap requires at least 100 replicates")
    return command


def main() -> int:
    args = parse_args()
    if args.threads < 1 or args.threads > 128:
        raise ComparativeSequenceError("threads must be between 1 and 128")
    output = Path(args.output_dir)
    if output.exists() or output.is_symlink():
        raise ComparativeSequenceError("output directory must be a new non-symlink path")
    output.mkdir(parents=True)
    input_fasta = Path(args.input_fasta)
    metadata = Path(args.metadata)
    records = load_records(input_fasta, args.sequence_type)
    input_ids = {record.id for record in records}
    metadata_record_ids = metadata_ids(metadata)
    if metadata_record_ids != input_ids:
        raise ComparativeSequenceError("metadata record_id values must exactly match FASTA record identifiers")
    outgroups = set(args.outgroup_id)
    if not outgroups:
        raise ComparativeSequenceError("at least one independently declared outgroup is required")
    if not outgroups <= input_ids:
        raise ComparativeSequenceError("declared outgroup identifiers must exist in FASTA")

    versions = {"mafft": command_version(args.mafft), "iqtree": command_version(args.iqtree)}
    alignment = output / "alignment.fasta"
    mafft = run_mafft_safely(args, input_fasta, alignment)
    alignment_qc = validate_alignment(alignment, input_ids)
    tree_prefix = output / "iqtree"
    iqtree = run_checked(iqtree_command(args, alignment, tree_prefix))
    tree = tree_prefix.with_suffix(".treefile")
    if not tree.is_file():
        raise ComparativeSequenceError("IQ-TREE completed without the expected treefile")
    tree_qc = validate_tree(tree, input_ids, outgroups)
    report = {
        "module_id": "comparative-sequence-phylogeny",
        "module_version": "0.1.0",
        "passed": True,
        "input": {"fasta_sha256": sha256(input_fasta), "metadata_sha256": sha256(metadata), "record_ids": sorted(input_ids), "sequence_type": args.sequence_type},
        "parameters": {"model": args.substitution_model, "support_method": args.support_method, "support_replicates": args.support_replicates, "outgroup_ids": sorted(outgroups), "seed": args.seed, "threads": args.threads},
        "tool_versions": versions,
        "commands": {"mafft": mafft, "iqtree": iqtree},
        "alignment": {**alignment_qc, "sha256": sha256(alignment), "path": alignment.name},
        "tree": {**tree_qc, "sha256": sha256(tree), "path": tree.name},
        "quality_gate_ids": ["comparative-sequence-identity-and-homology", "comparative-alignment-completeness", "comparative-tree-model-and-support", "comparative-outgroup-and-claim-boundary", "comparative-output-provenance"],
        "limitations": ["The tree is method-specific evidence, not proof of orthology, selection, recombination, divergence time, species history, or functional conservation.", "The template validates outgroup presence but does not choose or biologically validate an outgroup."],
    }
    (output / "comparative-phylogeny-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ComparativeSequenceError as exc:
        print(f"ComparativeSequenceError: {exc}", file=sys.stderr)
        raise SystemExit(2)
