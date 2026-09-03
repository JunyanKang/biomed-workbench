"""Primary HTML delivery for outward-facing scientific analysis reports."""

from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path
from typing import Any, Mapping


ANALYSIS_REPORT_RENDERER_VERSION = "1.0.0"


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pick(item: Mapping[str, Any], stem: str, language: str) -> str:
    suffixes = ("zh", "en") if language == "zh-CN" else ("en", "zh")
    for suffix in suffixes:
        value = item.get(f"{stem}_{suffix}")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = item.get(stem)
    return value.strip() if isinstance(value, str) else ""


def _language(report: Mapping[str, Any], requested: str) -> str:
    if requested in {"zh-CN", "en"}:
        return requested
    if requested != "auto":
        raise ValueError("language must be auto, zh-CN, or en")
    text = f"{report.get('biological_question', '')} {report.get('project', '')}"
    return "zh-CN" if any("\u4e00" <= char <= "\u9fff" for char in text) else "en"


def _normalize_links(report: Mapping[str, Any]) -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    candidates = list(report.get("evidence_links", []))
    for result in report.get("scientific_results", []):
        if isinstance(result, Mapping):
            candidates.extend(result.get("evidence_links", []))
            candidates.extend(result.get("literature_links", []))
    for index, item in enumerate(candidates, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"evidence link {index} must be an object")
        label = str(item.get("label") or item.get("title") or "").strip()
        path_value = str(item.get("path") or "").strip()
        url = str(item.get("url") or "").strip()
        doi = str(item.get("doi") or "").strip()
        if not label or bool(path_value) == bool(url):
            raise ValueError(f"evidence link {index} requires a label and exactly one path or URL")
        if path_value:
            path = Path(path_value).expanduser().resolve(strict=True)
            if not path.is_file():
                raise ValueError(f"evidence link {index} does not identify a file")
            observed = _sha256(path)
            declared = str(item.get("sha256") or "").strip()
            if declared and declared != observed:
                raise ValueError(f"evidence link {index} checksum does not match the file")
            collected.append({"label": label, "path": path.as_posix(), "sha256": observed, "kind": "file"})
        else:
            if not (url.startswith("https://") or url.startswith("http://")):
                raise ValueError(f"evidence link {index} URL must use HTTP or HTTPS")
            collected.append({"label": label, "url": url, "doi": doi, "kind": "literature"})
    if not collected:
        raise ValueError("an outward analysis report requires at least one linked data, figure, script, or literature source")
    return collected


def validate_analysis_report(report: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]]]:
    if not isinstance(report, Mapping):
        raise ValueError("report must be an object")
    question = str(report.get("biological_question") or "").strip()
    results = report.get("scientific_results")
    if not question or not isinstance(results, list) or not results:
        raise ValueError("report requires a biological question and at least one scientific result")
    for index, result in enumerate(results, start=1):
        if not isinstance(result, Mapping):
            raise ValueError(f"scientific result {index} must be an object")
        if not any(str(result.get(key) or "").strip() for key in ("observation", "observation_zh", "observation_en")):
            raise ValueError(f"scientific result {index} lacks an observation")
        if not any(str(result.get(key) or "").strip() for key in ("interpretation", "interpretation_zh", "interpretation_en")):
            raise ValueError(f"scientific result {index} lacks an interpretation")
        if not any(str(result.get(key) or "").strip() for key in ("experimental_unit", "statistical_unit")):
            raise ValueError(f"scientific result {index} lacks an experimental or statistical unit")
        if result.get("progress") not in {"SCIENTIFICALLY_REVIEWED", "FORMALLY_INCLUDED"}:
            raise ValueError(f"scientific result {index} has not completed scientific review")
        boundaries = result.get("evidence_boundary") or result.get("evidence_boundary_zh") or result.get("evidence_boundary_en")
        if not boundaries:
            raise ValueError(f"scientific result {index} lacks an evidence boundary")
    return question, results


