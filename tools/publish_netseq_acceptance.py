#!/usr/bin/env python3
"""Publish path-neutral evidence from an observed rdshear NET-seq run."""

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

from biomed_workbench.implementations.netseq import (  # noqa: E402
    CROMWELL_VERSION,
    REQUIRED_OUTPUTS,
    UPSTREAM_COMMIT,
    UPSTREAM_REPOSITORY,
    UPSTREAM_WDL_SHA256,
)
from biomed_workbench.modules.evidence_scope import module_evidence_scope  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


MODULE_ID = "bulk-nascent-transcription"
IMPLEMENTATION_PATH = "biomed_workbench/implementations/netseq.py"
PUBLIC_ACCESSION = "SRR12840066"
PUBLIC_SOURCE_URL = "https://www.ncbi.nlm.nih.gov/sra/SRR12840066"
REFERENCE_URL = "https://hgdownload.soe.ucsc.edu/goldenPath/sacCer3/bigZips/sacCer3.fa.gz"


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


def _validated_outputs(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    outputs = raw.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != set(REQUIRED_OUTPUTS):
        raise ValueError("raw report does not declare the exact NET-seq output set")
    published: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_OUTPUTS:
        item = outputs.get(name)
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError(f"NET-seq output record is incomplete: {name}")
        path = Path(item["path"])
        if (
            not path.is_file()
            or path.stat().st_size != item.get("bytes")
            or _sha256(path) != item.get("sha256")
        ):
            raise ValueError(f"NET-seq output no longer matches its execution record: {name}")
        published[name] = {
            "name": path.name,
            "bytes": item["bytes"],
            "sha256": item["sha256"],
        }
    return published


def build_reports(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    implementation = raw.get("implementation")
    workflow = raw.get("workflow")
    inputs = raw.get("inputs")
    reload_validation = raw.get("reload_validation")
    if (
        raw.get("schema_version") != 1
        or raw.get("module_id") != MODULE_ID
        or raw.get("assay") != "net-seq"
        or raw.get("passed") is not True
        or not isinstance(implementation, dict)
        or implementation.get("path") != IMPLEMENTATION_PATH
        or implementation.get("sha256") != _sha256(ROOT / IMPLEMENTATION_PATH)
        or not isinstance(workflow, dict)
        or workflow.get("repository") != UPSTREAM_REPOSITORY
        or workflow.get("commit") != UPSTREAM_COMMIT
        or workflow.get("upstream_sha256") != UPSTREAM_WDL_SHA256
        or workflow.get("runtime_version") != f"cromwell {CROMWELL_VERSION}"
        or not isinstance(inputs, dict)
        or inputs.get("sra_run_id") != PUBLIC_ACCESSION
        or not isinstance(reload_validation, dict)
    ):
        raise ValueError("raw report is not a passing current NET-seq public execution")
    parameters = raw.get("parameters")
    if (
        not isinstance(parameters, dict)
        or parameters.get("genome_name") != "sacCer3"
        or parameters.get("max_read_count") != 10000
        or parameters.get("umi_width") != 6
    ):
        raise ValueError("public NET-seq parameters do not match the reviewed official profile")
    reference = inputs.get("reference_fasta")
    if not isinstance(reference, dict) or len(str(reference.get("sha256", ""))) != 64:
        raise ValueError("reference FASTA is not checksum-bound")
    outputs = _validated_outputs(raw)
    rows = reload_validation.get("bedgraph_rows")
    gates = {
        "current_implementation": True,
        "pinned_upstream_commit_and_wdl": True,
        "digest_pinned_container": "@sha256:" in str(workflow.get("container_image", "")),
        "official_sra_case_processed": reload_validation.get("fastp_reads_before_filtering") == 10000,
        "external_workflow_exit_zero": True,
        "bam_reloaded": reload_validation.get("bam_reloaded") is True,
        "strand_bedgraphs_reloaded": isinstance(rows, dict)
        and int(rows.get("bedgraph_pos", 0)) + int(rows.get("bedgraph_neg", 0)) > 0,
        "fastp_reports_reloaded": reload_validation.get("fastp_json_reloaded") is True
        and reload_validation.get("fastp_html_reloaded") is True,
        "star_log_reloaded": int(reload_validation.get("star_input_reads", 0)) > 0,
        "input_and_output_checksums_recorded": True,
    }
    if not all(gates.values()):
        raise ValueError("NET-seq acceptance gates are incomplete")
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    manifest = registry.get(MODULE_ID)
    scope = module_evidence_scope(registry, [MODULE_ID]).to_dict()
    templates = {
        path.name: _sha256(path)
        for path in sorted((BUILTIN_ROOT / MODULE_ID / "templates").iterdir())
        if path.is_file()
    }
    execution = {
        "assay": "net-seq",
        "external_workflow_executed": True,
        "outputs_reloaded": True,
        "parameters": parameters,
        "reload_validation": reload_validation,
        "outputs": outputs,
    }
    source = {
        "accession": PUBLIC_ACCESSION,
        "url": PUBLIC_SOURCE_URL,
        "selection": "first 10,000 reads through the workflow's official maxReadCount parameter",
        "reference": {
            "assembly": "sacCer3",
            "url": REFERENCE_URL,
            "bytes": reference.get("bytes"),
            "sha256": reference.get("sha256"),
        },
        "workflow": workflow,
    }
    common = {
        "schema_version": 1,
        "passed": True,
        "assay": "net-seq",
        "evidence_scope": scope,
        "execution_evidence_level": "observed_scientific_workflow",
        "observed_at": raw.get("executed_at"),
        "implementation": implementation,
        "execution": execution,
        "source": source,
        "quality_gates": gates,
        "scientific_scope": (
            "This acceptance confirms the complete public-read execution path and reloadable NET-seq "
            "deliverables; full project inference uses complete biological replicates and study-specific design."
        ),
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
        "case_id": "netseq-rdshear-srr12840066-saccer3-first10000-v1",
        "case_type": "public-data-end-to-end",
        "module": {"id": MODULE_ID, "version": manifest.version},
    }
    return live, public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-report", type=Path, required=True)
    parser.add_argument("--live-report", type=Path, required=True)
    parser.add_argument("--public-case", type=Path, required=True)
    args = parser.parse_args()
    live, public = build_reports(_load(args.raw_report))
    for path, payload in ((args.live_report, live), (args.public_case, public)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "live_report": str(args.live_report), "public_case": str(args.public_case)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
