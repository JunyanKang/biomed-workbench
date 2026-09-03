"""Human-readable HTML delivery for verified biomedical writing revisions."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping


HTML_RENDERER_VERSION = "1.1.2"
_ROLE_ZH = {
    "field-premise": "领域基础", "knowledge-gap": "知识空白", "discovery": "主要发现",
    "source-context": "来源与背景", "mechanistic-consistency": "机制一致性",
    "orthogonal-validation": "正交验证", "boundary-null": "阴性与边界", "integration": "综合判断",
}
_DOCUMENT_ZH = {
    "research-article": "研究论文", "review-article": "综述", "thesis": "学位论文",
    "rebuttal": "审稿回复", "grant-proposal": "科研项目申请书", "results": "结果",
    "discussion": "讨论", "introduction": "引言", "methods": "方法", "abstract": "摘要",
}

def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _items(rows: list[Mapping[str, Any]], empty: str) -> str:
    if not rows:
        return f'<p class="empty">{_e(empty)}</p>'
    return "<ul>" + "".join(
        f'<li><strong>{_e(row.get("code", "Finding"))}</strong> '
        f'{_e(row.get("action") or row.get("revision") or row.get("message") or "")}</li>'
        for row in rows
    ) + "</ul>"


def _labels(text: str) -> dict[str, str]:
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text)) >= 4
    if not chinese:
        return {
            "lang": "en", "title": "Biomedical writing and scientific-logic review",
            "ready": "Ready for delivery", "revise": "Revision required",
            "summary": "Summary", "argument": "Scientific argument", "evidence": "Evidence",
            "revision": "Revision", "findings": "Review findings", "sources": "Sources",
            "decision": "Decision", "blocking": "Blocking findings", "question": "Question",
            "claim": "Claim under review", "source": "Source", "revised": "Revised",
            "project_evidence": "Project evidence", "literature": "Literature used in the argument",
            "venue": "Venue guidance", "no_findings": "No unresolved prose findings.",
            "headers": ["ID", "Role", "Finding", "Effect", "Uncertainty", "Unit"],
            "profile": "Writing profile", "delivery_message": "Deliver the revised text with this linked review.",
        }
    return {
        "lang": "zh-CN", "title": "生命科学写作与科学逻辑复核",
        "ready": "可以交付", "revise": "仍需修改",
        "summary": "结论", "argument": "科学论证", "evidence": "证据顺序",
        "revision": "文本修改", "findings": "尚需处理的问题", "sources": "证据与来源",
        "decision": "当前决定", "blocking": "阻断交付的问题", "question": "科学问题",
        "claim": "待检验的核心判断", "source": "原文", "revised": "修订稿",
        "project_evidence": "项目证据", "literature": "论证所依据的文献",
        "venue": "目标期刊要求", "no_findings": "没有尚未解决的文字问题。",
        "headers": ["编号", "科学作用", "结果", "效应", "不确定性", "实验单位"],
        "profile": "写作配置", "delivery_message": "修订稿已通过复核，可与本页所列证据和来源一并交付。",
    }


def render_biomedical_writing_html(report: Mapping[str, Any], report_directory: Path | None = None) -> str:
    document = report.get("document", {})
    argument = report.get("scientific_argument", {}) or {}
    evidence = argument.get("evidence_sequence", [])
    literature = argument.get("literature_context", [])
    paragraphs = argument.get("paragraph_plan", [])
    ready = bool(report.get("ready_for_delivery"))
    original = str(report.get("original_text", ""))
    revised = str(report.get("revised_text", ""))
    label = _labels(original + revised)
    status = label["ready"] if ready else label["revise"]
    document_type = str(document.get("type", ""))
    document_section = str(document.get("section", ""))
    if label["lang"] == "zh-CN":
        document_type = _DOCUMENT_ZH.get(document_type.lower(), document_type)
        document_section = _DOCUMENT_ZH.get(document_section.lower(), document_section)
    role_name = lambda value: _ROLE_ZH.get(str(value), str(value)) if label["lang"] == "zh-CN" else str(value)
    evidence_rows = "".join(
        "<tr>"
        f'<td>{_e(row.get("id", ""))}</td><td>{_e(role_name(row.get("evidence_role", "")))}</td>'
        f'<td>{_e(row.get("finding", ""))}</td><td>{_e(row.get("effect", ""))}</td>'
        f'<td>{_e(row.get("uncertainty", ""))}</td><td>{_e(row.get("experimental_unit", ""))}</td>'
        "</tr>" for row in evidence
    ) or '<tr><td colspan="6" class="empty">No evidence sequence supplied.</td></tr>'
    source_links = "".join(
        f'<li><a href="{_e(row.get("url") or "https://doi.org/" + str(row.get("doi", "")))}" '
        f'target="_blank" rel="noopener noreferrer">{_e(row.get("statement", row.get("id", "Source")))}</a>'
        f'<span class="meta"> DOI {_e(row.get("doi", ""))} · {_e(row.get("relation", ""))}</span></li>'
        for row in literature
    ) or '<li class="empty">No literature context supplied.</li>'
    def artifact_href(value: object) -> str:
        path = Path(str(value)).expanduser()
        if path.is_absolute():
            return path.resolve(strict=False).as_uri()
        if report_directory is None:
            return path.as_posix()
        return Path(os.path.relpath(path.resolve(strict=False), report_directory.resolve(strict=False))).as_posix()

    artifact_links = "".join(
        f'<li><a href="{_e(artifact_href(row["artifact_path"]))}" '
        f'target="_blank" rel="noopener">{_e(row.get("figure_or_table") or row.get("id"))}</a>'
        f'<span class="meta"> {_e(row.get("artifact_path"))}</span></li>'
        for row in evidence if row.get("artifact_path")
    ) or '<li class="empty">No local evidence file linked.</li>'
    plan = "".join(
        f'<article><span class="step">{_e(row.get("paragraph", ""))}</span>'
        f'<div><h3>{_e(role_name(row.get("job", "")))}</h3><p>{_e(row.get("topic_sentence_content", ""))}</p>'
        f'<small>{_e(" · ".join(str(v) for v in row.get("must_report", [])))}</small></div></article>'
        for row in paragraphs
    ) or '<p class="empty">No paragraph plan supplied.</p>'
    profile = report.get("venue_profile", {}) or {}
    profile_sources = "".join(
        f'<li><a href="{_e(url)}" target="_blank" rel="noopener noreferrer">{_e(url)}</a></li>'
        for url in profile.get("official_sources", [])
    )
    profile_examples = "".join(
        f'<li><a href="{_e(row.get("url", ""))}" target="_blank" rel="noopener noreferrer">DOI {_e(row.get("doi", ""))}</a>'
        f'<span class="meta"> {_e(row.get("use", ""))}</span></li>'
        for row in profile.get("research_examples", [])
    )
    return f'''<!doctype html>
<html lang="{label['lang']}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{label['title']}</title><style>
:root{{--ink:#17243b;--muted:#65728a;--line:#dbe3ef;--paper:#fff;--wash:#f5f8fc;--accent:#176b87;--ok:#217a58;--warn:#9a5b14}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);color:var(--ink);font:15px/1.68 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}}
main{{max-width:1120px;margin:auto;padding:42px 28px 80px}}header{{background:linear-gradient(135deg,#17395c,#176b87);color:white;padding:34px;border-radius:18px;box-shadow:0 14px 35px #183b6028}}
h1{{margin:0 0 8px;font-size:30px}}h2{{margin:0 0 18px;font-size:21px}}h3{{margin:0;font-size:15px}}.meta{{color:var(--muted);font-size:13px}}header .meta{{color:#d7edf5}}nav{{display:flex;flex-wrap:wrap;gap:9px;margin:20px 0}}nav a{{background:white;color:var(--accent);border:1px solid var(--line);border-radius:999px;padding:7px 12px;text-decoration:none}}
section{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:25px;margin-top:17px}}.status{{display:inline-block;padding:5px 10px;border-radius:99px;background:{'#dff5e9' if ready else '#fff0db'};color:{'var(--ok)' if ready else 'var(--warn)'};font-weight:700}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}pre{{white-space:pre-wrap;margin:0;background:#f8fafc;border:1px solid var(--line);padding:18px;border-radius:10px;font:14px/1.75 Georgia,"Times New Roman",serif}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}}th{{font-size:12px;color:var(--muted);text-transform:uppercase}}article{{display:grid;grid-template-columns:34px 1fr;gap:12px;padding:12px 0;border-bottom:1px solid var(--line)}}.step{{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#e4f3f7;color:var(--accent);font-weight:700}}a{{color:var(--accent)}}.empty{{color:var(--muted)}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}main{{padding:18px}}}}
</style></head><body><main>
<header><h1>{label['title']}</h1><p>{_e(document_type)} · {_e(document_section)} · {_e(document.get('target_venue',''))}</p><span class="status">{status}</span><p class="meta">{label['profile']} {_e(profile.get('profile_id','general-biomedical'))} · {_e(profile.get('profile_version',''))}</p></header>
<nav><a href="#summary">{label['summary']}</a><a href="#argument">{label['argument']}</a><a href="#evidence">{label['evidence']}</a><a href="#text">{label['revision']}</a><a href="#findings">{label['findings']}</a><a href="#sources">{label['sources']}</a></nav>
<section id="summary"><h2>{label['decision']}</h2><p>{_e(label['delivery_message'] if ready else report.get('next_step',''))}</p><p>{label['blocking']}: <strong>{_e(report.get('major_or_fatal_count',0))}</strong></p></section>
<section id="argument"><h2>{label['argument']}</h2><p><strong>{label['question']}:</strong> {_e(argument.get('central_question','Not supplied'))}</p><p><strong>{label['claim']}:</strong> {_e(argument.get('central_claim','Not supplied'))}</p>{plan}</section>
<section id="evidence"><h2>{label['evidence']}</h2><table><thead><tr>{''.join(f'<th>{_e(value)}</th>' for value in label['headers'])}</tr></thead><tbody>{evidence_rows}</tbody></table></section>
<section id="text"><h2>{label['revision']}</h2><div class="grid"><div><h3>{label['source']}</h3><pre>{_e(original)}</pre></div><div><h3>{label['revised']}</h3><pre>{_e(revised)}</pre></div></div></section>
<section id="findings"><h2>{label['findings']}</h2>{_items(list(report.get('findings',[])), label['no_findings'])}</section>
<section id="sources"><h2>{label['sources']}</h2><h3>{label['project_evidence']}</h3><ul>{artifact_links}</ul><h3>{label['literature']}</h3><ul>{source_links}</ul><h3>{label['venue']}</h3><ul>{profile_sources}{profile_examples}</ul></section>
</main></body></html>'''


def write_biomedical_writing_report(report: Mapping[str, Any], output_directory: Path) -> dict[str, Any]:
    revision_digest = str(report.get("revision_digest", ""))
    argument_digest = str((report.get("scientific_argument", {}) or {}).get("argument_digest", ""))
    if not revision_digest or not argument_digest:
        raise ValueError("revision and scientific-argument identities are required for versioned delivery")
    renderer_token = HTML_RENDERER_VERSION.replace(".", "")
    version_id = f"writing-{revision_digest[:12]}-{argument_digest[:12]}-r{renderer_token}"
    version_directory = output_directory / version_id
    version_directory.mkdir(parents=True, exist_ok=True)
    html_path = version_directory / "biomedical-writing-report.html"
    json_path = version_directory / "biomedical-writing-review.json"
    html_payload = render_biomedical_writing_html(report, version_directory)
    json_payload = json.dumps(dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    for path, payload in ((html_path, html_payload), (json_path, json_payload)):
        if path.exists() and path.read_text(encoding="utf-8") != payload:
            raise FileExistsError(f"versioned writing delivery already exists with different content: {path}")
        if not path.exists():
            path.write_text(payload, encoding="utf-8")
    reopened = html_path.read_text(encoding="utf-8")
    required = ('id="summary"', 'id="argument"', 'id="evidence"', 'id="text"', 'id="sources"')
    verified = all(marker in reopened for marker in required) and len(reopened) == len(html_payload)
    return {
        "html": html_path.resolve().as_posix(),
        "json": json_path.resolve().as_posix(),
        "html_sha256": hashlib.sha256(html_path.read_bytes()).hexdigest(),
        "json_sha256": hashlib.sha256(json_path.read_bytes()).hexdigest(),
        "version_id": version_id,
        "renderer_version": HTML_RENDERER_VERSION,
        "version_directory": version_directory.resolve().as_posix(),
        "delivery_verified": verified,
    }