def render_analysis_report_html(
    report: Mapping[str, Any], *, title: str, language: str, links: list[dict[str, str]], report_directory: Path
) -> str:
    question, results = validate_analysis_report(report)
    zh = language == "zh-CN"
    labels = {
        "eyebrow": "科学分析报告" if zh else "Scientific analysis report",
        "question": "生物学问题" if zh else "Biological question",
        "contents": "目录" if zh else "Contents",
        "results": "主要结果" if zh else "Key results",
        "observation": "观察结果" if zh else "Observation",
        "interpretation": "科学解释" if zh else "Scientific interpretation",
        "unit": "实验或统计单位" if zh else "Experimental or statistical unit",
        "boundary": "证据边界" if zh else "Evidence boundary",
        "decision": "下一步决定" if zh else "Next decision",
        "sources": "数据、图件、程序与文献" if zh else "Data, figures, code, and literature",
        "status": "当前进展" if zh else "Current progress",
    }
    cards = []
    for index, result in enumerate(results, start=1):
        boundaries = result.get(f"evidence_boundary_{'zh' if zh else 'en'}") or result.get("evidence_boundary") or []
        if isinstance(boundaries, str):
            boundaries = [boundaries]
        units = str(result.get("experimental_unit") or result.get("statistical_unit") or "")
        cards.append(
            f'<article id="result-{index}" class="result"><div class="result-head"><span>{index:02d}</span>'
            f'<strong>{_e(result.get("label") or result.get("panel") or labels["results"] + " " + str(index))}</strong>'
            f'<em>{_e(result.get("progress") or "reviewed")}</em></div>'
            f'<div class="pair"><section><h3>{labels["observation"]}</h3><p>{_e(_pick(result, "observation", language))}</p></section>'
            f'<section class="interpretation"><h3>{labels["interpretation"]}</h3><p>{_e(_pick(result, "interpretation", language))}</p></section></div>'
            f'<dl><div><dt>{labels["unit"]}</dt><dd>{_e(units)}</dd></div>'
            f'<div><dt>{labels["boundary"]}</dt><dd>{"<br>".join(_e(value) for value in boundaries)}</dd></div>'
            f'<div><dt>{labels["decision"]}</dt><dd>{_e(result.get("next_decision") or "")}</dd></div></dl></article>'
        )
    source_items = []
    for item in links:
        if item["kind"] == "file":
            href = Path(os.path.relpath(item["path"], report_directory)).as_posix()
            meta = f'SHA-256 {item["sha256"]}'
        else:
            href = item["url"]
            meta = f'DOI {item["doi"]}' if item.get("doi") else item["url"]
        source_items.append(
            f'<li><a href="{_e(href)}" target="_blank" rel="noopener noreferrer">{_e(item["label"])}</a>'
            f'<small>{_e(meta)}</small></li>'
        )
    toc = "".join(f'<a href="#result-{index}">{index:02d} · {_e(result.get("label") or labels["results"])}</a>' for index, result in enumerate(results, start=1))
    return f'''<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><style>
:root{{--ink:#18252b;--muted:#65747a;--paper:#f4f7f6;--card:#fff;--line:#d8e1df;--accent:#08766c;--wash:#e8f5f2}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.72 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif}}
main{{max-width:1160px;margin:auto;padding:38px 24px 80px}}header{{padding:38px;border-radius:22px;color:white;background:linear-gradient(130deg,#153e3b,#08766c);box-shadow:0 16px 42px #123c3722}}
.eyebrow{{font-size:12px;font-weight:750;letter-spacing:.12em;text-transform:uppercase;opacity:.78}}h1{{font-size:clamp(28px,4vw,42px);line-height:1.15;margin:8px 0 14px}}header p{{max-width:850px;font-size:17px;margin:0;color:#e0f2ef}}
.layout{{display:grid;grid-template-columns:230px 1fr;gap:20px;margin-top:20px}}nav{{position:sticky;top:20px;align-self:start;background:var(--card);border:1px solid var(--line);border-radius:15px;padding:16px}}nav strong{{display:block;margin-bottom:8px}}nav a{{display:block;color:var(--ink);text-decoration:none;padding:7px 8px;border-radius:8px}}nav a:hover{{background:var(--wash);color:var(--accent)}}
.result,.sources{{background:var(--card);border:1px solid var(--line);border-radius:17px;padding:24px;margin-bottom:16px}}.result{{border-top:4px solid var(--accent)}}.result-head{{display:flex;align-items:center;gap:10px;margin-bottom:17px}}.result-head span{{color:var(--accent);font-weight:800}}.result-head strong{{font-size:18px}}.result-head em{{margin-left:auto;color:var(--muted);font-size:12px;font-style:normal}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}.pair section{{background:#f8faf9;border:1px solid var(--line);border-radius:12px;padding:16px}}.pair .interpretation{{background:var(--wash);border-color:#b9dcd6}}h2{{font-size:22px}}h3{{font-size:13px;letter-spacing:.04em;margin:0 0 7px;color:var(--muted)}}p{{margin:0}}dl{{margin:14px 0 0}}dl div{{display:grid;grid-template-columns:180px 1fr;border-top:1px solid var(--line);padding:10px 0}}dt{{font-weight:700}}dd{{margin:0}}.sources ul{{padding:0;list-style:none}}.sources li{{padding:10px 0;border-bottom:1px solid var(--line)}}.sources a{{display:block;color:var(--accent);overflow-wrap:anywhere}}.sources small{{display:block;color:var(--muted);overflow-wrap:anywhere}}
@media(max-width:760px){{main{{padding:18px 12px 50px}}header{{padding:26px}}.layout{{grid-template-columns:1fr}}nav{{position:static}}.pair{{grid-template-columns:1fr}}dl div{{grid-template-columns:1fr}}}}
</style></head><body><main><header><div class="eyebrow">{labels["eyebrow"]}</div><h1>{_e(title)}</h1><p><strong>{labels["question"]}：</strong>{_e(question)}</p></header>
<div class="layout"><nav><strong>{labels["contents"]}</strong>{toc}<a href="#sources">{labels["sources"]}</a></nav><div>{''.join(cards)}
<section id="sources" class="sources"><h2>{labels["sources"]}</h2><ul>{''.join(source_items)}</ul></section></div></div></main></body></html>'''


