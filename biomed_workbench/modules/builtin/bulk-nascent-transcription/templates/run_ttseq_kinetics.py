#!/usr/bin/env python3
"""Run TT-seq abundance profiling or calibrated synthesis/degradation estimation."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from biomed_workbench.implementations.ttseq import execute_ttseq  # noqa: E402
def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--request',type=Path,required=True); parser.add_argument('--output-dir',type=Path,required=True); parser.add_argument('--report',type=Path,required=True); args=parser.parse_args()
    report=execute_ttseq(json.loads(args.request.read_text()),output_dir=args.output_dir,report_path=args.report); print(json.dumps({'passed':report['passed'],'mode':report['parameters']['analysis_mode'],'rows':report['outputs']['feature_estimates']['rows']},sort_keys=True)); return 0
if __name__ == '__main__': raise SystemExit(main())
