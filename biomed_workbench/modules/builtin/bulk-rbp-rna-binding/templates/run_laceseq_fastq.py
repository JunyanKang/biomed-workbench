#!/usr/bin/env python3
"""Run the published raw LACE-seq trimming, alignment and cluster workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.laceseq_fastq import execute_laceseq_fastq  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cutadapt", default="cutadapt")
    parser.add_argument("--bowtie", default="bowtie")
    parser.add_argument("--timeout-seconds", type=int, default=172800)
    args = parser.parse_args()
    report = execute_laceseq_fastq(
        json.loads(args.request.read_text(encoding="utf-8")),
        output_dir=args.output_dir,
        report_path=args.report,
        cutadapt=args.cutadapt,
        bowtie=args.bowtie,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps({"passed": report["passed"], "clusters": report["clusters"]["retained_clusters"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
