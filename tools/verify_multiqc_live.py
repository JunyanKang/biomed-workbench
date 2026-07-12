#!/usr/bin/env python3
"""Run FastQC-to-MultiQC aggregation on two bounded sample identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.scientific_command import execute_scientific_command  # noqa: E402
from biomed_workbench.quality import parse_multiqc_archive  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "quality-report-multiqc" / "module.json"
FIXTURE = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_lock(multiqc_executable: Path) -> dict[str, str]:
    interpreter = Path(multiqc_executable.read_text(encoding="utf-8").splitlines()[0][2:].strip())
    code = "import json; from importlib.metadata import distributions; print(json.dumps({d.metadata['Name']:d.version for d in distributions() if d.metadata['Name']}, sort_keys=True))"
    completed = subprocess.run([str(interpreter), "-c", code], text=True, capture_output=True, check=True, timeout=30)
    return json.loads(completed.stdout)


def verify(multiqc_executable: Path, fastqc_executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(multiqc_executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        expected_tools = {name: versions[0] for name, versions in row.tool_versions.items()}
        expected_dependencies = {name: versions[0] for name, versions in row.dependency_versions.items()}
        if environment.tools != expected_tools or environment.dependencies != expected_dependencies:
            raise RuntimeError("MultiQC runtime differs from the validated compatibility row")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fastqc_outputs = root / "fastqc"
            fastqc_outputs.mkdir()
            sample_paths = []
            for sample_id in ("sample-a", "sample-b"):
                sample = root / f"{sample_id}.fastq"
                shutil.copyfile(FIXTURE, sample)
                sample_paths.append(sample)
            completed = subprocess.run(
                [str(fastqc_executable), "--threads", "1", "--outdir", str(fastqc_outputs), *(str(path) for path in sample_paths)],
                text=True,
                capture_output=True,
                check=True,
                timeout=120,
            )
            archives = sorted(fastqc_outputs.glob("*_fastqc.zip"))
            if len(archives) != 2:
                raise RuntimeError("FastQC did not produce two source archives")
            collection = root / "fastqc-collection.zip"
            with zipfile.ZipFile(collection, "w", compression=zipfile.ZIP_STORED) as bundle:
                for archive in archives:
                    bundle.write(archive, arcname=archive.name)
            store = ProjectArtifactStore(root / "project")
            input_payload = store.import_file(collection, role="bundle", media_type="application/zip")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"bundle": input_payload},
                parameters={},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: multiqc_executable,
            )
            outputs = {payload.role: payload for payload in result.output_payloads}
            summary = parse_multiqc_archive(store.resolve(outputs["data"]), expected_version="1.35")
            html = store.resolve(outputs["report"]).read_text(encoding="utf-8")
            if summary["sample_count"] != 2 or set(summary["samples"]) != {"sample-a", "sample-b"}:
                raise RuntimeError("MultiQC sample accounting differs from the input collection")
            if "MultiQC" not in html or len(html) < 1000:
                raise RuntimeError("MultiQC HTML report is incomplete")
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
            "runtime_lock": _runtime_lock(multiqc_executable),
            "fixture": {"sha256": _sha256(FIXTURE), "source_sample_count": 2, "source_fastqc_version": "0.12.1"},
            "execution": {
                "command_contract_digest": provenance["command_contract_digest"],
                "executable_sha256": provenance["executable_sha256"],
                "input": provenance["inputs"]["bundle"],
                "outputs": provenance["outputs"],
                "parameters": provenance["parameters"],
            },
            "scientific_summary": summary,
            "html_report_validated": True,
            "source_fastqc_completed": completed.returncode == 0,
        }
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--multiqc-executable", type=Path, required=True)
    parser.add_argument("--fastqc-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "multiqc-live-verification.json")
    args = parser.parse_args()
    report = verify(args.multiqc_executable.expanduser().resolve(strict=True), args.fastqc_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "sample_count": report["scientific_summary"]["sample_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
