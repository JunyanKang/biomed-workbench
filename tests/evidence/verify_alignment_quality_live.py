#!/usr/bin/env python3
"""Run exact samtools flagstat through the scientific command contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore  # noqa: E402
from biomed_workbench.kernel.identity import digest_value  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.scientific_command import execute_scientific_command  # noqa: E402
from biomed_workbench.quality import parse_samtools_flagstat_report  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "alignment-quality-samtools" / "module.json"
SAMPLE_ID = "alignment-qc-fixture"
REFERENCE = {"name": "chr1", "length": 1000, "sequence_sha256": hashlib.sha256(b"N" * 1000).hexdigest()}
SAM = """@HD\tVN:1.6\tSO:coordinate
@SQ\tSN:chr1\tLN:1000
@RG\tID:fixture-rg\tSM:alignment-qc-fixture\tPL:ILLUMINA
pair1\t99\tchr1\t101\t60\t10M\t=\t151\t60\tACGTACGTAC\tIIIIIIIIII\tRG:Z:fixture-rg
pair1\t147\tchr1\t151\t60\t10M\t=\t101\t-60\tTGCATGCATG\tIIIIIIIIII\tRG:Z:fixture-rg
pair2\t77\t*\t0\t0\t*\t*\t0\t0\tAAAAAAAAAA\tIIIIIIIIII\tRG:Z:fixture-rg
pair2\t141\t*\t0\t0\t*\t*\t0\t0\tTTTTTTTTTT\tIIIIIIIIII\tRG:Z:fixture-rg
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        if environment.tools != {"samtools": "1.23"} or environment.dependencies != {"htslib": "1.23"}:
            raise RuntimeError("samtools runtime differs from the validated compatibility row")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle_root = root / "alignment-bundle"
            bundle_root.mkdir()
            bam = bundle_root / "alignment.bam"
            subprocess.run(
                [str(executable), "view", "-b", "-o", str(bam), "-"], input=SAM, text=True,
                check=True, capture_output=True, timeout=30,
            )
            subprocess.run([str(executable), "index", str(bam)], check=True, capture_output=True, timeout=30)
            subprocess.run([str(executable), "quickcheck", "-v", str(bam)], check=True, capture_output=True, timeout=30)
            header = subprocess.run(
                [str(executable), "view", "-H", str(bam)], check=True, capture_output=True, text=True, timeout=30
            ).stdout
            if "@HD\tVN:1.6\tSO:coordinate" not in header or f"SM:{SAMPLE_ID}" not in header:
                raise RuntimeError("BAM header does not preserve format, sorting, and sample identity")
            fixture_manifest = {
                "schema_version": 1,
                "sample_id": SAMPLE_ID,
                "format": "bam@1.6",
                "sort_order": "coordinate",
                "read_group": "fixture-rg",
                "reference": REFERENCE,
                "bam_sha256": _sha256(bam),
                "index_sha256": _sha256(bundle_root / "alignment.bam.bai"),
            }
            store = ProjectArtifactStore(root / "project")
            input_payload = store.import_file(bam, role="alignments", media_type="application/bam")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"alignments": input_payload},
                parameters={"threads": 1},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            output = result.output_payloads[0]
            summary = parse_samtools_flagstat_report(store.resolve(output), expected_version="1.23")
            provenance = result.to_dict()["provenance"]
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": manifest.id,
            "module_version": manifest.version,
            "compatibility_row_id": row.id,
            "regression_evidence_id": row.regression_evidence_ids[0],
            "end_to_end_evidence_id": row.end_to_end_evidence_ids[0],
            "tool_versions": environment.tools,
            "dependency_versions": environment.dependencies,
            "fixture_manifest": fixture_manifest,
            "fixture": fixture_manifest,
            "fixture_manifest_digest": digest_value(fixture_manifest),
            "bundle_integrity": {"quickcheck_passed": True, "index_present": True, "header_identity_passed": True},
            "execution": {
                "command_contract_digest": provenance["command_contract_digest"],
                "executable_sha256": provenance["executable_sha256"],
                "input": provenance["inputs"]["alignments"],
                "outputs": provenance["outputs"],
                "parameters": provenance["parameters"],
            },
            "scientific_summary": summary,
            "html_report_validated": False,
        }
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samtools-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "alignment-quality-live-verification.json")
    args = parser.parse_args()
    report = verify(args.samtools_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "total_reads": report["scientific_summary"]["counts"]["total"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
