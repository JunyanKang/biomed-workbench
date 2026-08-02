#!/usr/bin/env python3
"""Publish path-neutral evidence from an observed official RIPSeeker PRC2 run."""

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

from biomed_workbench.implementations.ripseeker import (  # noqa: E402
    RIPSEEKER_COMMIT,
    RIPSEEKER_SOURCE,
    RIPSEEKER_VERSION,
)
from biomed_workbench.modules.evidence_scope import module_evidence_scope  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


MODULE_ID = "bulk-rbp-rna-binding"
IMPLEMENTATION_PATH = "biomed_workbench/implementations/ripseeker.py"
TEMPLATE_ROOT = BUILTIN_ROOT / MODULE_ID / "templates"
OFFICIAL_CASE = {
    "SRR039210": {
        "group": "rip",
        "bam_sha256": "9b7115f4a0ba9c7e223f3176b5b595cb7686bd13aa57f6f702d3685ddacec3ce",
        "bai_sha256": "d1f1d06e8708987765911ad23f266e0c6e6f9bfc44a824765731b85ffcfa39e3",
    },
    "SRR039211": {
        "group": "rip",
        "bam_sha256": "f69eb78696d8087c1b86514efadb1dca54958d3e8ddf44d11f0071425dd52d9c",
        "bai_sha256": "949c3a476d00af4ade642c6437f954c6f816a2dec2b720e5fe124d4286387ff7",
    },
    "SRR039214": {
        "group": "control",
        "bam_sha256": "b2a0923606f7d96facc4ddc2050ffe4573608502a82245c17ffc523d7274b7f6",
        "bai_sha256": "27e84d4569a0c27f4b325774903367d099b6312b92325bd51a65768d1c884d9f",
    },
}


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("raw report must be a JSON object")
    return payload


