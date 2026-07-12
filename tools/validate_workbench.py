#!/usr/bin/env python3
"""Validate the clean-room Biomed Workbench development or release surface."""

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.catalog import all_capabilities, capability_to_dict, resolve_entrypoint  # noqa: E402
from biomed_workbench.services.credentials import ALLOWED_CREDENTIALS  # noqa: E402

CATALOG_FIELDS = {"id", "workflow", "kind", "title", "description", "entrypoint", "input_schema", "requirements", "access", "mutability"}
SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_-]{20,}"), re.compile(r"sk-[A-Za-z0-9_-]{32,}"), re.compile(r"gh[opsu]_[A-Za-z0-9]{30,}"),
]
LOCAL_PATH_PATTERNS = ("/Users/" + "kangjunyan", "/private/" + "var/folders/")
LEGACY_PATHS = ("scripts", "tools/adapters", "references/source_manifest.json", "references/source_file_audit.json")


def publishable_files():
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, check=True, capture_output=True)
    for relative in result.stdout.decode().split("\0"):
        if relative and (ROOT / relative).is_file():
            yield ROOT / relative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true", help="Enforce removal of all migration-only legacy surfaces")
    args = parser.parse_args()
    errors = []
    plugin_path = ROOT / ".codex-plugin" / "plugin.json"
    marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"
    if not plugin_path.is_file():
        errors.append("missing plugin manifest")
        plugin = {}
    else:
        plugin = json.loads(plugin_path.read_text())
        if plugin.get("name") != "biomed-workbench" or plugin.get("skills") != "./skills/" or plugin.get("license") != "Apache-2.0":
            errors.append("plugin manifest identity, skill path, or license is invalid")
    if not marketplace_path.is_file():
        errors.append("missing marketplace manifest")
    else:
        marketplace = json.loads(marketplace_path.read_text())
        plugins = marketplace.get("plugins", [])
        if len(plugins) != 1 or plugins[0].get("name") != "biomed-workbench" or plugins[0].get("source") != {"source": "local", "path": "."}:
            errors.append("marketplace must expose only the repository-root biomed-workbench plugin")
    skill_files = sorted((ROOT / "skills").glob("*/SKILL.md"))
    if [path.relative_to(ROOT).as_posix() for path in skill_files] != ["skills/biomed-workbench/SKILL.md"]:
        errors.append("exactly one user-facing skill is required")

    catalog_path = ROOT / "tools" / "catalog.json"
    catalog = json.loads(catalog_path.read_text()) if catalog_path.is_file() else {}
    capabilities = all_capabilities()
    expected_rows = [capability_to_dict(item) for item in capabilities]
    if catalog.get("entry_count") != len(capabilities) or catalog.get("entries") != expected_rows:
        errors.append("generated catalog does not exactly match the registry")
    if plugin.get("version") != catalog.get("version"):
        errors.append("plugin and catalog versions differ")
    for capability in capabilities:
        if set(capability_to_dict(capability)) != CATALOG_FIELDS:
            errors.append(f"capability {capability.id} has an invalid operational field set")
        try:
            resolve_entrypoint(capability)
        except Exception:
            errors.append(f"capability entrypoint does not resolve: {capability.id}")

    tracked = list(publishable_files())
    for path in tracked:
        text = path.read_text(errors="ignore")
        relative = path.relative_to(ROOT).as_posix()
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            errors.append(f"credential-like value found in {relative}")
        if any(pattern in text for pattern in LOCAL_PATH_PATTERNS):
            errors.append(f"machine-local path found in {relative}")

    operational_roots = [ROOT / "biomed_workbench", ROOT / "tools", ROOT / "skills"]
    credential_names = set()
    for root in operational_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and ".source-audit" not in path.parts:
                text = path.read_text(errors="ignore")
                credential_names.update(re.findall(r"\b[A-Z][A-Z0-9_]*(?:API_KEY|AUTH_TOKEN)\b", text))
    undeclared = sorted(credential_names - set(ALLOWED_CREDENTIALS))
    if undeclared:
        errors.append(f"undeclared operational credentials: {undeclared}")

    syntax_errors = []
    for root in (ROOT / "biomed_workbench", ROOT / "tools"):
        for path in root.rglob("*.py"):
            try:
                ast.parse(path.read_text(errors="ignore"), filename=str(path))
            except SyntaxError as exc:
                syntax_errors.append(f"{path.relative_to(ROOT)}:{exc.lineno}")
    if syntax_errors:
        errors.append(f"Python syntax errors: {syntax_errors[:10]}")

    if args.release:
        remaining = [path for path in LEGACY_PATHS if (ROOT / path).exists()]
        if remaining:
            errors.append(f"legacy migration surfaces remain: {remaining}")
        forbidden_fields = {"source", "source_path", "run_policy", "adapter"}
        if any(forbidden_fields & set(row) for row in catalog.get("entries", [])):
            errors.append("release catalog contains bridge fields")

    if errors:
        for error in dict.fromkeys(errors):
            print(f"FAIL: {error}")
        return 1
    print(f"OK: biomed-workbench {'release' if args.release else 'development'} validation passed")
    print(f"capabilities={len(capabilities)}")
    print("credentials=" + ",".join(sorted(ALLOWED_CREDENTIALS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
