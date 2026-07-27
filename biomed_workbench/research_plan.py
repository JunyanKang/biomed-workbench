"""Compile a natural-language objective into an agent-ready scientific run plan."""

from __future__ import annotations

from typing import Any

from .modules.contract import ArtifactPort, ModuleManifest
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry
from .router import ports_compatible, route


_SINGLE_CELL_PROGRAM_STAGE: dict[str, int] = {
    "single-cell-droplet-decontamination": 0,
    "single-cell-foundation-workflow": 1,
    "single-cell-qc": 1,
    "single-cell-doublet-detection": 2,
    "single-cell-batch-integration": 3,
    "single-cell-generative-modeling": 3,
    "single-cell-multimodal-integration": 3,
    "single-cell-atac-regulatory": 3,
    "single-cell-marker-discovery": 4,
    "single-cell-reference-annotation": 4,
    "single-cell-atlas-annotation": 4,
    "single-cell-donor-inference": 5,
    "single-cell-complex-inference": 5,
    "single-cell-communication": 6,
    "single-cell-regulatory-network": 6,
    "single-cell-spatial-analysis": 6,
    "single-cell-trajectory-topology": 6,
    "single-cell-trajectory-velocity": 6,
    "single-cell-fate-mapping": 7,
    "single-cell-regulatory-velocity": 7,
}


_EVIDENCE_PROGRAM_STAGE: dict[str, int] = {
    "gene-identifier-resolution": 0,
    "citation-record-resolution": 0,
    "ncbi-info": 0,
    "ncbi-search": 0,
    "uniprot-to-ensembl-evidence": 0,
    "literature-evidence": 1,
    "preprint-evidence": 1,
    "ncbi-summary": 1,
    "ncbi-fetch": 1,
    "ncbi-link": 1,
    "ncbi-search-summary": 1,
    "gene-evidence": 1,
    "ensembl-gene-evidence": 1,
    "uniprot-protein-evidence": 1,
    "dbsnp-rsid-evidence": 1,
    "variant-evidence": 1,
    "gnomad-gene-constraint-evidence": 1,
    "hpo-term-evidence": 1,
    "quickgo-term-evidence": 1,
    "reactome-pathway-evidence": 1,
    "gene-set-library-catalog": 1,
    "structure-search": 1,
    "structure-evidence": 1,
    "clinical-trial-evidence": 1,
    "cbioportal-study-evidence": 1,
    "chemical-evidence": 1,
    "gene-ortholog-evidence": 2,
    "gene-set-library-membership": 2,
    "reactome-overrepresentation-evidence": 2,
    "cbioportal-gene-mutation-evidence": 2,
    "cbioportal-gene-copy-number-evidence": 2,
    "copy-number-event-summary": 2,
    "structure-polymer-entities": 2,
    "structure-ligands": 2,
    "alphafold-structure-evidence": 2,
    "protein-disorder-evidence": 2,
    "opentargets-target-disease-evidence": 2,
    "pdf-evidence-extraction": 2,
    "citation-resolution-adjudication": 3,
    "source-freshness-audit": 3,
    "research-contract-consistency-audit": 3,
}


_PUBLICATION_PROGRAM_STAGE: dict[str, int] = {
    "manuscript-revision-base": 0,
    "figure-specification": 0,
    "citation-audit": 1,
    "assertion-citation-coverage-audit": 1,
    "claim-evidence-integrity-audit": 1,
    "temporal-integrity-audit": 1,
    "manuscript-audit": 1,
    "reviewer-assessment": 1,
    "response-matrix": 2,
    "manuscript-revision-lineage": 2,
    "patent-disclosure-audit": 2,
    "patent-claim-support-audit": 3,
    "patent-claim-structure-audit": 3,
    "patent-draft-readiness-audit": 4,
    "patent-flowchart-svg": 4,
    "presentation-delivery-plan": 4,
}


