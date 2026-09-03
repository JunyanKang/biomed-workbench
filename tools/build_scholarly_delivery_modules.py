#!/usr/bin/env python3
"""Build the project-owned scholarly writing and delivery module slice."""

from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILTIN = ROOT / "biomed_workbench" / "modules" / "builtin"
VERIFIED_AT = "2026-08-20"


def _format(orientation: str) -> dict[str, Any]:
    return {
        "name": "inline-json",
        "versions": ["1"],
        "representations": ["structured"],
        "compression": ["none"],
        "required_indexes": [],
        "coordinate_systems": [],
        "genome_build_policy": "not_applicable",
        "genome_builds": [],
        "annotation_releases": [],
        "orientations": [orientation],
    }


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": required}


def _module(
    *,
    module_id: str,
    title: str,
    description: str,
    module_type: str,
    domains: list[str],
    intents: list[str],
    question: str,
    entrypoint: str,
    input_name: str,
    input_type: str,
    output_name: str,
    output_type: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    assumptions: list[str],
    gates: list[tuple[str, str, str]],
    limitations: list[str],
    complements: list[str],
    concept_sources: list[str],
    scientific_stage: int,
    version: str = "0.1.0",
    mutability: str = "read_only",
    verified_at: str = VERIFIED_AT,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": module_id,
        "version": version,
        "title": title,
        "description": description,
        "module_type": module_type,
        "domains": domains,
        "intents": intents,
        "questions": [question],
        "entrypoint": entrypoint,
        "execution": {"kind": "python", "timeout_seconds": 30, "max_output_bytes": 50000000},
        "maturity": "validated",
        "input_artifacts": [{
            "name": input_name,
            "artifact_type": input_type,
            "formats": [_format("request-object")],
            "processing_levels": ["declared"],
            "required_metadata": [],
        }],
        "output_artifacts": [{
            "name": output_name,
            "artifact_type": output_type,
            "formats": [_format("module-output")],
            "processing_levels": ["derived", "validated"],
            "required_metadata": ["module_version", "compatibility_row_id"],
        }],
        "preconditions": ["The declared scholarly source material and project context are available without invented facts."],
        "assumptions": assumptions,
        "quality_gates": [
            {"id": gate_id, "severity": severity, "description": text, "blocks_interpretation": severity in {"major", "fatal"}}
            for gate_id, severity, text in gates
        ],
        "limitations": limitations,
        "evidence_effects": ["validates_scholarly_delivery_readiness"],
        "alternatives": [],
        "complements": complements,
        "tool_requirements": [],
        "dependencies": [{
            "name": "python",
            "ecosystem": "runtime",
            "identity": "python-runtime",
            "required": True,
            "tested_versions": ["3.14.3"],
            "allowed_versions": [">=3.14,<3.15"],
            "version_source": "https://www.python.org/downloads/release/python-3143/",
            "verified_at": verified_at,
            "version_probe": ["biomed_workbench.modules.compatibility:probe_python_runtime"],
            "version_probe_kind": "python_callable",
            "version_probe_timeout_seconds": 5,
            "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
            "purpose": "Execute deterministic scholarly-package validation.",
            "conflicts": [],
            "platforms": ["any"],
        }],
        "compatibility_matrix": [{
            "id": "python-3.14.3-inline-json-1",
            "module_version": version,
            "tool_versions": {},
            "dependency_versions": {"python": [">=3.14,<3.15"]},
            "input_formats": {input_name: ["inline-json@1"]},
            "output_formats": {output_name: ["inline-json@1"]},
            "platforms": ["any"],
            "regression_evidence_ids": [f"{module_id}-regression-v1"],
            "end_to_end_evidence_ids": [f"{module_id}-e2e-v1"],
            "verified_at": verified_at,
        }],
        "access": "offline",
        "mutability": mutability,
        "credentials": [],
        "input_schema": input_schema,
        "output_schema": output_schema,
        "kernel_compatibility": [">=0.2.0,<0.3.0"],
        "provenance": {"license": "Apache-2.0", "concept_sources": concept_sources},
        "routing": {
            "method_aliases": [module_id, title, *intents],
            "exclusion_terms": [],
            "required_any_terms": [],
            "named_method_priority": 100,
        },
        "orchestration": {"scientific_stage": scientific_stage, "requires_reviewed_upstream_types": []},
    }


