#!/usr/bin/env python3
"""Build one clean-room rewrite decision for every assimilated source file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.assimilation import load_private_manifest  # noqa: E402
from biomed_workbench.design_ledger import (  # noqa: E402
    build_design_record,
    summarize_design,
    verify_design_complete,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--private-ledger", type=Path, required=True)
    parser.add_argument("--public-summary", type=Path, required=True)
    args = parser.parse_args()
    _roots, records = load_private_manifest(args.manifest)
    designs = [build_design_record(record) for record in records]
    verify_design_complete(records, designs)
    args.private_ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.private_ledger.open("w", encoding="utf-8") as handle:
        for record in designs:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
    summary = summarize_design(designs)
    args.public_summary.parent.mkdir(parents=True, exist_ok=True)
    args.public_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"learned_file_count": summary["learned_file_count"], "design_digest": summary["design_digest"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
