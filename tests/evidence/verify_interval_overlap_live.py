#!/usr/bin/env python3
"""Run bedtools intersect through the versioned scientific command contract."""

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
from biomed_workbench.quality import parse_bedtools_intersect_report  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "interval-overlap-bedtools" / "module.json"
QUERY = "chr1\t10\t20\tq1\nchr1\t30\t40\tq2\nchr2\t0\t10\tq3\n"
REFERENCE = "chr1\t15\t18\tr1\nchr1\t18\t35\tr2\nchr2\t10\t20\tr3\n"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        row = manifest.compatibility_matrix[0]
        if environment.tools != {"bedtools": "2.31.1"} or environment.dependencies != {"xz": "5.8.3"}:
            raise RuntimeError("bedtools runtime differs from the validated compatibility row")
        fixture = {
            "schema_version": 1,
            "format": "bed@1.0",
            "bed_field_count": 4,
            "coordinate_system": "zero-based-half-open",
            "reference_build": "synthetic-build-1",
            "reference_sequence_digest": hashlib.sha256(b"synthetic-build-1").hexdigest(),
            "query_sha256": _sha256_text(QUERY),
            "reference_sha256": _sha256_text(REFERENCE),
            "query_interval_count": 3,
            "reference_interval_count": 3,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            query = root / "query.bed"
            reference = root / "reference.bed"
            query.write_text(QUERY, encoding="utf-8")
            reference.write_text(REFERENCE, encoding="utf-8")
            store = ProjectArtifactStore(root / "project")
            query_payload = store.import_file(query, role="query", media_type="text/bed")
            reference_payload = store.import_file(reference, role="reference", media_type="text/bed")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"query": query_payload, "reference": reference_payload},
                parameters={},
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            output = result.output_payloads[0]
            output_path = store.resolve(output)
            summary = parse_bedtools_intersect_report(output_path, query_columns=4, reference_columns=4)
            query_rows = {tuple(line.split("\t")) for line in QUERY.splitlines()}
            reference_rows = {tuple(line.split("\t")) for line in REFERENCE.splitlines()}
            for line in output_path.read_text(encoding="utf-8").splitlines():
                fields = tuple(line.split("\t"))
                if fields[:4] not in query_rows or fields[4:] not in reference_rows:
                    raise RuntimeError("bedtools output contains an interval absent from source fixtures")
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
            "fixture": fixture,
            "fixture_digest": digest_value(fixture),
            "source_reconciliation_passed": True,
            "execution": {"command_contract_digest": provenance["command_contract_digest"], "executable_sha256": provenance["executable_sha256"], "inputs": provenance["inputs"], "outputs": provenance["outputs"], "parameters": provenance["parameters"]},
            "scientific_summary": summary,
            "html_report_validated": False,
        }
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bedtools-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "interval-overlap-live-verification.json")
    args = parser.parse_args()
    report = verify(args.bedtools_executable.expanduser().resolve(strict=True))
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": report["module_id"], "passed": report["passed"], "overlap_pair_count": report["scientific_summary"]["overlap_pair_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
