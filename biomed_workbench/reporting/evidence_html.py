"""Accessible, dependency-free HTML views for scientific evidence maps."""

from __future__ import annotations

import html
from collections import defaultdict, deque
from pathlib import Path

from ..kernel.scientific_dependency import AnalysisAdmission
from ..kernel.scientific_evidence_map import EvidenceMapUnit, ScientificEvidenceMap


ROLE_LABELS = {
    "zh": {
        "registered-data": "登记数据",
        "plot-data": "作图数据",
        "analysis-script": "分析程序",
        "renderer": "排图程序",
        "final-data": "最终数据",
        "final-pdf": "PDF 图件",
        "final-png": "PNG 图件",
        "caption": "图注",
        "original-study": "原始研究",
        "dataset": "公共数据集",
        "method": "方法来源",
        "background": "背景文献",
        "claim": "结论来源",
    },
    "en": {
        "registered-data": "Registered data",
        "plot-data": "Plot-ready data",
        "analysis-script": "Analysis script",
        "renderer": "Figure renderer",
        "final-data": "Final data",
        "final-pdf": "PDF figure",
        "final-png": "PNG figure",
        "caption": "Caption",
        "original-study": "Original study",
        "dataset": "Public dataset",
        "method": "Method source",
        "background": "Background source",
        "claim": "Claim source",
    },
}

FILE_STAGE_ORDER = {
    "registered-data": 0,
    "plot-data": 2,
    "analysis-script": 3,
    "renderer": 4,
    "final-data": 5,
    "final-pdf": 5,
    "final-png": 5,
    "caption": 6,
}


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _anchor(value: str, prefix: str = "unit") -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value)
    return f"{prefix}-{safe}"


def _paragraphs(value: str) -> str:
    paragraphs = [part.strip() for part in value.split("\n\n") if part.strip()]
    return "".join(f"<p>{_e(part).replace(chr(10), '<br>')}</p>" for part in paragraphs)


def _list(items: list[str], css_class: str = "") -> str:
    if not items:
        return '<p class="empty">—</p>'
    class_attr = f' class="{_e(css_class)}"' if css_class else ""
    return f"<ul{class_attr}>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def _file_uri(path: Path) -> str:
    # pathlib.as_uri quotes filesystem characters and avoids treating an absolute
    # path as a host-relative web URL when the report is opened locally.
    return path.resolve(strict=False).as_uri()


def _file_link(item, workspace_root: Path, language: str, *, compact: bool = False) -> str:
    label = ROLE_LABELS[language].get(item.role, item.role)
    target = workspace_root / item.path
    checksum = item.sha256[:12] if compact else item.sha256
    return (
        f'<a class="evidence-link" href="{_e(_file_uri(target))}" target="_blank" '
        f'rel="noopener" data-evidence-id="{_e(item.id)}" data-sha256="{_e(item.sha256)}">'
        f'<span class="link-role">{_e(label)}</span>'
        f'<span class="link-path">{_e(item.path)}</span>'
        f'<span class="checksum">SHA-256 {_e(checksum)}</span></a>'
    )


def _source_link(source, language: str, *, compact: bool = False) -> str:
    label = ROLE_LABELS[language].get(source.role, source.role)
    title = source.title if not compact else source.title[:88] + ("…" if len(source.title) > 88 else "")
    return (
        f'<a class="evidence-link source-link" href="{_e(source.url)}" target="_blank" '
        f'rel="noopener noreferrer" data-source-id="{_e(source.id)}">'
        f'<span class="link-role">{_e(label)}</span>'
        f'<span class="link-path">{_e(title)}</span>'
        f'<span class="checksum">DOI {_e(source.doi)}</span></a>'
    )


def _status_class(value: str) -> str:
    lowered = value.lower()
    if lowered in {"accepted", "passed", "retain", "retained", "formal"}:
        return "status-good"
    if lowered in {"accepted-with-caveat", "retain-with-caveat", "major", "candidate", "sensitivity"}:
        return "status-caution"
    if lowered in {"failed", "fatal", "exclude", "excluded", "deprecated"}:
        return "status-stop"
    return "status-neutral"


def _panel_review(unit: EvidenceMapUnit):
    if unit.spec.panel_id is None:
        return None
    return next(panel for panel in unit.review.panels if panel.panel_id == unit.spec.panel_id)


def _unit_text(unit: EvidenceMapUnit, language: str) -> tuple[str, str, str, str]:
    zh = language == "zh"
    panel = _panel_review(unit)
    review = unit.review
    rationale = panel.rationale_zh if panel and zh else panel.rationale_en if panel else review.rationale_zh if zh else review.rationale_en
    methods = panel.methods_zh if panel and zh else panel.methods_en if panel else review.methods_zh if zh else review.methods_en
    results = panel.results_zh if panel and zh else panel.results_en if panel else review.results_zh if zh else review.results_en
    conclusion = panel.conclusion_zh if panel and zh else panel.conclusion_en if panel else review.conclusion_zh if zh else review.conclusion_en
    return rationale, methods, results, conclusion


