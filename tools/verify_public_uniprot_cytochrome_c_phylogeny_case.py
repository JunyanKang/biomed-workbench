#!/usr/bin/env python3
"""Run the public UniProt cytochrome c MAFFT and IQ-TREE acceptance case."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = ROOT / "biomed_workbench/modules/builtin/comparative-sequence-phylogeny"
TEMPLATE = MODULE_ROOT / "templates/run_mafft_iqtree.py"
FIXTURE_ROOT = ROOT / "tests/fixtures/comparative-sequence-phylogeny"
REPORT = ROOT / "reports/public-case-uniprot-cytochrome-c-phylogeny.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "output"
        command = [
            sys.executable, str(TEMPLATE),
            "--input-fasta", str(FIXTURE_ROOT / "cytochrome-c-uniprot.fasta"),
            "--metadata", str(FIXTURE_ROOT / "cytochrome-c-uniprot.tsv"),
            "--output-dir", str(output),
            "--sequence-type", "protein",
            "--substitution-model", "LG+G4",
            "--support-method", "ultrafast-bootstrap",
            "--support-replicates", "1000",
            "--outgroup-id", "yeast_cyc1",
            "--threads", "1",
            "--seed", "17",
        ]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=180)
        report_path = output / "comparative-phylogeny-report.json"
        if completed.returncode != 0 or not report_path.is_file():
            raise RuntimeError(completed.stdout + completed.stderr)
        observed = json.loads(report_path.read_text(encoding="utf-8"))

    manifest = json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8"))
    passed = (
        observed.get("passed") is True
        and observed.get("alignment", {}).get("record_count") == 4
        and observed.get("tree", {}).get("tip_count") == 4
        and observed.get("tree", {}).get("outgroups_present") == ["yeast_cyc1"]
        and observed.get("parameters", {}).get("support_replicates") == 1000
        and "7.526" in observed.get("tool_versions", {}).get("mafft", "")
        and "3.1.2" in observed.get("tool_versions", {}).get("iqtree", "")
    )
    payload = {
        "case_id": "uniprot-cytochrome-c-phylogeny-v1",
        "passed": passed,
        "module_id": manifest["id"],
        "module_version": manifest["version"],
        "module_manifest_sha256": sha256(MODULE_ROOT / "module.json"),
        "template_sha256": sha256(TEMPLATE),
        "fixture_sha256": sha256(FIXTURE_ROOT / "cytochrome-c-uniprot.fasta"),
        "metadata_sha256": sha256(FIXTURE_ROOT / "cytochrome-c-uniprot.tsv"),
        "source_records": [
            "UniProt:P99999", "UniProt:P62897", "UniProt:P00004", "UniProt:P00044"
        ],
        "analysis": observed,
        "scientific_boundary": [
            "This case validates record-preserving alignment and method-specific tree production, not orthology, species history, divergence time, selection, recombination, or functional conservation.",
            "The yeast record is a declared outgroup for presence validation; the case does not establish biological outgroup appropriateness for another project."
        ],
    }
    REPORT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"case_id": payload["case_id"], "passed": passed}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
