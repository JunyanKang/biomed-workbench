#!/usr/bin/env python3
import argparse
import ast
import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "tools" / "catalog.json"
BAD_MARKERS = {">-", "|", "\ufeff---"}
CODE_LIKE = re.compile(r"\b(import\s+\w+|from\s+\w+\s+import|def\s+[a-z_]\w*\s*\()")
NATURE_SKILLS = {
    "publication_academic_search": "nature-academic-search",
    "publication_citation": "nature-citation",
    "publication_data": "nature-data",
    "publication_downloader": "nature-downloader",
    "publication_experiment_log": "nature-experiment-log",
    "publication_figure": "nature-figure",
    "publication_literature_pipeline": "nature-literature-pipeline",
    "publication_paper_to_patent": "nature-paper-to-patent",
    "publication_paper2ppt": "nature-paper2ppt",
    "publication_polishing": "nature-polishing",
    "publication_proposal_writer": "nature-proposal-writer",
    "publication_reader": "nature-reader",
    "publication_ref_verifier": "nature-ref-verifier",
    "publication_response": "nature-response",
    "publication_reviewer": "nature-reviewer",
    "publication_statistics": "nature-statistics",
    "publication_writing": "nature-writing",
}


def compact(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def trim_description(value, limit=700):
    text = compact(value)
    if len(text) <= limit:
        return text
    shortened = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return shortened + "."


def frontmatter_description(path):
    lines = path.read_text(errors="ignore").lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            break
        if not line.startswith("description:"):
            continue
        value = line.split(":", 1)[1].strip()
        if value not in {">-", ">", "|", "|-"}:
            return trim_description(value.strip("\"'"))
        parts = []
        for continuation in lines[index + 1 :]:
            if continuation and not continuation[0].isspace():
                break
            stripped = continuation.strip()
            if stripped:
                parts.append(stripped)
        return trim_description(" ".join(parts))
    return ""


def module_description(path):
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except (OSError, SyntaxError):
        return ""
    return trim_description(ast.get_docstring(tree) or "")


def fallback_description(entry):
    name = compact(entry.get("name") or entry.get("id")).replace("_", " ")
    kind = compact(entry.get("kind", "capability")).replace("_", " ")
    workflow = compact(entry.get("workflow", "biomedical")).replace("_", " ")
    return f"{name}: reusable {kind} for the {workflow} workflow."


def description_is_bad(value):
    text = compact(value)
    return not text or text in BAD_MARKERS or bool(CODE_LIKE.search(text))


def refresh(catalog, nature_root=None):
    changed = []
    for entry in catalog.get("entries", []):
        replacement = ""
        skill_name = NATURE_SKILLS.get(entry.get("id"))
        if skill_name and nature_root:
            skill_file = nature_root / skill_name / "SKILL.md"
            if skill_file.exists():
                replacement = frontmatter_description(skill_file)

        if not replacement and description_is_bad(entry.get("description")):
            path = ROOT / entry.get("path", "")
            if entry.get("kind") == "script" and path.suffix.lower() == ".py" and path.exists():
                replacement = module_description(path)
            if not replacement:
                replacement = fallback_description(entry)

        if replacement and replacement != entry.get("description"):
            entry["description"] = replacement
            changed.append(entry.get("id"))

    catalog["generated"] = date.today().isoformat()
    catalog["entry_count"] = len(catalog.get("entries", []))
    return changed


def render_nature_reference(entries):
    patterns = [entry for entry in entries if entry.get("id") in NATURE_SKILLS]
    lines = [
        "# Nature Workflow Integration",
        "",
        "Nature-style capabilities are internal publication workflows behind the single `biomed-workbench` entry.",
        "The source skill names below are provenance metadata, not separate commands users must invoke.",
        "",
    ]
    for entry in sorted(patterns, key=lambda item: item["id"]):
        source_name = NATURE_SKILLS[entry["id"]]
        lines.append(f"- `{source_name}` -> `{entry['id']}`: {entry['description']}")
    return "\n".join(lines) + "\n"


def render_tool_catalog(entries):
    grouped = {}
    for entry in entries:
        grouped.setdefault(entry.get("workflow", "other"), []).append(entry)
    lines = [
        "# Tool Catalog",
        "",
        "This is the readable index behind the single `biomed-workbench` entry. Use `tools/search_tools.py` for ranked search.",
        "",
    ]
    for workflow in sorted(grouped):
        lines.extend([f"## {workflow.replace('_', ' ').title()}", ""])
        for entry in sorted(grouped[workflow], key=lambda item: item["id"]):
            lines.append(
                f"- `{entry['id']}` ({entry.get('kind', 'capability')}; {entry.get('run_policy', 'unspecified')}): "
                f"{entry['description']}"
            )
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Refresh human-readable metadata in the workbench catalog.")
    parser.add_argument("--nature-skills-root", type=Path, help="Optional directory containing installed nature-* skills.")
    parser.add_argument("--check", action="store_true", help="Exit nonzero if metadata would change.")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text())
    changed = refresh(catalog, args.nature_skills_root)
    if args.check:
        if changed:
            print("Metadata refresh required: " + ", ".join(changed))
            return 1
        print("Catalog metadata is current")
        return 0

    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    entries = catalog["entries"]
    (ROOT / "references" / "nature_workflows.md").write_text(render_nature_reference(entries))
    (ROOT / "references" / "tool_catalog.md").write_text(render_tool_catalog(entries))
    print(f"Refreshed {len(changed)} catalog description(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