def _render_markdown(report: Mapping[str, Any], *, title: str, language: str, links: list[dict[str, str]]) -> str:
    _, results = validate_analysis_report(report)
    zh = language == "zh-CN"
    lines = [f"# {title}", "", f"**{'生物学问题' if zh else 'Biological question'}:** {report['biological_question']}", ""]
    for index, result in enumerate(results, start=1):
        boundaries = result.get(f"evidence_boundary_{'zh' if zh else 'en'}") or result.get("evidence_boundary") or []
        if isinstance(boundaries, str):
            boundaries = [boundaries]
        lines.extend([
            f"## {index}. {result.get('label') or ('主要结果' if zh else 'Key result')}", "",
            f"**{'观察结果' if zh else 'Observation'}:** {_pick(result, 'observation', language)}", "",
            f"**{'科学解释' if zh else 'Scientific interpretation'}:** {_pick(result, 'interpretation', language)}", "",
            f"**{'实验或统计单位' if zh else 'Experimental or statistical unit'}:** {result.get('experimental_unit') or result.get('statistical_unit')}", "",
            f"**{'证据边界' if zh else 'Evidence boundary'}:** {'; '.join(str(value) for value in boundaries)}", "",
        ])
    lines.extend([f"## {'来源' if zh else 'Sources'}", ""])
    for item in links:
        target = item.get("path") or item.get("url")
        lines.append(f"- [{item['label']}]({target})")
    return "\n".join(lines) + "\n"


def assert_primary_html_delivery(files: Mapping[str, Any]) -> None:
    """Reject a Markdown-only or non-reopened formal analysis-report delivery."""
    if files.get("primary_format") != "html" or files.get("primary") != files.get("html"):
        raise ValueError("formal analysis-report delivery requires HTML as the primary artifact")
    html_path = Path(str(files.get("html", "")))
    if html_path.suffix.lower() not in {".html", ".htm"} or not html_path.is_file():
        raise ValueError("formal analysis-report HTML is missing")
    reopened = html_path.read_text(encoding="utf-8")
    if not all(marker in reopened for marker in ('<nav>', 'id="result-1"', 'id="sources"')):
        raise ValueError("formal analysis-report HTML failed reopen verification")
    if files.get("delivery_verified") is not True:
        raise ValueError("formal analysis-report delivery is not verified")


def write_analysis_report(
    report: Mapping[str, Any], output_directory: Path, *, title: str = "", language: str = "auto", markdown_companion: bool = True
) -> dict[str, Any]:
    validate_analysis_report(report)
    resolved_language = _language(report, language)
    links = _normalize_links(report)
    resolved_title = title.strip() or ("项目科学分析报告" if resolved_language == "zh-CN" else "Project scientific analysis report")
    report_digest = _canonical_digest(report)
    token = ANALYSIS_REPORT_RENDERER_VERSION.replace(".", "")
    version_directory = output_directory.expanduser() / f"analysis-{report_digest[:16]}-r{token}"
    version_directory.mkdir(parents=True, exist_ok=True)
    html_path = version_directory / "analysis-report.html"
    json_path = version_directory / "analysis-report.json"
    markdown_path = version_directory / "analysis-report.md"
    payloads = {
        html_path: render_analysis_report_html(report, title=resolved_title, language=resolved_language, links=links, report_directory=version_directory),
        json_path: json.dumps({"report": dict(report), "resolved_links": links}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    }
    if markdown_companion:
        payloads[markdown_path] = _render_markdown(report, title=resolved_title, language=resolved_language, links=links)
    for path, payload in payloads.items():
        if path.exists() and path.read_text(encoding="utf-8") != payload:
            raise FileExistsError(f"versioned analysis report already exists with different content: {path}")
        if not path.exists():
            path.write_text(payload, encoding="utf-8")
    files: dict[str, Any] = {
        "primary": html_path.resolve().as_posix(), "primary_format": "html", "html": html_path.resolve().as_posix(),
        "json": json_path.resolve().as_posix(), "markdown": markdown_path.resolve().as_posix() if markdown_companion else None,
        "html_sha256": _sha256(html_path), "json_sha256": _sha256(json_path),
        "markdown_sha256": _sha256(markdown_path) if markdown_companion else None,
        "version_directory": version_directory.resolve().as_posix(), "renderer_version": ANALYSIS_REPORT_RENDERER_VERSION,
        "report_digest": report_digest, "delivery_verified": True,
    }
    assert_primary_html_delivery(files)
    return files
