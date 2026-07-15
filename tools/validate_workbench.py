#!/usr/bin/env python3
"""Validate the clean-room Biomed Workbench development or release surface."""

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.catalog import all_capabilities, capability_to_dict, resolve_entrypoint  # noqa: E402
from biomed_workbench.formats import FormatRegistry  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT, MODULE_INDEX, build_index  # noqa: E402
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
)
from biomed_workbench.services.credentials import ALLOWED_CREDENTIALS  # noqa: E402
from biomed_workbench.version import VERSION  # noqa: E402
from tools.validate_module import validate_module  # noqa: E402
from tools.build_format_contract_report import build as build_format_contract_report  # noqa: E402
from tools.audit_bioinformatics_templates import build as build_bioinformatics_template_report  # noqa: E402

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
                or set(research_report.get("execution_contracts", ()))
                != {"scientific_command", "command_companion_sidecar_input", "command_digest_bound_project_implementation", "command_input_binding", "command_derived_sidecar_output", "command_output_binding", "command_scalar_parameter_template", "command_stream_output_capture", "command_zip_directory_input", "command_workdir_relative_paths", "tested_baseline_compatibility_policy", "bounded_process_result"}
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
                or communication_report.get("registry_digest") != registry.digest
                or communication_report.get("compatibility_rows") != expected_rows
                or communication_report.get("fixture", {}).get("cells") != 160
                or communication_report.get("fixture", {}).get("biological_samples") != 4
                or communication_report.get("fixture", {}).get("conditions") != 2
                or set(communication_report.get("python_backends", {}).get("methods", ()))
                != {"liana-rank-aggregate", "cellphonedb-statistical"}
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
            }
            scientific_summary = public_database_report.get("scientific_summary", {})
            if (
                public_database_report.get("passed") is not True
                or public_database_report.get("registry_digest") != registry.digest
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
                or chroma_report.get("dependency_versions") != {"Pillow": "10.4.0"}
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

        local_update_path = ROOT / "reports" / "local-update-verification.json"
        local_update_implementation = ROOT / "tools" / "prepare_local_update.py"
        try:
            local_update = json.loads(local_update_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append("local plugin update evidence is missing or invalid")
        else:
            if (
                local_update.get("passed") is not True
                or local_update.get("evidence_id") != "codex-local-update-cachebuster-v1"
                or local_update.get("evidence_type") != "codex-plugin-local-update-contract"
                or local_update.get("implementation", {}).get("sha256") != hashlib.sha256(local_update_implementation.read_bytes()).hexdigest()
                or local_update.get("regression", {}).get("passed") is not True
                or not all(local_update.get("verified_behaviors", {}).values())
                or local_update.get("scientific_runtime_capability") is not False
            ):
                errors.append("local plugin update evidence is stale, incomplete, or misclassified as scientific runtime")

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

        reconciliation_path = ROOT / "reports" / "source-reconciliation-summary.json"
        assimilation_path = ROOT / "reports" / "source-assimilation-summary.json"
        design_path = ROOT / "reports" / "rewrite-design-summary.json"
        scope_policy_path = ROOT / "reports" / "source-scope-policy.json"
        source_bindings_path = ROOT / "reports" / "source-capability-bindings.json"
        try:
            reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
            assimilation = json.loads(assimilation_path.read_text(encoding="utf-8"))
            design = json.loads(design_path.read_text(encoding="utf-8"))
            scope_policy = json.loads(scope_policy_path.read_text(encoding="utf-8"))
            source_bindings = json.loads(source_bindings_path.read_text(encoding="utf-8"))
            source_file_count = sum(source["file_count"] for source in assimilation["sources"])
            skill_digest = hashlib.sha256((ROOT / "skills" / "biomed-workbench" / "SKILL.md").read_bytes()).hexdigest()
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            errors.append("source reconciliation evidence is missing or invalid")
        else:
            current = reconciliation.get("current_evidence", {})
            serialized = reconciliation_path.read_text(encoding="utf-8")
            if (
                reconciliation.get("passed") is not True
                or reconciliation.get("file_count") != source_file_count
                or reconciliation.get("file_count") != design.get("learned_file_count")
                or reconciliation.get("reconciled_count", 0) + reconciliation.get("pending_count", 0) != source_file_count
                or sum(reconciliation.get("status_counts", {}).values()) != source_file_count
                or reconciliation.get("action_counts") != design.get("action_counts")
                or reconciliation.get("binding_count") != sum(reconciliation.get("binding_resolution_counts", {}).values())
                or reconciliation.get("bound_module_count", 0) > len(modules)
                or reconciliation.get("bound_project_evidence_count", 0) < 1
                or current.get("module_count") != len(modules)
                or current.get("registry_digest") != registry.digest
                or current.get("skill_sha256") != skill_digest
                or current.get("test_count") != research_report.get("test_count")
                or not re.fullmatch(r"[0-9a-f]{64}", str(reconciliation.get("receipt_root_digest", "")))
                or reconciliation.get("pending_count", 0) <= 0
                or any(marker.lower() in serialized.lower() for marker in ("/Users/", "/private/", '"path"', '"private_path"', "Biomni", "openscience", "claude"))
            ):
                errors.append("source reconciliation is stale, incomplete, path-bearing, or overclaims source-union coverage")
            public_source_reports = scope_policy_path.read_text(encoding="utf-8") + source_bindings_path.read_text(encoding="utf-8")
            if (
                scope_policy.get("row_count") != source_file_count
                or scope_policy.get("changed_count") != 414
                or scope_policy.get("transitions") != {"redesign_schema->retire": 25, "rewrite_capability->retire": 389}
                or scope_policy.get("policy_rules") != ["compute-infrastructure-explicitly-excluded"]
                or source_bindings.get("rule_count") != 5
                or source_bindings.get("added_binding_count") != 3
                or source_bindings.get("matched_receipt_count") != 20
                or source_bindings.get("total_binding_count") != reconciliation.get("binding_count")
                or sum(source_bindings.get("added_by_rule", {}).values()) != 3
                or sum(source_bindings.get("matches_by_rule", {}).values()) != 20
                or reconciliation.get("action_counts", {}).get("retire") != 441
                or any(marker.lower() in public_source_reports.lower() for marker in ("/Users/", "/private/", '"path"', '"private_path"'))
            ):
                errors.append("source scope policy or capability binding evidence is stale, path-bearing, or inconsistent with reconciliation")

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
            if path.is_file() and ".source-audit" not in path.parts and "__pycache__" not in path.parts:
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
    if format_registry is not None:
        print(f"format_profiles={len(format_registry.all())}")
        print(f"format_registry_digest={format_registry.digest}")
    print("credentials=" + ",".join(sorted(ALLOWED_CREDENTIALS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
