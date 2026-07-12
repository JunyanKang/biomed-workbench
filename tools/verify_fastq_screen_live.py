#!/usr/bin/env python3
"""Run exact FastQ Screen contamination screening on bounded synthetic references."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore  # noqa: E402
from biomed_workbench.kernel.identity import digest_value  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.scientific_command import execute_scientific_command  # noqa: E402
from biomed_workbench.quality import parse_fastq_screen_report  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "read-contamination-screen" / "module.json"
FIXTURE = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"
REFERENCES = {
    "target": "ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT",
    "contaminant": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _runtime_lock(bowtie2: Path) -> dict[str, str]:
    result = {}
    for record in sorted((bowtie2.parent.parent / "conda-meta").glob("*.json")):
        payload = json.loads(record.read_text(encoding="utf-8"))
        if payload.get("name") and payload.get("version") and payload.get("build"):
            result[payload["name"]] = f"{payload['version']}-{payload['build']}"
    return dict(sorted(result.items()))


def verify(fastq_screen: Path, bowtie2: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(fastq_screen.parent), str(bowtie2.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        expected_tools = {name: versions[0] for name, versions in row.tool_versions.items()}
        expected_dependencies = {name: versions[0] for name, versions in row.dependency_versions.items()}
        if environment.tools != expected_tools or environment.dependencies != expected_dependencies:
            raise RuntimeError("FastQ Screen runtime differs from the validated compatibility row")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference_root = root / "references"
            reference_root.mkdir()
            reference_rows = []
            for name, sequence in REFERENCES.items():
                fasta = reference_root / f"{name}.fa"
                fasta.write_text(f">{name}\n{sequence}\n", encoding="ascii")
                subprocess.run(
                    [str(bowtie2.parent / "bowtie2-build"), "--quiet", str(fasta), str(reference_root / name)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                reference_rows.append({"name": name, "sequence_sha256": _sha256_bytes(sequence.encode("ascii")), "index_prefix": name})
            reference_manifest = {"schema_version": 1, "references": reference_rows, "expected_references": ["target"]}
            (reference_root / "reference-manifest.json").write_text(json.dumps(reference_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            config = "".join(f"DATABASE\t{name}\t{name}\n" for name in REFERENCES) + "ALIGNER\tbowtie2\nBOWTIE2\tbowtie2\n"
            (reference_root / "fastq_screen.conf").write_text(config, encoding="utf-8")
            bundle_path = root / "reference-bundle.zip"
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_STORED) as bundle:
                for path in sorted(reference_root.iterdir()):
                    bundle.write(path, arcname=path.name)
            store = ProjectArtifactStore(root / "project")
            reads_payload = store.import_file(FIXTURE, role="reads", media_type="application/fastq")
            reference_payload = store.import_file(bundle_path, role="references", media_type="application/zip")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"reads": reads_payload, "references": reference_payload},
                parameters={"threads": 1},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: fastq_screen,
            )
            outputs = {payload.role: payload for payload in result.output_payloads}
            summary = parse_fastq_screen_report(
                store.resolve(outputs["data"]), expected_version="0.16.0", expected_references=("target",), max_unexpected_percent=1.0
            )
            html = store.resolve(outputs["report"]).read_text(encoding="utf-8")
            if "FastQ Screen Processing Report" not in html or len(html) < 1000:
                raise RuntimeError("FastQ Screen HTML report is incomplete")
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
            "runtime_lock": _runtime_lock(bowtie2),
            "fixture": {"sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), "record_count": 12},
            "reference_manifest": reference_manifest,
            "reference_manifest_digest": digest_value(reference_manifest),
            "execution": {
                "command_contract_digest": provenance["command_contract_digest"],
                "executable_sha256": provenance["executable_sha256"],
                "inputs": provenance["inputs"],
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
    parser.add_argument("--fastq-screen-executable", type=Path, required=True)
    parser.add_argument("--bowtie2-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "fastq-screen-live-verification.json")
    args = parser.parse_args()
    report = verify(args.fastq_screen_executable.expanduser().resolve(strict=True), args.bowtie2_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "reference_count": report["scientific_summary"]["contamination_screening"]["reference_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
