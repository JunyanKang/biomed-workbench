#!/usr/bin/env python3
"""Run the exact FastQC command module on the bounded sequencing fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore  # noqa: E402
from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.scientific_command import execute_scientific_command  # noqa: E402
from biomed_workbench.quality import parse_fastqc_archive  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "read-quality-fastqc" / "module.json"
FIXTURE = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _version(command: list[str], pattern: str) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=True, timeout=15)
    match = re.search(pattern, result.stdout + result.stderr)
    if not match:
        raise RuntimeError("scientific tool version probe did not match")
    return match.group(1)


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    fastqc_version = _version([str(executable), "--version"], r"FastQC v([0-9]+(?:\.[0-9]+)+)")
    java_version = _version(["java", "-version"], r'version "([0-9]+)')
    if fastqc_version != "0.12.1" or java_version != "22":
        raise RuntimeError("FastQC or Java differs from the validated compatibility row")
    with tempfile.TemporaryDirectory() as temporary:
        store = ProjectArtifactStore(Path(temporary) / "project")
        input_payload = store.import_file(FIXTURE, role="reads", media_type="application/fastq")
        result = execute_scientific_command(
            manifest.execution.command,
            store=store,
            input_payloads={"reads": input_payload},
            parameters={"threads": 1},
            tool_versions={"fastqc": fastqc_version},
            dependency_versions={"java": java_version},
            compatibility_row_id=manifest.compatibility_matrix[0].id,
            executable_resolver=lambda _name: executable,
        )
        outputs = {payload.role: payload for payload in result.output_payloads}
        summary = parse_fastqc_archive(store.resolve(outputs["archive"]), expected_version=fastqc_version)
        html = store.resolve(outputs["report"]).read_text(encoding="utf-8")
        if "FastQC Report" not in html or len(html) < 1000:
            raise RuntimeError("FastQC HTML report is incomplete")
        provenance = result.to_dict()["provenance"]
    return {
        "schema_version": 1,
        "passed": True,
        "module_id": manifest.id,
        "module_version": manifest.version,
        "compatibility_row_id": manifest.compatibility_matrix[0].id,
        "regression_evidence_id": manifest.compatibility_matrix[0].regression_evidence_ids[0],
        "end_to_end_evidence_id": manifest.compatibility_matrix[0].end_to_end_evidence_ids[0],
        "tool_versions": {"fastqc": fastqc_version},
        "dependency_versions": {"java": java_version},
        "fixture": {
            "sha256": _sha256(FIXTURE),
            "record_count": sum(1 for _line in FIXTURE.open(encoding="utf-8")) // 4,
            "format": "fastq@sanger-phred33",
        },
        "execution": {
            "command_contract_digest": provenance["command_contract_digest"],
            "executable_sha256": provenance["executable_sha256"],
            "input": provenance["inputs"]["reads"],
            "outputs": provenance["outputs"],
            "parameters": provenance["parameters"],
        },
        "scientific_summary": summary,
        "html_report_validated": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fastqc-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "fastqc-live-verification.json")
    args = parser.parse_args()
    report = verify(args.fastqc_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "record_count": report["fixture"]["record_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
