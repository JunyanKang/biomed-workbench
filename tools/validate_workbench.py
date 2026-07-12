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
from biomed_workbench.modules.index import BUILTIN_ROOT, MODULE_INDEX, build_index  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry, ModuleRegistryError  # noqa: E402
from biomed_workbench.orchestration.graph import build_capability_graph  # noqa: E402
from biomed_workbench.services.credentials import ALLOWED_CREDENTIALS  # noqa: E402
from biomed_workbench.version import VERSION  # noqa: E402
from tools.validate_module import validate_module  # noqa: E402

CATALOG_FIELDS = {"id", "workflow", "kind", "title", "description", "entrypoint", "input_schema", "requirements", "access", "mutability"}
SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_-]{20,}"), re.compile(r"sk-[A-Za-z0-9_-]{32,}"), re.compile(r"gh[opsu]_[A-Za-z0-9]{30,}"),
]
LOCAL_PATH_PATTERNS = ("/Users/" + "kangjunyan", "/private/" + "var/folders/")
LEGACY_PATHS = (
    "scripts",
    "tools/adapters",
    "tools/add_capability.py",
    "biomed_workbench/capability_specs",
    "references/source_manifest.json",
    "references/source_file_audit.json",
)
FORBIDDEN_INFRASTRUCTURE_MARKERS = ("runtime", "container", "slurm", "gpu", "local-model")


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
        interface = plugin.get("interface", {})
        if set(interface.get("capabilities", ())) != {"Interactive", "Read"}:
            errors.append("plugin interface capabilities must use Codex capability conventions")
        prompts = interface.get("defaultPrompt", ())
        if not isinstance(prompts, list) or len(prompts) > 3 or any(not isinstance(prompt, str) or len(prompt) > 128 for prompt in prompts):
            errors.append("plugin default prompts exceed Codex interface limits")
        for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
            if not str(interface.get(field, "")).startswith("https://"):
                errors.append(f"plugin interface {field} must be an https URL")
    if not marketplace_path.is_file():
        errors.append("missing marketplace manifest")
    else:
        marketplace = json.loads(marketplace_path.read_text())
        plugins = marketplace.get("plugins", [])
        if (
            marketplace.get("name") != "biomed-workbench"
            or marketplace.get("interface", {}).get("displayName") != "Biomed Workbench"
            or len(plugins) != 1
            or plugins[0].get("name") != "biomed-workbench"
            or plugins[0].get("source") != {"source": "local", "path": "."}
            or plugins[0].get("category") != plugin.get("interface", {}).get("category")
            or plugins[0].get("policy") != {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}
        ):
            errors.append("marketplace must expose only the repository-root biomed-workbench plugin")
    skill_files = sorted((ROOT / "skills").glob("*/SKILL.md"))
    if [path.relative_to(ROOT).as_posix() for path in skill_files] != ["skills/biomed-workbench/SKILL.md"]:
        errors.append("exactly one user-facing skill is required")
    agent_metadata = ROOT / "skills" / "biomed-workbench" / "agents" / "openai.yaml"
    if not agent_metadata.is_file() or "$biomed-workbench" not in agent_metadata.read_text(errors="ignore"):
        errors.append("skill must include Codex UI metadata with a default invocation prompt")
    for policy_file in (ROOT / "PRIVACY.md", ROOT / "TERMS.md"):
        if not policy_file.is_file():
            errors.append(f"missing public policy document: {policy_file.name}")

    catalog_path = ROOT / "tools" / "catalog.json"
    catalog = json.loads(catalog_path.read_text()) if catalog_path.is_file() else {}
    capabilities = all_capabilities()
    expected_rows = [capability_to_dict(item) for item in capabilities]
    if catalog.get("entry_count") != len(capabilities) or catalog.get("entries") != expected_rows:
        errors.append("generated catalog does not exactly match the registry")
    if plugin.get("version") != catalog.get("version") or plugin.get("version") != VERSION:
        errors.append("plugin, package, and catalog versions differ")
    for capability in capabilities:
        if set(capability_to_dict(capability)) != CATALOG_FIELDS:
            errors.append(f"capability {capability.id} has an invalid operational field set")
        try:
            resolve_entrypoint(capability)
        except Exception:
            errors.append(f"capability entrypoint does not resolve: {capability.id}")
        operational_identity = f"{capability.id} {capability.workflow} {capability.entrypoint}".lower()
        if any(marker in operational_identity for marker in FORBIDDEN_INFRASTRUCTURE_MARKERS):
            errors.append(f"capability claims excluded infrastructure ownership: {capability.id}")

    registry = None
    try:
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
    except ModuleRegistryError as exc:
        errors.append(f"module registry discovery failed: {exc}")
    if registry is not None:
        modules = registry.all()
        if len(modules) != 48:
            errors.append(f"built-in module count must be 48, found {len(modules)}")
        if len(modules) != len(capabilities) or {item.id for item in modules} != {item.id for item in capabilities}:
            errors.append("module registry and compatibility capability projection differ")
        try:
            checked_index = json.loads(MODULE_INDEX.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("checked module index is missing or invalid")
        else:
            if checked_index != build_index(registry):
                errors.append("checked module index differs from discovered module manifests")
        for manifest_path in sorted(BUILTIN_ROOT.glob("*/module.json")):
            report = validate_module(manifest_path.parent, require_tests=False)
            if not report["valid"]:
                errors.append(f"module package validation failed for {report['module_id']}: {'; '.join(report['errors'])}")
            if not (
                report["entrypoint_resolved"]
                and report["compatibility_rows"] >= 1
                and report["tool_evidence_complete"]
                and report["dependency_evidence_complete"]
                and report["format_evidence_complete"]
            ):
                errors.append(f"module scientific compatibility evidence is incomplete: {report['module_id']}")
        research_report_path = ROOT / "reports" / "research-engine-verification.json"
        fixture_root = ROOT / "tests" / "fixtures" / "research-cycles"
        try:
            research_report = json.loads(research_report_path.read_text(encoding="utf-8"))
            scenario_fixtures = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(fixture_root.glob("*.json"))]
        except (OSError, json.JSONDecodeError):
            errors.append("research engine verification report or fixtures are missing or invalid")
        else:
            graph = build_capability_graph(registry)
            graph_report = research_report.get("capability_graph", {})
            if (
                research_report.get("passed") is not True
                or research_report.get("module_count") != len(modules)
                or research_report.get("test_count", 0) < 303
                or research_report.get("registry_digest") != registry.digest
                or set(research_report.get("execution_contracts", ()))
                != {"scientific_command", "command_input_binding", "command_output_binding", "bounded_process_result"}
                or graph_report != {"node_count": len(graph.nodes), "edge_count": len(graph.edges), "digest": graph.digest}
            ):
                errors.append("research engine report differs from the discovered registry or capability graph")
            scenarios = research_report.get("scenarios", [])
            if (
                len(scenarios) != 4
                or len(scenario_fixtures) != 4
                or {item.get("plan_type") for item in scenarios} != {"single", "serial", "parallel", "mixed"}
                or {item.get("id"): item.get("final_state_digest") for item in scenarios}
                != {item.get("id"): item.get("expected_replay_digest") for item in scenario_fixtures}
                or any(
                    not item.get("failed_gate_code")
                    or item.get("revision_count", 0) < 1
                    or item.get("alternative_substitution_count", 0) < 1
                    or item.get("evidence_count", 0) < 1
                    or len(item.get("hypothesis_transition", ())) != 2
                    or item["hypothesis_transition"][0] == item["hypothesis_transition"][1]
                    or item.get("replay_passed") is not True
                    for item in scenarios
                )
            ):
                errors.append("research cycle scenarios lack gate, evidence, plan-type, revision, or replay coverage")
        orchestration_source = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "biomed_workbench" / "orchestration").glob("*.py")))
        leaked_ids = [module.id for module in modules if f'"{module.id}"' in orchestration_source or f"'{module.id}'" in orchestration_source]
        if leaked_ids:
            errors.append(f"orchestration source contains central built-in module IDs: {leaked_ids[:5]}")
        command_source = (ROOT / "biomed_workbench" / "modules" / "scientific_command.py").read_text(encoding="utf-8")
        if "shell=True" in command_source or "os.system(" in command_source:
            errors.append("scientific command execution contains a shell invocation surface")

    router_source = (ROOT / "biomed_workbench" / "router.py").read_text(encoding="utf-8")
    for forbidden_table in ("INTENT_BOOSTS", "WORKFLOW_KEYWORDS"):
        if forbidden_table in router_source:
            errors.append(f"central routing table is forbidden: {forbidden_table}")

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
    if registry is not None:
        print(f"modules={len(registry.all())}")
        print(f"registry_digest={registry.digest}")
    print("credentials=" + ",".join(sorted(ALLOWED_CREDENTIALS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
