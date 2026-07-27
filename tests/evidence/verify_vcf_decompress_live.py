#!/usr/bin/env python3
"""Run byte-preserving BGZF VCF decompression through the scientific command contract."""

from __future__ import annotations

import argparse
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
from biomed_workbench.quality import parse_vcf_document  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "variant-decompress-bgzip" / "module.json"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "variants"
SOURCE = FIXTURE_ROOT / "region-query.vcf"
VCF_GZ = FIXTURE_ROOT / "region-query.vcf.gz"
TBI = FIXTURE_ROOT / "region-query.vcf.gz.tbi"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        if environment.tools != {"bgzip": "1.23"} or environment.dependencies != {"htslib": "1.23"}:
            raise RuntimeError("bgzip runtime differs from the validated compatibility row")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ProjectArtifactStore(root / "project")
            vcf_payload = store.import_file(VCF_GZ, role="variants", media_type="application/gzip")
            index_payload = store.import_file(TBI, role="index", media_type="application/octet-stream")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"vcf": vcf_payload, "index": index_payload},
                parameters={},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            output = result.output_payloads[0]
            output_path = store.resolve(output)
            if output_path.read_bytes() != SOURCE.read_bytes():
                raise RuntimeError("decompressed VCF differs byte-for-byte from the source fixture")
            summary = parse_vcf_document(output_path, expected_samples=("SAMPLE_A",))
            provenance = result.to_dict()["provenance"]
        fixture = {
            "format": "vcf@4.5",
            "compression": "bgzf",
            "index_type": "tbi",
            "source_sha256": _sha256(SOURCE),
            "vcf_bgzf_sha256": _sha256(VCF_GZ),
            "index_sha256": _sha256(TBI),
            "record_count": 7,
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
            "tested_version_baseline": {"tools": {item.name: environment.tools[item.name] in item.tested_versions for item in manifest.tool_requirements}, "dependencies": {item.name: environment.dependencies[item.name] in item.tested_versions for item in manifest.dependencies}},
            "compatibility_policy": {"tools": {name: list(rules) for name, rules in row.tool_versions.items()}, "dependencies": {name: list(rules) for name, rules in row.dependency_versions.items()}},
            "fixture": fixture,
            "fixture_digest": digest_value(fixture),
            "bundle_integrity": {"vcf_payload_bound": provenance["inputs"]["vcf"]["sha256"] == fixture["vcf_bgzf_sha256"], "tbi_payload_bound": provenance["inputs"]["index"]["sha256"] == fixture["index_sha256"], "byte_exact_roundtrip": provenance["outputs"][0]["sha256"] == fixture["source_sha256"]},
            "execution": {"command_contract_digest": provenance["command_contract_digest"], "executable_sha256": provenance["executable_sha256"], "inputs": provenance["inputs"], "outputs": provenance["outputs"], "parameters": provenance["parameters"]},
            "scientific_summary": summary,
            "html_report_validated": False,
        }
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bgzip-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "vcf-decompress-live-verification.json")
    args = parser.parse_args()
    report = verify(args.bgzip_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "record_count": report["scientific_summary"]["record_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
