#!/usr/bin/env python3
"""Publish path-neutral evidence from an observed ENCODE ATAC/DNase run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.encode_accessibility import (  # noqa: E402
    CAPER_VERSION,
    PIPELINE_COMMIT,
    PIPELINE_VERSION,
)
from biomed_workbench.modules.evidence_scope import module_evidence_scope  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


MODULE_ID = "bulk-chromatin-accessibility"
IMPLEMENTATION_PATH = "biomed_workbench/implementations/encode_accessibility.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("raw report must be a JSON object")
    return payload


def _basename_records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("source record collection is not an array")
    records: list[dict[str, Any]] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("bytes"), int)
            or len(str(item.get("sha256", ""))) != 64
        ):
            raise ValueError("source record is incomplete")
        records.append({
            "name": Path(item["path"]).name,
            "bytes": item["bytes"],
            "sha256": item["sha256"],
        })
    return records


def _output_records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("output record collection is not an array")
    records: list[dict[str, Any]] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or Path(item["path"]).is_absolute()
            or not isinstance(item.get("bytes"), int)
            or len(str(item.get("sha256", ""))) != 64
        ):
            raise ValueError("output record is not path-neutral or checksum-bound")
        records.append({
            "path": item["path"],
            "bytes": item["bytes"],
            "sha256": item["sha256"],
        })
    return records


def build_reports(
    raw: dict[str, Any],
    *,
    case_id: str,
    accession: str,
    source_url: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    implementation_path = ROOT / IMPLEMENTATION_PATH
    implementation = raw.get("implementation")
    workflow = raw.get("workflow")
    if (
        raw.get("schema_version") != 1
        or raw.get("module_id") != MODULE_ID
        or raw.get("assay") not in {"atac-seq", "dnase-seq"}
        or raw.get("passed") is not True
        or not isinstance(implementation, dict)
        or implementation.get("path") != IMPLEMENTATION_PATH
        or implementation.get("sha256") != _sha256(implementation_path)
        or not isinstance(workflow, dict)
        or workflow.get("version") != PIPELINE_VERSION
        or workflow.get("commit") != PIPELINE_COMMIT
        or workflow.get("caper_version") != CAPER_VERSION
    ):
        raise ValueError("raw report is not a passing current ENCODE accessibility execution")
    reloaded = raw.get("reloaded")
    outputs = raw.get("outputs")
    provenance = raw.get("upstream_bam_provenance")
    if (
        not isinstance(reloaded, dict)
        or int(reloaded.get("qc_json_objects", 0)) < 1
        or int(reloaded.get("qc_html_documents", 0)) < 1
        or int(reloaded.get("peak_intervals", 0)) < 1
        or int(reloaded.get("bigwig_tracks", 0)) < 1
        or not isinstance(outputs, dict)
        or not isinstance(provenance, dict)
    ):
        raise ValueError("raw report has incomplete output-reload evidence")
    output_summary = {
        name: _output_records(outputs.get(name))
        for name in ("metadata", "qc_json", "qc_html", "peaks", "signals")
    }
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    manifest = registry.get(MODULE_ID)
    scope = module_evidence_scope(registry, [MODULE_ID]).to_dict()
    templates = {
        path.name: _sha256(path)
        for path in sorted((BUILTIN_ROOT / MODULE_ID / "templates").iterdir())
        if path.is_file()
    }
    execution = {
        "assay": raw["assay"],
        "external_workflow_executed": True,
        "outputs_reloaded": True,
        "input_mode": raw.get("input_mode"),
        "biological_replicates": len(raw.get("inputs", [])) - 1,
        "parameters": raw.get("parameters"),
        "reloaded": reloaded,
        "outputs": output_summary,
    }
    source = {
        "accession": accession,
        "url": source_url,
        "workflow": workflow,
        "workflow_inputs": _basename_records(raw.get("inputs")),
        "upstream_alignment": {
            "producer": provenance.get("producer"),
            "producer_version": provenance.get("producer_version"),
            "source": provenance.get("source"),
            "parameters": provenance.get("parameters"),
            "source_files": _basename_records(provenance.get("source_files")),
            "quality_files": _basename_records(provenance.get("quality_files")),
        },
    }
    quality_gates = {
        "current_implementation": True,
        "pinned_workflow_identity": True,
        "external_workflow_exit_zero": True,
        "biological_replicates_preserved": execution["biological_replicates"] >= 2,
        "qc_json_reloaded": reloaded["qc_json_objects"] >= 1,
        "qc_html_reloaded": reloaded["qc_html_documents"] >= 1,
        "peak_intervals_reloaded": reloaded["peak_intervals"] >= 1,
        "bigwig_tracks_reloaded": reloaded["bigwig_tracks"] >= 1,
        "input_and_output_checksums_recorded": True,
    }
    common = {
        "schema_version": 1,
        "passed": all(quality_gates.values()),
        "assay": raw["assay"],
        "evidence_scope": scope,
        "execution_evidence_level": "observed_scientific_workflow",
        "observed_at": raw.get("executed_at"),
        "implementation": implementation,
        "execution": execution,
        "source": source,
        "quality_gates": quality_gates,
        "scientific_boundary": raw.get("interpretation_scope"),
    }
    live = {
        **common,
        "module_id": MODULE_ID,
        "module_version": manifest.version,
        "registry_digest": registry.digest,
        "templates": templates,
    }
    public = {
        **common,
        "case_id": case_id,
        "case_type": "public-data-end-to-end",
        "module": {"id": MODULE_ID, "version": manifest.version},
    }
    return live, public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-report", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--accession", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--live-report", type=Path, required=True)
    parser.add_argument("--public-case", type=Path, required=True)
    args = parser.parse_args()
    live, public = build_reports(
        _load(args.raw_report),
        case_id=args.case_id,
        accession=args.accession,
        source_url=args.source_url,
    )
    for path, payload in ((args.live_report, live), (args.public_case, public)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": public["passed"],
        "public_case": str(args.public_case),
        "live_report": str(args.live_report),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
