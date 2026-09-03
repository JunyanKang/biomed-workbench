#!/usr/bin/env python3
"""Compare a reference and rerendered scientific figure for visual-semantic drift."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.figure_semantics import compare_figure_semantics  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_figure_semantics(args.reference, args.candidate)
    encoded = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise ValueError("visual-semantic review never overwrites an existing report")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if result["automated_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
