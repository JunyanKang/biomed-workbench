#!/usr/bin/env python3
"""Execute pinned exomePeak2 1.14.3 and reload enrichment outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.exomepeak2 import execute_exomepeak2  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--rscript", default="Rscript")
    parser.add_argument("--timeout-seconds", type=int, default=172800)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    report = execute_exomepeak2(
        request, output_dir=args.output_dir, report_path=args.report,
        rscript=args.rscript, timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps({"passed": report["passed"], "assay": report["assay"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
