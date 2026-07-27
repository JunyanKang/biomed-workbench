#!/usr/bin/env python3
"""Audit discrete copy-number event records stored in a JSON object."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from biomed_workbench.capabilities.clinical import copy_number_event_summary

TEMPLATE_VERSION = "0.1.0"
VERSION_PROVENANCE = "Biomed Workbench copy-number-event-summary module 0.1.0"


def load_audit_input(path: Path) -> dict:
    """Load and structurally validate the project-supplied audit object."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"records", "sample_count"}:
        raise ValueError("input must contain exactly records and sample_count")
    return payload


def write_report(path: Path, result: dict) -> None:
    """Write a versioned report that keeps the scientific audit decision explicit."""
    report = {"template_version": TEMPLATE_VERSION, "version_provenance": VERSION_PROVENANCE, **result}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def input_contract() -> dict:
    """Expose the expected scientific fields for project-specific adaptation."""
    return {
        "records": {"sample_id": "unique eligible sample identifier", "alteration": "integer in -2,-1,0,1,2"},
        "sample_count": "integer number of eligible samples under the same assay definition",
        "adaptation_notes": [
            "Filter to one cohort, assay, gene or genomic region before summary.",
            "Do not replace the denominator with a count parsed from free text.",
            "Retain excluded samples and reasons outside this summary for provenance.",
        ],
    }


def quality_gate_summary(result: dict) -> dict:
    """Turn deterministic audit fields into an explicit downstream-use decision."""
    complete = result["quality_status"] == "eligible_for_descriptive_cna_summary"
    return {
        "coverage_complete": complete,
        "allowed_downstream_use": "descriptive discrete-event summary" if complete else "record-level review only",
        "blocked_claims": [
            "cohort-wide prevalence" if not complete else "purity or ploidy inference",
            "purity or ploidy inference",
            "driver or treatment interpretation",
        ],
        "next_action": "reconcile assay eligibility and missing samples" if not complete else "review assay and biological context before interpretation",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = load_audit_input(args.input)
    result = copy_number_event_summary(payload.get("records"), payload.get("sample_count"))
    result["input_contract"] = input_contract()
    result["quality_gate_summary"] = quality_gate_summary(result)
    write_report(args.output, result)
    print(json.dumps({"quality_status": result["quality_status"], "output": str(args.output), "next_action": result["quality_gate_summary"]["next_action"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
