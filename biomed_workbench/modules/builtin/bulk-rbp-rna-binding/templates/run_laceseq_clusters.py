#!/usr/bin/env python3
"""Call LACE-seq read clusters from aligned experiment and matched-control BED6 files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.laceseq import execute_laceseq  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    report = execute_laceseq(request, output_dir=args.output_dir, report_path=args.report)
    print(json.dumps({"passed": report["passed"], "clusters": report["metrics"]["retained_clusters"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
