#!/usr/bin/env python3
"""Execute pinned nf-core/nascent 2.3.0 for GRO-seq or PRO-seq and reload outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.nfcore import (  # noqa: E402
    NASCENT,
    NfCoreExecutionError,
    execute_nfcore,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--nextflow", default="nextflow")
    parser.add_argument("--timeout-seconds", type=int, default=172800)
    args = parser.parse_args()
    if not args.request.is_file():
        raise NfCoreExecutionError(f"request does not exist: {args.request}")
    request = json.loads(args.request.read_text(encoding="utf-8"))
    report = execute_nfcore(
        request,
        spec=NASCENT,
        output_dir=args.output_dir,
        report_path=args.report,
        nextflow=args.nextflow,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps({
        "passed": report["passed"],
        "workflow": report["workflow"]["name"],
        "revision": report["workflow"]["revision"],
        "scientific_file_count": report["outputs"]["scientific_file_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NfCoreExecutionError as exc:
        print(f"NfCoreExecutionError: {exc}", file=sys.stderr)
        raise SystemExit(2)