def _metadata_cards(evidence_map: ScientificEvidenceMap, language: str) -> str:
    zh = language == "zh"
    values = [
        ("项目" if zh else "Project", evidence_map.project_id),
        ("地图版本" if zh else "Map version", f"{evidence_map.version.version} · revision {evidence_map.version.revision}"),
        ("地图类型" if zh else "Map type", evidence_map.version.map_kind),
        ("证据单元" if zh else "Evidence units", str(len(evidence_map.units))),
    ]
    return '<div class="metadata-grid">' + "".join(
        f'<div class="metadata-card"><span>{_e(label)}</span><strong>{_e(value)}</strong></div>'
        for label, value in values
    ) + "</div>"


def _page_shell(
    *,
    language: str,
    title: str,
    eyebrow: str,
    navigation: str,
    toc: str,
    body: str,
) -> str:
    lang_code = "zh-CN" if language == "zh" else "en"
    return f"""<!doctype html>
<html lang="{lang_code}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%230a7468'/%3E%3Cpath d='M8 16h16M16 8v16' stroke='white' stroke-width='3'/%3E%3C/svg%3E">
<title>{_e(title)}</title>
<style>
:root{{--ink:#15222b;--muted:#61717a;--paper:#f5f7f6;--surface:#ffffff;--line:#d8e0df;--accent:#0a7468;--accent-soft:#e8f4f1;--warm:#a45b24;--warm-soft:#fff2e7;--danger:#a33a3a;--danger-soft:#fdecec;--shadow:0 16px 42px rgba(24,48,53,.08);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:var(--paper)}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;line-height:1.7}} a{{color:var(--accent);text-decoration-thickness:.08em;text-underline-offset:.18em}} code,.checksum{{font-family:"SFMono-Regular",Consolas,monospace}} .topbar{{position:sticky;top:0;z-index:20;background:rgba(245,247,246,.94);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}} .topbar-inner{{max-width:1500px;margin:auto;padding:.75rem 1.35rem;display:flex;gap:.8rem;align-items:center;justify-content:space-between}} .brand{{font-weight:750;letter-spacing:.01em}} .page-links{{display:flex;flex-wrap:wrap;gap:.45rem}} .page-links a{{font-size:.84rem;text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:.28rem .66rem;background:var(--surface)}}
.layout{{max-width:1500px;margin:auto;display:grid;grid-template-columns:280px minmax(0,1fr);gap:2rem;padding:2rem 1.35rem 5rem}} .toc{{position:sticky;top:5.2rem;align-self:start;max-height:calc(100vh - 6rem);overflow:auto;background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:1.1rem;box-shadow:var(--shadow)}} .toc-title{{font-size:.78rem;font-weight:800;color:var(--muted);letter-spacing:.09em;text-transform:uppercase;margin-bottom:.75rem}} .toc ul{{list-style:none;margin:0;padding:0}} .toc li+li{{margin-top:.38rem}} .toc a{{display:block;color:var(--ink);text-decoration:none;font-size:.9rem;padding:.28rem .45rem;border-radius:8px}} .toc a:hover{{background:var(--accent-soft);color:var(--accent)}} .toc .toc-child{{padding-left:.75rem;color:var(--muted);font-size:.84rem}}
main{{min-width:0}} .hero{{background:linear-gradient(135deg,#123c3a 0%,#0c625a 62%,#177f72 100%);color:#fff;border-radius:26px;padding:clamp(2rem,5vw,4rem);box-shadow:var(--shadow);margin-bottom:1.5rem}} .eyebrow{{font-size:.78rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;opacity:.75}} h1{{font-size:clamp(2rem,4vw,3.45rem);line-height:1.12;margin:.55rem 0 1rem;letter-spacing:-.035em}} .hero p{{max-width:900px;font-size:1.08rem;color:rgba(255,255,255,.86)}} h2{{font-size:1.55rem;margin:2.2rem 0 1rem;scroll-margin-top:5rem}} h3{{font-size:1.2rem;margin:0;scroll-margin-top:5rem}} h4{{font-size:.96rem;margin:1.15rem 0 .45rem}} p{{margin:.55rem 0 1rem}} .metadata-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.8rem;margin:1.2rem 0 2rem}} .metadata-card{{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:1rem;min-width:0}} .metadata-card span{{display:block;color:var(--muted);font-size:.78rem;margin-bottom:.25rem}} .metadata-card strong{{display:block;overflow-wrap:anywhere}}
.section-card,.unit{{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:clamp(1.15rem,3vw,2rem);box-shadow:0 9px 28px rgba(24,48,53,.045);margin:1rem 0}} .unit{{border-top:4px solid var(--accent)}} .unit-header{{display:flex;gap:1rem;align-items:flex-start;justify-content:space-between;margin-bottom:1.2rem}} .unit-kicker{{font-size:.8rem;color:var(--muted);margin-bottom:.2rem}} .badges{{display:flex;gap:.42rem;flex-wrap:wrap;justify-content:flex-end}} .badge{{font-size:.74rem;font-weight:750;border-radius:999px;padding:.28rem .58rem;background:#edf1f1;color:#48585f;white-space:nowrap}} .status-good{{background:var(--accent-soft);color:#086258}} .status-caution{{background:var(--warm-soft);color:#8c4c1e}} .status-stop{{background:var(--danger-soft);color:var(--danger)}} .status-neutral{{background:#edf1f1;color:#536269}}
.finding{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem;margin:1rem 0}} .finding-card{{border-radius:14px;padding:1rem 1.1rem;background:#f7faf9;border:1px solid var(--line)}} .finding-card.conclusion{{background:var(--accent-soft);border-color:#badbd4}} .finding-label{{font-size:.76rem;color:var(--muted);font-weight:800;letter-spacing:.06em;text-transform:uppercase}} .finding-card p:last-child{{margin-bottom:0}} .link-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.65rem;margin:.75rem 0 1rem}} .evidence-link{{display:flex;flex-direction:column;gap:.18rem;text-decoration:none;background:#fbfcfc;border:1px solid var(--line);border-radius:12px;padding:.75rem .82rem;min-width:0}} .evidence-link:hover{{border-color:var(--accent);box-shadow:0 6px 18px rgba(10,116,104,.09)}} .link-role{{font-size:.73rem;text-transform:uppercase;letter-spacing:.06em;font-weight:800;color:var(--accent)}} .link-path{{font-size:.9rem;color:var(--ink);overflow-wrap:anywhere}} .checksum{{font-size:.68rem;color:var(--muted);overflow-wrap:anywhere}} .source-link .link-role{{color:var(--warm)}} details{{border-top:1px solid var(--line);padding:.85rem 0}} details:last-child{{padding-bottom:0}} summary{{cursor:pointer;font-weight:750;color:#32444b}} .detail-body{{padding:.65rem .2rem .2rem}} .detail-body ul{{padding-left:1.25rem}} .dependency-list{{display:flex;gap:.5rem;flex-wrap:wrap;list-style:none;padding:0}} .dependency-list li{{background:#f0f4f3;border-radius:9px;padding:.38rem .58rem;font-size:.84rem}}
.graph-scroll{{overflow:auto;border:1px solid var(--line);border-radius:16px;background:linear-gradient(#fff,#fbfdfc);padding:.5rem}} .story-graph{{display:block;min-width:760px;width:100%;height:auto}} .graph-node rect{{fill:#fff;stroke:#0a7468;stroke-width:1.4}} .graph-node text{{fill:#15222b;font-size:13px;font-weight:700}} .graph-node:hover rect{{fill:#e8f4f1}} .graph-edge{{stroke:#88aaa5;stroke-width:1.5;fill:none}} .route{{display:flex;align-items:stretch;gap:1.65rem;overflow:auto;padding:.65rem .1rem 1rem}} .route-stage{{position:relative;min-width:185px;max-width:245px;display:flex;flex-direction:column;gap:.45rem}} .route-stage:not(:last-child)::after{{content:"→";position:absolute;right:-1.3rem;top:50%;color:#7a918e;font-weight:800}} .route-label{{font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;font-weight:800;color:var(--muted)}} .route-card{{border:1px solid var(--line);border-radius:12px;padding:.65rem;background:#fff;font-size:.82rem;overflow-wrap:anywhere;text-decoration:none;color:var(--ink)}} .route-card.current{{border-color:var(--accent);background:var(--accent-soft);font-weight:750}} .route-card.source{{border-color:#e2c4ac;background:#fff8f2}} .digest-list{{display:grid;gap:.45rem}} .digest-row{{display:grid;grid-template-columns:170px minmax(0,1fr);gap:.6rem;font-size:.79rem}} .digest-row code{{overflow-wrap:anywhere;color:var(--muted)}} .back-top{{display:inline-block;margin-top:1rem;font-size:.82rem}}
.empty{{color:var(--muted);font-style:italic}} .callout{{border-left:4px solid var(--accent);background:var(--accent-soft);padding:.85rem 1rem;border-radius:0 12px 12px 0}} footer{{color:var(--muted);font-size:.78rem;border-top:1px solid var(--line);margin-top:2.5rem;padding-top:1rem}}
@media(max-width:980px){{.layout{{grid-template-columns:1fr}}.toc{{position:relative;top:auto;max-height:none}}.metadata-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}} @media(max-width:640px){{.topbar-inner{{align-items:flex-start;flex-direction:column}}.layout{{padding:1rem .75rem 3rem;gap:1rem}}.hero{{border-radius:18px}}.metadata-grid,.finding{{grid-template-columns:1fr}}.unit-header{{flex-direction:column}}.badges{{justify-content:flex-start}}.digest-row{{grid-template-columns:1fr}}}}
@media(prefers-color-scheme:dark){{:root{{--ink:#e6efed;--muted:#a6b5b1;--paper:#101716;--surface:#17201f;--line:#33413f;--accent:#62c9b9;--accent-soft:#173a35;--warm:#e2a270;--warm-soft:#402a1d;--danger:#ef8f8f;--danger-soft:#3f2020;--shadow:none}}.topbar{{background:rgba(16,23,22,.94)}}.hero{{background:linear-gradient(135deg,#173d39,#105c53)}}.finding-card,.evidence-link,.route-card,.graph-scroll{{background:#131b1a}}.finding-card.conclusion,.route-card.current{{background:var(--accent-soft)}}.story-graph .graph-node rect{{fill:#17201f}}.story-graph .graph-node text{{fill:#e6efed}}.dependency-list li{{background:#202b29}}}}
@media print{{.topbar,.toc,.back-top{{display:none!important}}body{{background:#fff;color:#111}}.layout{{display:block;max-width:none;padding:0}}.hero{{background:none!important;color:#111;padding:0;box-shadow:none}}.hero p{{color:#333}}.section-card,.unit{{box-shadow:none;break-inside:avoid}}details{{display:block}}details>summary{{list-style:none}}details>.detail-body{{display:block!important}}a{{color:#111;text-decoration:none}}}}
</style>
</head>
<body id="top">
<header class="topbar"><div class="topbar-inner"><div class="brand">Biomed Workbench</div><nav class="page-links" aria-label="Report views">{navigation}</nav></div></header>
<div class="layout"><aside class="toc" aria-label="Table of contents"><div class="toc-title">{'目录' if language == 'zh' else 'Contents'}</div>{toc}</aside><main>
<section class="hero"><div class="eyebrow">{_e(eyebrow)}</div><h1>{_e(title)}</h1></section>
{body}
<footer>{'该页面从已校验的科学证据地图生成；科学内容、路径和校验值未在展示阶段改写。' if language == 'zh' else 'This page is generated from a validated scientific evidence map; scientific content, paths, and checksums are not rewritten for display.'}</footer>
</main></div></body></html>"""