def _minimal_pptx() -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        files = {
            "[Content_Types].xml": "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
            "ppt/presentation.xml": "<?xml version='1.0'?><p:presentation xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'/>",
            "ppt/slides/slide1.xml": "<?xml version='1.0'?><p:sld xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main' xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Evidence-led title</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
        }
        for name, payload in files.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _specs() -> dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]:
    common_source = [
        "Academic Humanizer 0.3.3, MIT-licensed source skill, adapted into deterministic project-owned preservation gates.",
        "Nature-skills writing and delivery contracts available under their declared source licenses, adapted without copying host-specific runtime assumptions.",
    ]
    modules: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}

    modules["academic-prose-revision-audit"] = (
        _module(
            module_id="academic-prose-revision-audit",
            title="Audit evidence-bound academic prose revisions",
            description="Audit academic prose before editing and compare a supplied revision against exact number, citation, equation, protected-term, structure, claim-strength, voice, venue, and disclosure boundaries.",
            module_type="validation",
            domains=["publication", "research-quality"],
            intents=["academic prose revision", "manuscript polishing audit", "学术语言修订", "论文润色审查", "基金文本语言审查"],
            question="Does this academic revision improve clarity without changing scientific content or exceeding the evidence?",
            entrypoint="biomed_workbench.capabilities.academic_writing:audit_academic_prose_revision",
            input_name="academic_revision",
            input_type="academic_revision_pair",
            output_name="revision_audit",
            output_type="academic_revision_audit",
            input_schema=_schema({
                "original_text": {"type": "string", "minLength": 1},
                "document_type": {"type": "string", "enum": ["research-article", "review-article", "thesis", "rebuttal", "grant-proposal"]},
                "section_kind": {"type": "string", "minLength": 1},
                "target_venue": {"type": "string"},
                "revised_text": {"type": "string"},
                "author_voice_sample": {"type": "string"},
                "structure_policy": {"type": "string", "enum": ["preserve", "allow-declared-change"]},
                "protected_spans": {"type": "array", "items": {"type": "object"}},
                "claim_bindings": {"type": "array", "items": {"type": "object"}},
                "ai_disclosure_evasion": {"type": "boolean"},
                "content_domain": {"type": "string", "enum": ["biological", "clinical", "computational-methods", "mixed"]},
                "scientific_argument": {"type": "object"},
            }, ["original_text", "document_type", "section_kind", "target_venue"]),
            output_schema=_schema({
                "phase": {"type": "string"}, "document": {"type": "object"}, "source_digest": {"type": "string"},
                "revision_digest": {"type": "string", "nullable": True}, "source_audit": {"type": "object"}, "invariant_report": {"type": "object"},
                "claim_findings": {"type": "array"}, "findings": {"type": "array"}, "major_or_fatal_count": {"type": "integer"},
                "ready_for_delivery": {"type": "boolean"}, "required_output": {"type": "object"}, "next_step": {"type": "string"},
                "venue_profile": {"type": "object"}, "scientific_argument": {"type": "object"},
                "revision_contract": {"type": "object"}, "original_text": {"type": "string"}, "revised_text": {"type": "string"},
            }, ["phase", "document", "source_digest", "revision_digest", "source_audit", "invariant_report", "claim_findings", "findings", "major_or_fatal_count", "ready_for_delivery", "required_output", "next_step", "venue_profile", "scientific_argument", "revision_contract", "original_text", "revised_text"]),
            assumptions=["The caller supplies the exact original and revised text and declares any intended structural change."],
            gates=[
                ("academic-prose-content-preservation", "fatal", "Numbers, equations, citations, results, and protected terminology remain unchanged."),
                ("academic-prose-claim-evidence", "major", "Every revised empirical claim remains within its declared evidence strength and preserves required uncertainty."),
                ("academic-prose-voice-and-venue", "major", "The revision follows the supplied author voice and target venue without promotional or formulaic language."),
            ],
            limitations=["The deterministic gate verifies explicit language and preservation constraints; literature-grounded argument building and expert scientific judgment remain required."],
            complements=["biomedical-writing-delivery", "scientific-review-self-correction", "manuscript-revision-base", "manuscript-revision-lineage", "claim-evidence-integrity-audit", "journal-targeting-and-compliance"],
            concept_sources=common_source,
            scientific_stage=5,
            version="0.3.0",
            verified_at="2026-09-03",
        ),
        [{
            "name": "preserve-number-citation-and-claim-scope",
            "input": {
                "original_text": "In 3 cohorts, the association was observed [1].",
                "document_type": "research-article", "section_kind": "results", "target_venue": "Nature Communications",
                "revised_text": "The association was observed in 3 cohorts [1].", "structure_policy": "preserve",
                "protected_spans": [{"kind": "result", "text": "association"}],
                "claim_bindings": [{"claim_id": "C1", "claim": "The association was observed in 3 cohorts.", "claim_level": "associational", "evidence_level": "associational", "evidence_ids": ["E1"], "hedging_required": False, "hedging_preserved": True}],
                "ai_disclosure_evasion": False,
                "content_domain": "biological",
                "scientific_argument": {
                    "central_question": "Is the association reproducible across cohorts?",
                    "central_claim": "The association was observed in three cohorts.",
                    "evidence_sequence": [{"id": "E1", "evidence_role": "discovery", "finding": "The association was observed in three cohorts."}],
                    "literature_context": [],
                    "paragraph_plan": [{"paragraph": 1, "job": "discovery", "evidence_ids": ["E1"]}],
                    "ready_for_drafting": True,
                    "argument_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                },
            },
            "expected_subset": {"phase": "post-revision", "ready_for_delivery": True, "major_or_fatal_count": 0},
        }],
    )

    modules["biomedical-writing-delivery"] = (
        _module(
            module_id="biomedical-writing-delivery",
            title="Deliver evidence-ordered biomedical writing with an HTML review",
            description="Re-run scientific-argument, biomedical-language, claim-strength, and content-preservation checks on an exact revision, then write and reopen a navigable HTML report with evidence and literature links.",
            module_type="delivery",
            domains=["publication", "research-quality"],
            intents=["deliver biomedical writing", "write manuscript html report", "生命科学写作交付", "医学论文语言交付", "项目书写作报告"],
            question="Has the final prose passed scientific-logic and biomedical-language review, and was its HTML report written and reopened?",
            entrypoint="biomed_workbench.capabilities.academic_writing:deliver_biomedical_writing",
            input_name="biomedical_writing_package",
            input_type="biomedical_writing_delivery_request",
            output_name="writing_delivery",
            output_type="biomedical_writing_html_delivery",
            input_schema=_schema({
                "original_text": {"type": "string", "minLength": 1}, "revised_text": {"type": "string", "minLength": 1},
                "document_type": {"type": "string", "enum": ["research-article", "review-article", "thesis", "rebuttal", "grant-proposal"]},
                "section_kind": {"type": "string", "minLength": 1}, "target_venue": {"type": "string"},
                "scientific_argument": {"type": "object"}, "output_directory": {"type": "string", "minLength": 1},
                "author_voice_sample": {"type": "string"}, "structure_policy": {"type": "string", "enum": ["preserve", "allow-declared-change"]},
                "protected_spans": {"type": "array", "items": {"type": "object"}}, "claim_bindings": {"type": "array", "items": {"type": "object"}},
                "content_domain": {"type": "string", "enum": ["biological", "clinical", "computational-methods", "mixed"]},
            }, ["original_text", "revised_text", "document_type", "section_kind", "target_venue", "scientific_argument", "output_directory"]),
            output_schema=_schema({
                "ready_for_delivery": {"type": "boolean"}, "cleaned_text": {"type": "string"},
                "change_review": {"type": "object"}, "report_files": {"type": "object"},
            }, ["ready_for_delivery", "cleaned_text", "change_review", "report_files"]),
            assumptions=["The revised text was produced from the exact source after scientific-argument review."],
            gates=[
                ("biomedical-writing-scientific-logic", "major", "The revision follows a literature-grounded evidence order rather than source order or significance alone."),
                ("biomedical-writing-language", "major", "Outward prose uses life-science or clinical language and excludes internal software-governance vocabulary."),
                ("biomedical-writing-html-delivery", "fatal", "The HTML and JSON reports are written, reopened, and returned with checksums."),
            ],
            limitations=["The module does not invent prose, evidence, citations, or domain knowledge; the host writes the revision and this module verifies and delivers it."],
            complements=["academic-prose-revision-audit", "scientific-review-self-correction", "journal-targeting-and-compliance"],
            concept_sources=common_source,
            scientific_stage=6,
            version="1.0.0",
            mutability="writes_output",
            verified_at="2026-09-03",
        ),
        [{
            "name": "write-and-reopen-controlled-chinese-writing-report",
            "input": {
                "original_text": "端到端分析流水线显示，突变组分化标志物表达降低 20% [1]。",
                "revised_text": "在这一受控示例中，突变组的分化标志物表达较对照组降低 20% [1]；该观察提示二者相关，但不足以建立直接分子机制。",
                "document_type": "research-article", "section_kind": "results", "target_venue": "Nature",
                "output_directory": "reports/biomedical-writing-delivery-acceptance",
                "content_domain": "biological", "structure_policy": "preserve",
                "protected_spans": [{"kind": "result", "text": "20%"}, {"kind": "citation", "text": "[1]"}],
                "claim_bindings": [{
                    "claim_id": "C1", "claim": "突变组分化标志物表达降低。",
                    "claim_level": "associational", "evidence_level": "associational", "evidence_ids": ["E1"],
                    "hedging_required": True, "hedging_preserved": True,
                }],
                "scientific_argument": {
                    "central_question": "受控示例中，因子 X 缺失是否与视网膜祖细胞分化标志物表达降低相关？",
                    "central_claim": "受控示例支持因子 X 缺失与分化标志物表达降低相关，但不能据此建立直接分子机制。",
                    "study_design": "observational", "target_document": "research-article", "target_section": "results",
                    "evidence_sequence": [
                        {
                            "id": "E1", "source_index": 2, "evidence_role": "discovery",
                            "finding": "突变组分化标志物表达均值较对照组低 20%。", "evidence_type": "controlled fixture",
                            "status": "FORMAL", "experimental_unit": "模拟独立样本", "effect": "降低 20%",
                            "uncertainty": "受控格式测试，不作生物学推断", "independent_replicates": 3,
                            "supports_claim": True, "upstream_ids": [],
                            "artifact_path": "tests/fixtures/biomedical_writing/source.tsv", "figure_or_table": "受控源数据",
                            "disposition": "retain",
                        },
                        {
                            "id": "E2", "source_index": 1, "evidence_role": "boundary-null",
                            "finding": "非相关谱系标志物未显示一致变化。", "evidence_type": "controlled fixture",
                            "status": "FORMAL", "experimental_unit": "模拟独立样本", "effect": "未见一致变化",
                            "uncertainty": "受控格式测试，不作生物学推断", "independent_replicates": 3,
                            "supports_claim": False, "upstream_ids": ["E1"], "artifact_path": "", "figure_or_table": "",
                            "disposition": "retain-as-boundary",
                        },
                    ],
                    "excluded_evidence": [],
                    "literature_context": [{
                        "id": "L1", "doi": "10.1038/s41586-024-07855-6",
                        "url": "https://doi.org/10.1038/s41586-024-07855-6",
                        "statement": "该研究用于示范跨专业生命科学论文的论证结构；不作为此受控数据的生物学验证。",
                        "scope": "写作结构示例", "relation": "contextualises", "verified": True,
                    }],
                    "competing_explanations": ["细胞状态构成改变，而不是单个细胞内的分化程序延迟"],
                    "paragraph_plan": [
                        {
                            "paragraph": 1, "job": "discovery", "topic_sentence_content": "突变组分化标志物表达均值较对照组低 20%。",
                            "evidence_ids": ["E1"], "must_report": ["降低 20%", "受控格式测试，不作生物学推断", "模拟独立样本"],
                            "allowed_move": "observation", "transition": "advance the biological question; do not introduce the next method by name",
                        },
                        {
                            "paragraph": 2, "job": "boundary-null", "topic_sentence_content": "非相关谱系标志物未显示一致变化。",
                            "evidence_ids": ["E2"], "must_report": ["未见一致变化", "受控格式测试，不作生物学推断", "模拟独立样本"],
                            "allowed_move": "observation", "transition": "advance the biological question; do not introduce the next method by name",
                        },
                    ],
                    "source_order_preserved": False,
                    "ordering_basis": "declared evidence dependencies, biological argument role, project status, then source order; never p value alone",
                    "findings": [], "major_finding_count": 0, "ready_for_drafting": True,
                    "argument_digest": "a32075ac32ad4826946c53c798f8de408a5b056ec6f0ef230575ee0ec6b1c5f8",
                },
            },
            "expected_subset": {"ready_for_delivery": True, "report_files": {"delivery_verified": True, "renderer_version": "1.1.2"}},
        }],
    )

    modules["research-proposal-quality-audit"] = (
        _module(
            module_id="research-proposal-quality-audit",
            title="Audit research proposal foundations and feasibility",
            description="Validate a proposal scope, research canon, claim-evidence table, argument map, section contracts, aims, agency criteria, feasibility records, and bounded revision stopping rules before prose is promoted.",
            module_type="validation",
            domains=["publication", "experimental-design", "research-quality"],
            intents=["research proposal audit", "grant proposal writing", "specific aims review", "NIH Specific Aims", "基金申请审查", "科研计划书写作", "基金申请可行性审查"],
            question="Are the proposal argument, aims, feasibility, evidence, and agency-specific review criteria complete enough for scientific drafting?",
            entrypoint="biomed_workbench.capabilities.academic_writing:audit_research_proposal",
            input_name="proposal_foundation",
            input_type="research_proposal_foundation",
            output_name="proposal_audit",
            output_type="research_proposal_quality_report",
            input_schema=_schema({
                "mode": {"type": "string", "enum": ["compose", "revise", "hybrid", "qa"]}, "agency": {"type": "string", "minLength": 1},
                "scope": {"type": "object"}, "research_canon": {"type": "array", "items": {"type": "object"}},
                "evidence_table": {"type": "array", "items": {"type": "object"}}, "argument_map": {"type": "object"},
                "section_contracts": {"type": "array", "items": {"type": "object"}}, "aims": {"type": "array", "items": {"type": "object"}},
                "review_criteria": {"type": "array", "items": {"type": "string"}}, "iteration_scores": {"type": "array", "items": {"type": "number"}},
            }, ["mode", "agency", "scope", "research_canon", "evidence_table", "argument_map", "section_contracts", "aims", "review_criteria"]),
            output_schema=_schema({
                "mode": {"type": "string"}, "agency": {"type": "string"}, "foundation": {"type": "object"}, "findings": {"type": "array"},
                "major_finding_count": {"type": "integer"}, "ready_for_scientific_drafting": {"type": "boolean"}, "stop_iteration": {"type": "boolean"},
                "stop_reasons": {"type": "array"}, "next_step": {"type": "string"},
            }, ["mode", "agency", "foundation", "findings", "major_finding_count", "ready_for_scientific_drafting", "stop_iteration", "stop_reasons", "next_step"]),
            assumptions=["Every canon fact, feasibility record, prior result, collaborator, and agency criterion is supplied by the user or a verified source."],
            gates=[
                ("proposal-foundation-complete", "major", "Scope, canon, evidence table, argument map, and section contracts are complete before drafting."),
                ("proposal-aim-feasibility", "major", "Every aim has an independently useful objective, approach, expected outcome, feasibility evidence, and fallback."),
                ("proposal-agency-criteria", "major", "Agency-specific review criteria and first-page commitments are explicit and reviewable."),
            ],
            limitations=["This gate does not predict funding, replace agency instructions, or supply missing preliminary evidence, collaborators, or institutional commitments."],
            complements=["academic-prose-revision-audit", "claim-evidence-integrity-audit", "journal-targeting-and-compliance"],
            concept_sources=common_source,
            scientific_stage=1,
        ),
        [{
            "name": "complete-general-proposal-foundation",
            "input": {
                "mode": "compose", "agency": "Foundation",
                "scope": {"deliverable": "proposal", "target_reader": "scientific panel", "language": "English", "constraints": "10 pages", "version_target": "v1"},
                "research_canon": [{"id": "F1", "fact": "Preliminary assay is feasible."}],
                "evidence_table": [{"claim_id": "C1", "claim": "The assay is feasible.", "status": "evidence-backed", "source_ids": ["F1"]}],
                "argument_map": {"scientific_tension": "Signal is unresolved.", "central_question": "What controls the signal?", "central_thesis": "A bounded perturbation tests the model.", "limitations": ["One model system"]},
                "section_contracts": [{"id": "S1", "purpose": "State the rationale", "inputs": ["F1"], "allowed_claims": ["C1"], "forbidden_claims": ["causality"], "required_evidence": ["F1"], "validation": ["claim mapped"]}],
                "aims": [{"id": "A1", "objective": "Determine the regulator of the signal", "rationale": "The regulator is unresolved", "approach": "Perturb and measure", "expected_outcome": "Bounded regulator estimate", "feasibility_evidence": ["F1"], "independence": "Interpretable alone", "fallback": "Use orthogonal readout"}],
                "review_criteria": ["scientific merit"], "iteration_scores": [],
            },
            "expected_subset": {"ready_for_scientific_drafting": True, "major_finding_count": 0, "stop_iteration": False},
        }],
    )

    modules["statistical-reporting-audit"] = (
        _module(
            module_id="statistical-reporting-audit",
            title="Audit manuscript statistical reporting",
            description="Check experimental units, biological and technical replication, randomization, blinding, exclusions, missingness, model definitions, assumptions, multiplicity, effect sizes, uncertainty, software versions, result wording, and figure statistics.",
            module_type="validation",
            domains=["publication", "statistics", "research-quality"],
            intents=["statistical reporting audit", "statistics methods review", "figure statistics review", "统计报告审查", "图注统计审查"],
            question="Does the manuscript report the design and statistical inference transparently without pseudoreplication or overclaiming?",
            entrypoint="biomed_workbench.capabilities.academic_writing:audit_statistical_reporting",
            input_name="statistical_report",
            input_type="statistical_reporting_records",
            output_name="statistics_audit",
            output_type="statistical_reporting_quality_report",
            input_schema=_schema({
                "design": {"type": "object"}, "analyses": {"type": "array", "items": {"type": "object"}},
                "result_statements": {"type": "array", "items": {"type": "object"}}, "figure_statistics": {"type": "array", "items": {"type": "object"}},
            }, ["design", "analyses", "result_statements"]),
            output_schema=_schema({
                "design_readout": {"type": "object"}, "analysis_count": {"type": "integer"}, "result_statement_count": {"type": "integer"},
                "figure_panel_count": {"type": "integer"}, "findings": {"type": "array"}, "major_finding_count": {"type": "integer"},
                "ready_for_manuscript_reporting": {"type": "boolean"}, "author_input_needed": {"type": "array"}, "limitations": {"type": "array"},
            }, ["design_readout", "analysis_count", "result_statement_count", "figure_panel_count", "findings", "major_finding_count", "ready_for_manuscript_reporting", "author_input_needed", "limitations"]),
            assumptions=["The structured design and analysis records faithfully represent the analysis that was actually executed."],
            gates=[
                ("statistics-unit-and-replication", "major", "The independent unit and biological, technical, nested, and repeated measurements are distinguished."),
                ("statistics-model-reporting", "major", "Every reported comparison declares its model, assumptions, multiplicity, effect estimate, uncertainty, and software version."),
                ("statistics-figure-alignment", "major", "Figure panels define n, tests, comparisons, error bars, and exact p-value policy."),
            ],
            limitations=["The module reviews declared reporting records and does not replace a raw-data reanalysis or specialist statistical review."],
            complements=["manuscript-audit", "figure-specification", "claim-evidence-integrity-audit"],
            concept_sources=["Nature Statistics reporting skill source basis and project-owned deterministic reporting checks."],
            scientific_stage=5,
        ),
        [{
            "name": "complete-statistical-report",
            "input": {
                "design": {"experimental_unit": "mouse", "biological_replicates": 6, "technical_replicates": 2, "randomization": "blocked", "blinding": "analysis blinded", "exclusion_rules": "predefined", "missing_data": "none"},
                "analyses": [{"id": "A1", "comparison_or_model": "treated vs control", "test_or_model": "linear model", "unit_of_analysis": "mouse", "assumptions": ["residual review"], "multiple_comparison_policy": "BH", "effect_size": "mean difference", "uncertainty": "95% CI", "software_version": "R 4.5.1"}],
                "result_statements": [{"analysis_id": "A1", "text": "The estimated mean difference was reported with a 95% CI.", "causal_design": False}],
                "figure_statistics": [{"panel": "1a", "n_definition": "six mice per group", "error_bar_definition": "95% CI", "test_or_model": "linear model", "comparison": "treated vs control", "exact_p_value_policy": "exact values"}],
            },
            "expected_subset": {"ready_for_manuscript_reporting": True, "major_finding_count": 0, "analysis_count": 1},
        }],
    )

    modules["data-availability-audit"] = (
        _module(
            module_id="data-availability-audit",
            title="Audit data availability and repository mapping",
            description="Inventory claim-supporting datasets, classify each access route, validate repository and stable-identifier fields, record justified restrictions and access processes, and check explicit dataset-to-statement mapping.",
            module_type="validation",
            domains=["publication", "evidence", "research-quality"],
            intents=["data availability statement", "repository plan", "FAIR data audit", "数据可用性声明", "数据仓储计划"],
            question="Can readers locate or request every dataset needed to inspect the manuscript's claims?",
            entrypoint="biomed_workbench.capabilities.scholarly_delivery:audit_data_availability",
            input_name="availability_package",
            input_type="data_availability_package",
            output_name="availability_audit",
            output_type="data_availability_quality_report",
            input_schema=_schema({
                "target_journal": {"type": "string"}, "datasets": {"type": "array", "items": {"type": "object"}}, "statement": {"type": "string"},
                "code_availability": {"type": "object"}, "materials_availability": {"type": "object"},
            }, ["target_journal", "datasets", "statement"]),
            output_schema=_schema({
                "target_journal": {"type": "string"}, "dataset_inventory": {"type": "array"}, "dataset_count": {"type": "integer"}, "statement": {"type": "string"},
                "code_availability": {"type": "object"}, "materials_availability": {"type": "object"}, "findings": {"type": "array"},
                "major_finding_count": {"type": "integer"}, "ready_for_manuscript": {"type": "boolean"}, "inventory_digest": {"type": "string"}, "limitations": {"type": "array"},
            }, ["target_journal", "dataset_inventory", "dataset_count", "statement", "code_availability", "materials_availability", "findings", "major_finding_count", "ready_for_manuscript", "inventory_digest", "limitations"]),
            assumptions=["Every dataset needed for main and supplementary claims is included in the inventory."],
            gates=[
                ("availability-dataset-inventory", "major", "Every claim-supporting raw, processed, source-data, model, image, table, and reused dataset has one declared access route."),
                ("availability-repository-identity", "major", "Public and controlled datasets have a repository and stable identifier; restrictions have a reason and access process."),
                ("availability-statement-coverage", "major", "The manuscript statement maps every dataset to its location or governed access route."),
            ],
            limitations=["Current journal policy, consent, governance, repository acceptance, embargo, and identifier activation require authoritative verification."],
            complements=["manuscript-audit", "citation-audit", "journal-targeting-and-compliance"],
            concept_sources=["Nature Data Availability 2.0.0 workflow and FAIR/DataCite-aligned source hierarchy, adapted into a project-owned audit."],
            scientific_stage=5,
        ),
        [{
            "name": "mapped-source-data-within-paper",
            "input": {"target_journal": "Nature", "datasets": [{"id": "D1", "title": "Figure 1 source data", "claim_support_role": "Figure 1", "access_route": "within-paper-or-supplement"}], "statement": "Source data for D1 are provided with this paper."},
            "expected_subset": {"dataset_count": 1, "major_finding_count": 0, "ready_for_manuscript": True},
        }],
    )

    modules["paper-reader-package-audit"] = (
        _module(
            module_id="paper-reader-package-audit",
            title="Audit a bilingual full-paper reader package",
            description="Validate paragraph-level original and Chinese pairs, stable page-addressable source blocks, figure and table assets, source links, translation notes, and complete-package digests without replacing the paper with a summary.",
            module_type="validation",
            domains=["publication", "evidence"],
            intents=["bilingual paper reader", "full paper translation audit", "full-paper bilingual reading", "中英文论文精读", "全文中英对照精读", "全文翻译解读", "论文阅读包审查"],
            question="Is the paper reader complete, bilingual, figure-aware, and traceable to stable source blocks?",
            entrypoint="biomed_workbench.capabilities.scholarly_delivery:audit_paper_reader_package",
            input_name="reader_package",
            input_type="bilingual_paper_reader_package",
            output_name="reader_audit",
            output_type="paper_reader_quality_report",
            input_schema=_schema({
                "paper_markdown": {"type": "string"}, "source_map": {"type": "array", "items": {"type": "object"}}, "translation_notes": {"type": "string"},
                "assets": {"type": "array", "items": {"type": "object"}}, "source_complete": {"type": "boolean"},
            }, ["paper_markdown", "source_map", "translation_notes"]),
            output_schema=_schema({
                "source_block_count": {"type": "integer"}, "text_block_count": {"type": "integer"}, "asset_count": {"type": "integer"}, "source_complete": {"type": "boolean"},
                "findings": {"type": "array"}, "major_finding_count": {"type": "integer"}, "ready_for_reading": {"type": "boolean"},
                "source_map_digest": {"type": "string"}, "package_digest": {"type": "string"}, "limitations": {"type": "array"},
            }, ["source_block_count", "text_block_count", "asset_count", "source_complete", "findings", "major_finding_count", "ready_for_reading", "source_map_digest", "package_digest", "limitations"]),
            assumptions=["Source blocks and page numbers are extracted from the exact user-supplied or lawfully accessible paper artifact."],
            gates=[
                ("reader-source-map-complete", "major", "Every substantive text, caption, figure, and table block has a stable ID and page location."),
                ("reader-bilingual-pairs", "major", "Every extractable substantive text and caption block retains original and Chinese text without changing numbers, citations, equations, or terminology."),
                ("reader-assets-traceable", "major", "Every figure and table asset has a source pointer, digest, and visible placement in the reading file."),
            ],
            limitations=["Translation accuracy, OCR quality, and scientific crop fidelity still require source-aware human and visual review."],
            complements=["pdf-evidence-extraction", "citation-record-resolution", "figure-specification"],
            concept_sources=["Nature Reader 2.0.0 full-paper source-map and bilingual output contract, adapted into a project-owned package audit."],
            scientific_stage=2,
        ),
        [{
            "name": "one-block-bilingual-reader",
            "input": {"paper_markdown": "<a id=\"S001\"></a>\n**Source:** p.1 S001\n\n**Original:** Cells changed.\n\n**中文:** 细胞发生变化。", "source_map": [{"id": "S001", "type": "text", "page": 1, "original": "Cells changed.", "translation": "细胞发生变化。"}], "translation_notes": "Terminology checked.", "assets": [], "source_complete": True},
            "expected_subset": {"source_block_count": 1, "text_block_count": 1, "major_finding_count": 0, "ready_for_reading": True},
        }],
    )

    modules["experiment-log-standardization"] = (
        _module(
            module_id="experiment-log-standardization",
            title="Standardize a traceable experiment log",
            description="Create a deterministic experiment identity, structured record, Markdown log, raw-material archive plan, anomaly routing, and unresolved-field gate from declared samples, steps, observations, and source digests.",
            module_type="transform",
            domains=["wetlab", "research-quality"],
            intents=["experiment log", "laboratory record", "实验日志标准化", "实验记录归档"],
            question="Can this experiment be recorded with stable sample identities, complete procedural context, source files, and explicit anomalies?",
            entrypoint="biomed_workbench.capabilities.scholarly_delivery:standardize_experiment_log",
            input_name="experiment_record",
            input_type="raw_experiment_record",
            output_name="standardized_log",
            output_type="standardized_experiment_log",
            input_schema=_schema({
                "experiment_date": {"type": "string"}, "system_code": {"type": "string"}, "device_code": {"type": "string"}, "daily_sequence": {"type": "integer"},
                "experiment_type": {"type": "string"}, "objective": {"type": "string"}, "sample_batches": {"type": "array", "items": {"type": "object"}},
                "steps": {"type": "array", "items": {"type": "object"}}, "observations": {"type": "array", "items": {"type": "object"}},
                "raw_materials": {"type": "array", "items": {"type": "object"}}, "anomalies": {"type": "array", "items": {"type": "object"}},
            }, ["experiment_date", "system_code", "device_code", "daily_sequence", "experiment_type", "objective", "sample_batches", "steps", "observations", "raw_materials"]),
            output_schema=_schema({
                "experiment_id": {"type": "string"}, "record": {"type": "object"}, "log_markdown": {"type": "string"}, "archive_plan": {"type": "object"},
                "issues": {"type": "array"}, "major_issue_count": {"type": "integer"}, "ready_to_write": {"type": "boolean"}, "record_digest": {"type": "string"}, "limitations": {"type": "array"},
            }, ["experiment_id", "record", "log_markdown", "archive_plan", "issues", "major_issue_count", "ready_to_write", "record_digest", "limitations"]),
            assumptions=["Dates, device codes, sample batches, steps, observations, anomalies, and raw-file digests are factual user or instrument records."],
            gates=[
                ("experiment-log-identity", "major", "Experiment and sample-batch identities are stable and unique."),
                ("experiment-log-procedure", "major", "Every step has an action, conditions, and valid sample bindings."),
                ("experiment-log-source-and-anomaly", "major", "Raw materials have paths and digests; uncertain fields and anomalies remain explicit."),
            ],
            limitations=["Writing into an external vault and archiving raw files require explicit destination permission and byte-preserving file operations."],
            complements=["claim-evidence-integrity-audit"],
            concept_sources=["Nature Experiment Log 1.0.0, MIT-licensed source skill, adapted to biomedical experiment and sample identities."],
            scientific_stage=0,
        ),
        [{
            "name": "complete-bounded-experiment-log",
            "input": {"experiment_date": "2026-08-20", "system_code": "RT", "device_code": "B", "daily_sequence": 1, "experiment_type": "qPCR", "objective": "Measure target expression", "sample_batches": [{"sample_batch": "RT-1-B1", "description": "retina samples"}], "steps": [{"action": "Run qPCR", "conditions": {"cycles": 40}, "sample_batches": ["RT-1-B1"]}], "observations": [{"text": "Amplification completed."}], "raw_materials": [{"path": "raw/run.csv", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}], "anomalies": []},
            "expected_subset": {"experiment_id": "RT-B-260820-001", "major_issue_count": 0, "ready_to_write": True},
        }],
    )

    modules["literature-landscape-audit"] = (
        _module(
            module_id="literature-landscape-audit",
            title="Audit a multi-source literature landscape",
            description="Audit a bounded or recurring literature search plan, exact source coverage, identifier-based deduplication, six declared prioritisation dimensions, strict journal scope, retraction states, citation contexts, and author or affiliation overlap for candidate independent citing works.",
            module_type="validation",
            domains=["evidence", "publication"],
            intents=["multi-source literature landscape", "recurring literature monitoring", "independent citing work audit", "多来源文献检索审查", "系统文献格局分析", "判断研究空白", "定期文献追踪", "独立他引审查", "高影响力他引核验"],
            question="Is this literature landscape broad enough for its declared scope, transparently prioritized, deduplicated, and explicit about independent citation context?",
            entrypoint="biomed_workbench.capabilities.scholarly_delivery:audit_literature_landscape",
            input_name="literature_landscape",
            input_type="literature_landscape_records",
            output_name="landscape_audit",
            output_type="literature_landscape_quality_report",
            input_schema=_schema({
                "query_plan": {"type": "object"}, "records": {"type": "array", "items": {"type": "object"}},
                "scoring_weights": {"type": "object"}, "strict_journal_scope": {"type": "array", "items": {"type": "string"}},
                "focal_authors": {"type": "array", "items": {"type": "string"}}, "focal_affiliations": {"type": "array", "items": {"type": "string"}},
            }, ["query_plan", "records"]),
            output_schema=_schema({
                "query_plan": {"type": "object"}, "scoring_weights": {"type": "object"}, "record_count": {"type": "integer"},
                "source_coverage": {"type": "object"}, "strict_journal_scope": {"type": "array"}, "ranked_records": {"type": "array"},
                "duplicates": {"type": "array"}, "independent_citing_work_ids": {"type": "array"}, "findings": {"type": "array"},
                "blocking_finding_count": {"type": "integer"}, "ready_for_synthesis": {"type": "boolean"}, "landscape_digest": {"type": "string"},
                "limitations": {"type": "array"},
            }, ["query_plan", "scoring_weights", "record_count", "source_coverage", "strict_journal_scope", "ranked_records", "duplicates", "independent_citing_work_ids", "findings", "blocking_finding_count", "ready_for_synthesis", "landscape_digest", "limitations"]),
            assumptions=["Every record, score, source level, citation context, author identity, affiliation, and retraction status comes from a declared current source or explicit expert review."],
            gates=[
                ("literature-landscape-source-coverage", "major", "Comprehensive and recurring searches declare at least two appropriate sources and account for every declared source."),
                ("literature-landscape-selection", "major", "Every record has stable identity, source level, six bounded prioritisation scores, deduplication, and an explicit retraction state."),
                ("literature-landscape-citation-independence", "major", "Citing works retain citation context and explicit author or affiliation overlap rather than being labelled independent from citation count alone."),
            ],
            limitations=["The module audits supplied records and rankings; it does not retrieve literature, calculate citation counts, or infer scientific support from venue or score."],
            complements=["literature-evidence", "citation-record-resolution", "citation-resolution-adjudication", "literature-acquisition-manifest-audit", "paper-reader-package-audit"],
            concept_sources=["Nature Academic Search and Nature Literature Pipeline workflow concepts, adapted into a project-owned selection and independence audit."],
            scientific_stage=1,
        ),
        [{
            "name": "two-source-bounded-landscape",
            "input": {
                "query_plan": {"objective": "Map regulators of retinal maturation", "queries": ["retinal maturation regulator"], "sources": ["PubMed", "Crossref"], "coverage_mode": "comprehensive"},
                "records": [
                    {"id": "P1", "title": "Regulator study", "source": "PubMed", "source_level": "full-text", "doi": "10.1000/example.1", "journal": "Development", "retraction_status": "not-retracted", "record_role": "candidate", "authors": ["A. One"], "affiliations": ["Institute A"], "citation_contexts": [], "scores": {"topic_relevance": 5, "claim_directness": 4, "methodological_fit": 4, "evidence_depth": 4, "novelty_value": 3, "recency_value": 3}},
                    {"id": "P2", "title": "Independent citing study", "source": "Crossref", "source_level": "abstract-only", "doi": "10.1000/example.2", "journal": "Cell Reports", "retraction_status": "not-retracted", "record_role": "citing-work", "authors": ["B. Two"], "affiliations": ["Institute B"], "citation_contexts": ["Supports the developmental timing result."], "scores": {"topic_relevance": 4, "claim_directness": 3, "methodological_fit": 3, "evidence_depth": 2, "novelty_value": 3, "recency_value": 4}},
                ],
                "focal_authors": ["A. One"], "focal_affiliations": ["Institute A"],
            },
            "expected_subset": {"record_count": 2, "blocking_finding_count": 0, "ready_for_synthesis": True, "independent_citing_work_ids": ["P2"]},
        }],
    )

    modules["literature-acquisition-manifest-audit"] = (
        _module(
            module_id="literature-acquisition-manifest-audit",
            title="Audit authorized literature acquisition records",
            description="Validate per-paper access status, source level, lawful route, user handoff, PDF identity, page count, file digest, and credential boundary for open-access or institution-authorized literature retrieval.",
            module_type="validation",
            domains=["evidence", "publication"],
            intents=["literature download manifest", "authorized full text retrieval", "文献下载清单审查", "机构授权文献获取"],
            question="Does each literature item have an honest access outcome and a verified, lawful full-text artifact when one was obtained?",
            entrypoint="biomed_workbench.capabilities.scholarly_delivery:audit_literature_acquisition_manifest",
            input_name="acquisition_manifest",
            input_type="literature_acquisition_manifest",
            output_name="acquisition_audit",
            output_type="literature_acquisition_quality_report",
            input_schema=_schema({"items": {"type": "array", "items": {"type": "object"}}}, ["items"]),
            output_schema=_schema({
                "item_count": {"type": "integer"}, "status_counts": {"type": "object"}, "items": {"type": "array"}, "findings": {"type": "array"},
                "blocking_finding_count": {"type": "integer"}, "manifest_valid": {"type": "boolean"}, "manifest_digest": {"type": "string"}, "safety_boundary": {"type": "array"},
            }, ["item_count", "status_counts", "items", "findings", "blocking_finding_count", "manifest_valid", "manifest_digest", "safety_boundary"]),
            assumptions=["The caller used only lawful open-access or user-authorized institutional routes and did not export browser secrets."],
            gates=[
                ("literature-access-route", "fatal", "Every item uses an open-access or user-authorized route without bypassing access or verification controls."),
                ("literature-file-verification", "major", "Downloaded PDFs have a real PDF signature, nonzero page count, file identity, and digest."),
                ("literature-handoff-status", "major", "Login and publisher verification states identify the exact user action without requesting credentials."),
            ],
            limitations=["This module audits a retrieval manifest and does not itself authenticate, browse, download, or establish institutional entitlement."],
            complements=["literature-evidence", "citation-record-resolution", "paper-reader-package-audit"],
            concept_sources=["Nature Literature Downloader authorized-access and verification contract, adapted into a non-authenticating project-owned audit."],
            scientific_stage=1,
        ),
        [{
            "name": "verified-open-access-pdf",
            "input": {"items": [{"id": "P1", "title": "Open paper", "status": "open_access_downloaded", "source_level": "full-text", "access_route": "publisher-open-access", "file_name": "paper.pdf", "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "pdf_signature_verified": True, "page_count": 8, "access_boundary_violation": False}]},
            "expected_subset": {"item_count": 1, "blocking_finding_count": 0, "manifest_valid": True, "status_counts": {"open_access_downloaded": 1}},
        }],
    )

    modules["presentation-package-audit"] = (
        _module(
            module_id="presentation-package-audit",
            title="Reload and audit a scientific presentation package",
            description="Reload a PPTX binary package, verify its core parts and slide count, inspect visible text density, bind external assets to source digests and slide locations, and block unresolved high-severity quality findings before rendered visual review.",
            module_type="validation",
            domains=["publication", "visualization"],
            intents=["PPTX audit", "paper presentation quality", "论文汇报PPT审查", "学术幻灯片交付"],
            question="Is this real PPTX package structurally valid, traceable, and ready for rendered scientific and visual review?",
            entrypoint="biomed_workbench.capabilities.scholarly_delivery:audit_presentation_package",
            input_name="presentation_package",
            input_type="scientific_presentation_package",
            output_name="presentation_audit",
            output_type="presentation_package_quality_report",
            input_schema=_schema({
                "pptx_base64": {"type": "string", "minLength": 8}, "expected_slide_count": {"type": "integer", "minimum": 1},
                "asset_manifest": {"type": "array", "items": {"type": "object"}}, "qa_findings": {"type": "array", "items": {"type": "object"}},
            }, ["pptx_base64", "expected_slide_count", "asset_manifest"]),
            output_schema=_schema({
                "package": {"type": "object"}, "visible_text_character_count": {"type": "integer"}, "asset_count": {"type": "integer"},
                "findings": {"type": "array"}, "blocking_finding_count": {"type": "integer"}, "ready_for_visual_review": {"type": "boolean"}, "limitations": {"type": "array"},
            }, ["package", "visible_text_character_count", "asset_count", "findings", "blocking_finding_count", "ready_for_visual_review", "limitations"]),
            assumptions=["The PPTX binary and asset manifest belong to the same presentation revision."],
            gates=[
                ("presentation-package-reload", "fatal", "The PPTX reloads as a valid package with the declared slide count."),
                ("presentation-asset-traceability", "major", "Every external figure or table has a source, digest, and slide placement."),
                ("presentation-qa-resolution", "major", "No high-severity crop, overflow, overlap, legibility, or scientific-context defect remains unresolved."),
            ],
            limitations=["Structural package checks do not replace rendered visual inspection, source-figure review, or scientific claim validation."],
            complements=["presentation-delivery-plan", "figure-specification", "claim-evidence-integrity-audit"],
            concept_sources=["Nature Paper-to-PPTX evidence-led narrative, asset traceability, real-PPTX, and corrective-QA contract, adapted into a project-owned package audit."],
            scientific_stage=6,
        ),
        [{
            "name": "reload-one-slide-pptx",
            "input": {"pptx_base64": _minimal_pptx(), "expected_slide_count": 1, "asset_manifest": [], "qa_findings": []},
            "expected_subset": {"package": {"slide_count": 1}, "blocking_finding_count": 0, "ready_for_visual_review": True},
        }],
    )

    writing_manifest = modules["biomedical-writing-delivery"][0]
    writing_manifest["output_artifacts"] = [
        {
            "name": "writing_delivery",
            "artifact_type": "biomedical_writing_delivery_manifest",
            "formats": [_format("module-output")],
            "processing_levels": ["derived", "validated"],
            "required_metadata": ["module_version", "compatibility_row_id"],
        },
        {
            "name": "writing_html_report",
            "artifact_type": "biomedical_writing_html_report",
            "formats": [{**_format("human-readable-report"), "name": "html", "versions": ["5"], "representations": ["text"]}],
            "processing_levels": ["derived", "validated", "reloaded"],
            "required_metadata": ["module_version", "compatibility_row_id", "artifact_digest"],
        },
    ]
    writing_manifest["compatibility_matrix"][0]["output_formats"] = {
        "writing_delivery": ["inline-json@1"],
        "writing_html_report": ["html@5"],
    }
    return modules


def main() -> int:
    for module_id, (manifest, cases) in _specs().items():
        folder = BUILTIN / module_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "tests").mkdir(exist_ok=True)
        (folder / "module.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        (folder / "tests" / "cases.json").write_text(json.dumps({"schema_version": 1, "cases": cases}, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"modules": sorted(_specs()), "count": len(_specs())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
