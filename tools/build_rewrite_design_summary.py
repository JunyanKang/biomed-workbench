#!/usr/bin/env python3
"""Build a path-free deterministic summary from the private rewrite ledger."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


REQUIRED_FIELDS = {
    "action",
    "capability_cluster",
    "dependency_count",
    "path",
    "public_symbol_count",
    "purpose",
    "rationale",
    "reuse_mode",
    "role",
    "source",
    "source_sha256",
    "target",
}
REUSE_MODES = {"concept_only", "attribution_only", "none"}


def build_summary(ledger_path: Path) -> dict[str, object]:
    rows = []
    for number, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), start=1):
        row = json.loads(line)
        if not isinstance(row, dict) or set(row) != REQUIRED_FIELDS:
            raise ValueError(f"rewrite ledger row {number} has unsupported fields")
        text_fields = REQUIRED_FIELDS - {"dependency_count", "public_symbol_count", "target"}
        if (
            not all(isinstance(row[field], str) and row[field] for field in text_fields)
            or not (row["target"] is None or isinstance(row["target"], str) and row["target"])
            or row["reuse_mode"] not in REUSE_MODES
            or any(not isinstance(row[field], int) or isinstance(row[field], bool) or row[field] < 0 for field in ("dependency_count", "public_symbol_count"))
            or len(row["source_sha256"]) != 64
            or any(character not in "0123456789abcdef" for character in row["source_sha256"])
        ):
            raise ValueError(f"rewrite ledger row {number} is invalid")
        rows.append(row)
    if not rows:
        raise ValueError("rewrite ledger is empty")
    identities = [(row["source"], row["path"], row["source_sha256"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("rewrite ledger contains duplicate source identities")
    canonical = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
        for row in sorted(rows, key=lambda row: (row["source"], row["path"], row["source_sha256"]))
    )
    return {
        "schema_version": 1,
        "learned_file_count": len(rows),
        "source_counts": dict(sorted(Counter(row["source"] for row in rows).items())),
        "action_counts": dict(sorted(Counter(row["action"] for row in rows).items())),
        "capability_cluster_counts": dict(sorted(Counter(row["capability_cluster"] for row in rows).items())),
        "reuse_mode_counts": dict(sorted(Counter(row["reuse_mode"] for row in rows).items())),
        "public_symbol_count": sum(row["public_symbol_count"] for row in rows),
        "design_digest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_summary(args.ledger)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"design_digest": report["design_digest"], "learned_file_count": report["learned_file_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
