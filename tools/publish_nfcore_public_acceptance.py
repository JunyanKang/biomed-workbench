#!/usr/bin/env python3
"""Publish path-neutral acceptance evidence from an observed nf-core run."""

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

from biomed_workbench.implementations.nfcore import (  # noqa: E402
    CLIPSEQ,
    HIC,
    METHYLSEQ,
    NASCENT,
    RIBOSEQ,
    SPECS,
    reload_output,
)
from biomed_workbench.modules.evidence_scope import module_evidence_scope  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"report is not a JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate(raw: dict[str, Any], result_root: Path | None = None) -> tuple[Any, dict[str, Any]]:
    module_id = raw.get("module_id")
    if module_id not in SPECS:
        raise ValueError(f"unsupported nf-core evidence module: {module_id}")
    spec = SPECS[module_id]
    execution = raw.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("raw report has no execution record")
    checksum_bound_case = isinstance(raw.get("public_fixture"), dict)
    official_profile = execution.get("official_public_test_profile") is True
    if (
        raw.get("passed") is not True
        or raw.get("execution_evidence_level") != "observed_scientific_workflow"
        or execution.get("external_workflow_executed") is not True
        or execution.get("outputs_reloaded") is not True
        or not (official_profile or checksum_bound_case)
    ):
        raise ValueError("raw report is not a passing observed public workflow")
    workflow = raw.get("workflow")
    if not isinstance(workflow, dict) or (
        workflow.get("name"),
        workflow.get("revision"),
        workflow.get("revision_commit"),
        workflow.get("official_schema_sha256"),
    ) != (
        spec.pipeline,
        spec.revision,
        spec.revision_commit,
        spec.schema_sha256,
    ):
        raise ValueError("raw report does not match the pinned workflow identity")
    outputs = raw.get("outputs")
    groups = outputs.get("groups") if isinstance(outputs, dict) else None
    if not isinstance(groups, dict):
        raise ValueError("raw report has no reloaded output groups")
    required_by_module = {
        RIBOSEQ.module_id: {"multiqc", "pipeline_info", "ribo_qc", "orf_calls", "quantification"},
        NASCENT.module_id: {"multiqc", "pipeline_info", "coverage", "quantification"},
        CLIPSEQ.module_id: {"multiqc", "pipeline_info", "crosslinks", "clip_qc"},
        METHYLSEQ.module_id: {"multiqc", "pipeline_info", "methylation_calls"},
        HIC.module_id: {"multiqc", "pipeline_info", "valid_pairs", "contact_matrices"},
    }
    required = required_by_module[spec.module_id]
    missing = sorted(
        group
        for group in required
        if not isinstance(groups.get(group), dict) or groups[group].get("file_count", 0) < 1
    )
    if missing:
        raise ValueError("public acceptance is missing scientific output groups: " + ", ".join(missing))
    reloaded = outputs.get("reloaded_files")
    if not isinstance(reloaded, list) or not reloaded:
        raise ValueError("raw report contains no reloaded scientific files")
    if result_root is None:
        result_root_value = outputs.get("result_root")
        if isinstance(result_root_value, str):
            result_root = Path(result_root_value)
    if result_root is None:
        raise ValueError("--result-root is required to re-open observed scientific outputs")
    result_root = result_root.expanduser().resolve()
    if not result_root.is_dir():
        raise ValueError("observed result directory is unavailable at publication time")
    for item in reloaded:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or item["path"].startswith("/")
            or len(str(item.get("sha256", ""))) != 64
            or not item.get("reload")
        ):
            raise ValueError("raw report contains invalid output-reload evidence")
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("raw report contains an unsafe scientific output path")
        observed_path = (result_root / relative).resolve()
        if result_root not in observed_path.parents or not observed_path.is_file():
            raise ValueError(f"observed scientific output is unavailable: {item['path']}")
        observed = reload_output(observed_path)
        for field in ("bytes", "sha256", "reload", "row_count"):
            if field in item and observed.get(field) != item[field]:
                raise ValueError(
                    f"observed scientific output changed before publication: {item['path']} ({field})"
                )
    implementation = raw.get("implementation")
    implementation_path = ROOT / "biomed_workbench" / "implementations" / "nfcore.py"
    if (
        not isinstance(implementation, dict)
        or implementation.get("path") != "biomed_workbench/implementations/nfcore.py"
        or implementation.get("sha256") != _sha256(implementation_path)
    ):
        raise ValueError("raw report does not match the current nf-core executor implementation")
    return spec, groups


def _template_evidence(module_id: str) -> dict[str, dict[str, str]]:
    template_root = BUILTIN_ROOT / module_id / "templates"
    return {
        path.stem: {"name": path.name, "sha256": _sha256(path)}
        for path in sorted(template_root.iterdir())
        if path.is_file()
    }


