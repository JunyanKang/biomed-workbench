#!/usr/bin/env python3
"""Validate the Biomed Workbench product release surface."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from packaging.version import InvalidVersion
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.catalog import all_capabilities, capability_to_dict, resolve_entrypoint  # noqa: E402
from biomed_workbench.formats import FormatRegistry  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT, MODULE_INDEX, build_index  # noqa: E402
from biomed_workbench.modules.evidence_scope import evidence_scope_is_current, report_module_ids  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry, ModuleRegistryError  # noqa: E402
from biomed_workbench.orchestration.graph import build_capability_graph  # noqa: E402
from biomed_workbench.services.public_databases import (  # noqa: E402
    ALPHAFOLD_CONTRACT_VERSION,
    BIORXIV_CONTRACT_VERSION,
    CLINICAL_TRIALS_CONTRACT_VERSION,
    CROSSREF_CONTRACT_VERSION,
    EUROPE_PMC_CONTRACT_VERSION,
    PUBCHEM_CONTRACT_VERSION,
    RCSB_CONTRACT_VERSION,
    RCSB_SEARCH_CONTRACT_VERSION,
    STRING_CONTRACT_VERSION,
)
from biomed_workbench.services.credentials import ALLOWED_CREDENTIALS  # noqa: E402
from biomed_workbench.release_validation import validate_source_hygiene  # noqa: E402
from biomed_workbench.version import VERSION  # noqa: E402
from tools.validate_module import validate_module  # noqa: E402
from tools.build_format_contract_report import build as build_format_contract_report  # noqa: E402
from tools.build_tool_compatibility_matrix import build_compatibility_report  # noqa: E402
from tools.audit_bioinformatics_templates import build as build_bioinformatics_template_report  # noqa: E402
from tools.audit_execution_readiness import build as build_execution_readiness_report  # noqa: E402
from tools.build_research_engine_report import EXECUTION_CONTRACTS, KERNEL_CONTRACTS  # noqa: E402
from tools.build_experimental_maturity_report import build as build_experimental_maturity_report  # noqa: E402
from tools.audit_adapter_boundaries import build as build_adapter_boundary_report  # noqa: E402
from tools.verify_mcp_adapter import validate_report as validate_mcp_adapter_report  # noqa: E402

CATALOG_FIELDS = {"id", "workflow", "kind", "title", "description", "entrypoint", "input_schema", "requirements", "access", "mutability"}
def _scanpy_specs(row) -> list[str]:
    specs: list[str] = []
    for spec in getattr(row, "tool_versions", {}).get("scanpy", ()):
        specs.append(str(spec))
    for spec in getattr(row, "dependency_versions", {}).get("scanpy", ()):
        specs.append(str(spec))
    return specs


def _scanpy_is_compatible(version: str, row) -> bool:
    try:
        parsed = Version(version)
    except InvalidVersion:
        return False
    specs = _scanpy_specs(row)
    if not specs:
        return True
    for spec in specs:
        ok = True
        for clause in str(spec).split(","):
            token = clause.strip()
            if not token:
                continue
            if token.startswith(">="):
                if parsed < Version(token[2:]):
                    ok = False
                    break
            elif token.startswith(">"):
                if parsed <= Version(token[1:]):
                    ok = False
                    break
            elif token.startswith("<="):
                if parsed > Version(token[2:]):
                    ok = False
                    break
            elif token.startswith("<"):
                if parsed >= Version(token[1:]):
                    ok = False
                    break
            elif token.startswith("=="):
                if parsed != Version(token[2:]):
                    ok = False
                    break
            else:
                ok = False
                break
        if ok:
            return True
    return False

LEGACY_PATHS = (
    "scripts",
    "tools/adapters",
    "tools/add_capability.py",
    "biomed_workbench/capability_specs",
    "references/source_manifest.json",
    "references/source_file_audit.json",
)
FORBIDDEN_INFRASTRUCTURE_MARKERS = (
    "runtime",
    "container",
    "sl" + "urm",
    "g" + "pu",
    "local-" + "model",
)


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
    interoperability_path = ROOT / "reports" / "adapter-boundary-audit.json"
    try:
        interoperability_report = json.loads(interoperability_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append("agent interoperability audit is missing or invalid")
    else:
        if interoperability_report != build_adapter_boundary_report() or interoperability_report.get("passed") is not True:
            errors.append("Codex and optional-adapter boundary audit differs from the current source")
    mcp_report_path = ROOT / "reports" / "mcp-adapter-live-verification.json"
    try:
        mcp_report = json.loads(mcp_report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append("optional MCP adapter execution report is missing or invalid")
    else:
        if not validate_mcp_adapter_report(mcp_report):
            errors.append("optional MCP adapter execution report differs from the current adapter or registry")

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

    format_registry = None
    format_report_path = ROOT / "reports" / "format-contract-registry.json"
    try:
        format_registry = FormatRegistry.builtin()
        format_report = json.loads(format_report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"format contract registry or report is missing or invalid: {exc}")
    else:
        if format_report != build_format_contract_report():
            errors.append("format contract report differs from the built-in format registry")
        required_formats = {"fastq", "fasta", "sam", "bam", "cram", "vcf", "bcf", "bed", "gtf", "gff3", "h5ad", "loom", "matrix-market", "fragments", "bigwig", "count-matrix", "tabular", "png", "jpeg", "webp"}
        if not required_formats <= {profile.name for profile in format_registry.all()} or format_report.get("registry_digest") != format_registry.digest:
            errors.append("foundational format profiles or digest are invalid")

    registry = None
    try:
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
    except ModuleRegistryError as exc:
        errors.append(f"module registry discovery failed: {exc}")
    if registry is not None:
        modules = registry.all()
        if len(modules) < 48:
            errors.append(f"built-in modules no longer cover the 48-capability migration baseline: found {len(modules)}")
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
                and report["compatibility_evidence_complete"]
            ):
                errors.append(f"module scientific compatibility evidence is incomplete: {report['module_id']}")
        for report_path in sorted((ROOT / "reports").glob("*.json")):
            try:
                scoped_report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(scoped_report, dict)
                and report_module_ids(scoped_report)
                and not evidence_scope_is_current(scoped_report, registry)
            ):
                errors.append(f"module-specific report has a missing or stale evidence scope: {report_path.name}")
        compatibility_matrix_path = ROOT / "reports" / "tool-compatibility-matrix.json"
        try:
            compatibility_matrix = json.loads(compatibility_matrix_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("tool compatibility matrix is missing or invalid")
        else:
            if compatibility_matrix != build_compatibility_report(registry):
                errors.append("tool compatibility matrix differs from the discovered registry")
        research_report_path = ROOT / "reports" / "research-engine-verification.json"
        compatibility_evidence_path = ROOT / "reports" / "compatibility-execution-evidence.json"
        fixture_root = ROOT / "tests" / "fixtures" / "research-cycles"
        research_report = {}
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
                or research_report.get("test_count", 0) < 383
                or research_report.get("registry_digest") != registry.digest
                or research_report.get("kernel_contracts") != KERNEL_CONTRACTS
                or research_report.get("execution_contracts") != EXECUTION_CONTRACTS
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
        try:
            compatibility_evidence = json.loads(compatibility_evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("compatibility execution evidence is missing or invalid")
        else:
            expected_evidence = {
                (module.id, row.id, row.regression_evidence_ids[0], row.end_to_end_evidence_ids[0])
                for module in modules
                for row in module.compatibility_matrix
            }
            observed_evidence = {
                (item.get("module_id"), item.get("row_id"), item.get("regression", {}).get("id"), item.get("end_to_end", {}).get("id"))
                for item in compatibility_evidence.get("records", ())
            }
            if (
                compatibility_evidence.get("passed") is not True
                or compatibility_evidence.get("registry_digest") != registry.digest
                or compatibility_evidence.get("regression_passed") != len(expected_evidence)
                or compatibility_evidence.get("end_to_end_passed") != len(expected_evidence)
                or observed_evidence != expected_evidence
            ):
                errors.append("compatibility rows are not bound to current passing regression and end-to-end evidence")
        template_report_path = ROOT / "reports" / "bioinformatics-template-coverage.json"
        try:
            template_report = json.loads(template_report_path.read_text(encoding="utf-8"))
            expected_template_report = build_bioinformatics_template_report()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"bioinformatics template coverage report is missing or invalid: {exc}")
        else:
            if template_report != expected_template_report or template_report.get("passed") is not True:
                errors.append("bioinformatics template coverage differs from the registry or contains a failing template")
            if (
                template_report.get("bioinformatics_module_count") != template_report.get("covered_module_count")
                or template_report.get("covered_module_count") != template_report.get("passing_module_count")
                or any(item.get("template_count", 0) < 1 for item in template_report.get("records", ()))
            ):
                errors.append("every bioinformatics module must retain at least one passing code template")
        execution_readiness_path = ROOT / "reports" / "execution-readiness.json"
        try:
            execution_readiness = json.loads(execution_readiness_path.read_text(encoding="utf-8"))
            expected_execution_readiness = build_execution_readiness_report()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"execution readiness report is missing or invalid: {exc}")
        else:
            if (
                execution_readiness != expected_execution_readiness
                or execution_readiness.get("passed") is not True
                or execution_readiness.get("registry_digest") != registry.digest
                or execution_readiness.get("module_count") != len(modules)
                or execution_readiness.get("blocked_module_ids")
                or execution_readiness.get("counts", {}).get("manual-adaptation", 0) != 0
            ):
                errors.append(
                    "execution readiness differs from the registry or still contains a manual-adaptation module"
                )
        experimental_maturity_path = ROOT / "reports" / "experimental-module-maturity.json"
        try:
            experimental_maturity = json.loads(experimental_maturity_path.read_text(encoding="utf-8"))
            expected_experimental_maturity = build_experimental_maturity_report()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"experimental module maturity report is missing or invalid: {exc}")
        else:
            if (
                experimental_maturity != expected_experimental_maturity
                or experimental_maturity.get("passed") is not True
            ):
                errors.append("experimental module maturity evidence differs from current checked reports")
        communication_report_path = ROOT / "reports" / "single-cell-communication-live-verification.json"
        try:
            communication_report = json.loads(communication_report_path.read_text(encoding="utf-8"))
            communication_manifest = registry.get("single-cell-communication")
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("single-cell communication live verification is missing or invalid")
        else:
            expected_rows = [
                {
                    "id": row.id,
                    "regression_evidence_ids": list(row.regression_evidence_ids),
                    "end_to_end_evidence_ids": list(row.end_to_end_evidence_ids),
                }
                for row in communication_manifest.compatibility_matrix
            ]
            versions = communication_report.get("versions", {})
            if (
                communication_report.get("passed") is not True
                or communication_report.get("module_id") != communication_manifest.id
                or communication_report.get("module_version") != communication_manifest.version
                or not evidence_scope_is_current(communication_report, registry)
                or communication_report.get("compatibility_rows") != expected_rows
                or communication_report.get("fixture", {}).get("cells") != 160
                or communication_report.get("fixture", {}).get("biological_samples") != 4
                or communication_report.get("fixture", {}).get("conditions") != 2
                or set(communication_report.get("python_backends", {}).get("methods", ()))
                != {"liana-cellphonedb", "cellphonedb-statistical"}
                or set(communication_report.get("r_backends", {}).get("methods", ())) != {"cellchat", "nichenet"}
                or communication_report.get("python_backends", {}).get("sample_interaction_rows", 0) < 1
                or communication_report.get("r_backends", {}).get("cellchat_interaction_rows", 0) < 1
                or communication_report.get("r_backends", {}).get("nichenet_ligand_rows", 0) < 1
                or versions.get("liana") != "1.7.3"
                or versions.get("cellphonedb") != "5.0.1"
                or versions.get("CellChat") != "2.2.0"
                or versions.get("nichenetr") != "2.2.1.1"
                or not re.fullmatch(r"[0-9a-f]{64}", communication_report.get("cellphonedb_database", {}).get("sha256", ""))
            ):
                errors.append("single-cell communication verification differs from its module, fixture, or four validated backends")
        pbmc3k_report_path = ROOT / "reports" / "public-case-pbmc3k-foundation.json"
        pbmc3k_template_path = (
            BUILTIN_ROOT
            / "single-cell-foundation-workflow"
            / "templates"
            / "scanpy_foundation.py"
        )
        pbmc3k_manifest_path = BUILTIN_ROOT / "single-cell-foundation-workflow" / "module.json"
        try:
            pbmc3k_report = json.loads(pbmc3k_report_path.read_text(encoding="utf-8"))
            pbmc3k_manifest = registry.get("single-cell-foundation-workflow")
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("PBMC3k public-data acceptance case is missing or invalid")
        else:
            execution = pbmc3k_report.get("execution", {})
            reload_validation = execution.get("reload_validation", {})
            if (
                pbmc3k_report.get("passed") is not True
                or pbmc3k_report.get("case_type") != "public-data-end-to-end"
                or pbmc3k_report.get("module", {}).get("id") != pbmc3k_manifest.id
                or pbmc3k_report.get("module", {}).get("version") != pbmc3k_manifest.version
                or pbmc3k_report.get("module", {}).get("compatibility_row_id")
                != pbmc3k_manifest.compatibility_matrix[0].id
                or not evidence_scope_is_current(pbmc3k_report, registry)
                or pbmc3k_report.get("module", {}).get("template_sha256")
                != hashlib.sha256(pbmc3k_template_path.read_bytes()).hexdigest()
                or pbmc3k_report.get("source", {}).get("sha256")
                != "847d6ebd9a1ec9a768f2be7e40ca42cbfe75ebeb6d76a4c24167041699dc28b5"
                or pbmc3k_report.get("source", {}).get("documented_shape") != [2700, 32738]
                or not _scanpy_is_compatible(
                    pbmc3k_report.get("runtime", {}).get("scanpy", ""),
                    pbmc3k_manifest.compatibility_matrix[0],
                )
                or execution.get("input_cells") != 2700
                or execution.get("retained_cells", 0) + execution.get("excluded_cells", 0)
                != execution.get("input_cells")
                or execution.get("retained_features", 0) < 10000
                or any(value is not True for key, value in reload_validation.items() if key != "ephemeral_output_sha256")
                or set(pbmc3k_report.get("quality_gates", {}).values()) != {"pass"}
                or set(pbmc3k_report.get("methods_not_run", {}).values()) != {"not-run"}
            ):
                errors.append(
                    "PBMC3k public-data case differs from its source, module, template, runtime, execution, or scientific gates"
                )
        pbmc3k_atlas_report_path = ROOT / "reports" / "public-case-pbmc3k-atlas-annotation.json"
        pbmc3k_atlas_root = BUILTIN_ROOT / "single-cell-atlas-annotation"
        try:
            pbmc3k_atlas_report = json.loads(
                pbmc3k_atlas_report_path.read_text(encoding="utf-8")
            )
            pbmc3k_atlas_manifest = registry.get("single-cell-atlas-annotation")
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("PBMC3k atlas-annotation public-data acceptance case is missing or invalid")
        else:
            execution = pbmc3k_atlas_report.get("execution", {})
            output_validation = execution.get("output_validation", {})
            marker_review = execution.get("posthoc_marker_review", {})
            if (
                pbmc3k_atlas_report.get("passed") is not True
                or pbmc3k_atlas_report.get("case_type") != "public-data-end-to-end"
                or pbmc3k_atlas_report.get("module", {}).get("id")
                != pbmc3k_atlas_manifest.id
                or pbmc3k_atlas_report.get("module", {}).get("version")
                != pbmc3k_atlas_manifest.version
                or pbmc3k_atlas_report.get("module", {}).get("compatibility_row_id")
                != pbmc3k_atlas_manifest.compatibility_matrix[0].id
                or not evidence_scope_is_current(pbmc3k_atlas_report, registry)
                or pbmc3k_atlas_report.get("module", {}).get("template_sha256")
                != hashlib.sha256(
                    (pbmc3k_atlas_root / "templates" / "annotate_celltypist.py").read_bytes()
                ).hexdigest()
                or pbmc3k_atlas_report.get("source", {}).get("sha256")
                != "847d6ebd9a1ec9a768f2be7e40ca42cbfe75ebeb6d76a4c24167041699dc28b5"
                or pbmc3k_atlas_report.get("source", {}).get("documented_shape")
                != [2700, 32738]
                or pbmc3k_atlas_report.get("reference", {}).get("model")
                != "Immune_All_Low.pkl"
                or pbmc3k_atlas_report.get("reference", {}).get("version") != "v2"
                or pbmc3k_atlas_report.get("reference", {}).get("sha256")
                != "290874d35dac039d4c9218c343fde4aac1077709b72a331ce7266f6828c36502"
                or pbmc3k_atlas_report.get("reference", {}).get("classes") != 98
                or pbmc3k_atlas_report.get("runtime", {}).get("celltypist") != "1.7.1"
                or not _scanpy_is_compatible(
                    pbmc3k_atlas_report.get("runtime", {}).get("scanpy", ""),
                    pbmc3k_atlas_manifest.compatibility_matrix[0],
                )
                or execution.get("cells") != 2700
                or execution.get("features") != 32738
                or execution.get("model_feature_overlap", 0) < 1000
                or execution.get("prediction_label_count") != 98
                or execution.get("unknown_cells", 0) < 1
                or output_validation.get("probability_matrix_shape") != [2700, 98]
                or output_validation.get("raw_counts_preserved") is not True
                or output_validation.get("complete_probability_matrix") is not True
                or output_validation.get("unknown_policy_exact") is not True
                or output_validation.get("all_cells_accounted") is not True
                or marker_review.get("all_evaluable_families_enriched") is not True
                or len(marker_review.get("families", {})) < 3
                or "T" not in marker_review.get("not_evaluable_families", {})
                or set(pbmc3k_atlas_report.get("quality_gates", {}).values()) != {"pass"}
            ):
                errors.append(
                    "PBMC3k atlas-annotation public-data case differs from its query, model, module, template, uncertainty policy, marker review, or scientific gates"
                )
        zebrafish_regvelo_report_path = ROOT / "reports" / "public-case-zebrafish-regvelo.json"
        zebrafish_regvelo_root = BUILTIN_ROOT / "single-cell-regulatory-velocity"
        try:
            zebrafish_regvelo_report = json.loads(
                zebrafish_regvelo_report_path.read_text(encoding="utf-8")
            )
            zebrafish_regvelo_manifest = registry.get("single-cell-regulatory-velocity")
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("zebrafish RegVelo public-data acceptance case is missing or invalid")
        else:
            derivation = zebrafish_regvelo_report.get("derivation", {})
            execution = zebrafish_regvelo_report.get("execution", {})
            direction = execution.get("withheld_stage_direction", {})
            repeat_execution = execution.get("deterministic_repeat_execution", {})
            comparisons = execution.get("mode_comparisons", [])
            comparison = comparisons[0] if len(comparisons) == 1 else {}
            gates = zebrafish_regvelo_report.get("quality_gates", {})
            if (
                zebrafish_regvelo_report.get("passed") is not True
                or zebrafish_regvelo_report.get("case_type") != "public-data-end-to-end"
                or zebrafish_regvelo_report.get("module", {}).get("id")
                != zebrafish_regvelo_manifest.id
                or zebrafish_regvelo_report.get("module", {}).get("version")
                != zebrafish_regvelo_manifest.version
                or zebrafish_regvelo_report.get("module", {}).get("compatibility_row_id")
                != zebrafish_regvelo_manifest.compatibility_matrix[0].id
                or not evidence_scope_is_current(zebrafish_regvelo_report, registry)
                or zebrafish_regvelo_report.get("module", {}).get("template_sha256")
                != hashlib.sha256(
                    (zebrafish_regvelo_root / "templates" / "run_regvelo.py").read_bytes()
                ).hexdigest()
                or zebrafish_regvelo_report.get("source", {}).get("sha256")
                != "eccab081c44cfe335b726aec8172bbcda072241b4f006f6420bb5d46d39611cb"
                or zebrafish_regvelo_report.get("source", {}).get("documented_shape")
                != [697, 8012]
                or zebrafish_regvelo_report.get("prior_grn", {}).get("sha256")
                != "356bfde785af53e36f9334c4f5032c06f111d67d30b881b41e24a8ebde7a536a"
                or zebrafish_regvelo_report.get("prior_grn", {}).get("documented_shape")
                != [4508, 4508]
                or derivation.get("cells") != 697
                or derivation.get("features") != 1008
                or derivation.get("regulators") != 81
                or derivation.get("edges") != 4309
                or derivation.get("labels_used_for_preprocessing") is not False
                or derivation.get(
                    "labels_removed_before_preprocessing_and_restored_after"
                )
                is not True
                or derivation.get("splicing_layers", {}).get("Ms", {}).get("integer_like")
                is not False
                or derivation.get("splicing_layers", {}).get("Mu", {}).get("integer_like")
                is not False
                or zebrafish_regvelo_report.get("runtime", {}).get("regvelo") != "0.4.2"
                or zebrafish_regvelo_report.get("runtime", {}).get("scvelo") != "0.3.4"
                or zebrafish_regvelo_report.get("parameters", {}).get("model_modes")
                != ["hard", "soft"]
                or zebrafish_regvelo_report.get("parameters", {}).get("max_epochs") != 20
                or len(execution.get("runs", [])) != 2
                or execution.get("all_outputs_finite") is not True
                or execution.get("models_saved_and_reloaded") is not True
                or execution.get("source_layers_preserved") is not True
                or execution.get("output_reloaded") is not True
                or repeat_execution.get("independent_template_runs") != 2
                or repeat_execution.get("same_parameters_histories_and_mode_comparison")
                is not True
                or set(repeat_execution.get("outputs", {}))
                != {"velocity", "latent_time", "latent_state"}
                or any(
                    item.get("exactly_equal") is not True
                    or item.get("maximum_absolute_difference") != 0
                    for item in repeat_execution.get("outputs", {}).values()
                )
                or direction.get("used_for_fitting_or_preprocessing") is not False
                or direction.get("included_cells") != 695
                or direction.get("spearman_rho", 0) <= 0.7
                or direction.get("spearman_pvalue", 1) >= 1e-100
                or direction.get("excluded_stages")
                != [{"cells": 2, "reason": "fewer-than-20-cells", "stage": "3ss"}]
                or not isinstance(comparison.get("velocity_pearson"), (int, float))
                or not -1 <= comparison.get("velocity_pearson", 2) <= 1
                or execution.get("mode_sensitivity_status")
                != "warning-no-robustness-claim"
                or gates.get("mode_sensitivity_retained") != "pass-with-warning"
                or set(gates.values()) != {"pass", "pass-with-warning"}
                or set(zebrafish_regvelo_report.get("methods_not_run", {}).values())
                != {"not-run"}
            ):
                errors.append(
                    "zebrafish RegVelo public-data case differs from its official artifacts, continuous-layer contract, module, template, execution, withheld-stage direction, mode sensitivity, or scientific gates"
                )
        zebrafish_cellrank_report_path = (
            ROOT / "reports" / "public-case-zebrafish-cellrank.json"
        )
        zebrafish_cellrank_root = BUILTIN_ROOT / "single-cell-fate-mapping"
        try:
            zebrafish_cellrank_report = json.loads(
                zebrafish_cellrank_report_path.read_text(encoding="utf-8")
            )
            zebrafish_cellrank_manifest = registry.get(
                "single-cell-fate-mapping"
            )
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append(
                "zebrafish CellRank public-data acceptance case is missing or invalid"
            )
        else:
            cellrank_source = zebrafish_cellrank_report.get("source", {})
            cellrank_execution = zebrafish_cellrank_report.get("execution", {})
            cellrank_repeat = cellrank_execution.get(
                "deterministic_repeat", {}
            )
            cellrank_direction = cellrank_execution.get(
                "withheld_stage_direction", {}
            )
            cellrank_sensitivity = cellrank_execution.get(
                "connectivity_sensitivity", {}
            )
            cellrank_gates = zebrafish_cellrank_report.get(
                "quality_gates", {}
            )
            if (
                zebrafish_cellrank_report.get("passed") is not True
                or zebrafish_cellrank_report.get("case_type")
                != "public-data-end-to-end"
                or zebrafish_cellrank_report.get("module", {}).get("id")
                != zebrafish_cellrank_manifest.id
                or zebrafish_cellrank_report.get("module", {}).get("version")
                != zebrafish_cellrank_manifest.version
                or zebrafish_cellrank_report.get("module", {}).get(
                    "compatibility_row_id"
                )
                != zebrafish_cellrank_manifest.compatibility_matrix[0].id
                or not evidence_scope_is_current(zebrafish_cellrank_report, registry)
                or zebrafish_cellrank_report.get("module", {}).get(
                    "template_sha256"
                )
                != hashlib.sha256(
                    (
                        zebrafish_cellrank_root
                        / "templates"
                        / "run_cellrank_fate.py"
                    ).read_bytes()
                ).hexdigest()
                or cellrank_source.get("official_h5ad_sha256")
                != "eccab081c44cfe335b726aec8172bbcda072241b4f006f6420bb5d46d39611cb"
                or cellrank_source.get("upstream_report_sha256")
                != hashlib.sha256(
                    zebrafish_regvelo_report_path.read_bytes()
                ).hexdigest()
                or cellrank_source.get("validation", {}).get("cells") != 697
                or cellrank_source.get("validation", {}).get("features")
                != 1008
                or cellrank_source.get("validation", {}).get(
                    "expression_semantics"
                )
                != "log-normalized-continuous"
                or cellrank_source.get("validation", {}).get(
                    "velocity_finite_signed"
                )
                is not True
                or zebrafish_cellrank_report.get("runtime", {}).get(
                    "cellrank"
                )
                != "2.3.2"
                or cellrank_execution.get("independent_template_runs") != 3
                or cellrank_execution.get("pure_velocity_runs") != 2
                or cellrank_execution.get("velocity_connectivity_runs") != 1
                or cellrank_execution.get("source_expression_preserved")
                is not True
                or cellrank_execution.get("outputs_reloaded") is not True
                or set(cellrank_repeat)
                != {
                    "fate_probabilities",
                    "fate_table",
                    "transition_matrix",
                }
                or any(
                    item.get("exactly_equal") is not True
                    or item.get("maximum_absolute_difference") != 0
                    for item in cellrank_repeat.values()
                )
                or cellrank_direction.get("stage_used_for_fitting")
                is not False
                or cellrank_direction.get("expected_deltas", {}).get(
                    "pure_velocity", 0
                )
                <= 0
                or cellrank_direction.get("expected_deltas", {}).get(
                    "velocity_connectivity", 0
                )
                <= 0
                or cellrank_sensitivity.get("blended_connectivity_weight")
                != 0.2
                or cellrank_sensitivity.get("flattened_fate_pearson", 0)
                < cellrank_sensitivity.get("thresholds", {}).get(
                    "minimum_flattened_fate_pearson", 1
                )
                or cellrank_sensitivity.get(
                    "maximum_absolute_fate_difference", 1
                )
                > cellrank_sensitivity.get("thresholds", {}).get(
                    "maximum_absolute_fate_difference", 0
                )
                or cellrank_sensitivity.get("gate") != "pass"
                or cellrank_gates.get("terminal_state_consistency")
                != "pass-not-independent"
                or set(cellrank_gates.values())
                != {"pass", "pass-with-warning", "pass-not-independent"}
                or set(
                    zebrafish_cellrank_report.get(
                        "methods_not_run", {}
                    ).values()
                )
                != {"not-run"}
            ):
                errors.append(
                    "zebrafish CellRank public-data case differs from its admitted RegVelo input, velocity-kernel contract, exact repeat, withheld-stage direction, sensitivity bounds, or scientific claim limits"
                )
        gse96583_report_path = ROOT / "reports" / "public-case-gse96583-donor-inference.json"
        gse96583_root = BUILTIN_ROOT / "single-cell-donor-inference"
        try:
            gse96583_report = json.loads(gse96583_report_path.read_text(encoding="utf-8"))
            gse96583_manifest = registry.get("single-cell-donor-inference")
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("GSE96583 donor-aware public-data acceptance case is missing or invalid")
        else:
            source_validation = gse96583_report.get("source", {}).get("source_validation", {})
            execution = gse96583_report.get("execution", {})
            if (
                gse96583_report.get("passed") is not True
                or gse96583_report.get("case_type") != "public-data-end-to-end"
                or gse96583_report.get("module", {}).get("id") != gse96583_manifest.id
                or gse96583_report.get("module", {}).get("version") != gse96583_manifest.version
                or gse96583_report.get("module", {}).get("compatibility_row_id")
                != gse96583_manifest.compatibility_matrix[0].id
                or not evidence_scope_is_current(gse96583_report, registry)
                or gse96583_report.get("module", {}).get("template_sha256")
                != {
                    name: hashlib.sha256((gse96583_root / "templates" / name).read_bytes()).hexdigest()
                    for name in ("pseudobulk_aggregate.py", "donor_differential.R")
                }
                or gse96583_report.get("source", {}).get("accession") != "GSE96583"
                or gse96583_report.get("source", {}).get("files", {}).get("archive", {}).get("sha256")
                != "e5d41a3248a813f99d68fd5c9eb9773de7f46a83680a67f4a02d683b8955fe80"
                or source_validation.get("published_cells") != 29065
                or source_validation.get("retained_published_singlets_with_cell_type") != 24673
                or source_validation.get("paired_donors") != 8
                or source_validation.get("combined_metadata_barcode_normalizations") != {"ctrl": 0, "stim": 313}
                or gse96583_report.get("runtime", {}).get("scanpy") != "1.11.5"
                or gse96583_report.get("runtime", {}).get("edgeR") != "4.0.16"
                or execution.get("pseudobulks") != 128
                or execution.get("eligible_pseudobulks") != 109
                or execution.get("completed_cell_types") != 7
                or execution.get("all_cells_accounted") is not True
                or execution.get("raw_counts_conserved") is not True
                or execution.get("paired_designs_full_rank") is not True
                or execution.get("result_reload_validated") is not True
                or set(execution.get("ifn_response_genes_recovered", ()))
                != {"IFI6", "IFIT1", "IFIT2", "IFIT3", "ISG15", "MX1", "OAS1", "OAS2", "OAS3", "STAT1"}
                or len(execution.get("ifn_response_cell_types", ())) < 5
                or set(gse96583_report.get("quality_gates", {}).values()) != {"pass"}
            ):
                errors.append(
                    "GSE96583 donor-aware public-data case differs from its source, module, templates, runtime, paired design, or scientific gates"
                )
        gse96583_marker_report_path = (
            ROOT / "reports" / "public-case-gse96583-marker-discovery.json"
        )
        gse96583_marker_root = BUILTIN_ROOT / "single-cell-marker-discovery"
        try:
            gse96583_marker_report = json.loads(
                gse96583_marker_report_path.read_text(encoding="utf-8")
            )
            gse96583_marker_manifest = registry.get(
                "single-cell-marker-discovery"
            )
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append(
                "GSE96583 marker-discovery public-data acceptance case is missing or invalid"
            )
        else:
            marker_parameters = gse96583_marker_report.get("parameters", {})
            marker_execution = gse96583_marker_report.get("execution", {})
            marker_counts = marker_execution.get(
                "independently_validated_rows_by_cell_type", {}
            )
            marker_families = set(
                marker_execution.get(
                    "recovered_expected_marker_families", ()
                )
            )
            expected_marker_cell_types = {
                "B cells",
                "CD14+ Monocytes",
                "CD4 T cells",
                "CD8 T cells",
                "FCGR3A+ Monocytes",
                "NK cells",
            }
            if (
                gse96583_marker_report.get("passed") is not True
                or gse96583_marker_report.get("case_type")
                != "public-data-end-to-end"
                or gse96583_marker_report.get("module", {}).get("id")
                != gse96583_marker_manifest.id
                or gse96583_marker_report.get("module", {}).get("version")
                != gse96583_marker_manifest.version
                or gse96583_marker_report.get("module", {}).get(
                    "compatibility_row_id"
                )
                != gse96583_marker_manifest.compatibility_matrix[0].id
                or not evidence_scope_is_current(gse96583_marker_report, registry)
                or gse96583_marker_report.get("module", {}).get(
                    "template_sha256"
                )
                != hashlib.sha256(
                    (
                        gse96583_marker_root
                        / "templates"
                        / "discover_markers.py"
                    ).read_bytes()
                ).hexdigest()
                or gse96583_marker_report.get("source", {}).get("accession")
                != "GSE96583"
                or gse96583_marker_report.get("source", {})
                .get("files", {})
                .get("archive", {})
                .get("sha256")
                != "e5d41a3248a813f99d68fd5c9eb9773de7f46a83680a67f4a02d683b8955fe80"
                or gse96583_marker_report.get("runtime", {}).get("scanpy")
                != "1.10.4"
                or gse96583_marker_report.get("runtime", {}).get("anndata")
                != "0.10.8"
                or marker_parameters.get("sample_split_frozen_before_ranking")
                is not True
                or marker_parameters.get("feature_filter", {}).get(
                    "uses_cell_type_labels"
                )
                is not False
                or len(marker_parameters.get("discovery_donors", ())) != 6
                or len(marker_parameters.get("validation_donors", ())) != 2
                or set(marker_parameters.get("discovery_donors", ()))
                & set(marker_parameters.get("validation_donors", ()))
                or marker_execution.get("input_control_singlets") != 11990
                or marker_execution.get("retained_features") != 10859
                or marker_execution.get("cell_types") != 6
                or marker_execution.get("tested_marker_rows") != 900
                or marker_execution.get("discovery_admitted_rows") != 612
                or marker_execution.get("independently_validated_rows") != 606
                or set(marker_counts) != expected_marker_cell_types
                or any(value < 5 for value in marker_counts.values())
                or marker_families != expected_marker_cell_types
                or marker_execution.get("exact_repeat_marker_tsv") is not True
                or set(
                    gse96583_marker_report.get("quality_gates", {}).values()
                )
                != {"pass"}
            ):
                errors.append(
                    "GSE96583 marker-discovery public-data case differs from its source, sample split, module, template, runtime, held-out validation, repeatability, or scientific gates"
                )
        gse96583_doublet_report_path = (
            ROOT / "reports" / "public-case-gse96583-doublet-detection.json"
        )
        gse96583_doublet_root = BUILTIN_ROOT / "single-cell-doublet-detection"
        try:
            gse96583_doublet_report = json.loads(
                gse96583_doublet_report_path.read_text(encoding="utf-8")
            )
            gse96583_doublet_manifest = registry.get(
                "single-cell-doublet-detection"
            )
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append(
                "GSE96583 doublet-detection public-data acceptance case is missing or invalid"
            )
        else:
            doublet_parameters = gse96583_doublet_report.get("parameters", {})
            doublet_execution = gse96583_doublet_report.get("execution", {})
            doublet_metrics = doublet_execution.get("method_metrics", {})
            doublet_agreement = doublet_execution.get("method_agreement", {})
            if (
                gse96583_doublet_report.get("passed") is not True
                or gse96583_doublet_report.get("case_type")
                != "public-data-end-to-end"
                or gse96583_doublet_report.get("module", {}).get("id")
                != gse96583_doublet_manifest.id
                or gse96583_doublet_report.get("module", {}).get("version")
                != gse96583_doublet_manifest.version
                or gse96583_doublet_report.get("module", {}).get(
                    "compatibility_row_id"
                )
                != gse96583_doublet_manifest.compatibility_matrix[0].id
                or not evidence_scope_is_current(gse96583_doublet_report, registry)
                or gse96583_doublet_report.get("module", {}).get(
                    "template_sha256"
                )
                != {
                    name: hashlib.sha256(
                        (gse96583_doublet_root / "templates" / name).read_bytes()
                    ).hexdigest()
                    for name in ("run_scrublet.py", "run_scdblfinder.R")
                }
                or gse96583_doublet_report.get("source", {}).get("accession")
                != "GSE96583"
                or doublet_parameters.get("labels_available_to_methods") is not False
                or doublet_parameters.get("labels_used_for_threshold_selection")
                is not False
                or doublet_parameters.get("expected_doublet_rate") != 0.10
                or doublet_execution.get("input_cells") != 29065
                or doublet_execution.get(
                    "ambiguous_cells_excluded_from_metrics"
                )
                != 1217
                or doublet_execution.get("all_cells_accounted") is not True
                or doublet_execution.get("source_immutable") is not True
                or doublet_execution.get("outputs_reloaded") is not True
                or doublet_execution.get("automatic_cell_removal_performed")
                is not False
                or doublet_metrics.get("scrublet", {})
                .get("overall", {})
                .get("auroc", 0)
                < 0.85
                or doublet_metrics.get("scDblFinder", {})
                .get("overall", {})
                .get("auroc", 0)
                < 0.90
                or doublet_agreement.get(
                    "published_doublet_prevalence_among_both_called", 0
                )
                <= doublet_agreement.get("published_doublet_prevalence", 1)
                or set(
                    gse96583_doublet_report.get("quality_gates", {}).values()
                )
                != {"pass"}
            ):
                errors.append(
                    "GSE96583 doublet-detection public-data case differs from its source, module, templates, withheld-label design, execution, or scientific gates"
                )
        gse96583_reference_report_path = (
            ROOT / "reports" / "public-case-gse96583-reference-annotation.json"
        )
        gse96583_reference_root = BUILTIN_ROOT / "single-cell-reference-annotation"
        try:
            gse96583_reference_report = json.loads(
                gse96583_reference_report_path.read_text(encoding="utf-8")
            )
            gse96583_reference_manifest = registry.get(
                "single-cell-reference-annotation"
            )
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append(
                "GSE96583 reference-annotation public-data acceptance case is missing or invalid"
            )
        else:
            reference_parameters = gse96583_reference_report.get(
                "parameters", {}
            )
            reference_source = gse96583_reference_report.get(
                "source", {}
            ).get("source_validation", {})
            reference_execution = gse96583_reference_report.get(
                "execution", {}
            )
            if (
                gse96583_reference_report.get("passed") is not True
                or gse96583_reference_report.get("case_type")
                != "public-data-end-to-end"
                or gse96583_reference_report.get("module", {}).get("id")
                != gse96583_reference_manifest.id
                or gse96583_reference_report.get("module", {}).get("version")
                != gse96583_reference_manifest.version
                or gse96583_reference_report.get("module", {}).get(
                    "compatibility_row_id"
                )
                != gse96583_reference_manifest.compatibility_matrix[0].id
                or not evidence_scope_is_current(gse96583_reference_report, registry)
                or gse96583_reference_report.get("module", {}).get(
                    "template_sha256"
                )
                != {
                    name: hashlib.sha256(
                        (gse96583_reference_root / "templates" / name).read_bytes()
                    ).hexdigest()
                    for name in ("annotate_reference.py", "run_singler.R")
                }
                or gse96583_reference_report.get("source", {}).get("accession")
                != "GSE96583"
                or reference_parameters.get(
                    "donor_split_frozen_before_mapping"
                )
                is not True
                or reference_parameters.get(
                    "publisher_labels_available_to_mapping"
                )
                is not False
                or reference_parameters.get(
                    "publisher_labels_used_for_threshold_selection"
                )
                is not False
                or reference_parameters.get("held_out_reference_label")
                != "Megakaryocytes"
                or len(reference_source.get("reference_donors", ())) != 6
                or len(reference_source.get("query_donors", ())) != 2
                or set(reference_source.get("reference_donors", ()))
                & set(reference_source.get("query_donors", ()))
                or reference_source.get("reference_cells_after_balancing") != 840
                or reference_source.get("query_cells") != 4139
                or reference_source.get("genes") != 35635
                or reference_execution.get(
                    "known_label_accuracy_among_accepted", 0
                )
                < 0.95
                or reference_execution.get("known_label_coverage", 0) < 0.80
                or reference_execution.get(
                    "known_macro_f1_with_unknown_penalty", 0
                )
                < 0.60
                or reference_execution.get(
                    "held_out_class_unknown_retention", 0
                )
                < 0.50
                or reference_execution.get("all_query_cells_accounted") is not True
                or reference_execution.get("source_artifacts_immutable") is not True
                or reference_execution.get("output_reloaded") is not True
                or reference_execution.get("raw_counts_preserved") is not True
                or reference_execution.get("existing_labels_preserved") is not True
                or set(
                    gse96583_reference_report.get("quality_gates", {}).values()
                )
                != {"pass"}
            ):
                errors.append(
                    "GSE96583 reference-annotation public-data case differs from its source, module, templates, held-out-donor design, unknown boundary, execution, or scientific gates"
                )
        gse96583_integration_report_path = (
            ROOT / "reports" / "public-case-gse96583-batch-integration.json"
        )
        gse96583_integration_root = BUILTIN_ROOT / "single-cell-batch-integration"
        try:
            gse96583_integration_report = json.loads(
                gse96583_integration_report_path.read_text(encoding="utf-8")
            )
            gse96583_integration_manifest = registry.get(
                "single-cell-batch-integration"
            )
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append(
                "GSE96583 batch-integration public-data acceptance case is missing or invalid"
            )
        else:
            integration_source = gse96583_integration_report.get(
                "source", {}
            ).get("source_validation", {})
            integration_execution = gse96583_integration_report.get(
                "execution", {}
            )
            integration_results = integration_execution.get(
                "method_results", {}
            )
            if (
                gse96583_integration_report.get("passed") is not True
                or gse96583_integration_report.get("case_type")
                != "public-data-end-to-end"
                or gse96583_integration_report.get("module", {}).get("id")
                != gse96583_integration_manifest.id
                or gse96583_integration_report.get("module", {}).get("version")
                != gse96583_integration_manifest.version
                or gse96583_integration_report.get("module", {}).get(
                    "compatibility_row_id"
                )
                != gse96583_integration_manifest.compatibility_matrix[0].id
                or not evidence_scope_is_current(gse96583_integration_report, registry)
                or gse96583_integration_report.get("module", {}).get(
                    "template_sha256"
                )
                != hashlib.sha256(
                    (
                        gse96583_integration_root
                        / "templates"
                        / "benchmark_integration.py"
                    ).read_bytes()
                ).hexdigest()
                or gse96583_integration_report.get("source", {}).get("accession")
                != "GSE96583"
                or integration_source.get("selected_cells") != 6400
                or integration_source.get("genes") != 35635
                or integration_source.get("donors") != 8
                or integration_source.get("conditions") != 2
                or integration_source.get("biological_samples") != 16
                or integration_source.get("minimum_donors_per_stratum", 0) < 2
                or set(integration_execution.get("eligible_methods", ()))
                != {"bbknn", "harmony"}
                or set(
                    integration_execution.get("blocked_methods", {}).get(
                        "scanorama", ()
                    )
                )
                != {"batch_mixing_gain", "label_purity_preserved"}
                or integration_execution.get("selected_method") != "bbknn"
                or integration_execution.get("counterfactual_pca_exact")
                is not True
                or integration_execution.get(
                    "counterfactual_max_absolute_difference"
                )
                != 0.0
                or integration_results.get("bbknn", {})
                .get("metric_deltas", {})
                .get("batch_neighbor_entropy_gain", 0)
                < 0.02
                or integration_results.get("bbknn", {})
                .get("metric_deltas", {})
                .get("label_neighbor_purity_loss", 1)
                > 0.10
                or integration_results.get("scanorama", {})
                .get("metric_deltas", {})
                .get("batch_neighbor_entropy_gain", 0)
                >= 0
                or any(
                    result.get("source_immutable") is not True
                    or result.get("identity_preserved") is not True
                    or result.get("reload_validated") is not True
                    for result in integration_results.values()
                )
                or set(
                    gse96583_integration_report.get(
                        "quality_gates", {}
                    ).values()
                )
                != {"pass"}
            ):
                errors.append(
                    "GSE96583 batch-integration public-data case differs from its source, module, template, crossed design, anti-leakage evidence, method decision, or scientific gates"
                )
        public_database_report_path = ROOT / "reports" / "public-database-live-verification.json"
        public_database_module_ids = {
            "citation-record-resolution",
            "preprint-evidence",
            "chemical-evidence",
            "clinical-trial-evidence",
            "structure-evidence",
            "structure-search",
            "structure-polymer-entities",
            "structure-ligands",
            "alphafold-structure-evidence",
            "protein-interaction-network-evidence",
        }
        expected_public_database_contracts = {
            "alphafold-db-api": ALPHAFOLD_CONTRACT_VERSION,
            "biorxiv-details": BIORXIV_CONTRACT_VERSION,
            "clinicaltrials-gov-api": CLINICAL_TRIALS_CONTRACT_VERSION,
            "crossref-rest": CROSSREF_CONTRACT_VERSION,
            "europe-pmc-rest": EUROPE_PMC_CONTRACT_VERSION,
            "pubchem-pug-rest": PUBCHEM_CONTRACT_VERSION,
            "rcsb-pdb-data-api": RCSB_CONTRACT_VERSION,
            "rcsb-pdb-search-api": RCSB_SEARCH_CONTRACT_VERSION,
            "string-api": STRING_CONTRACT_VERSION,
        }
        try:
            public_database_report = json.loads(public_database_report_path.read_text(encoding="utf-8"))
            public_database_manifests = {module_id: registry.get(module_id) for module_id in public_database_module_ids}
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("public database live verification is missing or invalid")
        else:
            package_validation = public_database_report.get("module_package_validation", {})
            check_names = {item.get("name") for item in public_database_report.get("checks", ())}
            expected_check_names = {
                "citation_record_resolution",
                "preprint_version_history",
                "compound_identity",
                "trial_design_record",
                "structure_entry_context",
                "structure_attribute_search",
                "structure_polymer_entities",
                "structure_bound_ligands",
                "structure_prediction_metadata",
                "protein_interaction_network",
            }
            scientific_summary = public_database_report.get("scientific_summary", {})
            if (
                public_database_report.get("passed") is not True
                or not evidence_scope_is_current(public_database_report, registry)
                or set(public_database_report.get("module_ids", ())) != public_database_module_ids
                or public_database_report.get("contracts") != expected_public_database_contracts
                or check_names != expected_check_names
                or any(item.get("passed") is not True for item in public_database_report.get("checks", ()))
                or set(package_validation) != public_database_module_ids
                or any(
                    validation.get("valid") is not True
                    or validation.get("executed_test_cases") != 1
                    or validation.get("module_version") != public_database_manifests[module_id].version
                    for module_id, validation in package_validation.items()
                )
                or set(scientific_summary.values()) != {True}
            ):
                errors.append("public database evidence differs from its modules, service contracts, live checks, or scientific quality gates")
        command_source = (ROOT / "biomed_workbench" / "modules" / "scientific_command.py").read_text(encoding="utf-8")
        if "shell=True" in command_source or "os.system(" in command_source:
            errors.append("scientific command execution contains a shell invocation surface")
        fastqc_report_path = ROOT / "reports" / "fastqc-live-verification.json"
        fastqc_fixture_path = ROOT / "tests" / "fixtures" / "sequencing" / "read-qc-balanced.fastq"
        fixture_digest = hashlib.sha256(fastqc_fixture_path.read_bytes()).hexdigest()
        try:
            fastqc_report = json.loads(fastqc_report_path.read_text(encoding="utf-8"))
            fastqc_manifest = registry.get("read-quality-fastqc")
            fastqc_row = fastqc_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("FastQC live verification evidence is missing or invalid")
        else:
            if (
                fastqc_report.get("passed") is not True
                or fastqc_report.get("module_version") != fastqc_manifest.version
                or fastqc_report.get("compatibility_row_id") != fastqc_row.id
                or fastqc_report.get("regression_evidence_id") != fastqc_row.regression_evidence_ids[0]
                or fastqc_report.get("end_to_end_evidence_id") != fastqc_row.end_to_end_evidence_ids[0]
                or fastqc_report.get("tool_versions") != {"fastqc": "0.12.1"}
                or fastqc_report.get("dependency_versions") != {"java": "22"}
                or fastqc_report.get("fixture", {}).get("sha256") != fixture_digest
                or fastqc_report.get("html_report_validated") is not True
            ):
                errors.append("FastQC live verification differs from its module, compatibility row, or fixture")
        multiqc_report_path = ROOT / "reports" / "multiqc-live-verification.json"
        try:
            multiqc_report = json.loads(multiqc_report_path.read_text(encoding="utf-8"))
            multiqc_manifest = registry.get("quality-report-multiqc")
            multiqc_row = multiqc_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("MultiQC live verification evidence is missing or invalid")
        else:
            expected_dependencies = {item.name: item.tested_versions[0] for item in multiqc_manifest.dependencies}
            if (
                multiqc_report.get("passed") is not True
                or multiqc_report.get("module_version") != multiqc_manifest.version
                or multiqc_report.get("compatibility_row_id") != multiqc_row.id
                or multiqc_report.get("regression_evidence_id") != multiqc_row.regression_evidence_ids[0]
                or multiqc_report.get("end_to_end_evidence_id") != multiqc_row.end_to_end_evidence_ids[0]
                or multiqc_report.get("tool_versions") != {"multiqc": "1.35"}
                or multiqc_report.get("dependency_versions") != expected_dependencies
                or multiqc_report.get("fixture", {}).get("sha256") != fixture_digest
                or multiqc_report.get("scientific_summary", {}).get("sample_count") != 2
                or len(multiqc_report.get("runtime_lock", {})) < 50
                or multiqc_report.get("html_report_validated") is not True
            ):
                errors.append("MultiQC live verification differs from its module, compatibility row, fixture, or runtime lock")
        fastp_report_path = ROOT / "reports" / "fastp-live-verification.json"
        try:
            fastp_report = json.loads(fastp_report_path.read_text(encoding="utf-8"))
            fastp_manifest = registry.get("read-quality-fastp")
            fastp_row = fastp_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("fastp live verification evidence is missing or invalid")
        else:
            if (
                fastp_report.get("passed") is not True
                or fastp_report.get("module_version") != fastp_manifest.version
                or fastp_report.get("compatibility_row_id") != fastp_row.id
                or fastp_report.get("regression_evidence_id") != fastp_row.regression_evidence_ids[0]
                or fastp_report.get("end_to_end_evidence_id") != fastp_row.end_to_end_evidence_ids[0]
                or fastp_report.get("tool_versions") != {"fastp": "1.3.6"}
                or fastp_report.get("dependency_versions") != {"fastp-bioconda-build": "1.3.6-ha1d0559_0"}
                or fastp_report.get("runtime_lock", {}).get("fastp") != "1.3.6-ha1d0559_0"
                or fastp_report.get("fixture", {}).get("sha256") != fixture_digest
                or fastp_report.get("scientific_summary", {}).get("qc_only_read_accounting_passed") is not True
                or fastp_report.get("html_report_validated") is not True
            ):
                errors.append("fastp live verification differs from its module, compatibility row, fixture, or runtime lock")
        screen_report_path = ROOT / "reports" / "fastq-screen-live-verification.json"
        try:
            screen_report = json.loads(screen_report_path.read_text(encoding="utf-8"))
            screen_manifest = registry.get("read-contamination-screen")
            screen_row = screen_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("FastQ Screen live verification evidence is missing or invalid")
        else:
            expected_dependencies = {item.name: item.tested_versions[0] for item in screen_manifest.dependencies}
            if (
                screen_report.get("passed") is not True
                or screen_report.get("module_version") != screen_manifest.version
                or screen_report.get("compatibility_row_id") != screen_row.id
                or screen_report.get("regression_evidence_id") != screen_row.regression_evidence_ids[0]
                or screen_report.get("end_to_end_evidence_id") != screen_row.end_to_end_evidence_ids[0]
                or screen_report.get("tool_versions") != {"fastq-screen": "0.16.0"}
                or screen_report.get("dependency_versions") != expected_dependencies
                or screen_report.get("runtime_lock", {}).get("bowtie2") != "2.5.5-h9e91881_0"
                or screen_report.get("fixture", {}).get("sha256") != fixture_digest
                or screen_report.get("scientific_summary", {}).get("contamination_screening") != {"status": "passed", "reference_count": 2}
                or screen_report.get("html_report_validated") is not True
            ):
                errors.append("FastQ Screen live verification differs from its module, compatibility row, fixture, references, or runtime lock")
        alignment_report_path = ROOT / "reports" / "alignment-quality-live-verification.json"
        try:
            alignment_report = json.loads(alignment_report_path.read_text(encoding="utf-8"))
            alignment_manifest = registry.get("alignment-quality-samtools")
            alignment_row = alignment_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("samtools alignment quality live verification evidence is missing or invalid")
        else:
            if (
                alignment_report.get("passed") is not True
                or alignment_report.get("module_version") != alignment_manifest.version
                or alignment_report.get("compatibility_row_id") != alignment_row.id
                or alignment_report.get("regression_evidence_id") != alignment_row.regression_evidence_ids[0]
                or alignment_report.get("end_to_end_evidence_id") != alignment_row.end_to_end_evidence_ids[0]
                or alignment_report.get("tool_versions") != {"samtools": "1.23"}
                or alignment_report.get("dependency_versions") != {"htslib": "1.23"}
                or alignment_report.get("fixture_manifest", {}).get("format") != "bam@1.6"
                or not all(alignment_report.get("bundle_integrity", {}).values())
                or alignment_report.get("scientific_summary", {}).get("counts", {}).get("total") != 4
            ):
                errors.append("samtools alignment quality evidence differs from its module, row, BAM fixture, or integrity checks")
        interval_report_path = ROOT / "reports" / "interval-overlap-live-verification.json"
        try:
            interval_report = json.loads(interval_report_path.read_text(encoding="utf-8"))
            interval_manifest = registry.get("interval-overlap-bedtools")
            interval_row = interval_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("bedtools interval overlap live verification evidence is missing or invalid")
        else:
            summary = interval_report.get("scientific_summary", {})
            if (
                interval_report.get("passed") is not True
                or interval_report.get("module_version") != interval_manifest.version
                or interval_report.get("compatibility_row_id") != interval_row.id
                or interval_report.get("tool_versions") != {"bedtools": "2.31.1"}
                or interval_report.get("dependency_versions") != {"xz": "5.8.3"}
                or interval_report.get("fixture", {}).get("format") != "bed@1.0"
                or interval_report.get("source_reconciliation_passed") is not True
                or summary.get("overlap_pair_count") != 3
                or summary.get("total_pairwise_overlap_bp") != 10
            ):
                errors.append("bedtools interval evidence differs from its module, row, BED fixture, or overlap checks")
        bwa_report_path = ROOT / "reports" / "bwa-mem-live-verification.json"
        try:
            bwa_report = json.loads(bwa_report_path.read_text(encoding="utf-8"))
            bwa_manifest = registry.get("dna-align-bwa-mem-single")
            bwa_row = bwa_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("BWA-MEM live verification evidence is missing or invalid")
        else:
            if (
                bwa_report.get("passed") is not True
                or bwa_report.get("module_version") != bwa_manifest.version
                or bwa_report.get("compatibility_row_id") != bwa_row.id
                or bwa_report.get("tool_versions", {}).get("bwa") != "0.7.19-r1273"
                or bwa_report.get("dependency_versions", {}).get("bwa-homebrew-bottle") != "0.7.19-bottle-arm64"
                or not all(bwa_report.get("tested_version_baseline", {}).get("tools", {}).values())
                or not all(bwa_report.get("tested_version_baseline", {}).get("dependencies", {}).values())
                or bwa_report.get("scientific_summary", {}).get("counts", {}).get("total") != 2
                or bwa_report.get("portable_program_record_validated") is not True
            ):
                errors.append("BWA-MEM evidence differs from its module, policy, tested baseline, fixture, or portable SAM checks")
        sort_report_path = ROOT / "reports" / "alignment-sort-live-verification.json"
        try:
            sort_report = json.loads(sort_report_path.read_text(encoding="utf-8"))
            sort_manifest = registry.get("alignment-sort-index-samtools")
            sort_row = sort_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("samtools sort/index live verification evidence is missing or invalid")
        else:
            if (
                sort_report.get("passed") is not True
                or sort_report.get("module_version") != sort_manifest.version
                or sort_report.get("compatibility_row_id") != sort_row.id
                or sort_report.get("output_manifest", {}).get("format") != "bam@1.6"
                or sort_report.get("output_manifest", {}).get("index_type") != "csi"
                or sort_report.get("output_manifest", {}).get("sort_order") != "coordinate"
                or not all(sort_report.get("bundle_integrity", {}).values())
                or sort_report.get("scientific_summary", {}).get("counts", {}).get("total") != 3
            ):
                errors.append("samtools sort/index evidence differs from its module, BAM/CSI outputs, header, index, or read accounting")
        vcf_query_report_path = ROOT / "reports" / "vcf-region-query-live-verification.json"
        try:
            vcf_query_report = json.loads(vcf_query_report_path.read_text(encoding="utf-8"))
            vcf_query_manifest = registry.get("variant-region-query-tabix")
            vcf_query_row = vcf_query_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("tabix VCF region-query live verification evidence is missing or invalid")
        else:
            summary = vcf_query_report.get("scientific_summary", {})
            if (
                vcf_query_report.get("passed") is not True
                or vcf_query_report.get("module_version") != vcf_query_manifest.version
                or vcf_query_report.get("compatibility_row_id") != vcf_query_row.id
                or vcf_query_report.get("tool_versions") != {"tabix": "1.23"}
                or vcf_query_report.get("dependency_versions") != {"htslib": "1.23"}
                or vcf_query_report.get("fixture", {}).get("format") != "vcf@4.5"
                or vcf_query_report.get("fixture", {}).get("index_type") != "tbi"
                or not all(vcf_query_report.get("bundle_integrity", {}).values())
                or summary.get("record_count") != 2
                or summary.get("samples") != ["SAMPLE_A"]
                or summary.get("region") != "chr1:90-205"
            ):
                errors.append("tabix VCF region-query evidence differs from its module, row, VCF/TBI fixture, sample, or regional record checks")
        vcf_filter_report_path = ROOT / "reports" / "vcf-filter-live-verification.json"
        try:
            vcf_filter_report = json.loads(vcf_filter_report_path.read_text(encoding="utf-8"))
            vcf_filter_manifest = registry.get("variant-filter-vcf")
            vcf_filter_row = vcf_filter_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("strict VCF filter live verification evidence is missing or invalid")
        else:
            summary = vcf_filter_report.get("scientific_summary", {})
            implementation = vcf_filter_report.get("implementation", {})
            if (
                vcf_filter_report.get("passed") is not True
                or vcf_filter_report.get("module_version") != vcf_filter_manifest.version
                or vcf_filter_report.get("compatibility_row_id") != vcf_filter_row.id
                or vcf_filter_report.get("tool_versions") != {"python3": "3.14.3"}
                or vcf_filter_report.get("dependency_versions") != {"python-stdlib": "3.14.3"}
                or vcf_filter_report.get("fixture", {}).get("format") != "vcf@4.5"
                or implementation.get("module") != "biomed_workbench.implementations.vcf_filter"
                or not re.fullmatch(r"[0-9a-f]{64}", str(implementation.get("sha256", "")))
                or summary.get("input_record_count") != 7
                or summary.get("accepted_record_count") != 1
                or summary.get("excluded_record_count") != 6
                or summary.get("accepted_record_keys") != ["chr1:100:A:G:v1"]
                or sum(summary.get("exclusion_counts", {}).values()) != 6
            ):
                errors.append("strict VCF filter evidence differs from its module, implementation, row, fixture, parameters, or record accounting")
        vcf_decompress_report_path = ROOT / "reports" / "vcf-decompress-live-verification.json"
        try:
            vcf_decompress_report = json.loads(vcf_decompress_report_path.read_text(encoding="utf-8"))
            vcf_decompress_manifest = registry.get("variant-decompress-bgzip")
            vcf_decompress_row = vcf_decompress_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("BGZF VCF decompression live verification evidence is missing or invalid")
        else:
            summary = vcf_decompress_report.get("scientific_summary", {})
            if (
                vcf_decompress_report.get("passed") is not True
                or vcf_decompress_report.get("module_version") != vcf_decompress_manifest.version
                or vcf_decompress_report.get("compatibility_row_id") != vcf_decompress_row.id
                or vcf_decompress_report.get("tool_versions") != {"bgzip": "1.23"}
                or vcf_decompress_report.get("dependency_versions") != {"htslib": "1.23"}
                or vcf_decompress_report.get("fixture", {}).get("format") != "vcf@4.5"
                or not all(vcf_decompress_report.get("bundle_integrity", {}).values())
                or summary.get("record_count") != 7
                or summary.get("samples") != ["SAMPLE_A"]
                or summary.get("coordinate_sorted") is not True
            ):
                errors.append("BGZF VCF decompression evidence differs from its module, row, bundle, byte roundtrip, or VCF document checks")
        tmb_vcf_report_path = ROOT / "reports" / "tmb-vcf-live-verification.json"
        try:
            tmb_vcf_report = json.loads(tmb_vcf_report_path.read_text(encoding="utf-8"))
            tmb_vcf_manifest = registry.get("tumor-mutation-burden-vcf")
            tmb_vcf_row = tmb_vcf_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("VCF/BED TMB live verification evidence is missing or invalid")
        else:
            summary = tmb_vcf_report.get("scientific_summary", {})
            serial = tmb_vcf_report.get("serial_execution", {})
            implementation = tmb_vcf_report.get("implementation", {})
            if (
                tmb_vcf_report.get("passed") is not True
                or tmb_vcf_report.get("module_version") != tmb_vcf_manifest.version
                or tmb_vcf_report.get("compatibility_row_id") != tmb_vcf_row.id
                or tmb_vcf_report.get("tool_versions") != {"python3": "3.14.3"}
                or tmb_vcf_report.get("dependency_versions") != {"python-stdlib": "3.14.3"}
                or tmb_vcf_report.get("fixture", {}).get("vcf_format") != "vcf@4.5"
                or tmb_vcf_report.get("fixture", {}).get("bed_format") != "bed@1.0"
                or implementation.get("module") != "biomed_workbench.implementations.tmb_vcf"
                or not re.fullmatch(r"[0-9a-f]{64}", str(implementation.get("sha256", "")))
                or serial.get("plan") != ["variant-filter-vcf", "tumor-mutation-burden-vcf"]
                or summary.get("input_variant_count") != 2
                or summary.get("nonsynonymous_variant_count") != 2
                or summary.get("callable_bases") != 1500000
                or summary.get("merged_interval_count") != 2
                or not abs(summary.get("tmb_mutations_per_mb", 0) - 4 / 3) < 1e-12
                or not str(summary.get("classification_policy", "")).startswith("none")
            ):
                errors.append("VCF/BED TMB evidence differs from its module, serial filter plan, implementation, callable union, ANN counts, or arithmetic")
        nmf_report_path = ROOT / "reports" / "nmf-live-verification.json"
        try:
            nmf_report = json.loads(nmf_report_path.read_text(encoding="utf-8"))
            nmf_manifest = registry.get("metagene-factorization-nmf")
            nmf_row = nmf_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("stable NMF live verification evidence is missing or invalid")
        else:
            summary = nmf_report.get("scientific_summary", {})
            implementation = nmf_report.get("implementation", {})
            if (
                nmf_report.get("passed") is not True
                or nmf_report.get("module_version") != nmf_manifest.version
                or nmf_report.get("compatibility_row_id") != nmf_row.id
                or nmf_report.get("tool_versions") != {"python3": "3.14.3"}
                or nmf_report.get("dependency_versions") != {"numpy": "2.4.4", "scipy": "1.17.1", "scikit-learn": "1.8.0"}
                or nmf_report.get("fixture", {}).get("format") != "count-matrix@1.0.0"
                or nmf_report.get("fixture", {}).get("orientation") != "features-by-samples"
                or implementation.get("module") != "biomed_workbench.implementations.nmf_metagenes"
                or not re.fullmatch(r"[0-9a-f]{64}", str(implementation.get("sha256", "")))
                or summary.get("selected_rank") != 2
                or summary.get("removed_features") != ["GENE_ZERO", "GENE_CONSTANT"]
                or summary.get("quality_status") != "passed"
                or summary.get("selected_relative_error", 1) >= 0.001
                or summary.get("rank_metrics", [{}])[0].get("component_stability", 0) <= 0.99
            ):
                errors.append("stable NMF evidence differs from its module, runtime, implementation, fixture, rank selection, reconstruction, or stability checks")

        chroma_report_path = ROOT / "reports" / "chroma-key-live-verification.json"
        try:
            chroma_report = json.loads(chroma_report_path.read_text(encoding="utf-8"))
            chroma_manifest = registry.get("image-chroma-key-remove")
            chroma_row = chroma_manifest.compatibility_matrix[0]
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("chroma-key live verification evidence is missing or invalid")
        else:
            summary = chroma_report.get("scientific_summary", {})
            implementation = chroma_report.get("implementation", {})
            alpha_counts = summary.get("alpha_counts", {})
            if (
                chroma_report.get("passed") is not True
                or chroma_report.get("module_version") != chroma_manifest.version
                or chroma_report.get("compatibility_row_id") != chroma_row.id
                or chroma_report.get("tool_versions") != {"python3": "3.14.3"}
                or chroma_report.get("dependency_versions") != {"Pillow": "12.1.1"}
                or chroma_report.get("fixture", {}).get("format") != "png@3.0"
                or chroma_report.get("fixture", {}).get("orientation") != "top-left-raster"
                or implementation.get("module") != "biomed_workbench.implementations.chroma_key"
                or not re.fullmatch(r"[0-9a-f]{64}", str(implementation.get("sha256", "")))
                or summary.get("quality_status") != "passed"
                or summary.get("scientific_use") != "communication-asset-only"
                or summary.get("quantitative_interpretation_allowed") is not False
                or any(alpha_counts.get(name, 0) <= 0 for name in ("transparent", "partial", "opaque"))
            ):
                errors.append("chroma-key evidence differs from its module, runtime, implementation, format, alpha classes, or scientific-use boundary")

        plugin_contract_path = ROOT / "reports" / "plugin-contract-verification.json"
        try:
            plugin_contract = json.loads(plugin_contract_path.read_text(encoding="utf-8"))
            plugin_manifest_path = ROOT / ".codex-plugin" / "plugin.json"
            skill_path = ROOT / "skills" / "biomed-workbench" / "SKILL.md"
            snapshot_path = ROOT / "reports" / "module-registry-verification.json"
        except (OSError, json.JSONDecodeError):
            errors.append("official Codex plugin contract evidence is missing or invalid")
        else:
            official = plugin_contract.get("official_validation", {})
            snapshot = plugin_contract.get("isolated_registry_snapshot", {})
            if (
                plugin_contract.get("passed") is not True
                or plugin_contract.get("evidence_id") != "codex-plugin-manifest-contract-v1"
                or plugin_contract.get("evidence_type") != "codex-plugin-contract"
                or plugin_contract.get("plugin", {}).get("manifest_sha256") != hashlib.sha256(plugin_manifest_path.read_bytes()).hexdigest()
                or plugin_contract.get("plugin", {}).get("skill_sha256") != hashlib.sha256(skill_path.read_bytes()).hexdigest()
                or plugin_contract.get("plugin", {}).get("single_skill_entry") is not True
                or official.get("plugin_validator", {}).get("passed") is not True
                or official.get("skill_validator", {}).get("passed") is not True
                or not re.fullmatch(r"[0-9a-f]{64}", str(official.get("plugin_validator", {}).get("sha256", "")))
                or not re.fullmatch(r"[0-9a-f]{64}", str(official.get("skill_validator", {}).get("sha256", "")))
                or snapshot.get("report_sha256") != hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
                or snapshot.get("module_count") != len(modules)
                or snapshot.get("registry_digest") != registry.digest
                or snapshot.get("source_and_snapshot_indexes_match") is not True
            ):
                errors.append("official Codex plugin contract evidence is stale or differs from current manifest, skill, validators, or isolated registry")

        ci_quality_path = ROOT / "reports" / "ci-quality-verification.json"
        ci_workflow_path = ROOT / ".github" / "workflows" / "quality.yml"
        ci_requirements_path = ROOT / "requirements-ci.txt"
        try:
            ci_quality = json.loads(ci_quality_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("GitHub quality and secret-gate evidence is missing or invalid")
        else:
            if (
                ci_quality.get("passed") is not True
                or ci_quality.get("evidence_id") != "github-quality-and-secret-gates-v1"
                or ci_quality.get("workflow", {}).get("sha256") != hashlib.sha256(ci_workflow_path.read_bytes()).hexdigest()
                or ci_quality.get("requirements", {}).get("sha256") != hashlib.sha256(ci_requirements_path.read_bytes()).hexdigest()
                or not all(ci_quality.get("quality_gates", {}).values())
                or len(ci_quality.get("excluded_claims", ())) < 3
            ):
                errors.append("GitHub quality or secret-gate evidence is stale, incomplete, or overclaims scientific coverage")

        native_handoff_path = ROOT / "reports" / "codex-native-handoff-verification.json"
        native_skill_path = ROOT / "skills" / "biomed-workbench" / "SKILL.md"
        try:
            native_handoff = json.loads(native_handoff_path.read_text(encoding="utf-8"))
            native_manifest = registry.get("scientific-illustration-generation")
            native_manifest_path = ROOT / "biomed_workbench" / "modules" / "builtin" / native_manifest.id / "module.json"
            compatibility_path = ROOT / "reports" / "compatibility-execution-evidence.json"
        except (OSError, json.JSONDecodeError, ModuleRegistryError):
            errors.append("Codex-native image handoff evidence is missing or invalid")
        else:
            handoff = native_handoff.get("handoff", {})
            if (
                native_handoff.get("passed") is not True
                or native_handoff.get("evidence_id") != "codex-native-image-generation-handoff-v1"
                or native_handoff.get("evidence_type") != "codex-native-tool-handoff"
                or native_handoff.get("module", {}).get("manifest_sha256") != hashlib.sha256(native_manifest_path.read_bytes()).hexdigest()
                or native_handoff.get("module", {}).get("access") != "codex_native"
                or native_handoff.get("module", {}).get("credentials") != []
                or native_handoff.get("skill", {}).get("sha256") != hashlib.sha256(native_skill_path.read_bytes()).hexdigest()
                or handoff.get("tool") != "image_gen"
                or handoff.get("authentication") != "codex-managed"
                or handoff.get("provider_sdk_or_cli") is not False
                or handoff.get("provider_credential_requested") is not False
                or handoff.get("deterministic_handoff_executed") is not True
                or handoff.get("native_bitmap_invocation_tested") is not False
                or handoff.get("module_routed_once") is not True
                or native_handoff.get("compatibility_evidence_sha256") != hashlib.sha256(compatibility_path.read_bytes()).hexdigest()
                or native_handoff.get("source_behavior_disposition", {}).get("provider_auth_model_endpoint_and_retry_client") != "retired-codex-managed"
            ):
                errors.append("Codex-native image handoff evidence is stale, credential-bearing, duplicated, or overclaims bitmap execution")

    router_source = (ROOT / "biomed_workbench" / "router.py").read_text(encoding="utf-8")
    for forbidden_table in ("INTENT_BOOSTS", "WORKFLOW_KEYWORDS"):
        if forbidden_table in router_source:
            errors.append(f"central routing table is forbidden: {forbidden_table}")

    errors.extend(validate_source_hygiene(ROOT))

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
    if format_registry is not None:
        print(f"format_profiles={len(format_registry.all())}")
        print(f"format_registry_digest={format_registry.digest}")
    print("credentials=" + ",".join(sorted(ALLOWED_CREDENTIALS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