_MOLECULAR_PROGRAM_STAGE: dict[str, int] = {
    "sequence-inspect": 0,
    "genbank-coding-sequence-extraction": 0,
    "open-reading-frame-annotation": 0,
    "sequence-pairwise-alignment": 0,
    "aligned-protein-conservation": 0,
    "sequence-variant-localization": 0,
    "sequence-back-translate": 0,
    "primer-design": 1,
    "crispr-design": 1,
    "restriction-plan": 1,
    "golden-gate-plan": 1,
    "sanger-verification-coverage": 1,
    "pcr-primer-pair-selection": 2,
    "primer-pair-specificity-screen": 3,
    "pcr-amplicon-simulation": 3,
    "rna-secondary-structure-summary": 2,
    "glycosylation-scan": 2,
    "protein-secondary-structure": 2,
    "cd-thermal-transition-summary": 2,
    "itc-single-site-binding": 2,
    "enzyme-kinetics": 2,
    "structure-quality-assessment": 3,
    "structure-chain-comparison": 3,
    "structure-interactive-visualization": 3,
    "docking-pose-review": 4,
    "chemical-substructure-filter": 4,
}


_OMICS_PROGRAM_STAGE: dict[str, int] = {
    "data-profile": 0,
    "read-quality-fastqc": 0,
    "read-quality-fastp": 0,
    "read-contamination-screen": 0,
    "quality-report-multiqc": 1,
    "dna-align-bwa-mem-single": 1,
    "alignment-sort-index-samtools": 2,
    "alignment-quality-samtools": 2,
    "variant-decompress-bgzip": 3,
    "variant-filter-vcf": 3,
    "variant-region-query-tabix": 3,
    "genome-coordinate-liftover": 3,
    "interval-overlap-bedtools": 3,
    "multi-sample-variant-concordance": 3,
    "tumor-mutation-burden-vcf": 3,
    "tumor-mutation-burden": 3,
    "assembly-reference-alignment": 3,
    "bulk-chromatin-peak-calling": 4,
    "sequence-motif-enrichment": 4,
    "cool-contact-evidence": 4,
    "expression-qc": 4,
    "differential-expression": 5,
    "enrichment-analysis": 5,
    "metagene-factorization-nmf": 5,
    "network-analysis": 5,
    "ddr-coexpression-hypothesis-network": 5,
    "gwas-susie-fine-mapping": 6,
    "rrblup-genomic-prediction": 6,
    "comparative-sequence-phylogeny": 6,
    "msprime-demographic-simulation": 6,
}


_STATISTICS_PROGRAM_STAGE: dict[str, int] = {
    "data-profile": 0,
    "cohort-summary": 0,
    "expression-qc": 0,
    "survival-analysis": 1,
    "biomarker-performance": 1,
    "classification-gold-set-evaluation": 1,
    "fixed-period-cosinor": 1,
    "differential-expression": 1,
    "dose-response": 1,
    "growth-curve": 1,
    "qpcr-relative-expression": 1,
    "adverse-event-summary": 2,
    "clinical-report-audit": 2,
    "clinical-decision-boundary-audit": 2,
}


_PROGRAM_STAGE_MAPS: tuple[dict[str, int], ...] = (
    _EVIDENCE_PROGRAM_STAGE,
    _PUBLICATION_PROGRAM_STAGE,
    _MOLECULAR_PROGRAM_STAGE,
    _OMICS_PROGRAM_STAGE,
    _STATISTICS_PROGRAM_STAGE,
    _SINGLE_CELL_PROGRAM_STAGE,
)


def _format_tokens(port: ArtifactPort) -> list[str]:
    return sorted(
        f"{format_contract.name}@{version}"
        for format_contract in port.formats
        for version in format_contract.versions
    )


def _port_summary(port: ArtifactPort) -> dict[str, object]:
    return {
        "name": port.name,
        "artifact_type": port.artifact_type,
        "source_policy": port.source_policy,
        "accepted_formats": _format_tokens(port),
        "processing_levels": list(port.processing_levels),
        "required_metadata": list(port.required_metadata),
    }


def _execution_templates(module: ModuleManifest) -> list[dict[str, object]]:
    templates = [
        {
            "kind": "code_template",
            "path": template.path,
            "language": template.language,
            "purpose": template.purpose,
            "quality_gate_ids": list(template.quality_gate_ids),
            "requires_adaptation": template.requires_adaptation,
        }
        for template in module.code_templates
    ]
    if module.agent_protocol is not None:
        templates.extend(
            {
                "kind": "agent_protocol_section",
                "id": section.id,
                "purpose": section.purpose,
                "template_files": list(section.template_files),
                "required_logic": list(section.required_logic),
                "output_artifact_types": list(section.output_artifact_types),
            }
            for section in module.agent_protocol.template_sections
        )
    return templates