def _navigation(language: str, *, current: str) -> str:
    links = [
        ("中文报告", "Chinese report", "scientific-evidence-report.zh-CN.html"),
        ("English report", "English report", "scientific-evidence-report.en.html"),
        ("证据地图", "Evidence map", f"scientific-evidence-map.{'zh-CN' if language == 'zh' else 'en'}.html"),
        ("JSON", "JSON", "scientific-evidence-map.json"),
        ("关系表", "Edge table", "scientific-evidence-map.edges.tsv"),
    ]
    return "".join(
        f'<a href="{_e(href)}" aria-current="page">{_e(zh if language == "zh" else en)}</a>'
        if href == current
        else f'<a href="{_e(href)}">{_e(zh if language == "zh" else en)}</a>'
        for zh, en, href in links
    )


def _report_unit(unit: EvidenceMapUnit, evidence_map: ScientificEvidenceMap, language: str, workspace_root: Path) -> str:
    zh = language == "zh"
    rationale, methods, results, conclusion = _unit_text(unit, language)
    title = unit.spec.panel_id or unit.artifact_type
    incoming = [
        edge for edge in evidence_map.edges
        if edge.target == unit.spec.id and edge.relation in {"precedes", "panel-depends-on"}
    ]
    hypothesis_by_id = {item.id: item for item in evidence_map.hypotheses}
    hypothesis_ids = sorted(set(unit.decision.hypothesis_ids).union(
        hypothesis_id for admission in unit.admissions for hypothesis_id in admission.hypothesis_ids
    ))
    file_links = "".join(_file_link(item, workspace_root, language) for item in unit.spec.files)
    source_links = "".join(_source_link(source, language) for source in unit.spec.narrative_sources)
    hypotheses = _list([
        f'<code>{_e(hypothesis_id)}</code> · {_e(hypothesis_by_id[hypothesis_id].statement)} '
        f'<span class="badge">{_e(hypothesis_by_id[hypothesis_id].status)}</span>'
        for hypothesis_id in hypothesis_ids
    ])
    method_items: list[str] = []
    for admission in unit.admissions:
        if isinstance(admission, AnalysisAdmission):
            method_items.append(f'<strong>{_e(admission.method)}</strong> · {_e(admission.rationale_zh if zh else admission.rationale_en)}')
            method_items.extend(
                f'{"参数依据" if zh else "Parameter"} <code>{_e(parameter)}</code>: {_e(justification)}'
                for parameter, justification in sorted(admission.parameter_justifications.items())
            )
            method_items.extend(f'{"备选方法" if zh else "Alternative"}: {_e(value)}' for value in admission.alternatives_considered)
            method_items.extend(f'{"关键假设" if zh else "Assumption"}: {_e(value)}' for value in admission.assumptions)
            method_items.extend(f'{"接受标准" if zh else "Acceptance criterion"}: {_e(value)}' for value in admission.acceptance_criteria)
            method_items.extend(f'{"证伪标准" if zh else "Falsification criterion"}: {_e(value)}' for value in admission.falsification_criteria)
            method_items.extend(
                f'{"官方方法来源" if zh else "Official method source"}: <a href="{_e(value)}" target="_blank" rel="noopener noreferrer">{_e(value)}</a>'
                for value in admission.official_sources
            )
        else:
            method_items.append(
                f'<code>{_e(admission.id)}</code>: '
                + ("无法证明事前批准；仅限项目快照" if zh else "prior approval unavailable; project snapshot only")
            )
    limitations = unit.review.limitations_zh if zh else unit.review.limitations_en
    gate_items = []
    for adjudication in unit.gate_adjudications:
        gate_items.append(
            f'<code>{_e(adjudication.gate_id)}</code> · '
            f'<span class="badge {_status_class(adjudication.status)}">{_e(adjudication.status)}</span> · '
            f'{_e(adjudication.rationale_zh if zh else adjudication.rationale_en)}'
        )
    review_body = (
        '<div class="badges">'
        + "".join(
            f'<span class="badge {_status_class(value)}">{_e(label)}: {_e(value)}</span>'
            for label, value in [
                (("技术" if zh else "Technical"), unit.review.technical_status),
                (("统计" if zh else "Statistical"), unit.review.statistical_status),
                (("生物学" if zh else "Biological"), unit.review.biological_status),
                (("稳健性" if zh else "Robustness"), unit.review.robustness_status),
            ]
        )
        + '</div><h4>' + ("局限性" if zh else "Limitations") + '</h4>'
        + _list([_e(item) for item in limitations])
        + (('<h4>' + ("逐项科学复核" if zh else "Gate-level scientific review") + '</h4>' + _list(gate_items)) if gate_items else "")
    )
    dependencies = _list([
        f'<a href="#{_anchor(edge.source)}"><code>{_e(edge.source)}</code></a> → <code>{_e(edge.target)}</code>'
        for edge in incoming
    ], "dependency-list")
    prereq = unit.spec.prerequisite_conclusion_zh if zh else unit.spec.prerequisite_conclusion_en
    return f"""
<article class="unit" id="{_anchor(unit.spec.id)}">
  <div class="unit-header"><div><div class="unit-kicker">{_e(unit.spec.group_id)} · {_e(unit.artifact_type)}</div><h3>{_e(title)}</h3></div>
  <div class="badges"><span class="badge {_status_class(unit.review.overall_status)}">{_e(unit.review.overall_status)}</span><span class="badge {_status_class(unit.decision.action)}">{_e(unit.decision.action)}</span></div></div>
  <div class="finding"><div class="finding-card"><div class="finding-label">{'观测结果' if zh else 'Observed result'}</div>{_paragraphs(results)}</div><div class="finding-card conclusion"><div class="finding-label">{'科学结论' if zh else 'Scientific conclusion'}</div>{_paragraphs(conclusion)}</div></div>
  <h4>{'证据与数据' if zh else 'Evidence and data'}</h4><div class="link-grid">{file_links}{source_links}</div>
  <details open><summary>{'科学依据、假设与前置结论' if zh else 'Scientific rationale, hypothesis, and prerequisites'}</summary><div class="detail-body">{_paragraphs(rationale)}{hypotheses}<h4>{'前置结论与关系' if zh else 'Prerequisite conclusion and relationships'}</h4>{_paragraphs(prereq)}{dependencies}</div></details>
  <details><summary>{'分析方法与参数依据' if zh else 'Methods and parameter rationale'}</summary><div class="detail-body">{_paragraphs(methods)}{_list(method_items)}</div></details>
  <details><summary>{'科学复核与局限' if zh else 'Scientific review and limitations'}</summary><div class="detail-body">{review_body}</div></details>
  <details><summary>{'复现信息与完整校验值' if zh else 'Reproducibility details and full checksums'}</summary><div class="detail-body"><div class="digest-list">{''.join(f'<div class="digest-row"><span>{_e(ROLE_LABELS[language].get(item.role,item.role))}</span><code>{_e(item.sha256)}</code></div>' for item in unit.spec.files)}</div><p><strong>{'登记产物' if zh else 'Registered artifact'}:</strong> <code>{_e(unit.spec.artifact_id)}</code></p><p><strong>{'证据单元' if zh else 'Evidence unit'}:</strong> <code>{_e(unit.spec.id)}</code></p></div></details>
  <h4>{'对下一步的影响' if zh else 'Implication for the next step'}</h4>{_paragraphs(unit.decision.rationale_zh if zh else unit.decision.rationale_en)}
  <a class="back-top" href="#top">↑ {'返回顶部' if zh else 'Back to top'}</a>
</article>"""


