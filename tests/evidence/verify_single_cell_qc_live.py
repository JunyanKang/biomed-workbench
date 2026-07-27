#!/usr/bin/env python3
"""Generate a deterministic live evidence payload for single-cell QC."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
MODULE_ID = "single-cell-qc"
MODULE_VERSION = "1.0.0"
ROW_ID = "python-3.14.3-inline-json-1"
MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / MODULE_ID
TEMPLATE = MODULE_PATH / "templates" / "run_single_cell_qc.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, environment: dict[str, str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"single-cell-qc template execution failed: {completed.stderr[-2600:]}")
    return completed


def build_request(root: Path) -> tuple[Path, Path, dict[str, object]]:
    request: dict[str, object] = {
        "parameters": {
            "genes": ["MT-ND1", "MT-ND2", "G1", "G2", "G3", "G4", "G5"],
            "cells": ["c1", "c2", "c3", "c4", "c5", "c6"],
            "matrix": [
                [1, 2, 3, 0, 9, 0],
                [2, 0, 3, 10, 0, 9],
                [3, 6, 2, 3, 7, 1],
                [1, 0, 0, 2, 1, 4],
                [0, 5, 4, 0, 6, 0],
                [1, 0, 0, 0, 0, 0],
                [0, 0, 1, 0, 1, 0],
            ],
            "min_counts": 10,
            "min_genes": 3,
            "max_mito_percent": 30,
            "mitochondrial_prefixes": ["MT-"],
        },
        "artifacts": [
            {
                "port": "single_cell_counts",
                "format": "inline-json",
                "format_version": "1",
                "compression": "none",
                "indexes": [],
                "coordinate_system": None,
                "genome_build": None,
                "annotation_release": None,
                "orientation": "request-object",
                "metadata_fields": [],
                "representation": "structured",
                "sort_order": "unsorted",
                "reference_sequence_digest": None,
                "identifier_namespace": None,
                "sample_manifest_digest": None,
                "payload_roles": [],
                "processing_level": "declared",
            }
        ],
    }

    request_path = root / "single_cell_qc_request.json"
    output_path = root / "single_cell_qc_output.json"
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return request_path, output_path, request


def verify(scientific_python: Path) -> dict[str, object]:
    python_executable = scientific_python.expanduser().resolve(strict=True)
    if not python_executable.is_file() or not os.access(python_executable, os.X_OK):
        raise RuntimeError("scientific Python is not executable")

    with TemporaryDirectory(prefix="biomed-qc-live-") as temporary:
        work = Path(temporary)
        request_path, output_path, request = build_request(work)

        environment = {
            "PATH": str(python_executable.parent) + os.pathsep + os.environ.get("PATH", ""),
            "PYTHONHASHSEED": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }

        run(
            [str(python_executable), str(TEMPLATE), "--request", str(request_path), "--output", str(output_path)],
            environment=environment,
            timeout=120,
        )

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        if payload.get("module_id") != MODULE_ID or payload.get("module_version") != MODULE_VERSION:
            raise RuntimeError("module identity mismatch in template output")
        if payload.get("quality_gate_ids") != ["single-cell-qc-validity"]:
            raise RuntimeError("single-cell-qc output must bind the declared quality gate")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("single-cell-qc output result is missing or malformed")
        if not isinstance(result.get("cells"), list) or not result.get("cells"):
            raise RuntimeError("single-cell-qc result does not include per-cell records")
        if result.get("thresholds", {}).get("min_counts") != request["parameters"]["min_counts"]:
            raise RuntimeError("single-cell-qc thresholds in result do not match request")

        requested_cells = request["parameters"]["cells"]
        if {entry.get("cell") for entry in result["cells"]} != set(requested_cells):
            raise RuntimeError("single-cell-qc failed to return all requested cells")
        for entry in result["cells"]:
            if {
                "cell",
                "total_counts",
                "detected_genes",
                "mitochondrial_counts",
                "mitochondrial_percent",
                "flags",
            } - entry.keys():
                raise RuntimeError("single-cell-qc cell record missing required fields")

        c2 = next(entry for entry in result["cells"] if entry["cell"] == "c2")
        if c2["flags"] != []:
            raise RuntimeError("fixture expectation failed: c2 should pass current thresholds")
        if result["flagged_cell_count"] != 5:
            raise RuntimeError("fixture expectation failed: flagged-cell count should be exactly 5")
        if result["flagged_cell_count"] == len(result["cells"]):
            raise RuntimeError("single-cell-qc should flag at least two cells in this fixture")

        return {
            "schema_version": 1,
            "passed": True,
            "registry_digest": hashlib.sha256((ROOT / "biomed_workbench" / "modules" / "index.json").read_bytes()).hexdigest(),
            "module_id": MODULE_ID,
            "module_version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID,
            "templates": {
                "single_cell_qc": {
                    "name": TEMPLATE.name,
                    "sha256": sha256(TEMPLATE),
                }
            },
            "tool_versions": {
                "python": platform.python_version(),
            },
            "dependency_versions": {
                "python": platform.python_version(),
            },
            "fixture": {
                "sha256": sha256(request_path),
                "cells": len(request["parameters"]["cells"]),
                "genes": len(request["parameters"]["genes"]),
            },
            "compatibility_rows": [
                {
                    "id": ROW_ID,
                    "regression_evidence_ids": ["single-cell-qc-regression-v1"],
                    "end_to_end_evidence_ids": ["single-cell-qc-e2e-v1"],
                }
            ],
            "execution": {
                "template_completed": True,
                "result_cells_returned": len(result["cells"]),
                "flagged_cells_detected": int(result.get("flagged_cell_count", 0)),
            },
            "scientific_summary": {
                "qc_thresholds_applied": True,
                "cell_level_qc_flags_retained": True,
                "limitations_declared": len(result.get("limitations", [])) > 0,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = verify(args.scientific_python)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "module_id": MODULE_ID,
                "passed": True,
                "flagged_cells": report["execution"]["flagged_cells_detected"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
