#!/usr/bin/env python3
"""Run strict VCF filtering through the digest-bound project implementation contract."""

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
from biomed_workbench.kernel.identity import digest_value  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.scientific_command import execute_scientific_command  # noqa: E402
from biomed_workbench.quality import parse_vcf_filter_outputs  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "variant-filter-vcf" / "module.json"
FIXTURE = ROOT / "tests" / "fixtures" / "variants" / "region-query.vcf"
PARAMETERS = {
    "minimum-quality": 30.0,
    "minimum-depth": 10,
    "minimum-allele-fraction": 0.05,
    "genes": "GENE1",
    "require-pass": True,
    "missing-metric-policy": "exclude",
}
REPORT_PARAMETERS = {
    "minimum_quality": 30.0,
    "minimum_depth": 10,
    "minimum_allele_fraction": 0.05,
    "genes": ["GENE1"],
    "require_pass": True,
    "missing_metric_policy": "exclude",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        if environment.tools != {"python3": "3.14.3"} or environment.dependencies != {"python-stdlib": "3.14.3"}:
            raise RuntimeError("Python runtime differs from the validated compatibility row")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ProjectArtifactStore(root / "project")
            vcf_payload = store.import_file(FIXTURE, role="variants", media_type="text/vcf")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"vcf": vcf_payload},
                parameters=PARAMETERS,
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            outputs = {payload.role: payload for payload in result.output_payloads}
            summary = parse_vcf_filter_outputs(
                store.resolve(outputs["variants"]),
                store.resolve(outputs["report"]),
                expected_parameters=REPORT_PARAMETERS,
                expected_samples=("SAMPLE_A",),
                expected_input_count=7,
            )
            output_records = [line for line in store.resolve(outputs["variants"]).read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
            source_records = [line for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
            expected_records = [line for line in source_records if line.startswith("chr1\t100\t")]
            if output_records != expected_records:
                raise RuntimeError("filtered VCF does not reconcile with the expected source record")
            provenance = result.to_dict()["provenance"]
        fixture = {
            "format": "vcf@4.5",
            "coordinate_system": "one-based-inclusive",
            "reference_build": "synthetic-build-1",
            "reference_sequence_digest": hashlib.sha256(b"synthetic-build-1").hexdigest(),
            "sample_manifest_digest": hashlib.sha256(b"SAMPLE_A").hexdigest(),
            "vcf_sha256": _sha256(FIXTURE),
            "record_count": len(source_records),
            "parameters": REPORT_PARAMETERS,
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
            "implementation": provenance["implementation"],
            "execution": {"command_contract_digest": provenance["command_contract_digest"], "executable_sha256": provenance["executable_sha256"], "inputs": provenance["inputs"], "outputs": provenance["outputs"], "parameters": provenance["parameters"]},
            "source_reconciliation_passed": True,
            "scientific_summary": summary,
            "html_report_validated": False,
        }
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "vcf-filter-live-verification.json")
    args = parser.parse_args()
    report = verify(args.python_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "accepted": report["scientific_summary"]["accepted_record_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
