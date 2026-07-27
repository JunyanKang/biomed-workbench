#!/usr/bin/env python3
"""Verify serial VCF filtering and callable-territory TMB calculation."""

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
from biomed_workbench.quality import parse_tmb_report, parse_vcf_filter_outputs  # noqa: E402


MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"
FILTER_PATH = MODULE_ROOT / "variant-filter-vcf" / "module.json"
TMB_PATH = MODULE_ROOT / "tumor-mutation-burden-vcf" / "module.json"
VCF = ROOT / "tests" / "fixtures" / "variants" / "region-query.vcf"
BED = ROOT / "tests" / "fixtures" / "variants" / "callable-targets.bed"
FILTER_PARAMETERS = {
    "minimum-quality": 30.0,
    "minimum-depth": 10,
    "minimum-allele-fraction": 0.05,
    "genes": "*",
    "require-pass": True,
    "missing-metric-policy": "exclude",
}
FILTER_REPORT_PARAMETERS = {
    "minimum_quality": 30.0,
    "minimum_depth": 10,
    "minimum_allele_fraction": 0.05,
    "genes": ["*"],
    "require_pass": True,
    "missing_metric_policy": "exclude",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(executable: Path) -> dict[str, object]:
    filter_manifest = parse_manifest(json.loads(FILTER_PATH.read_text(encoding="utf-8")))
    tmb_manifest = parse_manifest(json.loads(TMB_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        filter_environment = detect_environment(filter_manifest)
        tmb_environment = detect_environment(tmb_manifest)
        expected_environment = ({"python3": "3.14.3"}, {"python-stdlib": "3.14.3"})
        if (filter_environment.tools, filter_environment.dependencies) != expected_environment or (tmb_environment.tools, tmb_environment.dependencies) != expected_environment:
            raise RuntimeError("Python runtime differs from the validated serial compatibility rows")
        filter_row = filter_manifest.compatibility_matrix[0]
        tmb_row = tmb_manifest.compatibility_matrix[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ProjectArtifactStore(root / "project")
            source_payload = store.import_file(VCF, role="variants", media_type="text/vcf")
            filter_result = execute_scientific_command(
                filter_manifest.execution.command,
                store=store,
                input_payloads={"vcf": source_payload},
                parameters=FILTER_PARAMETERS,
                tool_versions=filter_environment.tools,
                dependency_versions=filter_environment.dependencies,
                compatibility_row_id=filter_row.id,
                executable_resolver=lambda _name: executable,
            )
            filter_outputs = {payload.role: payload for payload in filter_result.output_payloads}
            filter_summary = parse_vcf_filter_outputs(
                store.resolve(filter_outputs["variants"]),
                store.resolve(filter_outputs["report"]),
                expected_parameters=FILTER_REPORT_PARAMETERS,
                expected_samples=("SAMPLE_A",),
                expected_input_count=7,
            )
            if filter_summary["accepted_record_keys"] != ["chr1:100:A:G:v1", "chr1:215:G:T:v6"]:
                raise RuntimeError("serial TMB filter stage accepted unexpected variants")
            bed_payload = store.import_file(BED, role="regions", media_type="text/bed")
            tmb_result = execute_scientific_command(
                tmb_manifest.execution.command,
                store=store,
                input_payloads={"vcf": filter_outputs["variants"], "bed": bed_payload},
                parameters={},
                tool_versions=tmb_environment.tools,
                dependency_versions=tmb_environment.dependencies,
                compatibility_row_id=tmb_row.id,
                executable_resolver=lambda _name: executable,
            )
            summary = parse_tmb_report(store.resolve(tmb_result.output_payloads[0]), expected_input_variants=2, expected_input_intervals=3)
            filter_provenance = filter_result.to_dict()["provenance"]
            tmb_provenance = tmb_result.to_dict()["provenance"]
        fixture = {
            "vcf_format": "vcf@4.5",
            "bed_format": "bed@1.0",
            "reference_build": "synthetic-build-1",
            "reference_sequence_digest": hashlib.sha256(b"synthetic-build-1").hexdigest(),
            "sample_manifest_digest": hashlib.sha256(b"SAMPLE_A").hexdigest(),
            "vcf_sha256": _sha256(VCF),
            "bed_sha256": _sha256(BED),
            "filter_parameters": FILTER_REPORT_PARAMETERS,
        }
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": tmb_manifest.id,
            "module_version": tmb_manifest.version,
            "compatibility_row_id": tmb_row.id,
            "regression_evidence_id": tmb_row.regression_evidence_ids[0],
            "end_to_end_evidence_id": tmb_row.end_to_end_evidence_ids[0],
            "tool_versions": tmb_environment.tools,
            "dependency_versions": tmb_environment.dependencies,
            "tested_version_baseline": {"tools": {item.name: tmb_environment.tools[item.name] in item.tested_versions for item in tmb_manifest.tool_requirements}, "dependencies": {item.name: tmb_environment.dependencies[item.name] in item.tested_versions for item in tmb_manifest.dependencies}},
            "compatibility_policy": {"tools": {name: list(rules) for name, rules in tmb_row.tool_versions.items()}, "dependencies": {name: list(rules) for name, rules in tmb_row.dependency_versions.items()}},
            "fixture": fixture,
            "fixture_digest": digest_value(fixture),
            "implementation": tmb_provenance["implementation"],
            "serial_execution": {
                "plan": [filter_manifest.id, tmb_manifest.id],
                "filter": {"row": filter_row.id, "implementation": filter_provenance["implementation"], "inputs": filter_provenance["inputs"], "outputs": filter_provenance["outputs"], "parameters": filter_provenance["parameters"]},
                "tmb": {"row": tmb_row.id, "implementation": tmb_provenance["implementation"], "inputs": tmb_provenance["inputs"], "outputs": tmb_provenance["outputs"], "parameters": tmb_provenance["parameters"]},
            },
            "execution": {"command_contract_digest": tmb_provenance["command_contract_digest"], "executable_sha256": tmb_provenance["executable_sha256"], "inputs": tmb_provenance["inputs"], "outputs": tmb_provenance["outputs"], "parameters": tmb_provenance["parameters"]},
            "scientific_summary": summary,
            "html_report_validated": False,
        }
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "tmb-vcf-live-verification.json")
    args = parser.parse_args()
    report = verify(args.python_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "tmb": report["scientific_summary"]["tmb_mutations_per_mb"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
