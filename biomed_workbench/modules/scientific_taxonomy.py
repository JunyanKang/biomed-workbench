"""Orthogonal scientific taxonomy for module discovery and documentation."""

from __future__ import annotations

from typing import Any

from .contract import ModuleManifest


BULK_ASSAY_MODULES = frozenset(
    {
        "bulk-chromatin-accessibility",
        "bulk-chromatin-peak-calling",
        "bulk-dna-methylation",
        "bulk-nascent-transcription",
        "bulk-rbp-rna-binding",
        "bulk-ribosome-profiling",
        "bulk-r-loop-mapping",
        "bulk-rna-modification-enrichment",
        "bulk-three-dimensional-genome",
    }
)
SPATIAL_MODULES = frozenset(
    {
        "single-cell-spatial-analysis",
        "spatial-multimethod-inference",
        "spatial-multislice-integration",
        "spatial-platform-image-foundation",
        "trajectory-spatial-figure-package",
    }
)
ASSAY_SPECIFIC_PREFIXES = (
    "bulk-",
    "single-cell-",
    "spatial-",
)
DOWNSTREAM_UNIVERSAL = frozenset(
    {
        "differential-expression",
        "rna-processing-alternative-splicing",
        "enrichment-analysis",
        "functional-enrichment",
        "wgcna-coexpression",
        "network-analysis",
        "metagene-factorization-nmf",
        "figure-specification",
        "journal-targeting-and-compliance",
        "manuscript-audit",
        "citation-audit",
        "academic-prose-revision-audit",
        "research-proposal-quality-audit",
        "nsfc-proposal-development",
        "nsfc-proposal-figure-development",
        "nsfc-proposal-semantic-audit",
        "biomedical-terminology-and-nomenclature-audit",
        "mechanism-claim-promotion-gate",
        "docx-citation-delivery-audit",
        "statistical-reporting-audit",
        "data-availability-audit",
        "paper-reader-package-audit",
        "literature-landscape-audit",
        "literature-acquisition-manifest-audit",
        "experiment-log-standardization",
        "presentation-package-audit",
        "publication-figure-package",
    }
)
QUANTITATIVE_IMAGING_MODULES = frozenset(
    {
        "cell-migration-metrics",
        "image-colocalization",
        "image-profile",
        "image-segment",
        "image-translation-registration",
        "point-tracking",
    }
)
PROJECT_WIDE_FIGURE_SUPPORT_MODULES = frozenset(
    {
        "figure-specification",
        "nsfc-proposal-figure-development",
        "publication-figure-package",
    }
)
SCIENTIFIC_COMMUNICATION_ASSET_MODULES = frozenset(
    {
        "image-chroma-key-remove",
        "scientific-illustration-generation",
    }
)


def classify_module(manifest: ModuleManifest) -> dict[str, Any]:
    """Classify scale, measurement family, and method role without conflating them."""
    module_id = manifest.id
    if module_id in SPATIAL_MODULES or module_id.startswith("spatial-"):
        scale = "spatial"
    elif module_id.startswith("single-cell-"):
        scale = "single-cell"
    elif module_id in BULK_ASSAY_MODULES:
        scale = "bulk"
    else:
        scale = "universal"

    if module_id in BULK_ASSAY_MODULES:
        measurement_family = {
            "bulk-chromatin-peak-calling": "protein-or-mark-associated chromatin enrichment",
            "bulk-chromatin-accessibility": "chromatin accessibility",
            "bulk-dna-methylation": "cytosine modification",
            "bulk-nascent-transcription": "nascent transcription",
            "bulk-rbp-rna-binding": "RNA-protein association or binding-site mapping",
            "bulk-ribosome-profiling": "ribosome occupancy and translation",
            "bulk-r-loop-mapping": "RNA-DNA hybrid and R-loop mapping",
            "bulk-rna-modification-enrichment": "RNA modification enrichment",
            "bulk-three-dimensional-genome": "chromosome conformation",
        }[module_id]
        role = "assay-specific"
    elif module_id in SPATIAL_MODULES or module_id.startswith("single-cell-"):
        measurement_family = "single-cell or spatial measurement"
        role = "assay-specific" if manifest.module_type in {"analysis", "transform"} else "cross-scale delivery"
    elif module_id in QUANTITATIVE_IMAGING_MODULES:
        measurement_family = "quantitative image measurement"
        role = "measurement-specific"
    elif module_id in SCIENTIFIC_COMMUNICATION_ASSET_MODULES:
        measurement_family = "non-evidentiary scientific communication image"
        role = "communication-support"
    elif module_id == "rna-processing-alternative-splicing":
        measurement_family = "RNA processing, splice-event, exon-usage, transcript-usage and isoform evidence"
        role = "cross-scale"
    elif module_id in DOWNSTREAM_UNIVERSAL:
        measurement_family = "derived statistical or publication evidence"
        role = "cross-scale"
    elif "omics" in manifest.domains:
        measurement_family = "sequence or molecular data infrastructure"
        role = "multi-assay"
    else:
        measurement_family = "not assay-scoped"
        role = "research-infrastructure-or-other-domain"

    if module_id in PROJECT_WIDE_FIGURE_SUPPORT_MODULES:
        capability_scope = "project-wide-figure-support"
    elif module_id in QUANTITATIVE_IMAGING_MODULES:
        capability_scope = "image-derived-measurement"
    elif module_id in SCIENTIFIC_COMMUNICATION_ASSET_MODULES:
        capability_scope = "scientific-communication-asset"
    elif scale == "universal":
        capability_scope = "project-wide-or-non-scale-specific"
    else:
        capability_scope = "scale-specific-analysis"

    return {
        "module_id": module_id,
        "module_version": manifest.version,
        "primary_scale": scale,
        "measurement_family": measurement_family,
        "method_role": role,
        "capability_scope": capability_scope,
        "module_type": manifest.module_type,
        "domains": list(manifest.domains),
        "invariants": {
            "scale_is_not_measurement_family": True,
            "assay_is_not_target_or_antibody": True,
            "normalization_is_not_assay": True,
            "specificity_control_is_not_biological_replicate": True,
        },
    }