def _validated_inputs(raw: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = raw.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != len(OFFICIAL_CASE):
        raise ValueError("official RIPSeeker case must contain two RIP BAMs and one control BAM")
    published: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("RIPSeeker input record is incomplete")
        accession = next((value for value in OFFICIAL_CASE if value in item["path"]), None)
        expected = OFFICIAL_CASE.get(accession or "")
        index = item.get("index")
        if (
            accession is None
            or accession in seen
            or expected is None
            or item.get("group") != expected["group"]
            or item.get("sha256") != expected["bam_sha256"]
            or not isinstance(item.get("bytes"), int)
            or not isinstance(index, dict)
            or index.get("sha256") != expected["bai_sha256"]
            or not isinstance(index.get("bytes"), int)
        ):
            raise ValueError("RIPSeeker input does not match the checksum-bound official PRC2 case")
        seen.add(accession)
        published.append({
            "accession": accession,
            "group": item["group"],
            "bam": {"name": Path(item["path"]).name, "bytes": item["bytes"], "sha256": item["sha256"]},
            "index": {"name": Path(str(index.get("path"))).name, "bytes": index["bytes"], "sha256": index["sha256"]},
        })
    return sorted(published, key=lambda item: item["accession"])


def _validated_outputs(raw: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    outputs = raw.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError("RIPSeeker output records are missing")
    published: dict[str, Any] = {}
    for group in ("regions", "models"):
        records = outputs.get(group)
        if not isinstance(records, list) or not records:
            raise ValueError(f"RIPSeeker {group} records are missing")
        published[group] = []
        for item in records:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or Path(item["path"]).is_absolute():
                raise ValueError(f"RIPSeeker {group} output is not path-neutral")
            path = run_dir / item["path"]
            if not path.is_file() or path.stat().st_size != item.get("bytes") or _sha256(path) != item.get("sha256"):
                raise ValueError(f"RIPSeeker {group} output no longer matches the execution record")
            published[group].append({"name": path.name, "bytes": item["bytes"], "sha256": item["sha256"]})
    for name in ("result_rds", "reload_validation"):
        item = outputs.get(name)
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or Path(item["path"]).is_absolute():
            raise ValueError(f"RIPSeeker {name} output is missing")
        path = run_dir / item["path"]
        if not path.is_file() or path.stat().st_size != item.get("bytes") or _sha256(path) != item.get("sha256"):
            raise ValueError(f"RIPSeeker {name} output no longer matches the execution record")
        published[name] = {"name": path.name, "bytes": item["bytes"], "sha256": item["sha256"]}
    return published


def build_reports(
    raw: dict[str, Any],
    run_dir: Path,
    reproducibility_raw: dict[str, Any],
    reproducibility_run_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    implementation = raw.get("implementation")
    workflow = raw.get("workflow")
    validation = raw.get("validation")
    if (
        raw.get("schema_version") != 1
        or raw.get("module_id") != MODULE_ID
        or raw.get("assay") != "rip-seq"
        or raw.get("passed") is not True
        or not isinstance(implementation, dict)
        or implementation.get("path") != IMPLEMENTATION_PATH
        or implementation.get("sha256") != _sha256(ROOT / IMPLEMENTATION_PATH)
        or not isinstance(workflow, dict)
        or workflow.get("name") != "RIPSeeker"
        or workflow.get("version") != RIPSEEKER_VERSION
        or workflow.get("commit") != RIPSEEKER_COMMIT
        or workflow.get("source") != RIPSEEKER_SOURCE
        or workflow.get("bioconductor_release") != "3.11"
        or "@sha256:" not in str(workflow.get("container_identity", ""))
        or not isinstance(validation, dict)
        or validation.get("reload_passed") is not True
        or int(validation.get("total_region_rows", 0)) < 1
        or not validation.get("model_files")
    ):
        raise ValueError("raw report is not a passing current RIPSeeker public execution")
    build = workflow.get("container_build")
    if not isinstance(build, dict):
        raise ValueError("RIPSeeker container build provenance is missing")
    for name in ("dockerfile", "compatibility_patch"):
        item = build.get(name)
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError(f"RIPSeeker {name} provenance is missing")
        path = ROOT / item["path"]
        if not path.is_file() or _sha256(path) != item.get("sha256"):
            raise ValueError(f"RIPSeeker {name} provenance is stale")
    inputs = _validated_inputs(raw)
    outputs = _validated_outputs(raw, run_dir)
    reproducibility_outputs = _validated_outputs(reproducibility_raw, reproducibility_run_dir)
    if (
        reproducibility_raw.get("passed") is not True
        or reproducibility_raw.get("implementation") != implementation
        or reproducibility_raw.get("workflow") != workflow
        or reproducibility_raw.get("parameters") != raw.get("parameters")
        or reproducibility_raw.get("validation") != validation
        or reproducibility_outputs != outputs
    ):
        raise ValueError("independent fixed-seed RIPSeeker executions are not byte-identical")
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    manifest = registry.get(MODULE_ID)
    scope = module_evidence_scope(registry, [MODULE_ID]).to_dict()
    templates = {path.name: _sha256(path) for path in sorted(TEMPLATE_ROOT.iterdir()) if path.is_file()}
    gates = {
        "current_implementation": True,
        "official_commit_and_version_pinned": True,
        "bioconductor_release_pinned": True,
        "container_digest_recorded": True,
        "compatibility_patch_checksum_recorded": True,
        "official_prc2_inputs_checksum_bound": len(inputs) == 3,
        "two_rip_and_one_control_preserved": [item["group"] for item in inputs].count("rip") == 2
        and [item["group"] for item in inputs].count("control") == 1,
        "external_hmm_execution_exit_zero": True,
        "enrichment_regions_nonempty": int(validation["total_region_rows"]) > 0,
        "rdata_model_reloaded": all(int(item.get("object_count", 0)) > 0 for item in validation["model_files"]),
        "rds_result_reloaded": validation.get("result_rds", {}).get("length", 0) > 0,
        "fixed_seed_repeat_is_byte_identical": True,
        "input_and_output_checksums_recorded": True,
    }
    if not all(gates.values()):
        raise ValueError("RIPSeeker acceptance gates are incomplete")
    execution = {
        "assay": "rip-seq",
        "external_workflow_executed": True,
        "outputs_reloaded": True,
        "parameters": raw.get("parameters"),
        "validation": validation,
        "outputs": outputs,
        "reproducibility": {
            "seed": raw.get("parameters", {}).get("seed"),
            "independent_executions": 2,
            "region_model_and_rds_outputs_byte_identical": True,
        },
    }
    source = {
        "package_example": "RIPSeeker inst/extdata/PRC2",
        "package_source": RIPSEEKER_SOURCE,
        "package_commit": RIPSEEKER_COMMIT,
        "sra_runs": [
            {"accession": item["accession"], "url": f"https://www.ncbi.nlm.nih.gov/sra/{item['accession']}", "group": item["group"]}
            for item in inputs
        ],
        "inputs": inputs,
        "workflow": workflow,
    }
    common = {
        "schema_version": 1,
        "passed": True,
        "assay": "rip-seq",
        "evidence_scope": scope,
        "execution_evidence_level": "observed_scientific_workflow",
        "observed_at": raw.get("executed_at"),
        "implementation": implementation,
        "execution": execution,
        "source": source,
        "quality_gates": gates,
        "scientific_scope": raw.get("interpretation_scope"),
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
        "case_id": "ripseeker-prc2-official-chrx-v1",
        "case_type": "official-package-data-end-to-end",
        "module": {"id": MODULE_ID, "version": manifest.version},
    }
    return live, public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-report", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--repro-report", type=Path, required=True)
    parser.add_argument("--repro-run-dir", type=Path, required=True)
    parser.add_argument("--live-report", type=Path, required=True)
    parser.add_argument("--public-case", type=Path, required=True)
    args = parser.parse_args()
    live, public = build_reports(
        _load(args.raw_report),
        args.run_dir,
        _load(args.repro_report),
        args.repro_run_dir,
    )
    for path, payload in ((args.live_report, live), (args.public_case, public)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "live_report": str(args.live_report), "public_case": str(args.public_case)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
