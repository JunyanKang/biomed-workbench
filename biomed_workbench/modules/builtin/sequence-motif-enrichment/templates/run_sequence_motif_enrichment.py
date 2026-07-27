#!/usr/bin/env python3
"""Run reproducible known-PWM motif enrichment on declared sequence sets.

Inputs must be independently prepared foreground and background FASTA files
from the same declared genome build and sequence extraction policy, plus a
versioned JSON PWM collection. The template performs bidirectional scanning,
per-sequence hit calls, one-sided Fisher enrichment, and BH correction. It
does not discover motifs, infer factor occupancy, or create a background set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "biomed_workbench").is_dir():
            return candidate
    raise RuntimeError("could not locate the Biomed Workbench project root")


ROOT = project_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.motif_enrichment import MotifEnrichmentError, known_motif_enrichment


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_fasta(path: Path) -> tuple[list[str], list[str]]:
    if path.is_symlink() or not path.is_file():
        raise MotifEnrichmentError(f"FASTA input must be a stable non-symlink file: {path}")
    records = []
    identifier = None
    sequence: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith(">"):
            if identifier is not None:
                records.append((identifier, "".join(sequence)))
            identifier = raw[1:].strip().split()[0]
            sequence = []
        elif raw.strip():
            sequence.append(raw.strip())
    if identifier is not None:
        records.append((identifier, "".join(sequence)))
    identifiers = [identifier for identifier, _sequence in records]
    if not records or any(not identifier for identifier in identifiers) or len(set(identifiers)) != len(identifiers):
        raise MotifEnrichmentError(f"{path.name} must contain unique nonempty FASTA identifiers")
    return identifiers, [sequence for _identifier, sequence in records]


def read_motifs(path: Path) -> list[dict[str, object]]:
    if path.is_symlink() or not path.is_file():
        raise MotifEnrichmentError("motif JSON must be a stable non-symlink file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MotifEnrichmentError("motif JSON is invalid") from exc
    motifs = payload.get("motifs") if isinstance(payload, dict) else None
    if not isinstance(motifs, list):
        raise MotifEnrichmentError("motif JSON must contain a motifs array")
    return motifs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--foreground-fasta", type=Path, required=True)
    parser.add_argument("--background-fasta", type=Path, required=True)
    parser.add_argument("--motifs-json", type=Path, required=True)
    parser.add_argument("--genome-build", required=True)
    parser.add_argument("--sequence-extraction-policy", required=True)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.genome_build.strip() or not args.sequence_extraction_policy.strip():
        raise MotifEnrichmentError("genome-build and sequence-extraction-policy must be declared")
    if args.output.exists() or args.output.is_symlink():
        raise MotifEnrichmentError("output must be a new non-symlink path")
    foreground_ids, foreground = read_fasta(args.foreground_fasta)
    background_ids, background = read_fasta(args.background_fasta)
    overlap = sorted(set(foreground_ids) & set(background_ids))
    if overlap:
        raise MotifEnrichmentError("foreground and background FASTA identifiers must not overlap")
    motifs = read_motifs(args.motifs_json)
    source_digests = {"foreground_fasta": sha256(args.foreground_fasta), "background_fasta": sha256(args.background_fasta), "motifs_json": sha256(args.motifs_json)}
    result = known_motif_enrichment(foreground, background, motifs, args.threshold)
    if source_digests != {"foreground_fasta": sha256(args.foreground_fasta), "background_fasta": sha256(args.background_fasta), "motifs_json": sha256(args.motifs_json)}:
        raise MotifEnrichmentError("a source artifact changed during motif enrichment")
    report = {
        "module_id": "sequence-motif-enrichment", "module_version": "0.1.0", "passed": True,
        "input": {"source_sha256": source_digests, "foreground_record_count": len(foreground_ids), "background_record_count": len(background_ids), "genome_build": args.genome_build, "sequence_extraction_policy": args.sequence_extraction_policy},
        "analysis": result,
        "quality_gate_ids": ["motif-sequence-background-contract", "motif-pwm-and-statistical-validity", "motif-output-provenance"],
        "source_inputs_immutable": True, "outputs_reloaded": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    reloaded = json.loads(args.output.read_text(encoding="utf-8"))
    if not reloaded.get("passed") or reloaded.get("input", {}).get("source_sha256") != source_digests:
        raise MotifEnrichmentError("motif enrichment output did not reload with intact provenance")
    reloaded["outputs_reloaded"] = True
    args.output.write_text(json.dumps(reloaded, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "motif_count": result["motif_count"], "result_count": len(result["results"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MotifEnrichmentError as exc:
        print(f"MotifEnrichmentError: {exc}", file=sys.stderr)
        raise SystemExit(2)
