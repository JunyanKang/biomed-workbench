#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.encode_accessibility import execute_encode_accessibility
def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--request',type=Path,required=True); parser.add_argument('--output-dir',type=Path,required=True); parser.add_argument('--report',type=Path,required=True); parser.add_argument('--caper-executable',default='caper'); parser.add_argument('--caper-config',type=Path); args=parser.parse_args()
    report=execute_encode_accessibility(json.loads(args.request.read_text()),output_dir=args.output_dir,report_path=args.report,caper_executable=args.caper_executable,caper_config=args.caper_config); print(json.dumps({'passed':report['passed'],'assay':report['assay'],'report':str(args.report)},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
