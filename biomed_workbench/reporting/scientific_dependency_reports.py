"""Render reports only from an integrity-checked scientific evidence map."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

from ..kernel.scientific_evidence_map import (
    EvidenceMapUnit,
    ScientificEvidenceMap,
    validate_evidence_map_files,
)


@dataclass(frozen=True)
class BilingualReportPair:
    chinese_markdown: str
    english_markdown: str
    evidence_map_digest: str


def _panel_review(unit: EvidenceMapUnit):
    if unit.spec.panel_id is None:
        return None
    return next(panel for panel in unit.review.panels if panel.panel_id == unit.spec.panel_id)


def _unit_section(
    unit: EvidenceMapUnit,
    evidence_map: ScientificEvidenceMap,
    language: str,
    workspace_root: Path,
) -> list[str]:
    zh = language == "zh"
    review = unit.review
    decision = unit.decision
    panel = _panel_review(unit)
    hypothesis_by_id = {item.id: item for item in evidence_map.hypotheses}
    hypothesis_ids = sorted(
        set(decision.hypothesis_ids).union(
            hypothesis_id
            for admission in unit.admissions
            for hypothesis_id in admission.hypothesis_ids
        )
    )
    rationale = panel.rationale_zh if panel and zh else panel.rationale_en if panel else review.rationale_zh if zh else review.rationale_en
    methods = panel.methods_zh if panel and zh else panel.methods_en if panel else review.methods_zh if zh else review.methods_en
    results = panel.results_zh if panel and zh else panel.results_en if panel else review.results_zh if zh else review.results_en
    conclusion = panel.conclusion_zh if panel and zh else panel.conclusion_en if panel else review.conclusion_zh if zh else review.conclusion_en
    title = unit.spec.panel_id or unit.artifact_type
    incoming = [
        edge for edge in evidence_map.edges
        if edge.target == unit.spec.id and edge.relation in {"precedes", "panel-depends-on"}
    ]
    lines = [
        f"### {title}",
        "",
        f"- {'证据单元' if zh else 'Evidence unit'}: `{unit.spec.id}`",
        f"- {'登记产物' if zh else 'Registered artifact'}: `{unit.spec.artifact_id}`",
        f"- {'综合评审状态' if zh else 'Overall review status'}: `{review.overall_status}`",
        f"- {'决策' if zh else 'Decision'}: `{decision.action}`",
        f"- {'有效证据' if zh else 'Active evidence'}: `{str(decision.active_evidence).lower()}`",
        "",
        f"#### {'科学依据与假设' if zh else 'Scientific rationale and hypothesis'}",
        "",
        rationale,
        "",
        *(
            [
                f"- {'假设' if zh else 'Hypothesis'} `{hypothesis_id}`: "
                f"{hypothesis_by_id[hypothesis_id].statement} "
                f"({'状态' if zh else 'status'}: `{hypothesis_by_id[hypothesis_id].status}`; "
                f"{'允许的结论强度' if zh else 'permitted claim strength'}: "
                f"`{hypothesis_by_id[hypothesis_id].permitted_claim_strength}`)"
                for hypothesis_id in hypothesis_ids
            ]
        ),
        "",
        *(
            [
                f"- {'分析准入依据' if zh else 'Analysis-admission rationale'} "
                f"`{admission.id}`: {admission.rationale_zh if zh else admission.rationale_en}"
                for admission in unit.admissions
            ]
        ),
        "",
        f"#### {'分析方法' if zh else 'Methods'}",
        "",
        methods,
        "",
        *(
            [
                f"- {'已批准方法' if zh else 'Approved method'} `{admission.id}`: {admission.method}"
                for admission in unit.admissions
            ]
        ),
        *(
            [
                f"- {'参数依据' if zh else 'Parameter justification'} "
                f"`{parameter}`: {justification}"
                for admission in unit.admissions
                for parameter, justification in sorted(admission.parameter_justifications.items())
            ]
        ),
        *(
            [
                f"- {'备选方法' if zh else 'Alternative considered'}: {alternative}"
                for admission in unit.admissions
                for alternative in admission.alternatives_considered
            ]
        ),
        *(
            [
                f"- {'关键假设' if zh else 'Assumption'}: {assumption}"
                for admission in unit.admissions
                for assumption in admission.assumptions
            ]
        ),
        *(
            [
                f"- {'接受标准' if zh else 'Acceptance criterion'}: {criterion}"
                for admission in unit.admissions
                for criterion in admission.acceptance_criteria
            ]
        ),
        *(
            [
                f"- {'证伪标准' if zh else 'Falsification criterion'}: {criterion}"
                for admission in unit.admissions
                for criterion in admission.falsification_criteria
            ]
        ),
        *(
            [
                f"- {'官方方法来源' if zh else 'Official method source'}: [{source}]({source})"
                for admission in unit.admissions
                for source in admission.official_sources
            ]
        ),
        "",
        f"#### {'结果与科学结论' if zh else 'Results and scientific conclusion'}",
        "",
        results,
        "",
        conclusion,
        "",
        f"#### {'前置结论与故事依赖' if zh else 'Prerequisite conclusions and story dependencies'}",
        "",
        unit.spec.prerequisite_conclusion_zh if zh else unit.spec.prerequisite_conclusion_en,
    ]
    lines.extend(f"- `{edge.source}` → `{edge.target}` ({edge.relation})" for edge in incoming)
    lines.extend(["", f"#### {'文件证据链' if zh else 'File evidence chain'}", ""])
    for item in unit.spec.files:
        target = (workspace_root / item.path).absolute().as_posix()
        lines.append(f"- `{item.role}`: [{item.path}]({target}) — SHA-256 `{item.sha256}`")
    lines.extend(
        [
            "",
            f"#### {'客观科学评审' if zh else 'Objective scientific review'}",
            "",
            f"- {'技术有效性' if zh else 'Technical validity'}: `{review.technical_status}`",
            f"- {'统计有效性' if zh else 'Statistical validity'}: `{review.statistical_status}`",
            f"- {'生物学有效性' if zh else 'Biological validity'}: `{review.biological_status}`",
            f"- {'稳健性' if zh else 'Robustness'}: `{review.robustness_status}`",
            f"- {'局限性' if zh else 'Limitations'}:",
        ]
    )
    lines.extend(f"  - {value}" for value in review.limitations_zh if zh)
    lines.extend(f"  - {value}" for value in review.limitations_en if not zh)
    if unit.gate_adjudications:
        lines.extend(["", f"- {'逐门科学审议' if zh else 'Gate-level scientific adjudication'}:"])
        for adjudication in unit.gate_adjudications:
            rationale = adjudication.rationale_zh if zh else adjudication.rationale_en
            lines.append(
                f"  - `{adjudication.gate_id}`: `{adjudication.status}`; "
                f"{'审议方式' if zh else 'mode'} `{adjudication.adjudication_mode}`; "
                f"{'结果摘要' if zh else 'result digest'} `{adjudication.gate_result_digest}`; {rationale}"
            )
            lines.extend(
                [
                    f"    - {'观测值' if zh else 'Observed value'}: `{adjudication.observed_value}`",
                    f"    - {'判定标准' if zh else 'Criterion'}: `{adjudication.criterion}`",
                    f"    - {'具体发现' if zh else 'Finding'}: {adjudication.finding}",
                ]
            )
            limitations = adjudication.limitations_zh if zh else adjudication.limitations_en
            lines.extend(f"    - {'局限' if zh else 'Limitation'}: {value}" for value in limitations)
    lines.extend(
        [
            "",
            f"#### {'叙述来源与原始研究 DOI' if zh else 'Narrative sources and original-study DOIs'}",
            "",
        ]
    )
    for source in unit.spec.narrative_sources:
        lines.append(f"- `{source.role}`: [{source.title}]({source.url}) — DOI `{source.doi}`")
    lines.extend(
        [
            "",
            f"#### {'决策影响' if zh else 'Decision impact'}",
            "",
            decision.rationale_zh if zh else decision.rationale_en,
            "",
        ]
    )
    return lines


def _render(evidence_map: ScientificEvidenceMap, language: str, workspace_root: Path) -> str:
    evidence_map.validate_integrity()
    zh = language == "zh"
    title = "基于科学证据地图的项目产物解读报告" if zh else "Project Artifact Interpretation Report from the Scientific Evidence Map"
    lines = [
        f"# {title}",
        "",
        f"- {'项目' if zh else 'Project'}: `{evidence_map.project_id}`",
        f"- {'证据地图版本' if zh else 'Evidence map version'}: `{evidence_map.version.version}` (revision {evidence_map.version.revision})",
        f"- {'变更类型' if zh else 'Change type'}: `{evidence_map.version.change_type}`",
        f"- {'版本说明' if zh else 'Version summary'}: "
        f"{evidence_map.version.change_summary_zh if zh else evidence_map.version.change_summary_en}",
        f"- {'父地图摘要' if zh else 'Parent map digest'}: `{evidence_map.version.parent_map_digest or 'none'}`",
        f"- {'科学问题' if zh else 'Scientific question'}: {evidence_map.scientific_question}",
        f"- {'项目状态摘要' if zh else 'Project state digest'}: `{evidence_map.state_digest}`",
        f"- {'科学证据地图摘要' if zh else 'Scientific evidence map digest'}: `{evidence_map.digest}`",
        f"- {'机器边表摘要' if zh else 'Machine edge-table digest'}: `{evidence_map.edge_table_digest}`",
        "",
        (
            "本报告只读取已校验的科学证据地图；文件路径、校验值、panel 依赖、caption 与 DOI 不在报告阶段重新拼接。"
            if zh
            else "This report reads only the validated scientific evidence map; file paths, checksums, panel dependencies, captions, and DOIs are not reassembled during reporting."
        ),
        "",
        f"## {'全局 panel 故事 DAG' if zh else 'Global panel story DAG'}",
        "",
    ]
    if evidence_map.story_edges:
        lines.extend(f"- `{edge.source}` → `{edge.target}`" for edge in evidence_map.story_edges)
    else:
        lines.append("- " + ("当前证据地图没有跨 panel 依赖。" if zh else "The current evidence map has no cross-panel dependency."))
    grouped: dict[str, list[EvidenceMapUnit]] = {}
    for unit in evidence_map.units:
        grouped.setdefault(unit.spec.group_id, []).append(unit)
    for group_id in sorted(grouped):
        lines.extend(["", f"## {'证据组' if zh else 'Evidence group'} `{group_id}`", ""])
        for unit in sorted(grouped[group_id], key=lambda item: item.spec.id):
            lines.extend(_unit_section(unit, evidence_map, language, workspace_root))
    return "\n".join(lines).rstrip() + "\n"


def render_bilingual_reports(
    evidence_map: ScientificEvidenceMap,
    *,
    workspace_root: Path,
) -> BilingualReportPair:
    validate_evidence_map_files(evidence_map, workspace_root=workspace_root)
    return BilingualReportPair(
        chinese_markdown=_render(evidence_map, "zh", workspace_root),
        english_markdown=_render(evidence_map, "en", workspace_root),
        evidence_map_digest=evidence_map.digest,
    )


def _edge_table(evidence_map: ScientificEvidenceMap) -> str:
    stream = io.StringIO()
    writer = csv.DictWriter(
        stream,
        fieldnames=("layer", "group_id", "source", "target", "relation"),
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    for edge in evidence_map.edges:
        writer.writerow(edge.to_dict())
    return stream.getvalue()


def _map_markdown(evidence_map: ScientificEvidenceMap, workspace_root: Path) -> str:
    evidence_map.validate_integrity()
    lines = [
        "# Scientific Evidence Map",
        "",
        f"- Map digest: `{evidence_map.digest}`",
        f"- Version: `{evidence_map.version.version}` (revision {evidence_map.version.revision})",
        f"- Change type: `{evidence_map.version.change_type}`",
        f"- Change summary: {evidence_map.version.change_summary_en}",
        f"- Parent map digest: `{evidence_map.version.parent_map_digest or 'none'}`",
        f"- Edge-table digest: `{evidence_map.edge_table_digest}`",
        "",
        "## Layer 1: Global panel story DAG",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for unit in evidence_map.units:
        if unit.spec.panel_id is not None:
            lines.append(f'  {unit.spec.id.replace("-", "_")}["{unit.spec.panel_id}"]')
    for edge in evidence_map.story_edges:
        lines.append(f'  {edge.source.replace("-", "_")} --> {edge.target.replace("-", "_")}')
    lines.extend(["```", "", "## Layer 2: Evidence mind maps", ""])
    grouped: dict[str, list[EvidenceMapUnit]] = {}
    for unit in evidence_map.units:
        grouped.setdefault(unit.spec.group_id, []).append(unit)
    for group_id in sorted(grouped):
        lines.extend([f"### {group_id}", "", "```mermaid", "flowchart LR"])
        group_edges = [edge for edge in evidence_map.detail_edges if edge.group_id == group_id]
        labels = {unit.spec.id: unit.spec.panel_id or unit.artifact_type for unit in grouped[group_id]}
        for unit in grouped[group_id]:
            labels.update({item.id: item.role for item in unit.spec.files})
            labels.update({item.id: f"DOI {item.doi}" for item in unit.spec.narrative_sources})
        for identifier, label in sorted(labels.items()):
            lines.append(f'  {identifier.replace("-", "_")}["{label}"]')
        for edge in group_edges:
            lines.append(f'  {edge.source.replace("-", "_")} -->|"{edge.relation}"| {edge.target.replace("-", "_")}')
        lines.extend(["```", ""])
        for unit in grouped[group_id]:
            for item in unit.spec.files:
                target = (workspace_root / item.path).absolute().as_posix()
                lines.append(f"- [{item.path}]({target}) — `{item.role}` — SHA-256 `{item.sha256}`")
            for source in unit.spec.narrative_sources:
                lines.append(f"- [{source.title}]({source.url}) — DOI `{source.doi}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_bilingual_reports(
    evidence_map: ScientificEvidenceMap,
    output_directory: Path,
    *,
    workspace_root: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    validate_evidence_map_files(evidence_map, workspace_root=workspace_root)
    pair = render_bilingual_reports(evidence_map, workspace_root=workspace_root)
    output_directory.mkdir(parents=True, exist_ok=True)
    chinese = output_directory / "scientific-evidence-report.zh-CN.md"
    english = output_directory / "scientific-evidence-report.en.md"
    map_json = output_directory / "scientific-evidence-map.json"
    edge_tsv = output_directory / "scientific-evidence-map.edges.tsv"
    map_markdown = output_directory / "scientific-evidence-map.md"
    chinese.write_text(pair.chinese_markdown, encoding="utf-8")
    english.write_text(pair.english_markdown, encoding="utf-8")
    map_json.write_text(json.dumps(evidence_map.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    edge_tsv.write_text(_edge_table(evidence_map), encoding="utf-8")
    map_markdown.write_text(_map_markdown(evidence_map, workspace_root), encoding="utf-8")
    return chinese, english, map_json, edge_tsv, map_markdown