def render_report_html(evidence_map: ScientificEvidenceMap, language: str, workspace_root: Path) -> str:
    evidence_map.validate_integrity()
    zh = language == "zh"
    grouped: dict[str, list[EvidenceMapUnit]] = defaultdict(list)
    for unit in evidence_map.units:
        grouped[unit.spec.group_id].append(unit)
    toc_items = [f'<li><a href="#overview">{"项目概览" if zh else "Project overview"}</a></li>']
    for group_id in sorted(grouped):
        toc_items.append(f'<li><a href="#{_anchor(group_id, "group")}">{_e(group_id)}</a></li>')
        toc_items.extend(
            f'<li><a class="toc-child" href="#{_anchor(unit.spec.id)}">{_e(unit.spec.panel_id or unit.artifact_type)}</a></li>'
            for unit in sorted(grouped[group_id], key=lambda value: value.spec.id)
        )
    relationship_items = [
        f'<a href="#{_anchor(edge.source)}"><code>{_e(edge.source)}</code></a> → '
        f'<a href="#{_anchor(edge.target)}"><code>{_e(edge.target)}</code></a>'
        for edge in evidence_map.story_edges
    ]
    body = f"""
<section id="overview">{_metadata_cards(evidence_map, language)}
<div class="section-card"><h2>{'研究问题' if zh else 'Research question'}</h2>{_paragraphs(evidence_map.scientific_question)}
<div class="callout">{_e(evidence_map.version.change_summary_zh if zh else evidence_map.version.change_summary_en)}</div></div>
<div class="section-card"><h2>{'项目结果关系' if zh else 'Relationships among project results'}</h2>{_list(relationship_items) if relationship_items else '<p class="empty">' + ('当前版本没有登记跨图组或跨数据依赖。' if zh else 'No cross-result dependency is registered in this version.') + '</p>'}</div></section>
"""
    for group_id in sorted(grouped):
        body += f'<section id="{_anchor(group_id, "group")}"><h2>{"证据组" if zh else "Evidence group"} · {_e(group_id)}</h2>'
        body += "".join(
            _report_unit(unit, evidence_map, language, workspace_root)
            for unit in sorted(grouped[group_id], key=lambda value: value.spec.id)
        )
        body += "</section>"
    body += f'<section class="section-card"><h2>{"版本与校验" if zh else "Version and verification"}</h2><div class="digest-list">'
    for label, value in [
        (("科学证据地图" if zh else "Evidence map"), evidence_map.digest),
        (("文件关系表" if zh else "Edge table"), evidence_map.edge_table_digest),
        (("项目状态" if zh else "Project state"), evidence_map.state_digest),
        (("父版本" if zh else "Parent version"), evidence_map.version.parent_map_digest or "none"),
    ]:
        body += f'<div class="digest-row"><span>{_e(label)}</span><code>{_e(value)}</code></div>'
    body += "</div></section>"
    filename = f"scientific-evidence-report.{'zh-CN' if zh else 'en'}.html"
    return _page_shell(
        language=language,
        title="基于科学证据地图的项目解读报告" if zh else "Project interpretation report",
        eyebrow="Scientific evidence report",
        navigation=_navigation(language, current=filename),
        toc="<ul>" + "".join(toc_items) + "</ul>",
        body=body,
    )


