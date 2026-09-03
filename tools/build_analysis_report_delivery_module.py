#!/usr/bin/env python3
"""Build the registered primary-HTML scientific analysis-report module."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin" / "scientific-analysis-report-delivery"


def _format(name: str, version: str, orientation: str, representation: str) -> dict[str, object]:
    return {
        "name": name, "versions": [version], "compression": ["none"], "orientations": [orientation],
        "representations": [representation], "coordinate_systems": [], "genome_builds": [],
        "annotation_releases": [], "required_indexes": [], "genome_build_policy": "not_applicable",
    }


def main() -> None:
    MODULE_ROOT.mkdir(parents=True, exist_ok=True)
    (MODULE_ROOT / "tests").mkdir(exist_ok=True)
    row_id = "python-3.14.3-scientific-analysis-html-1"
    manifest = {
        "schema_version": 1,
        "id": "scientific-analysis-report-delivery",
        "title": "Deliver a reviewed scientific analysis report as primary HTML",
        "version": "1.0.0",
        "description": "Render a result-first scientific interpretation as a navigable HTML report, link its data, figures, code and literature, reopen the file, and retain Markdown only as an optional companion.",
        "domains": ["evidence", "research-quality", "publication"],
        "module_type": "delivery",
        "maturity": "validated",
        "access": "offline",
        "mutability": "writes_output",
        "entrypoint": "biomed_workbench.capabilities.analysis_report:deliver_analysis_report_html",
        "execution": {"kind": "python", "timeout_seconds": 30, "max_output_bytes": 50000000},
        "kernel_compatibility": [">=0.2.0,<0.3.0"],
        "intents": [
            "deliver scientific analysis report", "generate analysis interpretation report", "project results report",
            "生成分析报告", "交付项目分析报告", "整理分析结果为报告", "科学解读报告", "完整项目报告", "项目结果报告",
        ],
        "routing": {
            "method_aliases": [
                "scientific-analysis-report-delivery", "Deliver a reviewed scientific analysis report as primary HTML",
                "deliver scientific analysis report", "generate analysis interpretation report", "project results report",
                "生成分析报告", "交付项目分析报告", "整理分析结果为报告", "科学解读报告", "完整项目报告", "项目结果报告",
            ],
            "required_any_terms": [], "exclusion_terms": ["quality control report", "qc report", "质控报告"],
            "named_method_priority": 100,
        },
        "questions": ["Was the reviewed scientific analysis delivered as reopened HTML with working evidence links?"],
        "assumptions": ["The supplied result view was built from reloaded and scientifically reviewed project artifacts."],
        "preconditions": [
            "The report states a biological question, observations, interpretations, experimental units and evidence boundaries.",
            "At least one registered data, figure, analysis script or literature source is linked.",
        ],
        "limitations": [
            "This delivery module does not perform upstream analysis or replace scientific review.",
            "It cannot prevent an external host from creating an unrelated Markdown file outside the registered workbench workflow.",
        ],
        "alternatives": [],
        "complements": ["scientific-review-self-correction", "biomedical-writing-delivery"],
        "evidence_effects": ["requires-primary-html-for-outward-analysis-report", "links-report-to-scientific-evidence"],
        "credentials": [],
        "dependencies": [{
            "name": "python", "identity": "python-runtime", "ecosystem": "runtime", "required": True,
            "purpose": "Render and reopen the project-owned HTML report.", "platforms": ["any"],
            "allowed_versions": [">=3.14,<3.15"], "tested_versions": ["3.14.3"],
            "version_pattern": "([0-9]+(?:\\.[0-9]+)+)",
            "version_probe_kind": "python_callable", "version_probe": ["biomed_workbench.modules.compatibility:probe_python_runtime"],
            "version_probe_timeout_seconds": 5, "conflicts": [],
            "version_source": "https://www.python.org/downloads/release/python-3143/", "verified_at": "2026-09-03",
        }],
        "tool_requirements": [],
        "input_artifacts": [{
            "name": "reviewed_analysis_report", "artifact_type": "reviewed_scientific_result_view",
            "formats": [_format("inline-json", "1", "request-object", "structured")],
            "processing_levels": ["reviewed"], "required_metadata": [],
        }],
        "output_artifacts": [
            {
                "name": "analysis_report_delivery", "artifact_type": "scientific_analysis_report_delivery_manifest",
                "formats": [_format("inline-json", "1", "module-output", "structured")],
                "processing_levels": ["derived", "validated"], "required_metadata": ["module_version", "compatibility_row_id"],
            },
            {
                "name": "analysis_html_report", "artifact_type": "scientific_analysis_html_report",
                "formats": [_format("html", "5", "human-readable-report", "text")],
                "processing_levels": ["derived", "validated", "reloaded"],
                "required_metadata": ["module_version", "compatibility_row_id", "artifact_digest"],
            },
        ],
        "input_schema": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "report": {"type": "object"}, "output_directory": {"type": "string", "minLength": 1},
                "title": {"type": "string"}, "language": {"type": "string", "enum": ["auto", "zh-CN", "en"]},
                "markdown_companion": {"type": "boolean"},
            },
            "required": ["report", "output_directory"],
        },
        "output_schema": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "ready_for_delivery": {"type": "boolean"}, "primary_delivery_format": {"type": "string", "enum": ["html"]},
                "markdown_is_companion_only": {"type": "boolean"}, "report_files": {"type": "object"},
            },
            "required": ["ready_for_delivery", "primary_delivery_format", "markdown_is_companion_only", "report_files"],
        },
        "compatibility_matrix": [{
            "id": row_id, "module_version": "1.0.0", "platforms": ["any"],
            "dependency_versions": {"python": [">=3.14,<3.15"]}, "tool_versions": {},
            "input_formats": {"reviewed_analysis_report": ["inline-json@1"]},
            "output_formats": {"analysis_report_delivery": ["inline-json@1"], "analysis_html_report": ["html@5"]},
            "regression_evidence_ids": ["scientific-analysis-report-delivery-regression-v1"],
            "end_to_end_evidence_ids": ["scientific-analysis-report-delivery-e2e-v1"], "verified_at": "2026-09-03",
        }],
        "quality_gates": [
            {"id": "analysis-report-result-first", "severity": "major", "blocks_interpretation": True,
             "description": "Each result reports the observation, scientific interpretation, experimental unit, evidence boundary and next decision."},
            {"id": "analysis-report-evidence-links", "severity": "fatal", "blocks_interpretation": True,
             "description": "The report contains at least one verified link to data, a figure, analysis code or literature."},
            {"id": "analysis-report-primary-html", "severity": "fatal", "blocks_interpretation": True,
             "description": "HTML is the primary outward artifact and is reopened successfully; Markdown may exist only as a companion."},
        ],
        "orchestration": {"scientific_stage": 6, "requires_reviewed_upstream_types": []},
        "provenance": {"license": "Apache-2.0", "concept_sources": ["Project-owned result-first HTML delivery contract."]},
    }
    fixture = {
        "schema_version": 1,
        "cases": [{
            "name": "write-reopen-and-link-primary-html-analysis-report",
            "input": {
                "report": {
                    "project": "controlled-retina-fixture",
                    "biological_question": "该观察是否支持视网膜祖细胞分化状态发生改变？",
                    "scientific_results": [{
                        "label": "主要结果", "progress": "SCIENTIFICALLY_REVIEWED",
                        "observation_zh": "受控示例中，突变组标志物均值较对照组低 20%。",
                        "interpretation_zh": "该结果与分化状态改变一致，但不能建立直接机制。",
                        "experimental_unit": "模拟独立样本", "evidence_boundary_zh": ["受控格式测试，不作生物学推断。"],
                        "next_decision": "retain-with-limit",
                    }],
                    "evidence_links": [{"label": "受控源数据", "path": "tests/fixtures/biomedical_writing/source.tsv"}],
                },
                "output_directory": ":temporary:",
                "title": "受控科学分析报告", "language": "zh-CN", "markdown_companion": True,
            },
            "expected_subset": {
                "ready_for_delivery": True, "primary_delivery_format": "html", "markdown_is_companion_only": True,
                "report_files": {"primary_format": "html", "delivery_verified": True, "renderer_version": "1.0.0"},
            },
        }],
    }
    (MODULE_ROOT / "module.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (MODULE_ROOT / "tests" / "cases.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
