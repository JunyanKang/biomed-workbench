"""Versioned scientific plotting rules shared by analysis modules.

The contract is expressed at final publication size.  Backends may render at a
larger canvas, but text, strokes, and symbols must be scaled back to these final
dimensions before export.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


STYLE_VERSION = "1.2.0"

COLORBLIND_SAFE = {
    "blue": "#0072B2",
    "orange": "#E69F00",
    "green": "#009E73",
    "vermillion": "#D55E00",
    "sky": "#56B4E9",
    "purple": "#CC79A7",
    "yellow": "#F0E442",
    "black": "#000000",
    "grey": "#7A7A7A",
    "light_grey": "#D9D9D9",
}

DIVERGING = {
    "negative": "#3B4CC0",
    "midpoint": "#F7F7F7",
    "positive": "#B40426",
}

STYLE_TOKENS: dict[str, Any] = {
    "version": STYLE_VERSION,
    "size_basis": "final-size",
    "evidence_policy": {
        "tool_plot_families": "official manual or vignette",
        "analysis_plot_inventory": "primary or major-journal research workflow",
        "journal_export_dimensions": "current target-journal author guide",
        "implementation_authority": "docs/capabilities/advanced-omics-evidence-standard.md",
    },
    "canvas": {
        "single_column_mm": 89,
        "double_column_mm": 183,
        "maximum_height_mm": 170,
        "panel_gap_mm": 2.5,
        "outer_margin_mm": 2.0,
    },
    "typography_pt": {
        "font_family": ["Arial", "Helvetica", "Noto Sans CJK SC", "sans-serif"],
        "figure_title": 7.0,
        "panel_label": 7.0,
        "axis_title": 7.0,
        "axis_tick": 6.0,
        "legend_title": 6.0,
        "legend_text": 6.0,
        "annotation": 6.0,
        "minimum": 5.0,
        "maximum": 7.0,
        "panel_label_weight": "bold",
    },
    "strokes_pt": {
        "axis": 0.5,
        "data": 0.5,
        "reference": 0.5,
        "grid": 0.5,
        "error_bar": 0.5,
        "box": 0.5,
        "minimum": 0.5,
    },
    "symbols_pt": {
        "scatter_default": 2.4,
        "scatter_dense": 1.2,
        "highlight": 3.0,
        "error_bar_cap": 2.0,
    },
    "legend": {
        "default_position": "right",
        "wide_panel_position": "top",
        "inside_panel_allowed": False,
        "maximum_rows": 2,
        "key_size_pt": 7.0,
        "order_follows_design": True,
        "drop_unused_levels": False,
    },
    "axes": {
        "show_units": True,
        "show_zero_when_interpretable": True,
        "minor_grid": False,
        "major_grid": "only-when-it-improves-quantitative-reading",
        "truncate_without_break_mark": False,
        "free_scales_across_comparable_panels": False,
    },
    "statistics": {
        "show_biological_n": True,
        "identify_experimental_unit": True,
        "state_test_and_multiplicity": True,
        "show_effect_size": True,
        "show_uncertainty": True,
        "asterisk_only_inference": False,
    },
    "export": {
        "primary": ["pdf", "svg"],
        "raster": ["png", "tiff"],
        "raster_dpi": 600,
        "continuous_tone_dpi": 300,
        "embed_fonts": True,
        "transparent_background": False,
        "retain_editable_vector_text": True,
    },
    "colors": {
        "categorical": COLORBLIND_SAFE,
        "diverging": DIVERGING,
        "missing": "#BDBDBD",
        "nonsignificant": "#B0B0B0",
        "background": "#FFFFFF",
        "do_not_encode_condition_by_red_green_pair": True,
    },
}

JOURNAL_PROFILES: dict[str, dict[str, Any]] = {
    "nature": {
        "status": "official-current-guide",
        "source": "https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/",
        "canvas": {"single_column_mm": 89, "double_column_mm": 183, "maximum_height_mm": 170},
        "typography_pt": {"minimum": 5.0, "maximum": 7.0},
        "font_family": ["Arial", "Helvetica", "sans-serif"],
        "vector_text_editable": True,
    },
    "science": {
        "status": "target-journal-guide-required",
        "source": None,
        "reason": "Do not present inferred or partner-journal values as official Science specifications.",
    },
    "cell": {
        "status": "target-journal-guide-required",
        "source": None,
        "reason": "Cell-family requirements vary by journal and production stage; attach the current target-journal guide.",
    },
    "screen": {
        "status": "workbench-accessibility-profile",
        "source": "project-owned",
        "typography_pt": {"minimum": 8.0, "maximum": 12.0},
    },
}


PLOT_CONTRACTS: dict[str, dict[str, Any]] = {
    "qc_distribution": {
        "required_elements": ["raw points or density", "median", "biological sample identity", "threshold if used", "n"],
        "layout": "facets share scales when quantities are comparable",
        "legend": "top for condition; suppress when direct labels are clearer",
    },
    "pca": {
        "required_elements": ["explained variance on axes", "sample labels or collision-safe labels", "condition color", "batch or sample shape"],
        "layout": "equal aspect; 95% ellipse only when group size supports it",
        "legend": "right; design order",
    },
    "volcano": {
        "required_elements": ["effect-size x axis", "-log10 adjusted-p y axis", "effect and FDR thresholds", "nonsignificant class", "bounded nonoverlapping labels"],
        "layout": "symmetric effect-size limits unless biology requires otherwise",
        "legend": "top or direct labels; never encode significance by color alone",
    },
    "ma": {
        "required_elements": ["mean-abundance x axis", "effect-size y axis", "zero line", "FDR class", "bounded labels"],
        "layout": "symmetric effect-size limits",
        "legend": "top",
    },
    "heatmap": {
        "required_elements": ["color scale with units", "sample annotations", "row/column clustering state", "missing-value color"],
        "layout": "annotation bars above columns; row labels shown only when legible",
        "legend": "right; separate continuous and categorical legends",
    },
    "enrichment_dotplot": {
        "required_elements": ["term label", "effect or gene ratio x axis", "adjusted-p encoding", "gene-set size encoding", "database and release"],
        "layout": "terms ordered by declared metric; wrap labels without truncating identifiers",
        "legend": "right; size above color when stacked",
    },
    "gsea_curve": {
        "required_elements": ["running enrichment score", "ranked-list metric", "hit ticks", "NES", "adjusted p", "leading-edge boundary"],
        "layout": "aligned x axes across curve, hit, and rank panels",
        "legend": "direct label or top",
    },
    "network": {
        "required_elements": ["edge meaning", "node meaning", "threshold", "isolated-node policy", "module or community key"],
        "layout": "fixed seed; avoid interpreting spatial proximity unless layout encodes a metric",
        "legend": "right; separate node and edge encodings",
    },
    "genome_track": {
        "required_elements": ["genome build", "coordinates", "shared y scale or explicit independent scales", "sample/condition", "normalization", "gene model", "peak track"],
        "layout": "aligned coordinates; gene model at bottom; controls adjacent to matched samples",
        "legend": "direct track labels on left; compact legend above",
    },
    "embedding_trajectory": {
        "required_elements": ["embedding identity", "cells or observations", "lineage curves or principal graph", "root and terminal states", "direction", "sample or condition identity"],
        "layout": "use the same embedding and limits across comparable panels; show direction explicitly and do not imply physical distance",
        "legend": "right; direct labels for a small number of lineages",
    },
    "velocity_field": {
        "required_elements": ["embedding identity", "velocity model", "directional vectors or streamlines", "velocity confidence", "root and terminal evidence", "sample identity"],
        "layout": "pair the field with confidence and latent-time panels using identical coordinates",
        "legend": "right; continuous scales separated from categorical annotations",
    },
    "spatial_map": {
        "required_elements": ["physical coordinate unit", "sample or section identity", "coordinate system", "tissue boundary or image context when available", "missing-value encoding", "scale bar when calibrated"],
        "layout": "fixed aspect and anatomically consistent orientation; never connect or pool coordinates across samples",
        "legend": "outside the tissue panel; preserve declared category order",
    },
    "spatial_vector_field": {
        "required_elements": ["physical coordinate unit", "distance threshold or neighborhood rule", "sender and receiver semantics", "edge or vector scale", "sample identity", "tested interaction and FDR"],
        "layout": "overlay only edges admitted by the declared physical-distance graph; provide an uncluttered scalar summary beside the map",
        "legend": "outside; separate interaction strength, direction, and cell-type encodings",
    },
    "registration_overlay": {
        "required_elements": ["moving and fixed section identity", "pre and post registration views", "transform family", "landmarks or image channel", "quantitative registration error", "coordinate unit"],
        "layout": "show identical crop and scale before and after registration; include deformation diagnostics for nonlinear transforms",
        "legend": "top; direct section labels preferred",
    },
    "three_dimensional_spatial": {
        "required_elements": ["section order", "inter-section spacing and unit", "aligned x y z axes", "transform provenance", "sample identity", "uncertainty or alignment error"],
        "layout": "pair the 3D view with orthogonal or section-wise views; do not hide missing sections",
        "legend": "right; shared across projections",
    },
}


ANALYSIS_FIGURE_PROFILES: dict[str, dict[str, list[str]]] = {
    "bulk-cuttag": {
        "required": [
            "read_qc_summary",
            "host_spikein_alignment_fraction",
            "spikein_scale_factor",
            "fragment_length_distribution",
            "replicate_correlation_heatmap",
            "pca",
            "frip_and_peak_count",
            "ma",
            "volcano",
            "genome_track",
        ],
        "optional": [
            "library_complexity",
            "strand_bias",
            "peak_annotation",
            "signal_distribution_by_genomic_feature",
            "target_specific_metaprofile_heatmap",
            "rnaseh_sensitivity_for_s96_target",
        ],
    },
    "bulk-r-loop-mapping": {
        "required": [
            "read_and_mapping_qc",
            "strand_accounting",
            "rnaseh_sensitivity",
            "replicate_correlation_heatmap",
            "signal_width_and_annotation",
            "tss_tts_metaprofiles",
            "sense_antisense_heatmap",
            "method_overlap_and_discordance",
            "genome_track",
        ],
        "optional": [
            "internal_reference_recovery",
            "gene_body_intergenic_distribution",
            "sensor_comparison",
            "orthogonal_validation_linkage",
        ],
    },
    "single-cell-atac-peak-recall": {
        "required": [
            "fragment_and_barcode_accounting",
            "groupwise_peak_yield",
            "peak_width_distribution",
            "consensus_peak_support",
            "feature_matrix_sparsity",
            "frip_before_after",
            "tss_enrichment",
            "nucleosome_signal",
            "lsi_depth_correlation",
            "umap",
            "marker_peak_heatmap",
            "genome_track",
        ],
        "optional": ["peak_set_upset", "blacklist_overlap", "doublet_score_distribution"],
    },
    "proteomics-deqms": {
        "required": [
            "missingness_and_intensity_qc",
            "sample_correlation_heatmap",
            "pca",
            "psm_count_distribution",
            "variance_count_trend",
            "residual_diagnostic",
            "ma",
            "volcano",
            "significant_protein_heatmap",
        ],
        "optional": ["contrast_effect_forest", "protein_count_sensitivity"],
    },
    "go-kegg-overrepresentation": {
        "required": ["enrichment_dotplot", "enrichment_barplot"],
        "optional": ["gene_term_network", "term_similarity_map", "upset_overlap"],
    },
    "preranked-gsea": {
        "required": ["nes_dotplot", "gsea_curve", "leading_edge_heatmap"],
        "optional": ["pathway_similarity_map", "ridgeplot"],
    },
    "wgcna": {
        "required": [
            "sample_dendrogram_and_traits",
            "soft_threshold_diagnostics",
            "gene_dendrogram_module_colors",
            "module_size_distribution",
            "module_trait_heatmap",
            "eigengene_network",
            "module_membership_gene_significance",
        ],
        "optional": ["tom_heatmap", "hub_gene_network", "module_expression_heatmap"],
    },
    "trajectory-topology": {
        "required": [
            "embedding_with_lineage_curves",
            "pseudotime_map",
            "root_terminal_annotation",
            "lineage_weight_map",
            "external_time_concordance",
            "lineage_gene_smooth_heatmap",
            "topology_parameter_sensitivity",
        ],
        "optional": ["branch_gene_trends", "method_topology_concordance", "sample_composition_by_pseudotime"],
    },
    "trajectory-velocity": {
        "required": [
            "velocity_stream_or_vector_field",
            "velocity_confidence_map",
            "latent_time_map",
            "root_terminal_evidence",
            "external_time_concordance",
            "phase_portrait_panel",
            "velocity_parameter_sensitivity",
        ],
        "optional": ["gene_velocity_heatmap", "velocity_length_distribution", "sample_stratified_velocity"],
    },
    "fate-mapping": {
        "required": [
            "terminal_state_annotation",
            "terminal_probability_maps",
            "fate_probability_composition",
            "macrostates_or_gpcca_spectrum",
            "lineage_driver_heatmap",
            "kernel_and_terminal_state_sensitivity",
        ],
        "optional": ["fate_simplex", "absorption_time_map", "sample_stratified_fate_probability"],
    },
    "regulatory-velocity": {
        "required": [
            "regulatory_constraint_summary",
            "training_and_holdout_diagnostics",
            "velocity_concordance",
            "latent_time_concordance",
            "regulator_effect_map",
            "perturbation_fate_sensitivity",
        ],
        "optional": ["regulator_target_network", "counterfactual_trajectory", "sample_stratified_regulator_effect"],
    },
    "spatial-platform-qc": {
        "required": [
            "counts_and_features_spatial_maps",
            "library_or_transcript_qc_distributions",
            "tissue_or_cell_assignment_summary",
            "coordinate_and_geometry_diagnostics",
            "platform_specific_control_metrics",
            "sample_qc_overview",
        ],
        "optional": ["image_alignment_overlay", "boundary_validity_map", "panel_detection_rate", "bin_size_sensitivity"],
    },
    "spatial-core-analysis": {
        "required": [
            "spatial_graph_diagnostics",
            "neighborhood_enrichment_heatmap",
            "cooccurrence_by_distance",
            "moran_effect_fdr",
            "replicated_spatial_gene_maps",
            "exploratory_domain_map",
            "domain_stability_and_sample_composition",
        ],
        "optional": ["local_spatial_statistic_map", "spatial_gene_heatmap", "graph_parameter_sensitivity"],
    },
    "spatial-deconvolution": {
        "required": [
            "cell_type_abundance_maps",
            "location_composition",
            "reference_signature_diagnostics",
            "reconstruction_or_heldout_gene_diagnostics",
            "uncertainty_map",
            "method_concordance_and_discordance",
        ],
        "optional": ["cell_type_colocalization", "posterior_quantiles", "reference_subsampling_sensitivity"],
    },
    "spatial-domain-benchmark": {
        "required": [
            "domain_maps_by_method",
            "seed_and_resolution_stability",
            "spatial_coherence_and_fragmentation",
            "method_pair_concordance",
            "runtime_and_memory",
            "label_blind_benchmark_summary",
            "discordant_region_map",
        ],
        "optional": ["withheld_annotation_posthoc_ari", "boundary_enrichment", "consensus_domain_map"],
    },
    "spatial-communication": {
        "required": [
            "distance_constrained_interaction_map",
            "sender_receiver_score_maps",
            "interaction_strength_by_distance",
            "sample_support_and_effect_summary",
            "multiplicity_and_database_summary",
            "distance_threshold_sensitivity",
        ],
        "optional": ["directional_vector_field", "cell_type_interaction_matrix", "method_sensitivity"],
    },
    "spatial-image-analysis": {
        "required": [
            "raw_image_and_segmentation_overlay",
            "cell_boundary_quality_maps",
            "cell_morphology_distributions",
            "transcript_assignment_diagnostics",
            "registration_pre_post_overlay",
            "registration_error_and_deformation",
        ],
        "optional": ["image_feature_embedding", "expression_morphology_association", "segmentation_parameter_sensitivity"],
    },
    "spatial-multislice": {
        "required": [
            "sections_before_and_after_alignment",
            "pairwise_coupling_or_correspondence",
            "alignment_error_by_section",
            "three_dimensional_reconstruction",
            "cross_sample_domain_composition",
            "hierarchical_spatial_effect_summary",
        ],
        "optional": ["transform_deformation_diagnostics", "partial_overlap_diagnostics", "section_order_sensitivity"],
    },
}


def scientific_figure_standard(
    analysis_type: str | None = None,
    journal_profile: str = "nature",
) -> dict[str, Any]:
    """Return a copy of the global style and one declared analysis profile."""
    profile: dict[str, list[str]] = {"required": [], "optional": []}
    if analysis_type is not None:
        if analysis_type not in ANALYSIS_FIGURE_PROFILES:
            raise ValueError(f"unsupported analysis_type: {analysis_type}")
        profile = deepcopy(ANALYSIS_FIGURE_PROFILES[analysis_type])
    if journal_profile not in JOURNAL_PROFILES:
        raise ValueError(f"unsupported journal_profile: {journal_profile}")
    journal = deepcopy(JOURNAL_PROFILES[journal_profile])
    journal["ready_for_submission_export"] = journal["status"] != "target-journal-guide-required"
    return {
        "style": {**deepcopy(STYLE_TOKENS), "journal_profile": journal_profile, "journal": journal},
        "plot_contracts": deepcopy(PLOT_CONTRACTS),
        "analysis_type": analysis_type,
        "journal_profile": journal_profile,
        "required_plots": profile["required"],
        "optional_plots": profile["optional"],
    }


def validate_panel_style(panel: dict[str, Any]) -> list[dict[str, str]]:
    """Return machine-readable findings for a panel-level style declaration."""
    findings: list[dict[str, str]] = []
    required = ("label", "claim", "data_source", "plot")
    for key in required:
        if not str(panel.get(key, "")).strip():
            findings.append({"code": "PANEL_FIELD_MISSING", "field": key, "message": f"panel requires {key}"})
    if panel.get("legend_position") == "inside":
        findings.append({"code": "LEGEND_INSIDE_PANEL", "field": "legend_position", "message": "inside-panel legends are not allowed"})
    font_size = panel.get("minimum_font_pt")
    if font_size is not None and (not isinstance(font_size, (int, float)) or float(font_size) < STYLE_TOKENS["typography_pt"]["minimum"]):
        findings.append({"code": "FONT_TOO_SMALL", "field": "minimum_font_pt", "message": "font is below the final-size minimum"})
    line_width = panel.get("minimum_line_pt")
    if line_width is not None and (not isinstance(line_width, (int, float)) or float(line_width) < STYLE_TOKENS["strokes_pt"]["minimum"]):
        findings.append({"code": "LINE_TOO_THIN", "field": "minimum_line_pt", "message": "line is below the final-size minimum"})
    return findings
