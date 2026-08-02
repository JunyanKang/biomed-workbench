#!/usr/bin/env python3
"""Execute pinned ChIA-PET2 0.9.3 from paired FASTQ through loop/QC outputs."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from biomed_workbench.implementations.chiapet2 import execute_chiapet2  # noqa:E402
def main()->int:
 p=argparse.ArgumentParser(description=__doc__); p.add_argument('--request',type=Path,required=True); p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--report',type=Path,required=True); p.add_argument('--chiapet2',default='ChIA-PET2'); p.add_argument('--timeout-seconds',type=int,default=172800); a=p.parse_args(); r=execute_chiapet2(json.loads(a.request.read_text()),output_dir=a.output_dir,report_path=a.report,executable=a.chiapet2,timeout_seconds=a.timeout_seconds); print(json.dumps({'passed':r['passed'],'assay':r['assay']},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
