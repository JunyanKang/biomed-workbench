#!/usr/bin/env python3
"""Verify Codex ownership and isolate optional interoperability adapters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILTIN_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"
CODEX_FILES = (
    ".codex-plugin/plugin.json",
    ".agents/plugins/marketplace.json",
    "skills/biomed-workbench/SKILL.md",
)
OPTIONAL_ADAPTER_FILES = (
    "requirements-mcp.txt",
    "tools/mcp_server.py",
    "docs/agent-integration.md",
    "docs/agent-integration.zh-CN.md",
)
FORBIDDEN_ADAPTER_REFERENCES = (
    "tools/mcp_server.py",
    "requirements-mcp.txt",
    "agent-integration.md",
    "agent-integration.zh-CN.md",
)


def _scientific_reverse_dependencies() -> list[dict[str, object]]:
    violations = []
    for path in sorted(BUILTIN_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".py", ".R", ".md", ".txt", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in FORBIDDEN_ADAPTER_REFERENCES:
            if token in text:
                violations.append({"module_file": path.relative_to(ROOT).as_posix(), "adapter_reference": token})
    return violations


def build() -> dict[str, object]:
    missing_codex = [relative for relative in CODEX_FILES if not (ROOT / relative).is_file()]
    missing_optional = [relative for relative in OPTIONAL_ADAPTER_FILES if not (ROOT / relative).is_file()]
    mcp_source = (ROOT / "tools" / "mcp_server.py").read_text(encoding="utf-8") if not missing_optional else ""
    read_only_gate = (
        'capability.mutability != "read_only"' in mcp_source
        and "run_read_only_biomedical_capability" in mcp_source
    )
    shared_core_imports = all(
        token in mcp_source
        for token in (
            "from biomed_workbench.catalog import all_capabilities, resolve",
            "from biomed_workbench.router import route",
            "from biomed_workbench.runner import run",
        )
    )
    english = (ROOT / "docs" / "agent-integration.md").read_text(encoding="utf-8") if not missing_optional else ""
    chinese = (ROOT / "docs" / "agent-integration.zh-CN.md").read_text(encoding="utf-8") if not missing_optional else ""
    documentation_markers = {
        "english": {
            "reference_host": "primary reference host",
            "not_exclusive": "does not make the scientific registry exclusive to Codex",
            "not_equivalent_certification": "entry compatibility rather than end-to-end certification",
            "codex_native_boundary": "`access: codex_native`",
        },
        "chinese": {
            "reference_host": "首要参考宿主",
            "not_exclusive": "并不表示科学注册表只能由 Codex 使用",
            "not_equivalent_certification": "入口兼容，而非全流程认证",
            "codex_native_boundary": "`access: codex_native`",
        },
    }
    documented = {"english": english, "chinese": chinese}
    missing_documentation_markers = {
        language: [marker_id for marker_id, marker in markers.items() if marker not in documented[language]]
        for language, markers in documentation_markers.items()
    }
    codex_first_documented = not any(missing_documentation_markers.values())
    reverse_dependencies = _scientific_reverse_dependencies()
    passed = not missing_codex and not missing_optional and read_only_gate and shared_core_imports and codex_first_documented and not reverse_dependencies
    return {
        "schema_version": 1,
        "passed": passed,
        "product_identity": "codex-first-scientific-plugin",
        "codex_native_files": list(CODEX_FILES),
        "optional_adapter_files": list(OPTIONAL_ADAPTER_FILES),
        "codex_native_files_complete": not missing_codex,
        "optional_adapter_files_complete": not missing_optional,
        "mcp_read_only_gate_present": read_only_gate,
        "mcp_reuses_primary_registry_router_runner": shared_core_imports,
        "codex_first_boundary_documented": codex_first_documented,
        "missing_documentation_markers": missing_documentation_markers,
        "scientific_module_reverse_dependencies": reverse_dependencies,
        "missing_codex_files": missing_codex,
        "missing_optional_adapter_files": missing_optional,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
