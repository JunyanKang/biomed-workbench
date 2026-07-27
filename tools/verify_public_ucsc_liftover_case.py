#!/usr/bin/env python3
"""Run the public UCSC hg19-to-hg38 chain-prefix liftover acceptance case."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/genome-coordinate-liftover/templates/run_crossmap_bed.py"
FIXTURES = ROOT / "tests/fixtures/genome-coordinate-liftover"
REPORT = ROOT / "reports/public-case-ucsc-coordinate-liftover.json"
CROSSMAP = os.environ.get("BIOMED_WORKBENCH_CROSSMAP") or shutil.which("CrossMap")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not CROSSMAP:
        raise RuntimeError("set BIOMED_WORKBENCH_CROSSMAP or expose CrossMap on PATH")
    chain = FIXTURES / "hg19-to-hg38-public-chain-prefix.chain"
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "liftover"
        run = subprocess.run([
            sys.executable, str(TEMPLATE), "--input-bed", str(FIXTURES / "public-hg19-intervals.bed"),
            "--chain", str(chain), "--chain-sha256", digest(chain), "--output-dir", str(output),
            "--source-assembly", "hg19", "--target-assembly", "hg38", "--crossmap", CROSSMAP,
            "--split-mapping-policy", "retain-and-flag", "--unmapped-policy", "retain-and-report",
        ], text=True, capture_output=True, check=False, timeout=180)
        if run.returncode:
            raise RuntimeError(run.stdout + run.stderr)
        observed = json.loads((output / "liftover-report.json").read_text(encoding="utf-8"))
    module = ROOT / "biomed_workbench/modules/builtin/genome-coordinate-liftover/module.json"
    payload = {
        "case_id": "ucsc-hg19-hg38-coordinate-liftover-v1", "passed": observed.get("passed") is True and observed.get("records", {}).get("input") == 2 and observed.get("records", {}).get("mapped") == 1 and observed.get("records", {}).get("unmapped") == 1,
        "module_id": "genome-coordinate-liftover", "module_manifest_sha256": digest(module), "template_sha256": digest(TEMPLATE),
        "chain_fixture_sha256": digest(chain), "interval_fixture_sha256": digest(FIXTURES / "public-hg19-intervals.bed"),
        "source": "UCSC hg19ToHg38.over.chain.gz public release header and first mapping block", "analysis": observed,
        "scientific_boundary": ["The fixture verifies chain-bound coordinate conversion and explicit unmapped-record preservation.", "It does not establish that any biological feature, variant allele, gene, peak, or regulatory element is equivalent between assemblies."],
    }
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"case_id": payload["case_id"], "passed": payload["passed"]}, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
