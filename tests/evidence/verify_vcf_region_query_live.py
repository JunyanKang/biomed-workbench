#!/usr/bin/env python3
"""Run tabix VCF region retrieval through the versioned command contract."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
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
from biomed_workbench.quality import parse_tabix_vcf_query  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "variant-region-query-tabix" / "module.json"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "variants"
VCF_GZ = FIXTURE_ROOT / "region-query.vcf.gz"
TBI = FIXTURE_ROOT / "region-query.vcf.gz.tbi"
REGION = "chr1:90-205"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _data_records(text: str) -> list[str]:
    return [line for line in text.splitlines() if line and not line.startswith("#")]


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        if environment.tools != {"tabix": "1.23"} or environment.dependencies != {"htslib": "1.23"}:
            raise RuntimeError("tabix runtime differs from the validated compatibility row")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ProjectArtifactStore(root / "project")
            vcf_payload = store.import_file(VCF_GZ, role="variants", media_type="application/gzip")
            index_payload = store.import_file(TBI, role="index", media_type="application/octet-stream")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"vcf": vcf_payload, "index": index_payload},
                parameters={"region": REGION},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            output = result.output_payloads[0]
            output_path = store.resolve(output)
            summary = parse_tabix_vcf_query(output_path, region=REGION, expected_samples=("SAMPLE_A",))
            output_text = output_path.read_text(encoding="utf-8")
            with gzip.open(VCF_GZ, "rt", encoding="utf-8") as handle:
                source_text = handle.read()
            source_records = _data_records(source_text)
            expected_records = [line for line in source_records if line.startswith("chr1\t100\t") or line.startswith("chr1\t200\t")]
            if _data_records(output_text) != expected_records:
                raise RuntimeError("tabix regional output does not reconcile with source VCF records")
            provenance = result.to_dict()["provenance"]
        fixture = {
            "format": "vcf@4.5",
            "compression": "bgzf",
            "index_type": "tbi",
            "coordinate_system": "one-based-inclusive",
            "reference_build": "synthetic-build-1",
            "reference_sequence_digest": hashlib.sha256(b"synthetic-build-1").hexdigest(),
            "sample_manifest_digest": hashlib.sha256(b"SAMPLE_A").hexdigest(),
            "vcf_sha256": _sha256(VCF_GZ),
            "index_sha256": _sha256(TBI),
            "source_record_count": len(source_records),
            "region": REGION,
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
            "compatibility_policy": {"tools": {"tabix": [">=1.23,<1.24"]}, "dependencies": {"htslib": [">=1.23,<1.24"]}},
            "fixture": fixture,
            "fixture_digest": digest_value(fixture),
            "bundle_integrity": {
                "vcf_payload_bound": provenance["inputs"]["vcf"]["sha256"] == fixture["vcf_sha256"],
                "tbi_payload_bound": provenance["inputs"]["index"]["sha256"] == fixture["index_sha256"],
                "source_records_reconciled": True,
                "header_and_sample_identity_validated": summary["header_preserved"] and summary["samples"] == ["SAMPLE_A"],
            },
            "execution": {
                "command_contract_digest": provenance["command_contract_digest"],
                "executable_sha256": provenance["executable_sha256"],
                "inputs": provenance["inputs"],
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
    parser.add_argument("--tabix-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "vcf-region-query-live-verification.json")
    args = parser.parse_args()
    report = verify(args.tabix_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "record_count": report["scientific_summary"]["record_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
