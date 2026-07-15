#!/usr/bin/env python3
"""Execute and bind regression and end-to-end evidence to compatibility rows."""

from __future__ import annotations

import argparse
import hashlib
import inspect
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
    "alphafold-structure-evidence": (("structure_prediction_metadata", "alphafold-db"),),
    "chemical-evidence": (("compound_identity", "pubchem"),),
    "citation-record-resolution": (("citation_record_resolution", "crossref-europe-pmc"),),
    "clinical-trial-evidence": (("trial_design_record", "clinicaltrials-gov"),),
    "gene-evidence": (("composed_workflow", "gene_evidence_bundle"),),
    "literature-evidence": (("composed_workflow", "literature_evidence_bundle"),),
    "ncbi-fetch": (("fetch", "protein"), ("fetch", "nuccore")),
    "ncbi-info": (("info", "entrez"),),
    "ncbi-link": (("link", "gene_to_protein"),),
    "ncbi-search": (("search", "pubmed"),),
    "ncbi-search-summary": (("search", "pubmed"), ("summary", "pubmed")),
    "ncbi-summary": (("summary", "pubmed"),),
    "preprint-evidence": (("preprint_version_history", "biorxiv"),),
    "structure-evidence": (("structure_entry_context", "rcsb-pdb"),),
    "structure-search": (("structure_attribute_search", "rcsb-pdb-search"),),
    "structure-polymer-entities": (("structure_polymer_entities", "rcsb-pdb"),),
    "structure-ligands": (("structure_bound_ligands", "rcsb-pdb"),),
    "variant-evidence": (("composed_workflow", "variant_evidence_bundle"),),
}

COMMAND_EVIDENCE = {
    "alignment-quality-samtools": ("reports/alignment-quality-live-verification.json", "tests.unit.quality.test_alignment"),
    "alignment-sort-index-samtools": ("reports/alignment-sort-live-verification.json", "tests.unit.modules.test_scientific_command"),
    "dna-align-bwa-mem-single": ("reports/bwa-mem-live-verification.json", "tests.unit.quality.test_alignment"),
    "interval-overlap-bedtools": ("reports/interval-overlap-live-verification.json", "tests.unit.quality.test_intervals"),
    "image-chroma-key-remove": ("reports/chroma-key-live-verification.json", "tests.unit.quality.test_chroma_key"),
    "metagene-factorization-nmf": ("reports/nmf-live-verification.json", "tests.unit.quality.test_nmf"),
    "quality-report-multiqc": ("reports/multiqc-live-verification.json", "tests.unit.quality.test_multiqc"),
    "read-contamination-screen": ("reports/fastq-screen-live-verification.json", "tests.unit.quality.test_fastq_screen"),
    "read-quality-fastqc": ("reports/fastqc-live-verification.json", "tests.unit.quality.test_fastqc"),
    "read-quality-fastp": ("reports/fastp-live-verification.json", "tests.unit.quality.test_fastp"),
    "variant-region-query-tabix": ("reports/vcf-region-query-live-verification.json", "tests.unit.quality.test_vcf"),
    "variant-filter-vcf": ("reports/vcf-filter-live-verification.json", "tests.unit.quality.test_vcf_filter"),
    "variant-decompress-bgzip": ("reports/vcf-decompress-live-verification.json", "tests.unit.quality.test_vcf"),
    "tumor-mutation-burden-vcf": ("reports/tmb-vcf-live-verification.json", "tests.unit.quality.test_tmb"),
}