def _story_levels(evidence_map: ScientificEvidenceMap) -> dict[str, int]:
    nodes = {unit.spec.id for unit in evidence_map.units if unit.spec.panel_id is not None}
    parents: dict[str, set[str]] = {node: set() for node in nodes}
    children: dict[str, set[str]] = {node: set() for node in nodes}
    for edge in evidence_map.story_edges:
        if edge.source in nodes and edge.target in nodes:
            parents[edge.target].add(edge.source)
            children[edge.source].add(edge.target)
    indegree = {node: len(values) for node, values in parents.items()}
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    levels = {node: 0 for node in queue}
    while queue:
        node = queue.popleft()
        for child in sorted(children[node]):
            levels[child] = max(levels.get(child, 0), levels[node] + 1)
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    for node in sorted(nodes):
        levels.setdefault(node, 0)
    return levels


def _story_svg(evidence_map: ScientificEvidenceMap, language: str) -> str:
    units = {unit.spec.id: unit for unit in evidence_map.units if unit.spec.panel_id is not None}
    if not units:
        return '<p class="empty">' + (
            "当前版本没有登记跨图组关系。" if language == "zh"
            else "No cross-figure relationship is registered in this version."
        ) + '</p>'
    levels = _story_levels(evidence_map)
    grouped: dict[int, list[str]] = defaultdict(list)
    for node, level in levels.items():
        grouped[level].append(node)
    for nodes in grouped.values():
        nodes.sort()
    width = max(760, (max(grouped) + 1) * 240 + 100)
    height = max(190, max(len(nodes) for nodes in grouped.values()) * 105 + 70)
    positions: dict[str, tuple[int, int]] = {}
    for level, nodes in grouped.items():
        for index, node in enumerate(nodes):
            y = 35 + index * 105 + max(0, (height - 70 - len(nodes) * 105) // 2)
            positions[node] = (45 + level * 240, y)
    elements = [
        '<svg class="story-graph" role="img" aria-label="Scientific evidence relationships" '
        f'viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#88aaa5"/></marker></defs>',
    ]
    for edge in evidence_map.story_edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        sx, sy = positions[edge.source]
        tx, ty = positions[edge.target]
        elements.append(
            f'<path class="graph-edge" marker-end="url(#arrow)" d="M {sx + 180} {sy + 28} C {sx + 205} {sy + 28}, {tx - 25} {ty + 28}, {tx} {ty + 28}"/>'
        )
    for node, (x, y) in positions.items():
        label = units[node].spec.panel_id or units[node].artifact_type
        short_label = label[:24] + ("…" if len(label) > 24 else "")
        elements.append(
            f'<a href="#{_anchor(node)}" class="graph-node"><rect x="{x}" y="{y}" width="180" height="56" rx="12"/>'
            f'<text x="{x + 90}" y="{y + 33}" text-anchor="middle">{_e(short_label)}</text></a>'
        )
    elements.append("</svg>")
    return '<div class="graph-scroll">' + "".join(elements) + "</div>"


def _route_stage(label: str, cards: list[str]) -> str:
    return f'<div class="route-stage"><div class="route-label">{_e(label)}</div>{"".join(cards)}</div>'


def _map_unit(unit: EvidenceMapUnit, language: str, workspace_root: Path) -> str:
    zh = language == "zh"
    title = unit.spec.panel_id or unit.artifact_type
    stages: dict[int, list[str]] = defaultdict(list)
    if unit.spec.predecessor_unit_ids:
        stages[-1].extend(
            f'<a class="route-card" href="#{_anchor(value)}">{_e(value)}</a>'
            for value in unit.spec.predecessor_unit_ids
        )
    stages[1].append(f'<div class="route-card current">{_e(title)}<br><small>{_e(unit.spec.artifact_id)}</small></div>')
    for item in sorted(unit.spec.files, key=lambda value: (FILE_STAGE_ORDER[value.role], value.path)):
        stages[FILE_STAGE_ORDER[item.role]].append(_file_link(item, workspace_root, language, compact=True))
    stages[7].extend(_source_link(source, language, compact=True) for source in unit.spec.narrative_sources)
    stage_names = {
        -1: "前置数据或结论" if zh else "Prerequisite data or conclusion",
        0: "登记数据" if zh else "Registered data",
        1: "当前数据或图组" if zh else "Current data or figure",
        2: "作图数据" if zh else "Plot-ready data",
        3: "分析程序" if zh else "Analysis",
        4: "排图程序" if zh else "Renderer",
        5: "最终数据与图件" if zh else "Final data and figures",
        6: "图注" if zh else "Caption",
        7: "研究来源" if zh else "Research sources",
    }
    route = '<div class="route">' + "".join(_route_stage(stage_names[index], stages[index]) for index in sorted(stages)) + "</div>"
    return f"""<article class="unit" id="{_anchor(unit.spec.id)}"><div class="unit-header"><div><div class="unit-kicker">{_e(unit.spec.group_id)}</div><h3>{_e(title)}</h3></div><span class="badge {_status_class(unit.review.overall_status)}">{_e(unit.review.overall_status)}</span></div>{route}<details><summary>{'完整文件与来源列表' if zh else 'Complete file and source list'}</summary><div class="detail-body"><div class="link-grid">{''.join(_file_link(item, workspace_root, language) for item in unit.spec.files)}{''.join(_source_link(source, language) for source in unit.spec.narrative_sources)}</div></div></details><a class="back-top" href="#top">↑ {'返回顶部' if zh else 'Back to top'}</a></article>"""


def render_map_html(evidence_map: ScientificEvidenceMap, language: str, workspace_root: Path) -> str:
    evidence_map.validate_integrity()
    zh = language == "zh"
    grouped: dict[str, list[EvidenceMapUnit]] = defaultdict(list)
    for unit in evidence_map.units:
        grouped[unit.spec.group_id].append(unit)
    toc = ['<li><a href="#story">' + ("项目主线" if zh else "Project story") + '</a></li>']
    for group_id in sorted(grouped):
        toc.append(f'<li><a href="#{_anchor(group_id, "map-group")}">{_e(group_id)}</a></li>')
        toc.extend(
            f'<li><a class="toc-child" href="#{_anchor(unit.spec.id)}">{_e(unit.spec.panel_id or unit.artifact_type)}</a></li>'
            for unit in sorted(grouped[group_id], key=lambda value: value.spec.id)
        )
    body = _metadata_cards(evidence_map, language)
    body += f'<section class="section-card" id="story"><h2>{"项目结果之间的关系" if zh else "Relationships among project results"}</h2><p>{"选择任一节点可跳转到对应数据、程序、图件、图注和原始研究。" if zh else "Select a node to jump to its data, scripts, figures, caption, and original studies."}</p>{_story_svg(evidence_map, language)}</section>'
    for group_id in sorted(grouped):
        body += f'<section id="{_anchor(group_id, "map-group")}"><h2>{"证据组" if zh else "Evidence group"} · {_e(group_id)}</h2>'
        body += "".join(_map_unit(unit, language, workspace_root) for unit in sorted(grouped[group_id], key=lambda value: value.spec.id))
        body += "</section>"
    filename = f"scientific-evidence-map.{'zh-CN' if zh else 'en'}.html"
    return _page_shell(
        language=language,
        title="科学证据地图" if zh else "Scientific evidence map",
        eyebrow="Evidence relationships and source files",
        navigation=_navigation(language, current=filename),
        toc="<ul>" + "".join(toc) + "</ul>",
        body=body,
    )


def render_portal_html(evidence_map: ScientificEvidenceMap) -> str:
    """Create a compact language-neutral landing page for one immutable version."""
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%230a7468'/%3E%3Cpath d='M8 16h16M16 8v16' stroke='white' stroke-width='3'/%3E%3C/svg%3E"><title>Biomed Workbench · Evidence report</title><style>body{{margin:0;background:#f3f6f5;color:#17242b;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif}}main{{max-width:940px;margin:8vh auto;padding:2rem}}.hero{{background:linear-gradient(135deg,#123c3a,#0a7468);color:white;border-radius:26px;padding:3rem}}h1{{font-size:clamp(2rem,5vw,3.5rem);margin:.4rem 0}}p{{line-height:1.7}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem;margin-top:1.2rem}}a{{display:block;background:white;color:#173b38;border:1px solid #d8e0df;border-radius:16px;padding:1.2rem;text-decoration:none}}a:hover{{border-color:#0a7468;box-shadow:0 10px 30px rgba(10,116,104,.1)}}small{{display:block;color:#687772;margin-top:.35rem}}code{{overflow-wrap:anywhere}}@media(prefers-color-scheme:dark){{body{{background:#101716;color:#e6efed}}a{{background:#17201f;color:#e6efed;border-color:#33413f}}}}</style></head><body><main><section class="hero"><div>Biomed Workbench</div><h1>科学证据报告<br><span lang="en">Scientific evidence report</span></h1><p>{_e(evidence_map.project_id)} · v{_e(evidence_map.version.version)}</p></section><div class="grid"><a href="scientific-evidence-report.zh-CN.html"><strong>中文项目解读报告</strong><small>结果、结论、证据与下一步</small></a><a href="scientific-evidence-report.en.html"><strong>English interpretation report</strong><small>Results, conclusions, evidence, and next step</small></a><a href="scientific-evidence-map.zh-CN.html"><strong>中文科学证据地图</strong><small>数据、程序、图件、图注与文献关系</small></a><a href="scientific-evidence-map.en.html"><strong>English evidence map</strong><small>Data, scripts, figures, captions, and sources</small></a><a href="scientific-evidence-map.json"><strong>Machine-readable map</strong><small>JSON · <code>{_e(evidence_map.digest[:16])}…</code></small></a><a href="scientific-evidence-map.edges.tsv"><strong>Relationship table</strong><small>TSV · <code>{_e(evidence_map.edge_table_digest[:16])}…</code></small></a></div></main></body></html>"""
