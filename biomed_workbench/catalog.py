"""Source-neutral capability registry."""

from __future__ import annotations

import importlib
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .models import Capability


class CapabilityResolutionError(LookupError):
    """Raised when a capability ID or entrypoint cannot be resolved."""


_REGISTRY: dict[str, Capability] = {}


def register(capability: Capability) -> Capability:
    if capability.id in _REGISTRY:
        raise ValueError(f"duplicate capability id: {capability.id}")
    _REGISTRY[capability.id] = capability
    return capability


def resolve(capability_id: str) -> Capability:
    try:
        return _REGISTRY[capability_id]
    except KeyError:
        raise CapabilityResolutionError(f"unknown capability: {capability_id}") from None


def resolve_entrypoint(capability: Capability) -> Callable[..., object] | Path:
    if capability.kind == "workflow" and ":" not in capability.entrypoint:
        path = Path(capability.entrypoint)
        if not path.is_file():
            raise CapabilityResolutionError(f"workflow entrypoint does not exist: {capability.id}")
        return path
    module_name, separator, attribute_name = capability.entrypoint.partition(":")
    if not separator or not module_name or not attribute_name:
        raise CapabilityResolutionError(f"invalid entrypoint for {capability.id}")
    try:
        module = importlib.import_module(module_name)
        entrypoint = getattr(module, attribute_name)
    except (ImportError, AttributeError):
        raise CapabilityResolutionError(f"entrypoint cannot be resolved: {capability.id}") from None
    if not callable(entrypoint):
        raise CapabilityResolutionError(f"entrypoint is not callable: {capability.id}")
    return entrypoint


def all_capabilities() -> tuple[Capability, ...]:
    return tuple(_REGISTRY[capability_id] for capability_id in sorted(_REGISTRY))


def capability_to_dict(capability: Capability) -> dict[str, object]:
    return asdict(capability)


def _object_schema(properties: dict[str, object], required: tuple[str, ...]) -> dict[str, object]:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