def _public_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    fixture = raw.get("public_fixture")
    if not isinstance(fixture, dict):
        fixture = raw.get("input", {}).get("public_fixture")
    if not isinstance(fixture, dict):
        raise ValueError("raw report is missing its pinned public fixture ledger")
    downloads = fixture.get("downloads")
    if not isinstance(downloads, list) or not downloads:
        raise ValueError("raw report public fixture has no downloaded source ledger")
    source_files = []
    for item in downloads:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or len(str(item.get("sha256", ""))) != 64
        ):
            raise ValueError("raw report public fixture contains invalid source evidence")
        source_files.append({
            "name": Path(item["path"]).name,
            "source_url": item.get("source_url"),
            "bytes": item.get("bytes"),
            "sha256": item["sha256"],
            "rewritten_to_local_immutable_paths": item.get(
                "rewritten_to_local_immutable_paths",
                False,
            ),
        })
    derived_tools = []
    for item in fixture.get("derived_tools", []):
        if not isinstance(item, dict):
            raise ValueError("raw report public fixture contains invalid derived-tool evidence")
        output = item.get("output", {})
        derived_tools.append({
            "name": item.get("name"),
            "version": item.get("version"),
            "output_name": Path(str(output.get("path", ""))).name,
            "output_bytes": output.get("bytes"),
            "output_sha256": output.get("sha256"),
        })
    return {
        "pipeline_revision": fixture.get("pipeline_revision"),
        "pipeline_commit": fixture.get("pipeline_commit"),
        "test_data_commits": fixture.get("test_data_commits"),
        "official_samplesheet_row_count": fixture.get("official_samplesheet_row_count"),
        "selected_samplesheet_row_count": fixture.get("selected_samplesheet_row_count"),
        "selected_pair_ids": fixture.get("selected_pair_ids", []),
        "selection_policy": fixture.get("selection_policy"),
        "source_file_count": len(source_files),
        "source_files": sorted(source_files, key=lambda item: (str(item["source_url"]), item["name"])),
        "derived_tools": derived_tools,
    }


def build_reports(
    raw: dict[str, Any],
    *,
    result_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec, groups = _validate(raw, result_root)
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    manifest = registry.get(spec.module_id)
    scope = module_evidence_scope(registry, [spec.module_id]).to_dict()
    output_summary = {
        name: {
            "file_count": value["file_count"],
            "paths": value["paths"],
        }
        for name, value in sorted(groups.items())
    }
    reloaded = raw["outputs"]["reloaded_files"]
    runtime = raw.get("runtime", {})
    execution = {
        "assay": raw["assay"],
        "external_workflow_executed": True,
        "outputs_reloaded": True,
        "outputs_reverified_at_publication": True,
        "official_public_test_profile": raw["execution"].get(
            "official_public_test_profile",
            False,
        ),
        "checksum_bound_public_case": isinstance(raw.get("public_fixture"), dict),
        "workflow": {
            "name": spec.pipeline,
            "revision": spec.revision,
            "revision_commit": spec.revision_commit,
            "official_schema_sha256": spec.schema_sha256,
        },
        "scientific_file_count": len(reloaded),
        "output_groups": output_summary,
        "reloaded_files": reloaded,
        "runtime_compatibility": raw.get("runtime_compatibility", []),
    }
    public_source = _public_fixture(raw)
    common = {
        "schema_version": 1,
        "passed": True,
        "assay": raw["assay"],
        "evidence_scope": scope,
        "execution_evidence_level": "observed_scientific_workflow",
        "execution": execution,
        "implementation": raw["implementation"],
        "source": public_source,
        "runtime": {
            "nextflow_version": runtime.get("nextflow_version"),
            "engine_profile": runtime.get("engine_profile"),
            "profile_runtime_version": runtime.get("profile_runtime_version"),
        },
        "quality_gates": {
            "pinned_workflow_identity": True,
            "pinned_official_schema": True,
            "pinned_public_source_commits": True,
            "all_inputs_checksum_bound": True,
            "external_workflow_exit_zero": True,
            "multiqc_reloaded": True,
            "assay_specific_outputs_reloaded": True,
            "scientific_output_checksums_recorded": True,
            "scientific_outputs_reverified_at_publication": True,
        },
        "scientific_boundary": (
            "This is an executable integration and output-reload acceptance on a checksum-bound "
            "representative subset of the pinned official public fixture. The subset retains the "
            "declared replicate and modality structure but does not support a biological project conclusion."
            if public_source.get("selected_pair_ids")
            else "This is an executable integration and output-reload acceptance on the pinned "
            "official minimal public fixture. It is not a biological project conclusion."
        ),
    }
    if raw.get("observed_at"):
        common["observed_at"] = raw["observed_at"]
    live = {
        **common,
        "module_id": spec.module_id,
        "module_version": manifest.version,
        "registry_digest": registry.digest,
        "templates": _template_evidence(spec.module_id),
    }
    public = {
        **common,
        "case_id": raw.get("public_case_id")
        or f"nfcore-{spec.pipeline.split('/')[-1]}-{spec.revision}-official-minimal-v1",
        "case_type": "public-data-end-to-end",
        "module": {"id": spec.module_id, "version": manifest.version},
    }
    return live, public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-report", type=Path, required=True)
    parser.add_argument(
        "--result-root",
        type=Path,
        required=True,
        help="Still-present results directory to re-open before publishing evidence",
    )
    parser.add_argument("--live-report", type=Path)
    parser.add_argument("--public-case", type=Path)
    args = parser.parse_args()
    raw = _load(args.raw_report)
    live, public = build_reports(raw, result_root=args.result_root)
    module_id = str(live["module_id"])
    live_path = args.live_report or ROOT / "reports" / f"{module_id}-live-verification.json"
    public_path = args.public_case or ROOT / "reports" / (
        f"public-case-nfcore-{raw['workflow']['name'].split('/')[-1]}-{raw['workflow']['revision']}.json"
    )
    for path, payload in ((live_path, live), (public_path, public)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "live_report": str(live_path),
        "public_case": str(public_path),
        "scientific_file_count": live["execution"]["scientific_file_count"],
        "passed": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
