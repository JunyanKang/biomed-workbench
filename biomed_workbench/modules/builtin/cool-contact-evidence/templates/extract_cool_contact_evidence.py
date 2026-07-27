#!/usr/bin/env python3
"""Extract bounded enhancer-promoter contact evidence from a declared .cool file.

This template accepts only a project-supplied Cooler HDF5 file and a BED table
with explicit enhancer/promoter labels. It reports cis contact candidates with
raw count and distance-stratified descriptive normalization. It does not call
loops, balance matrices, construct TADs, infer regulation, or make causal
claims. The input files remain untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def plugin_root(template_path: Path) -> Path:
    """Find the installed workbench root without relying on the caller's CWD."""
    for candidate in template_path.resolve().parents:
        if (candidate / "biomed_workbench" / "implementations" / "cool_contact_evidence.py").is_file():
            return candidate
    raise RuntimeError("Biomed Workbench package root is unavailable beside this template")


ROOT = plugin_root(Path(__file__))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.cool_contact_evidence import CoolContactError, cool_contact_candidates


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cool", type=Path, required=True, help="Single-resolution project .cool input")
    parser.add_argument("--regulatory-elements", type=Path, required=True, help="BED: chrom, start, end, id, explicit enhancer|promoter")
    parser.add_argument("--genome-build", required=True)
    parser.add_argument("--contact-assay", choices=("hic", "microc", "capture-c", "other"), required=True)
    parser.add_argument("--replicate-id", required=True)
    parser.add_argument("--max-candidates", type=int, default=10000)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.genome_build.strip() or not args.replicate_id.strip():
        raise CoolContactError("genome-build and replicate-id must be nonempty")
    if args.report.exists() or args.report.is_symlink():
        raise CoolContactError("report must be a new non-symlink path")
    evidence = cool_contact_candidates(args.cool, args.regulatory_elements, max_candidates=args.max_candidates)
    if sha256(args.cool) != evidence["cool"]["sha256"] or sha256(args.regulatory_elements) != evidence["regulatory_elements"]["sha256"]:
        raise CoolContactError("a source input changed while contact evidence was extracted")
    report = {
        "module_id": "cool-contact-evidence",
        "module_version": "0.1.0",
        "passed": True,
        "contact_assay": args.contact_assay,
        "genome_build": args.genome_build,
        "replicate_id": args.replicate_id,
        "parameters": {"max_candidates": args.max_candidates, "normalization": "raw-count-over-cis-distance-median"},
        "evidence": evidence,
        "quality_gate_ids": ["cool-contact-input-contract", "cool-contact-structural-validity", "cool-contact-provenance", "cool-contact-claim-boundary"],
        "outputs_reloaded": True,
        "source_inputs_immutable": True,
        "no_environment_or_compute_infrastructure_managed": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "candidate_count": evidence["candidate_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CoolContactError as exc:
        print(f"CoolContactError: {exc}", file=sys.stderr)
        raise SystemExit(2)