_DATABASE = {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"}
_IDS = {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10000}


def _register_builtins() -> None:
    definitions = (
        Capability(
            id="ncbi-info",
            workflow="evidence",
            kind="service",
            title="Inspect NCBI Entrez databases",
            description="Return current Entrez database metadata and searchable fields.",
            entrypoint="biomed_workbench.capabilities.ncbi:info",
            input_schema=_object_schema({"database": {**_DATABASE, "nullable": True}}, ()),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-search",
            workflow="evidence",
            kind="service",
            title="Search NCBI Entrez",
            description="Search any valid Entrez database with bounded pagination and optional history state.",
            entrypoint="biomed_workbench.capabilities.ncbi:search",
            input_schema=_object_schema(
                {
                    "database": _DATABASE,
                    "term": {"type": "string", "minLength": 1},
                    "retmax": {"type": "integer", "minimum": 0, "maximum": 100000},
                    "retstart": {"type": "integer", "minimum": 0},
                    "sort": {"type": "string", "nullable": True},
                    "use_history": {"type": "boolean"},
                    "idtype": {"type": "string", "nullable": True},
                },
                ("database", "term"),
            ),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-summary",
            workflow="evidence",
            kind="service",
            title="Summarize NCBI Entrez records",
            description="Retrieve normalized document summaries for identifiers in an Entrez database.",
            entrypoint="biomed_workbench.capabilities.ncbi:summary",
            input_schema=_object_schema({"database": _DATABASE, "ids": _IDS}, ("database", "ids")),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-fetch",
            workflow="evidence",
            kind="service",
            title="Fetch NCBI Entrez records",
            description="Fetch database-native records such as XML, MEDLINE, GenBank, or FASTA.",
            entrypoint="biomed_workbench.capabilities.ncbi:fetch",
            input_schema=_object_schema(
                {
                    "database": _DATABASE,
                    "ids": _IDS,
                    "rettype": {"type": "string", "nullable": True},
                    "retmode": {"type": "string", "nullable": True},
                },
                ("database", "ids"),
            ),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-link",
            workflow="evidence",
            kind="service",
            title="Link NCBI Entrez databases",
            description="Resolve linked identifiers between Entrez databases for evidence chaining.",
            entrypoint="biomed_workbench.capabilities.ncbi:link",
            input_schema=_object_schema(
                {
                    "source_database": _DATABASE,
                    "target_database": _DATABASE,
                    "ids": _IDS,
                    "linkname": {"type": "string", "nullable": True},
                },
                ("source_database", "target_database", "ids"),
            ),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-search-summary",
            workflow="evidence",
            kind="service",
            title="Search and summarize NCBI Entrez",
            description="Run a bounded Entrez search and return normalized summaries in one composable action.",
            entrypoint="biomed_workbench.capabilities.ncbi:search_summary",
            input_schema=_object_schema(
                {
                    "database": _DATABASE,
                    "term": {"type": "string", "minLength": 1},
                    "retmax": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                ("database", "term"),
            ),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="runtime-status",
            workflow="runtime",
            kind="python",
            title="Inspect scientific compute readiness",
            description="Read available Python, R, container, GPU, SLURM, and local scientific model backends without changing the system.",
            entrypoint="biomed_workbench.capabilities.runtime:status",
            input_schema=_object_schema({}, ()),
            requirements=(),
            access="local_runtime",
            mutability="read_only",
        ),
        Capability(
            id="sequence-inspect",
            workflow="omics",
            kind="python",
            title="Inspect a biological sequence",
            description="Validate and summarize DNA, RNA, or protein sequence composition and ambiguity.",
            entrypoint="biomed_workbench.capabilities.data:sequence_inspect",
            input_schema=_object_schema(
                {"sequence": {"type": "string", "minLength": 1}, "alphabet": {"type": "string", "enum": ["dna", "rna", "protein"]}},
                ("sequence",),
            ),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="data-profile",
            workflow="omics",
            kind="python",
            title="Profile structured scientific rows",
            description="Report table shape, inferred column types, missingness, uniqueness, and numeric ranges.",
            entrypoint="biomed_workbench.capabilities.data:profile_table",
            input_schema=_object_schema({"rows": {"type": "array", "items": {"type": "object"}}}, ("rows",)),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="primer-design",
            workflow="molecular_design",
            kind="python",
            title="Design PCR primer candidates",
            description="Rank facing primer pairs with explicit thermodynamic approximations and validation limits.",
            entrypoint="biomed_workbench.capabilities.molecular:design_primers",
            input_schema=_object_schema(
                {
                    "template": {"type": "string", "minLength": 28},
                    "min_length": {"type": "integer", "minimum": 14, "maximum": 40},
                    "max_length": {"type": "integer", "minimum": 14, "maximum": 40},
                    "target_tm": {"type": "number", "minimum": 20, "maximum": 100},
                    "max_pairs": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                ("template",),
            ),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="crispr-design",
            workflow="molecular_design",
            kind="python",
            title="Discover CRISPR guide candidates",
            description="Find SpCas9 NGG guide contexts on both strands and report transparent heuristic checks.",
            entrypoint="biomed_workbench.capabilities.molecular:crispr_guides",
            input_schema=_object_schema(
                {
                    "sequence": {"type": "string", "minLength": 18},
                    "guide_length": {"type": "integer", "minimum": 15, "maximum": 25},
                    "max_guides": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                ("sequence",),
            ),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="restriction-plan",
            workflow="molecular_design",
            kind="python",
            title="Map restriction enzyme sites",
            description="Locate selected restriction motifs with explicit one-based coordinates.",
            entrypoint="biomed_workbench.capabilities.molecular:restriction_sites",
            input_schema=_object_schema(
                {"sequence": {"type": "string", "minLength": 1}, "enzymes": {"type": "array", "items": {"type": "string"}, "nullable": True}},
                ("sequence",),
            ),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="sequence-back-translate",
            workflow="molecular_design",
            kind="python",
            title="Back-translate a protein sequence",
            description="Create a deterministic preferred-codon coding sequence with explicit optimization limits.",
            entrypoint="biomed_workbench.capabilities.molecular:back_translate",
            input_schema=_object_schema(
                {"protein": {"type": "string", "minLength": 1}, "organism": {"type": "string", "enum": ["human", "ecoli"]}},
                ("protein",),
            ),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="dilution-plan",
            workflow="wetlab",
            kind="python",
            title="Plan a serial dilution",
            description="Calculate stepwise concentrations and transfer volumes for a constant-factor dilution series.",
            entrypoint="biomed_workbench.capabilities.experiment:serial_dilution",
            input_schema=_object_schema(
                {
                    "initial_concentration": {"type": "number", "minimum": 0.0},
                    "dilution_factor": {"type": "number", "minimum": 1.0},
                    "steps": {"type": "integer", "minimum": 1, "maximum": 100},
                    "final_volume_ul": {"type": "number", "minimum": 0.0},
                },
                ("initial_concentration", "dilution_factor", "steps", "final_volume_ul"),
            ),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="pcr-plan",
            workflow="wetlab",
            kind="python",
            title="Calculate a PCR master mix",
            description="Calculate per-reaction and overage-adjusted PCR component volumes with conservation checks.",
            entrypoint="biomed_workbench.capabilities.experiment:pcr_mix",
            input_schema=_object_schema(
                {
                    "reactions": {"type": "integer", "minimum": 1, "maximum": 100000},
                    "reaction_volume_ul": {"type": "number", "minimum": 0.0},
                    "components": {"type": "object"},
                    "overage_percent": {"type": "number", "minimum": 0, "maximum": 100},
                },
                ("reactions", "reaction_volume_ul", "components"),
            ),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="dose-response",
            workflow="wetlab",
            kind="python",
            title="Summarize a dose-response series",
            description="Check monotonicity and estimate an empirical half-range concentration on a log scale.",
            entrypoint="biomed_workbench.capabilities.experiment:dose_response_summary",
            input_schema=_object_schema(
                {
                    "concentrations": {"type": "array", "items": {"type": "number"}, "minItems": 3},
                    "responses": {"type": "array", "items": {"type": "number"}, "minItems": 3},
                    "direction": {"type": "string", "enum": ["decreasing", "increasing"]},
                },
                ("concentrations", "responses"),
            ),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="growth-curve",
            workflow="wetlab",
            kind="python",
            title="Summarize a growth curve",
            description="Estimate maximum log-phase growth rate and doubling time from positive measurements.",
            entrypoint="biomed_workbench.capabilities.experiment:growth_curve_summary",
            input_schema=_object_schema(
                {
                    "times": {"type": "array", "items": {"type": "number"}, "minItems": 3},
                    "values": {"type": "array", "items": {"type": "number"}, "minItems": 3},
                    "window": {"type": "integer", "minimum": 2},
                },
                ("times", "values"),
            ),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="literature-evidence",
            workflow="evidence",
            kind="service",
            title="Retrieve literature evidence",
            description="Search PubMed or PMC and return normalized summaries with query provenance.",
            entrypoint="biomed_workbench.capabilities.evidence:literature_evidence",
            input_schema=_object_schema(
                {
                    "query": {"type": "string", "minLength": 1},
                    "max_records": {"type": "integer", "minimum": 1, "maximum": 100},
                    "database": {"type": "string", "enum": ["pubmed", "pmc"]},
                },
                ("query",),
            ),
            requirements=(), access="public_api", mutability="read_only",
        ),
        Capability(
            id="gene-evidence",
            workflow="evidence",
            kind="service",
            title="Build an NCBI gene evidence bundle",
            description="Resolve gene records and linked protein, ClinVar, and PubMed identifiers in one bounded workflow.",
            entrypoint="biomed_workbench.capabilities.evidence:gene_evidence",
            input_schema=_object_schema(
                {
                    "gene": {"type": "string", "minLength": 1},
                    "organism": {"type": "string", "minLength": 1},
                    "max_links": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                ("gene",),
            ),
            requirements=(), access="public_api", mutability="read_only",
        ),
        Capability(
            id="variant-evidence",
            workflow="evidence",
            kind="service",
            title="Build an NCBI variant evidence bundle",
            description="Retrieve ClinVar summaries and linked gene and PubMed records with interpretation limits.",
            entrypoint="biomed_workbench.capabilities.evidence:variant_evidence",
            input_schema=_object_schema(
                {
                    "query": {"type": "string", "minLength": 1},
                    "max_records": {"type": "integer", "minimum": 1, "maximum": 100},
                    "max_links": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                ("query",),
            ),
            requirements=(), access="public_api", mutability="read_only",
        ),
        Capability(
            id="container-plan",
            workflow="runtime",
            kind="python",
            title="Build a container execution plan",
            description="Construct a validated Docker or Podman argument vector without starting a container.",
            entrypoint="biomed_workbench.services.compute:container_plan",
            input_schema=_object_schema(
                {
                    "image": {"type": "string", "minLength": 3},
                    "command": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "mounts": {"type": "array", "items": {"type": "object"}, "nullable": True},
                    "gpu": {"type": "boolean"},
                    "engine": {"type": "string", "enum": ["docker", "podman"]},
                    "workdir": {"type": "string", "nullable": True},
                },
                ("image", "command"),
            ),
            requirements=(), access="local_runtime", mutability="read_only",
        ),
        Capability(
            id="slurm-plan",
            workflow="runtime",
            kind="python",
            title="Build a SLURM job plan",
            description="Construct a validated, quoted batch script and resource record without submitting work.",
            entrypoint="biomed_workbench.services.compute:slurm_plan",
            input_schema=_object_schema(
                {
                    "command": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "job_name": {"type": "string", "minLength": 1},
                    "cpus": {"type": "integer", "minimum": 1, "maximum": 4096},
                    "memory_gb": {"type": "integer", "minimum": 1, "maximum": 1048576},
                    "time_minutes": {"type": "integer", "minimum": 1, "maximum": 525600},
                    "gpus": {"type": "integer", "minimum": 0, "maximum": 128},
                    "partition": {"type": "string", "nullable": True},
                    "output": {"type": "string", "minLength": 1},
                },
                ("command", "job_name", "cpus", "memory_gb", "time_minutes"),
            ),
            requirements=(), access="local_runtime", mutability="read_only",
        ),
        Capability(
            id="local-model-plan",
            workflow="molecular_design",
            kind="python",
            title="Build a local scientific model plan",
            description="Construct a validated command for an allowed local structure, search, design, or docking backend.",
            entrypoint="biomed_workbench.services.compute:local_model_plan",
            input_schema=_object_schema(
                {
                    "backend": {"type": "string", "enum": ["boltz", "foldseek", "mmseqs", "proteinmpnn", "diffdock"]},
                    "inputs": {"type": "object"},
                },
                ("backend", "inputs"),
            ),
            requirements=(), access="local_runtime", mutability="read_only",
        ),
        Capability(
            id="expression-qc",
            workflow="omics", kind="python", title="Quality-control an expression matrix",
            description="Compute library sizes, detected features, sparsity, and zero-library warnings for a numeric matrix.",
            entrypoint="biomed_workbench.capabilities.omics:expression_qc",
            input_schema=_object_schema({"genes":{"type":"array","items":{"type":"string"},"minItems":1},"samples":{"type":"array","items":{"type":"string"},"minItems":1},"matrix":{"type":"array","items":{"type":"array"},"minItems":1}},("genes","samples","matrix")),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="differential-expression",
            workflow="omics", kind="python", title="Run compact differential expression",
            description="Calculate feature means, log2 fold changes, Welch tests, and BH-adjusted p-values for two groups.",
            entrypoint="biomed_workbench.capabilities.omics:differential_expression",
            input_schema=_object_schema({"genes":{"type":"array","items":{"type":"string"},"minItems":1},"group_a":{"type":"array","items":{"type":"array"},"minItems":1},"group_b":{"type":"array","items":{"type":"array"},"minItems":1},"pseudocount":{"type":"number","minimum":0.000000001}},("genes","group_a","group_b")),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="enrichment-analysis",
            workflow="omics", kind="python", title="Run gene-set overrepresentation",
            description="Calculate one-sided hypergeometric enrichment and BH correction against an explicit background.",
            entrypoint="biomed_workbench.capabilities.omics:enrichment_analysis",
            input_schema=_object_schema({"query_genes":{"type":"array","items":{"type":"string"},"minItems":1},"gene_sets":{"type":"object"},"background_genes":{"type":"array","items":{"type":"string"},"minItems":1}},("query_genes","gene_sets","background_genes")),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="single-cell-qc",
            workflow="omics", kind="python", title="Quality-control single-cell count data",
            description="Compute per-cell counts, detected genes, mitochondrial fraction, and transparent threshold flags.",
            entrypoint="biomed_workbench.capabilities.omics:single_cell_qc",
            input_schema=_object_schema({"genes":{"type":"array","items":{"type":"string"},"minItems":1},"cells":{"type":"array","items":{"type":"string"},"minItems":1},"matrix":{"type":"array","items":{"type":"array"},"minItems":1},"mitochondrial_prefixes":{"type":"array","items":{"type":"string"},"nullable":True},"min_counts":{"type":"number","minimum":0},"min_genes":{"type":"integer","minimum":0},"max_mito_percent":{"type":"number","minimum":0,"maximum":100}},("genes","cells","matrix")),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="variant-summary",
            workflow="omics", kind="python", title="Summarize structured variants",
            description="Count SNVs, indels, MNVs, filters, chromosomes, transitions, transversions, and Ti/Tv ratio.",
            entrypoint="biomed_workbench.capabilities.omics:variant_summary",
            input_schema=_object_schema({"variants":{"type":"array","items":{"type":"object"}}},("variants",)),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="network-analysis",
            workflow="omics", kind="python", title="Summarize a biological network",
            description="Deduplicate edges and report degrees, hubs, and weakly connected components.",
            entrypoint="biomed_workbench.capabilities.omics:network_summary",
            input_schema=_object_schema({"edges":{"type":"array","items":{"type":"array"}},"directed":{"type":"boolean"}},("edges",)),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="image-profile", workflow="imaging", kind="python", title="Profile an image array",
            description="Report shape, range, mean, variance, percentiles, and zero fraction for a finite image matrix.",
            entrypoint="biomed_workbench.capabilities.imaging:image_profile",
            input_schema=_object_schema({"image":{"type":"array","items":{"type":"array"},"minItems":1}},("image",)),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="image-segment", workflow="imaging", kind="python", title="Segment image components",
            description="Threshold a small image and measure connected-component area, centroid, bounds, perimeter, and circularity.",
            entrypoint="biomed_workbench.capabilities.imaging:segment_components",
            input_schema=_object_schema({"image":{"type":"array","items":{"type":"array"},"minItems":1},"threshold":{"type":"number"},"connectivity":{"type":"integer","enum":[4,8]},"minimum_area":{"type":"integer","minimum":1},"polarity":{"type":"string","enum":["high","low"]}},("image","threshold")),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="image-colocalization", workflow="imaging", kind="python", title="Measure two-channel colocalization",
            description="Calculate Pearson intensity correlation and thresholded Manders overlap coefficients.",
            entrypoint="biomed_workbench.capabilities.imaging:colocalization",
            input_schema=_object_schema({"channel_a":{"type":"array","items":{"type":"array"},"minItems":1},"channel_b":{"type":"array","items":{"type":"array"},"minItems":1},"threshold_a":{"type":"number"},"threshold_b":{"type":"number"}},("channel_a","channel_b")),
            requirements=(), access="offline", mutability="read_only",
        ),
        Capability(
            id="point-tracking", workflow="imaging", kind="python", title="Track points across frames",
            description="Link point detections with a bounded one-to-one nearest-neighbor rule and explicit tracking limits.",
            entrypoint="biomed_workbench.capabilities.imaging:track_points",
            input_schema=_object_schema({"frames":{"type":"array","items":{"type":"array"},"minItems":1},"max_distance":{"type":"number","minimum":0.000000001}},("frames","max_distance")),
            requirements=(), access="offline", mutability="read_only",
        ),
    )
    for definition in definitions:
        register(definition)


_register_builtins()