AGENT_EVIDENCE = {
    "chemical-substructure-filter": {
        "path": "reports/chemical-substructure-filter-live-verification.json",
        "execution_flags": ("template_completed", "outputs_reloaded"),
        "summary_flags": ("all_records_accounted", "invalid_molecule_retained", "include_and_exclude_smarts_executed"),
        "live_dependency_keys": ("python",),
    },
    "docking-pose-review": {
        "path": "reports/docking-pose-review-live-verification.json",
        "execution_flags": ("template_completed", "outputs_reloaded"),
        "summary_flags": ("all_pose_files_accounted", "invalid_sdf_retained", "confidence_not_affinity", "receptor_clashes_computed"),
        "live_dependency_keys": ("python",),
    },
    "protein-secondary-structure": {
        "path": "reports/protein-secondary-structure-live-verification.json",
        "execution_flags": ("template_completed", "outputs_reloaded"),
        "summary_flags": ("mkdssp_executed", "dssp_resources_digested", "full_dssp_alphabet_retained", "residue_accounting_reconciled"),
        "live_dependency_keys": ("python",),
    },
    "single-cell-communication": {
        "path": "reports/single-cell-communication-live-verification.json",
        "execution_flags": ("liana_completed", "cellphonedb_completed", "cellchat_completed", "nichenet_completed"),
        "summary_flags": ("all_four_backends_executed", "biological_samples_used_as_replicates", "cells_not_used_as_condition_replicates", "method_specific_results_retained", "cross_sample_support_computed", "nichenet_receiver_evidence_used", "source_counts_and_identifiers_preserved", "outputs_reloaded", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": (),
    },
    "single-cell-foundation-workflow": {
        "path": "reports/single-cell-foundation-live-verification.json",
        "execution_flags": ("scanpy_completed", "seurat_completed"),
        "summary_flags": ("scanpy_and_seurat_backends_passed",),
        "live_dependency_keys": (),
    },
    "single-cell-donor-inference": {
        "path": "reports/single-cell-donor-inference-live-verification.json",
        "execution_flags": ("aggregation_completed", "edger_completed", "deseq2_completed", "limma_voom_completed"),
        "summary_flags": ("edger_deseq2_limma_voom_passed", "global_bh_independently_recomputed", "planted_effect_direction_recovered_by_all_engines"),
        "live_dependency_keys": ("anndata", "numpy", "pandas", "scipy", "r", "jsonlite", "digest"),
    },
    "single-cell-batch-integration": {
        "path": "reports/single-cell-batch-integration-live-verification.json",
        "execution_flags": ("harmony_completed", "scanorama_completed", "bbknn_completed"),
        "summary_flags": ("harmony_scanorama_bbknn_executed", "one_frozen_baseline_used", "labels_used_only_for_posthoc_evaluation", "unknown_cells_retained", "raw_counts_preserved", "biological_conservation_gates_passed", "eligible_method_selected_without_umap_scoring"),
        "live_dependency_keys": ("anndata", "numpy", "pandas", "scipy", "scikit-learn", "umap-learn"),
    },
    "single-cell-generative-modeling": {
        "path": "reports/single-cell-generative-modeling-live-verification.json",
        "execution_flags": ("scvi_completed", "scanvi_completed"),
        "summary_flags": ("scvi_and_scanvi_trained", "models_and_h5ad_reloaded", "raw_counts_preserved", "reviewed_and_unknown_labels_preserved", "scanvi_evaluated_on_hidden_labels", "scanvi_predictions_are_reviewable_suggestions", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("anndata", "numpy", "pandas", "scipy", "scikit-learn", "torch", "lightning"),
    },
    "single-cell-reference-annotation": {
        "path": "reports/single-cell-reference-annotation-live-verification.json",
        "execution_flags": ("singler_completed",),
        "summary_flags": ("singler_reference_mapping_executed", "marker_contracts_applied", "ontology_ancestor_constraints_applied", "unknown_population_retained", "existing_labels_and_raw_counts_preserved", "evaluation_labels_posthoc_only", "annotated_h5ad_reloaded", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("anndata", "numpy", "pandas", "scipy", "scikit-learn", "r", "Matrix", "BiocParallel", "jsonlite"),
    },
    "single-cell-trajectory-velocity": {
        "path": "reports/single-cell-trajectory-velocity-live-verification.json",
        "execution_flags": ("dynamical_model_completed", "velocity_graph_completed"),
        "summary_flags": ("spliced_unspliced_layers_validated", "dynamical_rna_velocity_executed", "velocity_graph_and_pseudotime_executed", "latent_time_direction_validated_against_known_time", "root_and_terminal_direction_validated", "experimental_time_withheld_from_model_fitting", "source_counts_and_identifiers_preserved", "velocity_h5ad_reloaded", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("anndata", "numpy", "pandas", "scipy", "scikit-learn", "numba", "umap-learn"),
    },
    "structure-chain-comparison": {
        "path": "reports/structure-chain-comparison-live-verification.json",
        "execution_flags": ("template_completed", "outputs_reloaded"),
        "summary_flags": ("chain_mapping_explicit", "sequence_correspondence_used", "rigid_transform_recovered", "tm_score_not_fabricated"),
        "live_dependency_keys": ("python",),
    },
    "structure-interactive-visualization": {
        "path": "reports/structure-interactive-visualization-live-verification.json",
        "execution_flags": ("template_completed", "outputs_reloaded"),
        "summary_flags": ("html_nonblank", "plddt_provenance_explicit", "selected_chains_explicit", "rendering_not_analysis"),
        "live_dependency_keys": ("python",),
    },
    "structure-quality-assessment": {
        "path": "reports/structure-quality-assessment-live-verification.json",
        "execution_flags": ("template_completed", "outputs_reloaded"),
        "summary_flags": ("plddt_semantics_explicit", "coordinate_accounting_reconciled", "confidence_range_validated"),
        "live_dependency_keys": ("python",),
    },
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
        json.loads((ROOT / "reports" / "public-database-live-verification.json").read_text(encoding="utf-8")),
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
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.contract.test_eutils",
            "tests.contract.test_service_version_probe",
            "tests.unit.test_public_databases",
        ],
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
            "reports/public-database-live-verification.json",
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
            if manifest.id != "single-cell-communication" or manifest.agent_protocol is None:
                raise RuntimeError(f"module requires explicit multi-row evidence handling: {manifest.id}")
            case = fixtures.get(manifest.id)
            if not isinstance(case, dict):
                packaged_cases = json.loads((BUILTIN_ROOT / manifest.id / "tests" / "cases.json").read_text(encoding="utf-8"))
                first_case = packaged_cases.get("cases", [None])[0]
                if not isinstance(first_case, dict):
                    raise RuntimeError(f"agent-generated regression fixture is missing: {manifest.id}")
                case = {"input": first_case["input"], "output": first_case["expected_subset"]}
            entrypoint = registry.resolve_entrypoint(manifest.id)
            implementation_path = Path(inspect.getsourcefile(entrypoint) or "").resolve()
            try:
                implementation_path.relative_to(ROOT.resolve())
            except ValueError as exc:
                raise RuntimeError(f"module implementation is outside the independent project: {manifest.id}") from exc
            direct = json.loads(json.dumps(entrypoint(**case["input"]), sort_keys=True))
            _assert_subset(case["output"], direct)
            evidence_config = AGENT_EVIDENCE[manifest.id]
            report_path = ROOT / evidence_config["path"]
            live_report = json.loads(report_path.read_text(encoding="utf-8"))
            template_hashes = {
                path.name: _sha256(path)
                for path in sorted((BUILTIN_ROOT / manifest.id / "templates").iterdir())
                if path.is_file()
            }
            observed_templates = {item["name"]: item["sha256"] for item in live_report.get("templates", {}).values()}
            expected_rows = [
                {
                    "id": item.id,
                    "regression_evidence_ids": list(item.regression_evidence_ids),
                    "end_to_end_evidence_ids": list(item.end_to_end_evidence_ids),
                }
                for item in manifest.compatibility_matrix
            ]
            if (
                live_report.get("passed") is not True
                or live_report.get("module_id") != manifest.id
                or live_report.get("module_version") != manifest.version
                or live_report.get("registry_digest") != registry.digest
                or live_report.get("compatibility_rows") != expected_rows
                or observed_templates != template_hashes
                or any(live_report.get("execution", {}).get(flag) is not True for flag in evidence_config["execution_flags"])
                or any(live_report.get("scientific_summary", {}).get(flag) is not True for flag in evidence_config["summary_flags"])
            ):
                raise RuntimeError(f"multi-row agent execution evidence differs from module contract: {manifest.id}")
            plan = route(manifest.intents[0], registry=registry)
            candidates = [item["id"] for step in plan["steps"] for item in step["candidates"]]
            if manifest.id not in candidates:
                raise RuntimeError(f"agent-generated module did not route through the unified entry: {manifest.id}")
            for row in manifest.compatibility_matrix:
                if any(not version_is_allowed(live_report.get("versions", {}).get(key, ""), rules) for key, rules in row.tool_versions.items()):
                    raise RuntimeError(f"multi-row live tool versions differ from compatibility row: {row.id}")
                context = {
                    "module_id": manifest.id,
                    "module_version": manifest.version,
                    "row_id": row.id,
                    "tool_versions": {key: list(value) for key, value in row.tool_versions.items()},
                    "dependency_versions": {key: list(value) for key, value in row.dependency_versions.items()},
                    "input_formats": {key: list(value) for key, value in row.input_formats.items()},
                    "output_formats": {key: list(value) for key, value in row.output_formats.items()},
                    "implementation_sha256": _sha256(implementation_path),
                }
                regression_digest = digest_value({**context, "kind": "regression", "input": case["input"], "handoff": direct, "templates": template_hashes})
                e2e_digest = digest_value({**context, "kind": "end-to-end", "live_report_sha256": _sha256(report_path), "execution": live_report["execution"], "scientific_summary": live_report["scientific_summary"]})
                records.append(
                    {
                        **context,
                        "verified_at": row.verified_at,
                        "regression": {"id": row.regression_evidence_ids[0], "passed": True, "digest": regression_digest},
                        "end_to_end": {"id": row.end_to_end_evidence_ids[0], "passed": True, "digest": e2e_digest},
                    }
                )
            continue
        row = manifest.compatibility_matrix[0]
        entrypoint = registry.resolve_entrypoint(manifest.id)
        implementation_path = Path(inspect.getsourcefile(entrypoint) or "").resolve()
        try:
            implementation_path.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise RuntimeError(f"module implementation is outside the independent project: {manifest.id}") from exc
        context = {
            "module_id": manifest.id,
            "module_version": manifest.version,
            "row_id": row.id,
            "tool_versions": {key: list(value) for key, value in row.tool_versions.items()},
            "dependency_versions": {key: list(value) for key, value in row.dependency_versions.items()},
            "input_formats": {key: list(value) for key, value in row.input_formats.items()},
            "output_formats": {key: list(value) for key, value in row.output_formats.items()},
            "implementation_sha256": _sha256(implementation_path),
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
        elif manifest.agent_protocol is not None:
            case = fixtures.get(manifest.id)
            if not isinstance(case, dict):
                packaged_cases = json.loads((BUILTIN_ROOT / manifest.id / "tests" / "cases.json").read_text(encoding="utf-8"))
                first_case = packaged_cases.get("cases", [None])[0]
                if not isinstance(first_case, dict):
                    raise RuntimeError(f"agent-generated regression fixture is missing: {manifest.id}")
                case = {"input": first_case["input"], "output": first_case["expected_subset"]}
            direct = json.loads(json.dumps(entrypoint(**case["input"]), sort_keys=True))
            _assert_subset(case["output"], direct)
            try:
                evidence_config = AGENT_EVIDENCE[manifest.id]
            except KeyError:
                raise RuntimeError(f"agent-generated execution evidence is not configured: {manifest.id}") from None
            report_path = ROOT / evidence_config["path"]
            live_report = json.loads(report_path.read_text(encoding="utf-8"))
            template_hashes = {
                path.name: _sha256(path)
                for path in sorted((BUILTIN_ROOT / manifest.id / "templates").iterdir())
                if path.is_file()
            }
            observed_templates = {
                item["name"]: item["sha256"]
                for item in live_report.get("templates", {}).values()
            }
            if (
                live_report.get("passed") is not True
                or live_report.get("module_id") != manifest.id
                or live_report.get("module_version") != manifest.version
                or live_report.get("compatibility_row_id") != row.id
                or live_report.get("registry_digest") != registry.digest
                or observed_templates != template_hashes
                or any(not version_is_allowed(live_report.get("tool_versions", {}).get(key, ""), rules) for key, rules in row.tool_versions.items())
                or any(not version_is_allowed(live_report.get("dependency_versions", {}).get(key, ""), row.dependency_versions[key]) for key in evidence_config["live_dependency_keys"])
                or any(live_report.get("execution", {}).get(flag) is not True for flag in evidence_config["execution_flags"])
                or any(live_report.get("scientific_summary", {}).get(flag) is not True for flag in evidence_config["summary_flags"])
            ):
                raise RuntimeError(f"agent-generated live execution evidence differs from module contract: {manifest.id}")
            plan = route(manifest.intents[0], registry=registry)
            candidates = [item["id"] for step in plan["steps"] for item in step["candidates"]]
            if manifest.id not in candidates:
                raise RuntimeError(f"agent-generated module did not route through the unified entry: {manifest.id}")
            regression_digest = digest_value({**context, "kind": "regression", "input": case["input"], "handoff": direct, "templates": template_hashes})
            e2e_digest = digest_value({**context, "kind": "end-to-end", "live_report_sha256": _sha256(report_path), "execution": live_report["execution"], "scientific_summary": live_report["scientific_summary"]})
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
            direct = json.loads(json.dumps(entrypoint(**case["input"]), sort_keys=True))
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