def _port_bindings(selected: tuple[ModuleManifest, ...]) -> dict[str, dict[str, str]]:
    """Bind compatible selected producers to consumer ports in a routed plan."""
    position = {module.id: index for index, module in enumerate(selected)}
    bindings: dict[str, dict[str, str]] = {}
    for consumer in selected:
        bound = {}
        for port in consumer.input_artifacts:
            candidates = [
                producer
                for producer in selected
                if producer.id != consumer.id
                and position[producer.id] < position[consumer.id]
                and any(ports_compatible(output, port) for output in producer.output_artifacts)
            ]
            if candidates:
                bound[port.name] = candidates[-1].id
        bindings[consumer.id] = bound
    return bindings


def _scientific_dependencies(selected: tuple[ModuleManifest, ...]) -> dict[str, tuple[str, ...]]:
    """Add research-program ordering when artifact ports are intentionally project-owned.

    Many biomedical modules accept project inputs because real analyses often
    need human-reviewed objects rather than blindly consuming another module's
    file. When a broad program selects several related single-cell modules,
    the plan still needs to communicate the scientific order: input validation
    before artifact correction, correction before annotation, annotation before
    donor-aware inference, and inference before dynamics/regulatory delivery.
    """
    selected_ids = {module.id for module in selected}
    dependencies: dict[str, set[str]] = {module.id: set() for module in selected}
    for stage_map in _PROGRAM_STAGE_MAPS:
        staged = {module_id: stage for module_id, stage in stage_map.items() if module_id in selected_ids}
        if len(staged) < 2:
            continue
        for module_id, stage in staged.items():
            dependencies[module_id].update(
                upstream_id
                for upstream_id, upstream_stage in staged.items()
                if upstream_stage < stage
            )
    non_publication = {module.id for module in selected if module.domains[0] != "publication"}
    if non_publication:
        for module in selected:
            if module.domains[0] == "publication":
                dependencies[module.id].update(non_publication)
    return {module_id: tuple(sorted(values)) for module_id, values in dependencies.items()}


def _dependencies(
    bindings: dict[str, dict[str, str]],
    scientific_dependencies: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, tuple[str, ...]]:
    dependency_map = {
        module_id: tuple(dict.fromkeys(port_bindings.values()))
        for module_id, port_bindings in bindings.items()
    }
    for module_id, extra_dependencies in (scientific_dependencies or {}).items():
        dependency_map[module_id] = tuple(dict.fromkeys((*dependency_map.get(module_id, ()), *extra_dependencies)))
    return dependency_map


def _layers(selected: tuple[ModuleManifest, ...], dependencies: dict[str, tuple[str, ...]]) -> list[dict[str, object]]:
    remaining = {module.id: set(dependencies[module.id]) for module in selected}
    order = {module.id: index for index, module in enumerate(selected)}
    layers = []
    while remaining:
        ready = sorted((module_id for module_id, needs in remaining.items() if not needs), key=order.__getitem__)
        if not ready:
            raise ValueError("selected module contracts contain a dependency cycle")
        layers.append({"mode": "parallel" if len(ready) > 1 else "serial", "module_ids": ready})
        deltas = set(ready)
        for module_id in ready:
            del remaining[module_id]
        for needs in remaining.values():
            needs.difference_update(deltas)
    return layers


def _plan_type(layers: list[dict[str, object]]) -> str:
    if len(layers) == 1 and len(layers[0]["module_ids"]) == 1:
        return "single"
    if len(layers) == 1:
        return "parallel"
    if any(len(layer["module_ids"]) > 1 for layer in layers):
        return "mixed"
    return "serial"


def _evidence_contract(module: ModuleManifest) -> dict[str, object]:
    return {
        "module_version": module.version,
        "compatibility_row_ids": [row.id for row in module.compatibility_matrix],
        "regression_evidence_ids": sorted(
            {evidence_id for row in module.compatibility_matrix for evidence_id in row.regression_evidence_ids}
        ),
        "end_to_end_evidence_ids": sorted(
            {evidence_id for row in module.compatibility_matrix for evidence_id in row.end_to_end_evidence_ids}
        ),
        "required_tool_identities": [tool.identity for tool in module.tool_requirements if tool.required],
        "required_dependency_identities": [dependency.identity for dependency in module.dependencies if dependency.required],
        "provenance_fields": (
            list(module.agent_protocol.provenance_fields)
            if module.agent_protocol is not None
            else [
                "input-artifact-digest",
                "module-version",
                "template-digest",
                "actual-tool-versions",
                "quality-gate-results",
            ]
        ),
        "claim_level": module.maturity,
    }


