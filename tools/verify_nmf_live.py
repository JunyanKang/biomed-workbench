#!/usr/bin/env python3
"""Verify stable NMF execution through the scientific command boundary."""

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
from biomed_workbench.quality import parse_nmf_outputs  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "metagene-factorization-nmf" / "module.json"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "omics"
MATRIX = FIXTURE_ROOT / "nmf-matrix.tsv"
FEATURES = FIXTURE_ROOT / "nmf-features.txt"
SAMPLES = FIXTURE_ROOT / "nmf-samples.txt"
COMMAND_PARAMETERS = {
    "ranks": "2,3",
    "restarts": 8,
    "max-iter": 2000,
    "tolerance": 0.00001,
    "top-genes": 3,
    "selection-error-gap": 0.01,
    "minimum-component-stability": 0.95,
    "minimum-assignment-stability": 0.95,
    "maximum-component-similarity": 0.95,
    "seed": 271828,
}
QUALITY_PARAMETERS = {key.replace("-", "_"): value for key, value in COMMAND_PARAMETERS.items()}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        expected = (
            {"python3": "3.14.3"},
            {"numpy": "2.4.4", "scipy": "1.17.1", "scikit-learn": "1.8.0"},
        )
        if (environment.tools, environment.dependencies) != expected:
            raise RuntimeError("numeric runtime differs from the validated NMF compatibility row")
        row = manifest.compatibility_matrix[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ProjectArtifactStore(root / "project")
            input_payloads = {
                "matrix": store.import_file(MATRIX, role="matrix", media_type="text/tab-separated-values"),
                "features": store.import_file(FEATURES, role="features", media_type="text/plain"),
                "samples": store.import_file(SAMPLES, role="observations", media_type="text/plain"),
            }
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads=input_payloads,
                parameters=COMMAND_PARAMETERS,
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            outputs = {payload.role: payload for payload in result.output_payloads}
            summary = parse_nmf_outputs(
                MATRIX,
                FEATURES,
                SAMPLES,
                store.resolve(outputs["loadings"]),
                store.resolve(outputs["exposures"]),
                store.resolve(outputs["report"]),
                expected_parameters=QUALITY_PARAMETERS,
            )
            provenance = result.to_dict()["provenance"]
        fixture = {
            "format": "count-matrix@1.0.0",
            "orientation": "features-by-samples",
            "processing_level": "normalized",
            "feature_identifier_namespace": "synthetic-gene-symbol",
            "experimental_unit": "synthetic-independent-sample",
            "sample_manifest_digest": _sha256(SAMPLES),
            "matrix_sha256": _sha256(MATRIX),
            "features_sha256": _sha256(FEATURES),
            "samples_sha256": _sha256(SAMPLES),
            "parameters": COMMAND_PARAMETERS,
        }
        expected_assignments = {
            "SAMPLE_A1": "Metagene_1",
            "SAMPLE_A2": "Metagene_1",
            "SAMPLE_A3": "Metagene_1",
            "SAMPLE_B1": "Metagene_2",
            "SAMPLE_B2": "Metagene_2",
            "SAMPLE_B3": "Metagene_2",
        }
        if summary["selected_rank"] != 2 or any(summary["dominant_component_by_sample"][sample] != component for sample, component in expected_assignments.items()):
            raise RuntimeError("NMF did not recover the declared synthetic programs")
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
            "fixture_digest": digest_value(fixture),
            "implementation": provenance["implementation"],
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
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "nmf-live-verification.json")
    args = parser.parse_args()
    report = verify(args.python_executable.resolve())
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "selected_rank": report["scientific_summary"]["selected_rank"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
