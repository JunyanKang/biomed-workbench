#!/usr/bin/env python3
"""Refresh public current-evidence metadata without rewriting private receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def refresh(report_path: Path) -> dict[str, object]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assimilation = json.loads(
        (ROOT / "reports" / "source-assimilation-summary.json").read_text(encoding="utf-8")
    )
    design = json.loads(
        (ROOT / "reports" / "rewrite-design-summary.json").read_text(encoding="utf-8")
    )
    research = json.loads(
        (ROOT / "reports" / "research-engine-verification.json").read_text(encoding="utf-8")
    )
    source_file_count = sum(source["file_count"] for source in assimilation["sources"])
    if (
        report.get("passed") is not True
        or report.get("schema_version") != 1
        or report.get("file_count") != source_file_count
        or report.get("file_count") != design.get("learned_file_count")
        or report.get("reconciled_count", 0) + report.get("pending_count", 0)
        != source_file_count
        or report.get("pending_count", 0) <= 0
        or not re.fullmatch(r"[0-9a-f]{64}", str(report.get("receipt_root_digest", "")))
    ):
        raise RuntimeError(
            "public reconciliation invariants changed; rerun full private-ledger reconciliation"
        )
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    skill_path = ROOT / "skills" / "biomed-workbench" / "SKILL.md"
    report["current_evidence"] = {
        "module_count": len(registry.all()),
        "registry_digest": registry.digest,
        "skill_sha256": hashlib.sha256(skill_path.read_bytes()).hexdigest(),
        "test_count": research["test_count"],
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports" / "source-reconciliation-summary.json",
    )
    args = parser.parse_args()
    report = refresh(args.report)
    print(
        json.dumps(
            {
                "passed": True,
                "file_count": report["file_count"],
                "pending_count": report["pending_count"],
                "current_evidence": report["current_evidence"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
