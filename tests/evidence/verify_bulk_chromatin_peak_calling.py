#!/usr/bin/env python3
"""Run a synthetic, source-preserving MACS3 bulk chromatin acceptance case."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "biomed_workbench/modules/builtin/bulk-chromatin-peak-calling"
TEMPLATE = MODULE / "templates/call_macs3_chromatin.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_fixture(path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for index in range(240):
            handle.write(f"chr1\t{10000 + (index % 12) * 4}\t{10050 + (index % 12) * 4}\n")
        for index in range(30):
            handle.write(f"chr1\t{50000 + index * 20}\t{50030 + index * 20}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--macs3", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=ROOT / "reports/bulk-chromatin-peak-calling-live-verification.json")
    args = parser.parse_args()
    if not args.python.is_file() or not args.macs3.is_file():
        raise SystemExit("a Python runtime and MACS3 executable are required")
    with tempfile.TemporaryDirectory(prefix="biomed-bulk-chromatin-") as temporary:
        work = Path(temporary)
        treatment = work / "treatment.bed"
        write_fixture(treatment)
        source_before = sha256(treatment)
        command = [str(args.python), str(TEMPLATE), "--assay", "cutrun", "--treatment", str(treatment), "--input-format", "BED", "--peak-mode", "narrow", "--genome-size", "100000", "--qvalue", "0.05", "--keep-dup", "all", "--nomodel-extsize", "50", "--name", "fixture", "--output-dir", str(work / "output"), "--report", str(work / "template-report.json"), "--macs3", str(args.macs3)]
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=300)
        if completed.returncode != 0:
            raise RuntimeError(f"bulk chromatin template failed: {completed.stderr[-4000:]}")
        template_report = json.loads((work / "template-report.json").read_text(encoding="utf-8"))
        source_after = sha256(treatment)
        if not template_report["passed"] or not template_report["outputs_reloaded"] or template_report["outputs"]["peaks"]["rows"] < 1:
            raise RuntimeError("bulk chromatin template did not return reload-validated peaks")
        report = {
            "case_id": "bulk-chromatin-peak-calling-synthetic-cutrun-v1",
            "passed": source_before == source_after,
            "module": {"id": "bulk-chromatin-peak-calling", "manifest_sha256": sha256(MODULE / "module.json"), "template_sha256": sha256(TEMPLATE)},
            "fixture": {"format": "BED", "sha256": source_before, "record_count": 270},
            "execution": {"macs3_completed": True, "outputs_reloaded": True, "source_artifact_immutable": source_before == source_after},
            "analysis": template_report,
            "scientific_boundary": ["This synthetic fixture verifies executable peak calling and output reload only.", "It does not validate alignment, controls, replicate reproducibility, differential binding, specificity, direct binding, or causal regulation."],
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "peak_count": report["analysis"]["outputs"]["peaks"]["rows"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