def compile_research_plan(
    objective: str,
    *,
    per_workflow: int = 3,
    registry: ModuleRegistry | None = None,
) -> dict[str, Any]:
    """Return the bounded, non-evidentiary execution briefing for one objective.

    This bridges natural-language routing and actual Codex-led execution. It
    intentionally does not invent project artifacts, parameters, environment
    versions, or scientific conclusions.
    """
    active = registry or ModuleRegistry.discover(BUILTIN_ROOT)
    routed = route(objective, per_workflow=per_workflow, registry=active)
    selected_ids = tuple(dict.fromkeys(routed["selected_module_ids"]))
    selected = tuple(active.get(module_id) for module_id in selected_ids)
    port_bindings = _port_bindings(selected)
    dependencies = _dependencies(port_bindings, _scientific_dependencies(selected))
    execution_layers = _layers(selected, dependencies)
    candidate_reasons = {
        candidate["id"]: candidate["selection_reasons"]
        for step in routed["steps"]
        for candidate in step["candidates"]
        if candidate["id"] in selected_ids
    }
    modules = []
    unresolved_inputs = []
    unresolved_required_inputs = []
    for module in selected:
        bound_port_names = set(port_bindings[module.id])
        project_inputs = [
            port
            for port in module.input_artifacts
            if port.name not in bound_port_names and port.source_policy != "upstream_required"
        ]
        upstream_inputs = [port for port in module.input_artifacts if port.name in bound_port_names or port.source_policy == "upstream_required"]

        def input_summary(port: ArtifactPort) -> dict[str, object]:
            summary = _port_summary(port)
            producer_id = port_bindings[module.id].get(port.name)
            if producer_id is not None:
                summary["selected_upstream_module_id"] = producer_id
            return summary

        modules.append(
            {
                "id": module.id,
                "version": module.version,
                "title": module.title,
                "domain": module.domains[0],
                "maturity": module.maturity,
                "access": module.access,
                "depends_on": list(dependencies[module.id]),
                "compatibility_row_ids": [row.id for row in module.compatibility_matrix],
                "selection_reasons": candidate_reasons.get(module.id, []),
                "project_inputs": [input_summary(port) for port in project_inputs],
                "upstream_inputs": [input_summary(port) for port in upstream_inputs],
                "outputs": [_port_summary(port) for port in module.output_artifacts],
                "quality_gate_ids": [gate.id for gate in module.quality_gates],
                "optional_credentials": list(module.credentials),
                "execution": {
                    "kind": module.execution.kind,
                    "timeout_seconds": module.execution.timeout_seconds,
                    "max_output_bytes": module.execution.max_output_bytes,
                },
                "input_schema": module.input_schema,
                "execution_templates": _execution_templates(module),
                "evidence_contract": _evidence_contract(module),
            }
        )
        for port in project_inputs:
            unresolved_inputs.append({"module_id": module.id, **_port_summary(port)})
        for port in module.input_artifacts:
            if port.name in bound_port_names:
                continue
            unresolved_required_inputs.append(
                {
                    "module_id": module.id,
                    **_port_summary(port),
                    "resolution": (
                        "missing_selected_upstream_producer"
                        if port.source_policy == "upstream_required"
                        else "project_artifact_required"
                    ),
                }
            )
    return {
        "schema_version": 1,
        "objective": objective,
        "plan_type": _plan_type(execution_layers),
        "matched_workflows": routed["matched_workflows"],
        "selected_module_ids": list(selected_ids),
        "execution_layers": execution_layers,
        "modules": modules,
        "unresolved_project_inputs": unresolved_inputs,
        "unresolved_required_inputs": unresolved_required_inputs,
        "execution_boundary": (
            "This is an agent-ready plan, not an execution record. Codex must inspect real project inputs, "
            "validate every declared contract, and record observed results before scientific interpretation."
        ),
    }
