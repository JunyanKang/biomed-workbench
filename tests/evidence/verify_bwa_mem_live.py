#!/usr/bin/env python3
"""Run BWA-MEM on a bounded synthetic DNA fixture through the unified command contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore  # noqa: E402
from biomed_workbench.kernel.identity import digest_value  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.contract import parse_manifest, version_is_allowed  # noqa: E402
from biomed_workbench.modules.scientific_command import execute_scientific_command  # noqa: E402
from biomed_workbench.quality import parse_bwa_mem_sam  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "dna-align-bwa-mem-single" / "module.json"
SAMPLE_ID = "bwa-fixture-01"
REFERENCE_NAME = "chrSynthetic"
REFERENCE_LENGTH = 1200


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        if not all(version_is_allowed(environment.tools.get(name, ""), rules) for name, rules in row.tool_versions.items()):
            raise RuntimeError("BWA runtime is outside the declared compatibility policy")
        if not all(version_is_allowed(environment.dependencies.get(name, ""), rules) for name, rules in row.dependency_versions.items()):
            raise RuntimeError("BWA installation identity is outside the declared compatibility policy")
        rng = random.Random(20260713)
        reference_sequence = "".join(rng.choice("ACGT") for _ in range(REFERENCE_LENGTH))
        mapped_read = reference_sequence[420:520]
        unmapped_read = "N" * 100
        fastq_text = (
            f"@mapped-read\n{mapped_read}\n+\n{'I' * 100}\n"
            f"@unmapped-read\n{unmapped_read}\n+\n{'I' * 100}\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference_root = root / "reference"
            reference_root.mkdir()
            reference = reference_root / "reference.fa"
            reference.write_text(f">{REFERENCE_NAME}\n{reference_sequence}\n", encoding="ascii")
            subprocess.run([str(executable), "index", str(reference)], check=True, capture_output=True, timeout=60)
            index_suffixes = ("amb", "ann", "bwt", "pac", "sa")
            index_digests = {suffix: _sha256(reference.with_suffix(f".fa.{suffix}")) for suffix in index_suffixes}
            reference_manifest = {
                "schema_version": 1,
                "format": "bwa-reference@0.7",
                "reference_build": "synthetic-build-1",
                "reference_sequence_digest": hashlib.sha256(reference_sequence.encode("ascii")).hexdigest(),
                "sequences": [{"name": REFERENCE_NAME, "length": REFERENCE_LENGTH}],
                "index_digests": index_digests,
                "bwa_tested_baseline": environment.tools["bwa"],
            }
            (reference_root / "reference-manifest.json").write_text(
                json.dumps(reference_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            archive = root / "reference-bundle.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
                for path in sorted(reference_root.iterdir()):
                    output.write(path, arcname=path.name)
            reads = root / "reads.fastq"
            reads.write_text(fastq_text, encoding="ascii")
            fixture = {
                "schema_version": 1,
                "sample_id": SAMPLE_ID,
                "read_count": 2,
                "read_length": 100,
                "read_layout": "single-end",
                "quality_encoding": "sanger-phred33",
                "fastq_sha256": _sha256(reads),
                "reference_manifest_digest": digest_value(reference_manifest),
            }
            store = ProjectArtifactStore(root / "project")
            reads_payload = store.import_file(reads, role="reads", media_type="application/fastq")
            reference_payload = store.import_file(archive, role="reference", media_type="application/zip")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"reads": reads_payload, "reference": reference_payload},
                parameters={"threads": 1, "sample-id": SAMPLE_ID},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            sam_payload = result.output_payloads[0]
            sam_path = store.resolve(sam_payload)
            sam_text = sam_path.read_text(encoding="utf-8")
            if any(marker in sam_text for marker in ("/Users/", "/private/", "/tmp/", "/var/folders/")):
                raise RuntimeError("BWA SAM contains a machine-local path")
            summary = parse_bwa_mem_sam(
                sam_path,
                expected_version=environment.tools["bwa"],
                expected_sample_id=SAMPLE_ID,
                reference_sequences={REFERENCE_NAME: REFERENCE_LENGTH},
                expected_read_count=2,
            )
            if summary["counts"]["mapped"] != 1 or summary["counts"]["unmapped"] != 1:
                raise RuntimeError("BWA fixture did not preserve expected mapped and unmapped reads")
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
            "tested_version_baseline": {
                "tools": {item.name: environment.tools[item.name] in item.tested_versions for item in manifest.tool_requirements},
                "dependencies": {item.name: environment.dependencies[item.name] in item.tested_versions for item in manifest.dependencies},
            },
            "compatibility_policy": {
                "tools": {name: list(rules) for name, rules in row.tool_versions.items()},
                "dependencies": {name: list(rules) for name, rules in row.dependency_versions.items()},
            },
            "fixture": fixture,
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
            "portable_program_record_validated": True,
            "html_report_validated": False,
        }
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bwa-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "bwa-mem-live-verification.json")
    args = parser.parse_args()
    report = verify(args.bwa_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "counts": report["scientific_summary"]["counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
