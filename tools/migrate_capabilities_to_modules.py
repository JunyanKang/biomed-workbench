#!/usr/bin/env python3
"""Migrate the v0.2 capability catalog to independent scientific modules."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.contract import manifest_to_dict, parse_manifest  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from tools.build_tool_compatibility_matrix import build_compatibility_report  # noqa: E402
from tools.module_migration_definitions import ARTIFACTS, ASSUMPTIONS, CHINESE_INTENTS, COMPLEMENTS, QUESTIONS  # noqa: E402


CATALOG = ROOT / "tools" / "catalog.json"
CASES = ROOT / "tests" / "fixtures" / "offline-capability-cases.json"
BUILTIN_ROOT = ROOT / "biomed_workbench" / "modules" / "builtin"
MIGRATION_REPORT = ROOT / "reports" / "module-registry-migration.json"
COMPATIBILITY_REPORT = ROOT / "reports" / "tool-compatibility-matrix.json"
PUBLIC_SERVICE_IDS = {
    "gene-evidence",
    "literature-evidence",
    "ncbi-fetch",
    "ncbi-info",
    "ncbi-link",
    "ncbi-search",
    "ncbi-search-summary",
    "ncbi-summary",
    "variant-evidence",
}

DOMAIN_GATES = {
    "evidence": "Identifiers, query provenance, database scope, record version, and retrieval limits are reviewed before evidence synthesis.",
    "omics": "Biological denominator, matrix orientation, identifier system, data quality, model assumptions, and multiplicity are reviewed before inference.",
    "molecular_design": "Sequence identity, coordinate convention, model approximations, off-target scope, and orthogonal validation needs are reviewed.",
    "imaging": "Acquisition scale, registration, threshold or tracking assumptions, field replication, and measurement uncertainty are reviewed.",
    "clinical": "Cohort denominator, missingness, censoring or outcome definition, privacy, and non-clinical-use limits are reviewed.",
    "wetlab": "Controls, calibration range, replicate structure, units, transfer assumptions, and assay-specific uncertainty are reviewed.",
    "publication": "Every conclusion is linked to supplied evidence, scope, limitations, figures, and reproducibility information before delivery.",
}
DOMAIN_LIMITS = {
    "evidence": "Database retrieval is time-dependent and must be reconciled with record version, curation status, and independent evidence.",
    "omics": "This bounded analysis does not replace assay-specific normalization, sample-aware models, sensitivity analysis, and biological validation.",
    "molecular_design": "Candidates require reference-aware off-target, thermodynamic, structural, and experimental validation before use.",
    "imaging": "Numeric image summaries do not replace acquisition calibration, blinded sampling, biological replication, and expert review.",
    "clinical": "This research summary is not a diagnostic, treatment, regulatory, privacy-compliance, or clinical management decision.",
    "wetlab": "Calculated plans require assay controls, instrument calibration, replicate design, and laboratory validation.",
    "publication": "A structural audit cannot replace full scientific, editorial, statistical, ethical, or legal expert review.",
}
EVIDENCE_EFFECTS = {
    "evidence": "grounds_external_evidence",
    "omics": "quantifies_molecular_observation",
    "molecular_design": "proposes_testable_candidate",
    "imaging": "quantifies_image_observation",
    "clinical": "quantifies_clinical_research_observation",
    "wetlab": "supports_experimental_execution_or_measurement",
    "publication": "validates_claim_or_delivery_readiness",
}


SERVICE_OUTPUT_KEYS = {
    "gene-evidence": {"query": "string", "match_count": "integer", "gene_records": "array", "linked": "object", "warnings": "array", "provenance": "object"},
    "literature-evidence": {"database": "string", "query": "string", "query_translation": "string", "count": "integer", "returned_ids": "array", "records": "array", "provenance": "object"},
    "ncbi-fetch": {"database": "string", "rettype": "string", "retmode": "string", "content_type": "string", "text": "string"},
    "ncbi-info": {"einforesult": "object"},
    "ncbi-link": {"source_database": "string", "target_database": "string", "source_ids": "array", "links": "array", "link_names": "array"},
    "ncbi-search": {"database": "string", "count": "integer", "ids": "array", "query_translation": "string", "webenv": "string", "query_key": "string"},
    "ncbi-search-summary": {"search": "object", "summary": "object"},
    "ncbi-summary": {"database": "string", "records": "array"},
    "variant-evidence": {"query": "string", "match_count": "integer", "variant_records": "array", "linked": "object", "warnings": "array", "provenance": "object", "limitations": "array"},
}


def _value_schema(value: Any) -> dict[str, object]:
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        return {"type": "array"}
    if isinstance(value, dict):
        return {"type": "object"}
    if value is None:
        return {"nullable": True}
    raise ValueError(f"unsupported observed output type: {type(value).__name__}")


def _output_schema(capability_id: str, cases: dict[str, dict[str, object]]) -> dict[str, object]:
    if capability_id in cases:
        output = cases[capability_id]["output"]
        if not isinstance(output, dict):
            raise ValueError(f"observed output is not an object: {capability_id}")
        properties = {key: _value_schema(value) for key, value in output.items()}
    else:
        properties = {key: {"type": value} for key, value in SERVICE_OUTPUT_KEYS[capability_id].items()}
    return {"type": "object", "properties": properties, "required": sorted(properties), "additionalProperties": False}


def _format(name: str = "inline-json", version: str = "1") -> dict[str, object]:
    return {
        "name": name,
        "versions": [version],
        "representations": ["structured"],
        "compression": ["none"],
        "required_indexes": [],
        "coordinate_systems": [],
        "genome_build_policy": "not_applicable",
        "genome_builds": [],
        "annotation_releases": [],
        "orientations": ["request-object"],
    }


def _module_type(capability_id: str, workflow: str) -> str:
    if capability_id in PUBLIC_SERVICE_IDS:
        return "data_source"
    if capability_id.endswith("audit") or capability_id in {"data-profile", "expression-qc", "single-cell-qc", "reviewer-assessment"}:
        return "validation"
    if capability_id.endswith("plan") or capability_id in {"crispr-design", "primer-design", "figure-specification", "response-matrix"}:
        return "design"
    if workflow == "publication":
        return "delivery"
    return "analysis"


def _dependencies() -> list[dict[str, object]]:
    return [
        {
            "name": "python",
            "ecosystem": "runtime",
            "required": True,
            "tested_versions": ["3.14.3"],
            "allowed_versions": ["==3.14.3"],
            "version_source": "https://www.python.org/downloads/release/python-3143/",
            "verified_at": "2026-07-12",
            "purpose": "Execute the validated module implementation.",
            "conflicts": [],
            "platforms": ["any"],
        }
    ]


def _eutils_tool() -> list[dict[str, object]]:
    return [
        {
            "name": "ncbi-eutils",
            "ecosystem": "service",
            "identity": "eutils.ncbi.nlm.nih.gov/entrez/eutils",
            "required": True,
            "tested_versions": ["contract-2026-03-04"],
            "allowed_versions": ["==contract-2026-03-04"],
            "version_source": "https://www.ncbi.nlm.nih.gov/books/NBK25499/",
            "verified_at": "2026-07-12",
            "version_probe": ["einfo-json-contract"],
            "version_pattern": "(contract-[0-9]{4}-[0-9]{2}-[0-9]{2})",
            "mismatch_policy": "block",
            "version_differences": [
                "ESummary 2.0 uses database-specific document-summary schemas.",
                "EFetch output depends on database, rettype, and retmode.",
            ],
            "platforms": ["any"],
        }
    ]


def _limits(capability_id: str, workflow: str, cases: dict[str, dict[str, object]]) -> list[str]:
    output = cases.get(capability_id, {}).get("output", {})
    limitations = output.get("limitations") if isinstance(output, dict) else None
    if isinstance(limitations, list) and limitations and all(isinstance(item, str) and item.strip() for item in limitations):
        return limitations
    return [DOMAIN_LIMITS[workflow]]


def _manifest(row: dict[str, object], cases: dict[str, dict[str, object]]) -> dict[str, object]:
    capability_id = str(row["id"])
    workflow = str(row["workflow"])
    input_name, input_type, output_name, output_type = ARTIFACTS[capability_id]
    service = capability_id in PUBLIC_SERVICE_IDS
    input_format = _format()
    output_format = _format("normalized-json" if service else "inline-json")
    output_format["orientations"] = ["module-output"]
    tools = _eutils_tool() if service else []
    compatibility_id = "eutils-contract-2026-03-04-python-3.14.3" if service else "python-3.14.3-inline-json-1"
    return {
        "schema_version": 1,
        "id": capability_id,
        "version": "1.0.0",
        "title": row["title"],
        "description": row["description"],
        "module_type": _module_type(capability_id, workflow),
        "domains": [workflow],
        "intents": [capability_id.replace("-", " "), str(row["title"]), CHINESE_INTENTS[capability_id]],
        "questions": [QUESTIONS[capability_id]],
        "entrypoint": row["entrypoint"],
        "execution": {"kind": row["kind"], "timeout_seconds": 60 if service else 30, "max_output_bytes": 10000000},
        "maturity": "validated",
        "input_artifacts": [
            {
                "name": input_name,
                "artifact_type": input_type,
                "formats": [input_format],
                "processing_levels": ["declared"],
                "required_metadata": [],
            }
        ],
        "output_artifacts": [
            {
                "name": output_name,
                "artifact_type": output_type,
                "formats": [output_format],
                "processing_levels": ["derived"],
                "required_metadata": ["module_version", "compatibility_row_id"],
            }
        ],
        "preconditions": [f"A schema-valid {input_type.replace('_', ' ')} is available for the declared scientific scope."],
        "assumptions": [ASSUMPTIONS[capability_id]],
        "quality_gates": [
            {
                "id": f"{capability_id}-validity",
                "severity": "major",
                "description": DOMAIN_GATES[workflow],
                "blocks_interpretation": True,
            }
        ],
        "limitations": _limits(capability_id, workflow, cases),
        "evidence_effects": [EVIDENCE_EFFECTS[workflow]],
        "alternatives": [],
        "complements": COMPLEMENTS.get(capability_id, []),
        "tool_requirements": tools,
        "dependencies": _dependencies(),
        "compatibility_matrix": [
            {
                "id": compatibility_id,
                "module_version": "1.0.0",
                "tool_versions": {"ncbi-eutils": ["contract-2026-03-04"]} if service else {},
                "dependency_versions": {"python": ["3.14.3"]},
                "input_formats": {input_name: ["inline-json@1"]},
                "output_formats": {output_name: [f"{'normalized-json' if service else 'inline-json'}@1"]},
                "platforms": ["any"],
            }
        ],
        "access": row["access"],
        "mutability": row["mutability"],
        "credentials": ["NCBI_API_KEY"] if service else [],
        "input_schema": row["input_schema"],
        "output_schema": _output_schema(capability_id, cases),
        "kernel_compatibility": [">=0.2.0,<0.3.0"],
        "provenance": {
            "license": "Apache-2.0",
            "concept_sources": ["Project-owned clean-room rewrite documented by the aggregate source-assimilation report."],
        },
    }


def migrate(*, replace: bool = False) -> dict[str, object]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    rows = catalog["entries"]
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    ids = {str(row["id"]) for row in rows}
    mapping_ids = set(QUESTIONS) & set(CHINESE_INTENTS) & set(ARTIFACTS) & set(ASSUMPTIONS)
    if len(rows) != 48 or ids != mapping_ids or set(cases) != ids - PUBLIC_SERVICE_IDS:
        raise ValueError("migration inputs do not account for exactly 48 capabilities")
    temporary = BUILTIN_ROOT.with_name("builtin.tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        for row in sorted(rows, key=lambda item: item["id"]):
            payload = _manifest(row, cases)
            manifest = parse_manifest(payload)
            directory = temporary / manifest.id
            directory.mkdir()
            (directory / "module.json").write_text(json.dumps(manifest_to_dict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if BUILTIN_ROOT.exists():
            if not replace:
                raise ValueError("built-in module root already exists; use --replace after review")
            shutil.rmtree(BUILTIN_ROOT)
        temporary.rename(BUILTIN_ROOT)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    modules = {module.id: module for module in registry.all()}
    legacy = {row["id"]: row for row in rows}
    report = {
        "schema_version": 1,
        "legacy_capability_count": len(legacy),
        "module_count": len(modules),
        "module_ids": sorted(modules),
        "entrypoint_parity_count": sum(modules[module_id].entrypoint == row["entrypoint"] for module_id, row in legacy.items()),
        "input_schema_parity_count": sum(modules[module_id].input_schema == row["input_schema"] for module_id, row in legacy.items()),
        "scientific_contract_complete_count": sum(
            bool(module.questions and module.preconditions and module.assumptions and module.quality_gates and module.limitations and module.evidence_effects)
            for module in modules.values()
        ),
        "compatibility_contract_complete_count": sum(bool(module.dependencies and module.compatibility_matrix) for module in modules.values()),
        "registry_digest": registry.digest,
        "runtime_external_paths_present": False,
    }
    MIGRATION_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    compatibility = build_compatibility_report(registry)
    COMPATIBILITY_REPORT.write_text(json.dumps(compatibility, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    report = migrate(replace=args.replace)
    print(json.dumps({"created": report["module_count"], "validated": report["compatibility_contract_complete_count"], "unmapped": 0, "duplicate": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
