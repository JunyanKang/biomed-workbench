#!/usr/bin/env python3
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = [
    "/Users/" + "kangjunyan",
    ".claude" + "-science",
    "biomedical-agent" + "-sources",
    "local" + ":",
]
REQUIRED_WORKFLOWS = {
    "evidence",
    "omics",
    "molecular_design",
    "imaging",
    "clinical",
    "wetlab",
    "publication",
    "runtime",
}
REQUIRED_ENTRY_FIELDS = {"id", "workflow", "kind", "name", "description", "source", "run_policy", "path"}
BAD_DESCRIPTION = re.compile(r"\b(import\s+\w+|from\s+\w+\s+import|def\s+[a-z_]\w*\s*\()")
SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{32,}"),
    re.compile(r"gh[opsu]_[A-Za-z0-9]{30,}"),
]


def fail(message):
    print(f"FAIL: {message}")
    return 1


def text_files():
    skip_dirs = {".git", "__pycache__", ".venv", "build", "dist"}
    for path in ROOT.rglob("*"):
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.is_file():
            yield path


def main():
    errors = []

    plugin_json = ROOT / ".codex-plugin" / "plugin.json"
    if not plugin_json.exists():
        errors.append("missing .codex-plugin/plugin.json")
        plugin = {}
    else:
        plugin = json.loads(plugin_json.read_text())
        if plugin.get("name") != "biomed-workbench":
            errors.append("plugin name must be biomed-workbench")
        if plugin.get("skills") != "./skills/":
            errors.append("plugin skills path must be ./skills/")
        if plugin.get("license") != "Apache-2.0":
            errors.append("plugin license must be Apache-2.0")

    if not (ROOT / "LICENSE").exists():
        errors.append("missing LICENSE")

    marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"
    if not marketplace_path.exists():
        errors.append("missing .agents/plugins/marketplace.json")
    else:
        marketplace = json.loads(marketplace_path.read_text())
        plugins = marketplace.get("plugins", [])
        if marketplace.get("name") != "biomed-workbench":
            errors.append("marketplace name must be biomed-workbench")
        if len(plugins) != 1 or plugins[0].get("name") != "biomed-workbench":
            errors.append("marketplace must expose exactly biomed-workbench")
        elif plugins[0].get("source") != {"source": "local", "path": "."}:
            errors.append("marketplace plugin source must point to repository root")

    skill_files = sorted((ROOT / "skills").glob("*/SKILL.md"))
    if [p.relative_to(ROOT).as_posix() for p in skill_files] != ["skills/biomed-workbench/SKILL.md"]:
        errors.append("skills must expose exactly skills/biomed-workbench/SKILL.md")

    catalog_path = ROOT / "tools" / "catalog.json"
    if not catalog_path.exists():
        errors.append("missing tools/catalog.json")
        catalog = {"entries": []}
    else:
        catalog = json.loads(catalog_path.read_text())

    entries = catalog.get("entries", [])
    if catalog.get("entry_count") != len(entries):
        errors.append(f"catalog entry_count {catalog.get('entry_count')} != actual {len(entries)}")

    ids = [entry.get("id") for entry in entries]
    duplicates = sorted([tool_id for tool_id, count in Counter(ids).items() if count > 1])
    if duplicates:
        errors.append(f"duplicate catalog ids: {duplicates[:10]}")

    if set(catalog.get("workflows", [])) != REQUIRED_WORKFLOWS:
        errors.append("catalog workflows do not match the supported internal routes")
    if plugin.get("version") != catalog.get("version"):
        errors.append("plugin and catalog versions differ")

    malformed = []
    bad_descriptions = []
    unsafe_paths = []
    for entry in entries:
        missing = sorted(REQUIRED_ENTRY_FIELDS - entry.keys())
        if missing or entry.get("workflow") not in REQUIRED_WORKFLOWS:
            malformed.append((entry.get("id"), missing))
        description = str(entry.get("description", "")).strip()
        if description in {"", ">-", "|", "\ufeff---"} or BAD_DESCRIPTION.search(description):
            bad_descriptions.append(entry.get("id"))
        rel = str(entry.get("path", ""))
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts:
            unsafe_paths.append((entry.get("id"), rel))
    if malformed:
        errors.append(f"malformed catalog entries: {malformed[:10]}")
    if bad_descriptions:
        errors.append(f"non-human catalog descriptions: {bad_descriptions[:10]}")
    if unsafe_paths:
        errors.append(f"unsafe catalog paths: {unsafe_paths[:10]}")

    required_sources = {"Biomni", "OpenScience", "Claude Science", "Nature Skills"}
    source_counts = Counter(entry.get("source") for entry in entries)
    missing_sources = sorted(source for source in required_sources if source_counts[source] == 0)
    if missing_sources:
        errors.append(f"missing source coverage: {missing_sources}")

    source_manifest_path = ROOT / "references" / "source_manifest.json"
    if source_manifest_path.exists():
        manifest = json.loads(source_manifest_path.read_text())
        expected_counts = manifest.get("counts", {}).get("by_source", {})
        if dict(source_counts) != expected_counts:
            errors.append("source_manifest.json source counts are stale")
        expected_workflows = manifest.get("counts", {}).get("by_workflow", {})
        actual_workflows = dict(Counter(entry.get("workflow") for entry in entries))
        if actual_workflows != expected_workflows:
            errors.append("source_manifest.json workflow counts are stale")
    else:
        errors.append("missing references/source_manifest.json")

    missing_paths = []
    for entry in entries:
        rel = entry.get("path")
        if not rel:
            continue
        if "://" in rel:
            continue
        if not (ROOT / rel).exists():
            missing_paths.append((entry.get("id"), rel))
    if missing_paths:
        sample = ", ".join(f"{tool_id}:{rel}" for tool_id, rel in missing_paths[:10])
        errors.append(f"catalog path entries missing in project: {sample}")

    forbidden_hits = []
    for path in text_files():
        try:
            text = path.read_text(errors="ignore")
        except UnicodeDecodeError:
            continue
        for needle in FORBIDDEN:
            if needle in text:
                forbidden_hits.append((path.relative_to(ROOT).as_posix(), needle))
                break
    if forbidden_hits:
        sample = ", ".join(f"{path}:{needle}" for path, needle in forbidden_hits[:10])
        errors.append(f"forbidden publish strings found: {sample}")

    secret_hits = []
    for path in text_files():
        text = path.read_text(errors="ignore")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            secret_hits.append(path.relative_to(ROOT).as_posix())
    if secret_hits:
        errors.append(f"credential-like values found: {secret_hits[:10]}")

    syntax_errors = []
    for path in list((ROOT / "tools").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")):
        try:
            ast.parse(path.read_text(errors="ignore"), filename=str(path))
        except SyntaxError as exc:
            syntax_errors.append(f"{path.relative_to(ROOT)}:{exc.lineno}")
    if syntax_errors:
        errors.append(f"Python syntax errors: {syntax_errors[:10]}")

    readme = (ROOT / "README.md").read_text(errors="ignore")
    required_readme = [
        "codex plugin marketplace add JunyanKang/biomed-workbench --ref main",
        "codex plugin add biomed-workbench@biomed-workbench",
        "python3 -m unittest discover -s tests -v",
        "new Codex task",
    ]
    missing_docs = [line for line in required_readme if line not in readme]
    if missing_docs:
        errors.append(f"README missing release guidance: {missing_docs}")

    if errors:
        for error in errors:
            fail(error)
        return 1

    print("OK: biomed-workbench validation passed")
    print(f"entries={len(entries)}")
    print("sources=" + ", ".join(f"{k}:{source_counts[k]}" for k in sorted(required_sources)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
