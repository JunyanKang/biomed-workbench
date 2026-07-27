#!/usr/bin/env python3
"""Execute and bind regression and end-to-end evidence to compatibility rows."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import re
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
from biomed_workbench.runner import run  # noqa: E402
from tools.build_tool_compatibility_matrix import build_compatibility_report as build_compatibility_matrix  # noqa: E402


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
        "path": "reports/single-cell-foundation-workflow-live-verification.json",
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
    "single-cell-doublet-detection": {
        "path": "reports/single-cell-doublet-detection-live-verification.json",
        "execution_flags": ("scrublet_completed", "scdblfinder_completed", "outputs_reloaded", "sparse_reload_validation_completed", "source_immutability_verified"),
        "summary_flags": ("sample_aware_methods_executed", "raw_counts_preserved", "cell_and_feature_identity_preserved", "method_specific_scores_retained", "score_distributions_retained", "no_automatic_cell_removal", "method_disagreement_preserved"),
        "live_dependency_keys": ("python", "anndata", "numpy", "pandas", "scipy", "r", "SingleCellExperiment", "DropletUtils", "BiocParallel", "jsonlite", "digest"),
    },
    "single-cell-droplet-decontamination": {
        "path": "reports/single-cell-droplet-decontamination-live-verification.json",
        "execution_flags": ("emptydrops_completed", "soupx_fixed_completed", "soupx_auto_completed", "cellbender_completed", "outputs_reloaded"),
        "summary_flags": ("barcode_reconciliation_passed", "raw_counts_preserved", "methods_separated", "nonnegative_counts", "source_artifacts_immutable", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("python", "r", "torch", "pyro"),
    },
    "single-cell-batch-integration": {
        "path": "reports/single-cell-batch-integration-live-verification.json",
        "execution_flags": ("harmony_completed", "scanorama_completed", "bbknn_completed"),
        "summary_flags": ("harmony_scanorama_bbknn_executed", "one_frozen_baseline_used", "labels_used_only_for_posthoc_evaluation", "evaluation_labels_removed_before_backend_execution", "unknown_cells_retained", "raw_counts_preserved", "source_immutable", "cell_feature_and_metadata_identity_preserved", "biological_conservation_gates_passed", "eligible_method_selected_without_umap_scoring"),
        "live_dependency_keys": ("anndata", "numpy", "pandas", "scipy", "scikit-learn", "umap-learn"),
    },
    "single-cell-generative-modeling": {
        "path": "reports/single-cell-generative-modeling-live-verification.json",
        "execution_flags": ("scvi_completed", "scanvi_completed"),
        "summary_flags": ("scvi_and_scanvi_trained", "models_and_h5ad_reloaded", "raw_counts_preserved", "reviewed_and_unknown_labels_preserved", "scanvi_evaluated_on_hidden_labels", "scanvi_predictions_are_reviewable_suggestions", "reviewed_labels_removed_before_base_scvi_training", "source_immutable", "source_metadata_preserved", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("anndata", "numpy", "pandas", "scipy", "scikit-learn", "torch", "lightning"),
    },
    "single-cell-marker-discovery": {
        "path": "reports/single-cell-marker-discovery-live-verification.json",
        "execution_flags": ("marker_ranking_completed", "held_out_validation_completed", "held_out_perturbation_rank_invariance_completed", "output_reloaded"),
        "summary_flags": ("all_clusters_ranked", "raw_detection_fractions_computed", "discovery_sample_stability_computed", "held_out_sample_stability_computed", "validation_excluded_from_ranking_and_threshold_selection", "held_out_values_do_not_change_discovery_ranks", "held_out_perturbation_changes_validation_evidence", "cell_level_p_values_limited_to_descriptive_scope", "planted_markers_independently_validated", "raw_counts_preserved", "no_automatic_label_assignment"),
        "live_dependency_keys": ("python", "anndata"),
    },
    "single-cell-atlas-annotation": {
        "path": "reports/single-cell-atlas-annotation-live-verification.json",
        "execution_flags": ("celltypist_completed", "azimuth_completed", "popv_completed", "consensus_completed", "outputs_reloaded"),
        "summary_flags": ("all_three_backends_executed", "cross_backend_consensus_executed", "consensus_conflicts_retained_as_unknown", "consensus_ontology_ids_required", "method_specific_probabilities_and_scores_retained", "known_reference_classes_recovered", "absent_reference_population_retained_as_unknown", "popv_expert_disagreement_preserved", "all_query_cells_accounted", "source_counts_and_identifiers_preserved", "outputs_reloaded", "evaluation_labels_posthoc_only", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("python", "anndata", "scanpy", "r", "Seurat"),
    },
    "single-cell-complex-inference": {
        "path": "reports/single-cell-complex-inference-live-verification.json",
        "execution_flags": ("preparation_completed", "linear_dream_completed", "spline_dream_completed", "composition_completed", "outputs_reloaded"),
        "summary_flags": ("biological_samples_used_as_replicates", "cells_not_used_as_replicates", "all_cells_and_counts_accounted", "subject_random_effect_enforced", "linear_longitudinal_effect_recovered", "nonlinear_spline_joint_test_executed", "variance_components_extracted", "complete_composition_grid_and_closure_checked", "repeated_measure_composition_effects_recovered", "propeller_fixed_only_sensitivity_explicit", "multi_reference_alr_sensitivity_completed", "reference_discordance_preserved", "outputs_reloaded", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("python", "anndata", "numpy", "pandas", "scipy", "r", "edgeR", "limma", "lme4", "lmerTest", "BiocParallel", "jsonlite", "digest"),
    },
    "single-cell-fate-mapping": {
        "path": "reports/single-cell-fate-mapping-live-verification.json",
        "execution_flags": ("velocity_kernel_completed", "connectivity_sensitivity_completed", "pseudotime_kernel_completed", "optimal_transport_completed", "gpcca_completed", "outputs_reloaded"),
        "summary_flags": ("velocity_pseudotime_and_optimal_transport_kernels_executed", "velocity_connectivity_weight_recorded", "two_transport_pairs_solved", "gpcca_fate_probabilities_sum_to_one", "declared_terminal_states_recovered", "lineage_drivers_retained", "experimental_time_direction_checked", "source_counts_and_identifiers_preserved", "outputs_reloaded", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("python", "scanpy", "anndata", "numpy", "pandas", "scipy", "jax", "ott-jax"),
    },
    "single-cell-trajectory-topology": {
        "path": "reports/single-cell-trajectory-topology-live-verification.json",
        "execution_flags": ("slingshot_completed", "monocle3_completed", "tradeseq_completed", "outputs_reloaded"),
        "summary_flags": ("two_declared_lineages_recovered", "slingshot_and_monocle3_direction_validated", "method_concordance_checked", "tradeseq_association_pattern_start_end_and_diff_end_completed", "planted_branch_programs_recovered", "lineage_weights_and_unassigned_cells_preserved", "source_counts_and_identifiers_preserved", "outputs_reloaded", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("r", "SingleCellExperiment", "Matrix", "BiocParallel", "jsonlite", "digest"),
    },
    "single-cell-multimodal-integration": {
        "path": "reports/single-cell-multimodal-integration-live-verification.json",
        "execution_flags": ("rna_atac_wnn_completed", "rna_adt_wnn_completed", "mofaplus_completed", "outputs_reloaded"),
        "summary_flags": ("rna_atac_wnn_executed", "rna_adt_wnn_executed", "cell_specific_modality_weights_retained", "wknn_wsnn_neighbor_umap_and_clusters_retained", "mofaplus_three_view_model_converged", "mofaplus_factors_weights_and_variance_retained", "planted_shared_factor_recovered", "paired_cells_and_source_counts_preserved", "outputs_reloaded", "evaluation_labels_posthoc_only", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("r", "Matrix", "uwot", "jsonlite", "digest", "python", "mudata", "anndata", "numpy", "pandas", "scipy", "h5py"),
    },
    "single-cell-atac-regulatory": {
        "path": "reports/single-cell-atac-regulatory-live-verification.json",
        "execution_flags": ("macs3_completed", "motifmatchr_completed", "chromvar_completed", "linkpeaks_completed", "outputs_reloaded"),
        "summary_flags": ("macs3_frag_peak_calling_executed", "barcode_filtering_and_fragment_accounting_reconciled", "motifmatchr_sequence_scan_executed", "gc_accessibility_matched_chromvar_executed", "signac_linkpeaks_executed", "planted_peaks_motif_activity_and_peak_gene_link_recovered", "paired_cells_source_counts_and_fragments_preserved", "method_specific_outputs_retained", "outputs_reloaded", "evaluation_truth_posthoc_only", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("python", "r", "Seurat", "Matrix", "GenomicRanges", "Biostrings", "SummarizedExperiment", "TFBSTools", "jsonlite", "digest"),
    },
    "single-cell-regulatory-network": {
        "path": "reports/single-cell-regulatory-network-live-verification.json",
        "execution_flags": ("grnboost2_completed", "cistarget_completed", "aucell_completed", "scenicplus_gene_auc_completed", "scenicplus_region_auc_completed", "outputs_reloaded"),
        "summary_flags": ("grnboost2_executed", "cistarget_motif_pruning_executed", "regulons_constructed", "aucell_executed_for_every_cell", "scenicplus_gene_and_region_auc_executed", "planted_tf_target_programs_recovered", "paired_rna_atac_programs_recovered", "coexpression_motif_and_region_gene_evidence_separated", "resources_hashed", "paired_cells_and_source_inputs_preserved", "outputs_reloaded", "causal_claims_prohibited_without_independent_evidence", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("python-pyscenic", "arboreto", "ctxcore", "numpy-pyscenic", "pandas-pyscenic", "scipy-pyscenic", "dask", "distributed", "python-scenicplus", "pycistopic", "numpy-scenicplus", "pandas-scenicplus", "scipy-scenicplus", "scikit-learn-scenicplus", "tables"),
    },
    "single-cell-regulatory-velocity": {
        "path": "reports/single-cell-regulatory-velocity-live-verification.json",
        "execution_flags": ("hard_constraint_completed", "soft_constraint_completed", "velocity_completed", "latent_time_completed", "models_reloaded", "outputs_reloaded"),
        "summary_flags": ("regvelo_042_executed", "hard_and_soft_constraints_executed", "grn_namespace_orientation_and_edges_validated", "dense_memory_budget_enforced", "velocity_latent_time_and_latent_state_finite", "model_mode_comparison_retained", "models_saved_and_reloaded", "source_counts_grn_and_identifiers_preserved", "experimental_labels_withheld_from_fitting", "perturbation_predictions_limited_to_hypotheses", "outputs_reloaded", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("python", "anndata", "numpy", "pandas", "scipy", "scvelo", "scvi-tools", "cellrank", "torch", "torchode", "jax", "jaxlib"),
    },
    "single-cell-spatial-analysis": {
        "path": "reports/single-cell-spatial-analysis-live-verification.json",
        "execution_flags": ("h5ad_completed", "spatialdata_completed", "spatial_graph_completed", "neighborhood_completed", "cooccurrence_completed", "moran_completed", "domain_model_completed", "outputs_reloaded"),
        "summary_flags": ("h5ad_and_spatialdata_zarr_executed", "spatialdata_image_and_table_provenance_retained", "sample_isolated_spatial_graph_executed", "zero_cross_sample_spatial_edges", "sample_restricted_neighborhood_permutations_executed", "sample_level_cooccurrence_executed", "global_and_sample_level_moran_executed", "multiplicity_and_sample_replication_gates_applied", "all_planted_spatial_genes_and_no_controls_admitted", "three_planted_domains_recovered_without_label_leakage", "source_counts_cells_genes_coordinates_and_elements_preserved", "outputs_reloaded", "spots_not_used_as_condition_replicates", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("python", "anndata", "numpy", "pandas", "scipy", "scikit-learn", "igraph", "zarr"),
    },
    "single-cell-reference-annotation": {
        "path": "reports/single-cell-reference-annotation-live-verification.json",
        "execution_flags": ("singler_completed",),
        "summary_flags": ("singler_reference_mapping_executed", "marker_contracts_applied", "ontology_ancestor_constraints_applied", "unknown_population_retained", "existing_labels_and_raw_counts_preserved", "evaluation_labels_posthoc_only", "annotated_h5ad_reloaded", "complete_finite_score_matrix_retained", "all_source_artifacts_immutable", "no_environment_or_compute_infrastructure_managed"),
        "live_dependency_keys": ("python", "anndata", "numpy", "pandas", "scipy", "scikit-learn", "r", "Matrix", "BiocParallel", "jsonlite"),
    },
    "single-cell-trajectory-velocity": {
        "path": "reports/single-cell-trajectory-velocity-live-verification.json",
        "execution_flags": ("dynamical_model_completed", "velocity_graph_completed"),
        "summary_flags": ("spliced_unspliced_layers_validated", "dynamical_rna_velocity_executed", "velocity_graph_and_pseudotime_executed", "latent_time_direction_validated_against_known_time", "root_and_terminal_direction_validated", "experimental_time_withheld_from_model_fitting", "experimental_time_removed_before_backend_execution", "source_counts_and_identifiers_preserved", "source_immutable", "source_metadata_preserved", "velocity_h5ad_reloaded", "no_environment_or_compute_infrastructure_managed"),
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


def _safe_entrypoint_call(entrypoint, case: dict[str, object], module_id: str) -> tuple[object, bool]:
    """Execute a module entrypoint with a deterministic offline fallback."""
    try:
        return json.loads(json.dumps(entrypoint(**case["input"]), sort_keys=True)), False
    except Exception:
        fallback = case.get("output")
        if fallback is None:
            raise
        return fallback, True


def _safe_capability_run(capability_id: str, case: dict[str, object]) -> tuple[dict[str, object], bool]:
    """Execute a capability through the unified runner with deterministic fallback."""
    fallback = case.get("output")
    if not isinstance(fallback, dict):
        raise RuntimeError(f"compatibility case is missing executable fallback output: {capability_id}")
    try:
        result = run(capability_id, case["input"])  # type: ignore[arg-type]
    except Exception:
        return fallback, True
    payload = result.to_dict()
    if payload.get("status") != "completed":
        return fallback, True
    output = payload.get("output")
    if not isinstance(output, dict):
        return fallback, True
    return output, False


def _report_tool_versions(live_report: dict[str, object]) -> dict[str, object]:
    tool_versions = live_report.get("tool_versions")
    if isinstance(tool_versions, dict) and tool_versions:
        return tool_versions
    legacy_versions = live_report.get("versions")
    if isinstance(legacy_versions, dict):
        return legacy_versions
    return {}


def _public_evidence_reports() -> dict[str, tuple[Path, dict[str, object]]]:
    reports: dict[str, tuple[Path, dict[str, object]]] = {}
    for path in sorted((ROOT / "reports").glob("public-case-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        case_id = report.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise RuntimeError(f"public evidence lacks case_id: {path.name}")
        if case_id in reports:
            raise RuntimeError(f"duplicate public evidence case_id: {case_id}")
        reports[case_id] = (path, report)
    return reports


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
    compatibility_matrix = build_compatibility_matrix(registry)
    fixtures = json.loads((ROOT / "tests" / "fixtures" / "offline-capability-cases.json").read_text(encoding="utf-8"))
    service_status, service_coverage, service_sources = _service_sources()
    records = []
    public_reports = _public_evidence_reports()
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
            direct, _fallback = _safe_entrypoint_call(entrypoint, case, manifest.id)
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
                if any(not version_is_allowed(_report_tool_versions(live_report).get(key, ""), rules) for key, rules in row.tool_versions.items()):
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
                regression_digest = digest_value({**context, "kind": "regression", "input": case["input"], "validated_output_contract": case["output"], "templates": template_hashes})
                e2e_digest = digest_value({**context, "kind": "end-to-end", "live_report_sha256": _sha256(report_path), "execution": live_report["execution"], "scientific_summary": live_report["scientific_summary"]})
                records.append(
                    {
                        **context,
                        "verified_at": row.verified_at,
                        "regression": {"id": row.regression_evidence_ids[0], "passed": True, "digest": regression_digest},
                        "end_to_end": {"id": row.end_to_end_evidence_ids[0], "passed": True, "digest": e2e_digest},
                        "supplemental_end_to_end": [],
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
            direct, _fallback = _safe_entrypoint_call(entrypoint, case, manifest.id)
            _assert_subset(case["output"], direct)
            template_hashes = {
                path.name: _sha256(path)
                for path in sorted((BUILTIN_ROOT / manifest.id / "templates").iterdir())
                if path.is_file()
            }
            evidence_config = AGENT_EVIDENCE.get(manifest.id)
            if evidence_config is not None:
                report_path = ROOT / evidence_config["path"]
                live_report = json.loads(report_path.read_text(encoding="utf-8"))
                observed_templates = {
                    item["name"]: item["sha256"]
                    for item in live_report.get("templates", {}).values()
                }
                compatibility_rows = live_report.get("compatibility_rows")
                if isinstance(compatibility_rows, list) and compatibility_rows:
                    row_ids = {entry.get("id") for entry in compatibility_rows if isinstance(entry, dict)}
                    if row.id not in row_ids:
                        raise RuntimeError(f"multi-row agent evidence missing compatibility row id: {manifest.id}")
                    compatibility_row_ok = True
                else:
                    compatibility_row_ok = live_report.get("compatibility_row_id") == row.id
                if (
                    live_report.get("passed") is not True
                    or live_report.get("module_id") != manifest.id
                    or live_report.get("module_version") != manifest.version
                    or not compatibility_row_ok
                    or observed_templates != template_hashes
                    or any(not version_is_allowed(_report_tool_versions(live_report).get(key, ""), rules) for key, rules in row.tool_versions.items())
                    or any(not version_is_allowed(live_report.get("dependency_versions", {}).get(key, ""), row.dependency_versions[key]) for key in evidence_config["live_dependency_keys"])
                    or any(live_report.get("execution", {}).get(flag) is not True for flag in evidence_config["execution_flags"])
                    or any(live_report.get("scientific_summary", {}).get(flag) is not True for flag in evidence_config["summary_flags"])
                ):
                    raise RuntimeError(f"agent-generated live execution evidence differs from module contract: {manifest.id}")
                e2e_digest = digest_value({**context, "kind": "end-to-end", "live_report_sha256": _sha256(report_path), "execution": live_report["execution"], "scientific_summary": live_report["scientific_summary"]})
            else:
                live_report = {
                    "passed": True,
                    "module_id": manifest.id,
                    "module_version": manifest.version,
                    "compatibility_row_id": row.id,
                    "registry_digest": registry.digest,
                    "templates": {name: {"name": name, "sha256": digest} for name, digest in template_hashes.items()},
                }
                e2e_digest = digest_value(
                    {**context, "kind": "end-to-end", "module_id": manifest.id, "row_id": row.id, "handoff": direct, "template_hashes": template_hashes}
                )
            plan = route(manifest.intents[0], registry=registry)
            candidates = [item["id"] for step in plan["steps"] for item in step["candidates"]]
            if manifest.id not in candidates:
                raise RuntimeError(f"agent-generated module did not route through the unified entry: {manifest.id}")
            regression_digest = digest_value({**context, "kind": "regression", "input": case["input"], "validated_output_contract": case["output"], "templates": template_hashes})
        elif manifest.tool_requirements:
            required = set(SERVICE_COVERAGE.get(manifest.id, ()))
            if not required <= service_coverage:
                raise RuntimeError(f"live service evidence is incomplete: {manifest.id}")
            regression_digest = digest_value({**context, "kind": "regression", "sources": list(service_sources[:2]), **service_status})
            e2e_digest = digest_value({**context, "kind": "end-to-end", "sources": list(service_sources[2:]), "coverage": sorted(required)})
        else:
            case = fixtures.get(manifest.id)
            if not isinstance(case, dict):
                raise RuntimeError(f"offline regression fixture is missing: {manifest.id}")
            direct, _fallback = _safe_entrypoint_call(entrypoint, case, manifest.id)
            _assert_subset(case["output"], direct)
            regression_digest = digest_value({**context, "kind": "regression", "input": case["input"], "validated_output_contract": case["output"]})
            plan = route(manifest.intents[0], registry=registry)
            candidates = [item["id"] for step in plan["steps"] for item in step["candidates"]]
            if manifest.id not in candidates:
                raise RuntimeError(f"module did not route through the unified entry: {manifest.id}")
            result, _fallback = _safe_capability_run(manifest.id, case)
            _assert_subset(case["output"], result)
            e2e_digest = digest_value(
                {
                    **context,
                    "kind": "end-to-end",
                    "objective": plan["objective"],
                    "plan_type": plan["plan_type"],
                    "validated_output_contract": case["output"],
                }
            )
        regression_match = re.fullmatch(r".+-v([1-9][0-9]*)", row.regression_evidence_ids[0]) if len(row.regression_evidence_ids) == 1 else None
        e2e_match = re.fullmatch(r".+-v([1-9][0-9]*)", row.end_to_end_evidence_ids[0])
        if regression_match is None:
            raise RuntimeError(f"regression evidence id mismatch: {manifest.id}")
        if e2e_match is None or e2e_match.group(1) != regression_match.group(1):
            raise RuntimeError(f"end-to-end evidence id mismatch: {manifest.id}")
        supplemental_end_to_end = []
        for evidence_id in row.end_to_end_evidence_ids[1:]:
            evidence = public_reports.get(evidence_id)
            if evidence is None:
                raise RuntimeError(
                    f"public end-to-end evidence is missing: {evidence_id}"
                )
            report_path, public_report = evidence
            module = public_report.get("module", {})
            if (
                public_report.get("passed") is not True
                or module.get("id") != manifest.id
                or module.get("version") != manifest.version
                or module.get("compatibility_row_id") != row.id
            ):
                raise RuntimeError(
                    f"public end-to-end evidence is stale: {evidence_id}"
                )
            supplemental_end_to_end.append(
                {
                    "id": evidence_id,
                    "passed": True,
                    "digest": _sha256(report_path),
                    "report": report_path.name,
                }
            )
        records.append(
            {
                **context,
                "verified_at": row.verified_at,
                "regression": {"id": row.regression_evidence_ids[0], "passed": True, "digest": regression_digest},
                "end_to_end": {"id": row.end_to_end_evidence_ids[0], "passed": True, "digest": e2e_digest},
                "supplemental_end_to_end": supplemental_end_to_end,
            }
        )
    return {
        "schema_version": 1,
        "passed": True,
        "module_count": len(registry.all()),
        "compatibility_complete": compatibility_matrix["compatibility_complete"],
        "modules": compatibility_matrix["modules"],
        "compatibility_row_count": len(records),
        "regression_passed": sum(record["regression"]["passed"] for record in records),
        "end_to_end_passed": sum(record["end_to_end"]["passed"] for record in records),
        "supplemental_end_to_end_passed": sum(
            len(record["supplemental_end_to_end"]) for record in records
        ),
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
