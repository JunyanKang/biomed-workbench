#!/usr/bin/env python3
"""Run the exact fastp QC-only module on the bounded sequencing fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.scientific_command import execute_scientific_command  # noqa: E402
from biomed_workbench.quality import parse_fastp_report  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "read-quality-fastp" / "module.json"
FIXTURE = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_lock(executable: Path) -> dict[str, str]:
    records = sorted((executable.parent.parent / "conda-meta").glob("*.json"))
    result = {}
    for record in records:
        payload = json.loads(record.read_text(encoding="utf-8"))
        if payload.get("name") and payload.get("version") and payload.get("build"):
            result[payload["name"]] = f"{payload['version']}-{payload['build']}"
    return dict(sorted(result.items()))


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        if environment.tools != {"fastp": "1.3.6"} or environment.dependencies != {"fastp-bioconda-build": "1.3.6-ha1d0559_0"}:
            raise RuntimeError("fastp runtime differs from the validated compatibility row")
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectArtifactStore(Path(temporary) / "project")
            input_payload = store.import_file(FIXTURE, role="reads", media_type="application/fastq")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"reads": input_payload},
                parameters={"threads": 1},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            outputs = {payload.role: payload for payload in result.output_payloads}
            summary = parse_fastp_report(store.resolve(outputs["data"]), expected_version="1.3.6")
            html = store.resolve(outputs["report"]).read_text(encoding="utf-8")
            if "fastp report" not in html.lower() or len(html) < 1000:
                raise RuntimeError("fastp HTML report is incomplete")
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
            "runtime_lock": _runtime_lock(executable),
            "fixture": {"sha256": _sha256(FIXTURE), "record_count": 12, "format": "fastq@sanger-phred33"},
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
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fastp-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "fastp-live-verification.json")
    args = parser.parse_args()
    report = verify(args.fastp_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "record_count": report["fixture"]["record_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
