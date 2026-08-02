#!/usr/bin/env python3
"""Execute pinned RIPSeeker 1.28.0 and reload HMM enrichment regions."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from biomed_workbench.implementations.ripseeker import execute_ripseeker  # noqa: E402
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True); parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True); parser.add_argument("--rscript", default="Rscript")
    parser.add_argument("--container-image"); parser.add_argument("--container-platform", default="linux/amd64")
    parser.add_argument("--timeout-seconds", type=int, default=172800); args = parser.parse_args()
    report = execute_ripseeker(json.loads(args.request.read_text()), output_dir=args.output_dir, report_path=args.report, rscript=args.rscript, container_image=args.container_image, container_platform=args.container_platform, timeout_seconds=args.timeout_seconds)
    print(json.dumps({"passed": report["passed"], "assay": report["assay"]}, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
