#!/usr/bin/env python3
"""Run samtools coordinate sort and CSI generation through the unified command contract."""

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
from biomed_workbench.modules.contract import parse_manifest, version_is_allowed  # noqa: E402
from biomed_workbench.modules.scientific_command import execute_scientific_command  # noqa: E402
from biomed_workbench.quality import parse_samtools_flagstat_report  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "alignment-sort-index-samtools" / "module.json"
SAMPLE_ID = "sort-fixture-01"
SAM = """@HD\tVN:1.6\tSO:unsorted
@SQ\tSN:chr1\tLN:1000
@RG\tID:sort-rg\tSM:sort-fixture-01\tPL:ILLUMINA
read-late\t0\tchr1\t201\t60\t10M\t*\t0\t0\tACGTACGTAC\tIIIIIIIIII\tRG:Z:sort-rg
read-early\t0\tchr1\t101\t60\t10M\t*\t0\t0\tTGCATGCATG\tIIIIIIIIII\tRG:Z:sort-rg
read-unmapped\t4\t*\t0\t0\t*\t*\t0\t0\tAAAAAAAAAA\tIIIIIIIIII\tRG:Z:sort-rg
"""


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        if not all(version_is_allowed(environment.tools.get(name, ""), rules) for name, rules in row.tool_versions.items()):
            raise RuntimeError("samtools runtime is outside the sort compatibility policy")
        if not all(version_is_allowed(environment.dependencies.get(name, ""), rules) for name, rules in row.dependency_versions.items()):
            raise RuntimeError("htslib runtime is outside the sort compatibility policy")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sam = root / "input.sam"
            sam.write_text(SAM, encoding="ascii")
            fixture = {
                "schema_version": 1,
                "format": "sam@1.6",
                "sample_id": SAMPLE_ID,
                "read_group": "sort-rg",
                "reference_build": "synthetic-build-1",
                "reference_sequence_digest": hashlib.sha256(b"N" * 1000).hexdigest(),
                "record_count": 3,
                "sam_sha256": hashlib.sha256(SAM.encode("ascii")).hexdigest(),
            }
            store = ProjectArtifactStore(root / "project")
            input_payload = store.import_file(sam, role="alignments", media_type="text/sam")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"sam": input_payload},
                parameters={"threads": 1},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            outputs = {payload.role: payload for payload in result.output_payloads}
            bam = store.resolve(outputs["alignments"])
            csi = store.resolve(outputs["index"])
            subprocess.run([str(executable), "quickcheck", "-v", str(bam)], check=True, capture_output=True, timeout=30)
            header = subprocess.run([str(executable), "view", "--no-PG", "-H", str(bam)], check=True, capture_output=True, text=True, timeout=30).stdout
            if "@HD\tVN:1.6\tSO:coordinate" not in header or f"SM:{SAMPLE_ID}" not in header:
                raise RuntimeError("sorted BAM header does not preserve sorting and sample identity")
            if any(marker in header for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/")):
                raise RuntimeError("sorted BAM program record contains a machine-local path")
            view = subprocess.run([str(executable), "view", str(bam)], check=True, capture_output=True, text=True, timeout=30).stdout.splitlines()
            positions = [int(line.split("\t")[3]) for line in view if line.split("\t")[2] != "*"]
            if positions != sorted(positions) or positions != [101, 201]:
                raise RuntimeError("BAM records are not coordinate sorted")
            index_check = subprocess.run(
                [str(executable), "idxstats", "-X", str(bam), str(csi)], check=True, capture_output=True, text=True, timeout=30
            ).stdout
            if "chr1\t1000\t2\t0" not in index_check:
                raise RuntimeError("CSI does not reconcile with sorted BAM reference counts")
            flagstat = root / "flagstat.json"
            flagstat.write_text(
                subprocess.run([str(executable), "flagstat", "-O", "json", str(bam)], check=True, capture_output=True, text=True, timeout=30).stdout,
                encoding="utf-8",
            )
            summary = parse_samtools_flagstat_report(flagstat, expected_version=environment.tools["samtools"])
            if summary["counts"]["total"] != 3 or summary["counts"]["mapped"] != 2:
                raise RuntimeError("sorted BAM read accounting differs from the SAM fixture")
            provenance = result.to_dict()["provenance"]
            output_manifest = {
                "format": "bam@1.6",
                "index_type": "csi",
                "sort_order": "coordinate",
                "bam_sha256": outputs["alignments"].sha256,
                "csi_sha256": outputs["index"].sha256,
                "sample_id": SAMPLE_ID,
            }
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
            "tested_version_baseline": {
                "tools": {item.name: environment.tools[item.name] in item.tested_versions for item in manifest.tool_requirements},
                "dependencies": {item.name: environment.dependencies[item.name] in item.tested_versions for item in manifest.dependencies},
            },
            "compatibility_policy": {"tools": {name: list(rules) for name, rules in row.tool_versions.items()}, "dependencies": {name: list(rules) for name, rules in row.dependency_versions.items()}},
            "fixture": fixture,
            "fixture_digest": digest_value(fixture),
            "output_manifest": output_manifest,
            "output_manifest_digest": digest_value(output_manifest),
            "bundle_integrity": {"quickcheck_passed": True, "csi_readable": True, "coordinate_sorted": True, "header_identity_passed": True, "portable_program_record": True},
            "execution": {"command_contract_digest": provenance["command_contract_digest"], "executable_sha256": provenance["executable_sha256"], "inputs": provenance["inputs"], "outputs": provenance["outputs"], "parameters": provenance["parameters"]},
            "scientific_summary": summary,
            "html_report_validated": False,
        }
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samtools-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "alignment-sort-live-verification.json")
    args = parser.parse_args()
    report = verify(args.samtools_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "output_manifest": report["output_manifest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
