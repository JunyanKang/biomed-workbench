#!/usr/bin/env python3
"""Apply private path rules and publish only path-free binding counts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.audit import SourceBindingError, apply_binding_rule_files  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design-ledger", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "source-capability-bindings.json")
    args = parser.parse_args()
    try:
        report = apply_binding_rule_files(args.design_ledger, args.bindings, args.rules)
    except SourceBindingError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
