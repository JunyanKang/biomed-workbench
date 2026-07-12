#!/usr/bin/env python3
"""Execute and bind regression and end-to-end evidence to compatibility rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.identity import digest_value  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from biomed_workbench.modules.contract import version_is_allowed  # noqa: E402
from biomed_workbench.router import route  # noqa: E402


SERVICE_COVERAGE = {
    "gene-evidence": (("composed_workflow", "gene_evidence_bundle"),),
    "literature-evidence": (("composed_workflow", "literature_evidence_bundle"),),
    "ncbi-fetch": (("fetch", "protein"), ("fetch", "nuccore")),
    "ncbi-info": (("info", "entrez"),),
    "ncbi-link": (("link", "gene_to_protein"),),
    "ncbi-search": (("search", "pubmed"),),
    "ncbi-search-summary": (("search", "pubmed"), ("summary", "pubmed")),
    "ncbi-summary": (("summary", "pubmed"),),
    "variant-evidence": (("composed_workflow", "variant_evidence_bundle"),),
}

COMMAND_EVIDENCE = {
    "alignment-quality-samtools": ("reports/alignment-quality-live-verification.json", "tests.unit.quality.test_alignment"),
    "alignment-sort-index-samtools": ("reports/alignment-sort-live-verification.json", "tests.unit.modules.test_scientific_command"),
    "dna-align-bwa-mem-single": ("reports/bwa-mem-live-verification.json", "tests.unit.quality.test_alignment"),
    "interval-overlap-bedtools": ("reports/interval-overlap-live-verification.json", "tests.unit.quality.test_intervals"),
    "quality-report-multiqc": ("reports/multiqc-live-verification.json", "tests.unit.quality.test_multiqc"),
    "read-contamination-screen": ("reports/fastq-screen-live-verification.json", "tests.unit.quality.test_fastq_screen"),
    "read-quality-fastqc": ("reports/fastqc-live-verification.json", "tests.unit.quality.test_fastqc"),
    "read-quality-fastp": ("reports/fastp-live-verification.json", "tests.unit.quality.test_fastp"),
    "variant-region-query-tabix": ("reports/vcf-region-query-live-verification.json", "tests.unit.quality.test_vcf"),
    "variant-filter-vcf": ("reports/vcf-filter-live-verification.json", "tests.unit.quality.test_vcf_filter"),
    "variant-decompress-bgzip": ("reports/vcf-decompress-live-verification.json", "tests.unit.quality.test_vcf"),
    "tumor-mutation-burden-vcf": ("reports/tmb-vcf-live-verification.json", "tests.unit.quality.test_tmb"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_subset(expected, actual, location="output") -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or not set(expected) <= set(actual):
            raise RuntimeError(f"{location} differs from regression evidence")
        for key, value in expected.items():
            _assert_subset(value, actual[key], f"{location}.{key}")
    elif isinstance(expected, list):
        if actual != expected:
            raise RuntimeError(f"{location} differs from regression evidence")
    elif actual != expected:
        raise RuntimeError(f"{location} differs from regression evidence")


def _service_sources() -> tuple[dict[str, object], set[tuple[str, str]], tuple[str, ...]]:
    reports = [
        json.loads((ROOT / "reports" / "eutils-live-verification.json").read_text(encoding="utf-8")),
        json.loads((ROOT / "reports" / "eutils-live-zero-key-verification.json").read_text(encoding="utf-8")),
    ]
    if not all(report.get("passed") is True for report in reports):
        raise RuntimeError("E-utilities live evidence is not passing")
    coverage = {
        (check["name"], check["database"])
        for report in reports
        for check in report["checks"]
        if check.get("passed") is True
    }
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "tests.contract.test_eutils", "tests.contract.test_service_version_probe"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError("E-utilities contract regression suite failed")
    sources = tuple(
        _sha256(ROOT / path)
        for path in (
            "tests/contract/test_eutils.py",
            "tests/contract/test_service_version_probe.py",
            "reports/eutils-live-verification.json",
            "reports/eutils-live-zero-key-verification.json",
        )
    )
    return {"contract_tests_passed": True, "live_reports_passed": True}, coverage, sources


def capture() -> dict[str, object]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    fixtures = json.loads((ROOT / "tests" / "fixtures" / "offline-capability-cases.json").read_text(encoding="utf-8"))
    service_status, service_coverage, service_sources = _service_sources()
    records = []
    for manifest in registry.all():
        if len(manifest.compatibility_matrix) != 1:
            raise RuntimeError(f"module requires explicit multi-row evidence handling: {manifest.id}")
        row = manifest.compatibility_matrix[0]
        context = {
            "module_id": manifest.id,
            "module_version": manifest.version,
            "row_id": row.id,
            "tool_versions": {key: list(value) for key, value in row.tool_versions.items()},
            "dependency_versions": {key: list(value) for key, value in row.dependency_versions.items()},
            "input_formats": {key: list(value) for key, value in row.input_formats.items()},
            "output_formats": {key: list(value) for key, value in row.output_formats.items()},
        }
        if manifest.execution.kind == "command":
            try:
                report_path, regression_test = COMMAND_EVIDENCE[manifest.id]
            except KeyError:
                raise RuntimeError(f"command execution evidence is not configured: {manifest.id}") from None
            live_report = json.loads((ROOT / report_path).read_text(encoding="utf-8"))
            if (
                live_report.get("passed") is not True
                or live_report.get("module_id") != manifest.id
                or live_report.get("compatibility_row_id") != row.id
                or any(not version_is_allowed(live_report.get("tool_versions", {}).get(key, ""), rules) for key, rules in row.tool_versions.items())
                or any(not version_is_allowed(live_report.get("dependency_versions", {}).get(key, ""), rules) for key, rules in row.dependency_versions.items())
            ):
                raise RuntimeError(f"live command evidence differs from compatibility row: {manifest.id}")
            regression = subprocess.run(
                [sys.executable, "-m", "unittest", regression_test],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            if regression.returncode != 0:
                raise RuntimeError(f"command regression suite failed: {manifest.id}")
            plan = route(manifest.intents[0], registry=registry)
            candidates = [item["id"] for step in plan["steps"] for item in step["candidates"]]
            if manifest.id not in candidates:
                raise RuntimeError(f"command module did not route through the unified entry: {manifest.id}")
            source_digest = _sha256(ROOT / report_path)
            regression_digest = digest_value(
                {**context, "kind": "regression", "source": source_digest, "fixture": live_report["fixture"], "summary": live_report["scientific_summary"]}
            )
            e2e_digest = digest_value(
                {**context, "kind": "end-to-end", "source": source_digest, "execution": live_report["execution"], "html_validated": live_report["html_report_validated"]}
            )
        elif manifest.tool_requirements:
            required = set(SERVICE_COVERAGE[manifest.id])
            if not required <= service_coverage:
                raise RuntimeError(f"live service evidence is incomplete: {manifest.id}")
            regression_digest = digest_value({**context, "kind": "regression", "sources": list(service_sources[:2]), **service_status})
            e2e_digest = digest_value({**context, "kind": "end-to-end", "sources": list(service_sources[2:]), "coverage": sorted(required)})
        else:
            case = fixtures.get(manifest.id)
            if not isinstance(case, dict):
                raise RuntimeError(f"offline regression fixture is missing: {manifest.id}")
            direct = json.loads(json.dumps(registry.resolve_entrypoint(manifest.id)(**case["input"]), sort_keys=True))
            _assert_subset(case["output"], direct)
            regression_digest = digest_value({**context, "kind": "regression", "input": case["input"], "output": direct})
            plan = route(manifest.intents[0], registry=registry)
            candidates = [item["id"] for step in plan["steps"] for item in step["candidates"]]
            if manifest.id not in candidates:
                raise RuntimeError(f"module did not route through the unified entry: {manifest.id}")
            completed = subprocess.run(
                [sys.executable, "tools/run_tool.py", manifest.id, "--input", json.dumps(case["input"], sort_keys=True)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=manifest.execution.timeout_seconds,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"module end-to-end execution failed: {manifest.id}")
            result = json.loads(completed.stdout)
            if result.get("status") != "completed":
                raise RuntimeError(f"module end-to-end status failed: {manifest.id}")
            _assert_subset(case["output"], result["output"])
            e2e_digest = digest_value(
                {**context, "kind": "end-to-end", "objective": plan["objective"], "plan_type": plan["plan_type"], "output": result["output"]}
            )
        if row.regression_evidence_ids != (f"{manifest.id}-regression-v1",):
            raise RuntimeError(f"regression evidence id mismatch: {manifest.id}")
        if row.end_to_end_evidence_ids != (f"{manifest.id}-e2e-v1",):
            raise RuntimeError(f"end-to-end evidence id mismatch: {manifest.id}")
        records.append(
            {
                **context,
                "verified_at": row.verified_at,
                "regression": {"id": row.regression_evidence_ids[0], "passed": True, "digest": regression_digest},
                "end_to_end": {"id": row.end_to_end_evidence_ids[0], "passed": True, "digest": e2e_digest},
            }
        )
    return {
        "schema_version": 1,
        "passed": True,
        "module_count": len(registry.all()),
        "compatibility_row_count": len(records),
        "regression_passed": sum(record["regression"]["passed"] for record in records),
        "end_to_end_passed": sum(record["end_to_end"]["passed"] for record in records),
        "registry_digest": registry.digest,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = capture()
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("module_count", "compatibility_row_count", "regression_passed", "end_to_end_passed")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
