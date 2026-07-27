#!/usr/bin/env python3
"""Generate reviewed RCSB search, polymer-entity, and ligand modules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from tools.scaffold_public_database_modules import _manifest  # noqa: E402


def _specs() -> dict[str, dict[str, object]]:
    common = {
        "assumption": "The requested identifiers and filters describe structures relevant to the intended construct, state, and biological question.",
        "complements": ["structure-evidence", "chemical-evidence", "literature-evidence"],
    }
    return {
        "structure-search": {
            **common,
            "tools": ["rcsb-search"],
            "title": "Search RCSB structures with scientific filters",
            "description": "Search experimental or computed RCSB entries by text, organism, taxonomy, UniProt, method, resolution, or ligand with count-verified pagination.",
            "entrypoint": "biomed_workbench.capabilities.evidence:structure_search",
            "intents": ["search RCSB structures", "find PDB entries by organism method resolution or ligand", "按物种方法分辨率或配体检索PDB结构"],
            "questions": ["Which RCSB entries satisfy the declared structural criteria, and is the returned set complete?"],
            "input_properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 1000}, "organism": {"type": "string", "minLength": 1, "maxLength": 300},
                "taxonomy_id": {"type": "integer", "minimum": 1}, "uniprot_accession": {"type": "string", "minLength": 1, "maxLength": 100},
                "experimental_method": {"type": "string", "minLength": 1, "maxLength": 100}, "max_resolution": {"type": "number", "minimum": 0.000001},
                "ligand_comp_id": {"type": "string", "minLength": 1, "maxLength": 20}, "include_computed_models": {"type": "boolean"},
                "max_records": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "input_required": [],
            "output_properties": {"query": {"type": "object"}, "total_count": {"type": "integer"}, "returned_count": {"type": "integer"}, "records_truncated": {"type": "boolean"}, "records": {"type": "array"}, "provenance": {"type": "object"}, "limitations": {"type": "array"}},
            "output_required": ["query", "total_count", "returned_count", "records_truncated", "records", "provenance", "limitations"],
            "quality": "Every result must preserve a valid unique PDB identifier; page offsets, total_count, returned count, model scope, and truncation must reconcile.",
            "limitations": ["Search relevance is not validation of assembly, construct, model quality, or biological relevance."],
            "effect": "grounds-structure-discovery-evidence",
        },
        "structure-polymer-entities": {
            **common,
            "tools": ["rcsb"],
            "title": "Retrieve RCSB polymer entity evidence",
            "description": "Retrieve bounded polymer entities, source organisms, UniProt links, sequence lengths, mutations, and optional canonical sequences for one PDB entry.",
            "entrypoint": "biomed_workbench.capabilities.evidence:structure_polymer_entities",
            "intents": ["retrieve PDB polymer entities", "inspect structure chains sequences organisms and UniProt", "检索PDB聚合物实体序列物种和UniProt"],
            "questions": ["Which polymer entities and sequence identities are represented in the deposited entry?"],
            "input_properties": {"pdb_id": {"type": "string", "pattern": "^[0-9][A-Za-z0-9]{3}$"}, "entity_ids": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 40}, "minItems": 1, "maxItems": 25, "uniqueItems": True}, "include_sequences": {"type": "boolean"}},
            "input_required": ["pdb_id"],
            "output_properties": {"pdb_id": {"type": "string"}, "requested_entity_ids": {"type": "array"}, "entry_polymer_entity_count": {"type": "integer", "nullable": True}, "returned_count": {"type": "integer"}, "records_truncated": {"type": "boolean"}, "not_found": {"type": "array"}, "entities": {"type": "array"}, "provenance": {"type": "object"}, "limitations": {"type": "array"}},
            "output_required": ["pdb_id", "requested_entity_ids", "entry_polymer_entity_count", "returned_count", "records_truncated", "not_found", "entities", "provenance", "limitations"],
            "quality": "Entity identifiers, entry membership, missing entities, sequence inclusion, source organism, UniProt links, and truncation must remain explicit.",
            "limitations": ["Deposited entity metadata does not establish construct completeness, assembly state, or experimental relevance."],
            "effect": "grounds-polymer-entity-identity",
        },
        "structure-ligands": {
            **common,
            "tools": ["rcsb"],
            "title": "Retrieve RCSB bound-ligand evidence",
            "description": "Walk one PDB entry through nonpolymer entities to chemical components while retaining missing records, charge, formula, InChIKey, and stereochemical SMILES.",
            "entrypoint": "biomed_workbench.capabilities.evidence:structure_ligands",
            "intents": ["retrieve PDB bound ligands", "inspect structure chemical components and ligand identity", "检索PDB结合配体和化学组分身份"],
            "questions": ["Which nonpolymer components are deposited in the entry, and is their chemical identity sufficiently explicit?"],
            "input_properties": {"pdb_id": {"type": "string", "pattern": "^[0-9][A-Za-z0-9]{3}$"}, "max_ligands": {"type": "integer", "minimum": 1, "maximum": 25}},
            "input_required": ["pdb_id"],
            "output_properties": {"pdb_id": {"type": "string"}, "entry_nonpolymer_entity_count": {"type": "integer"}, "returned_count": {"type": "integer"}, "records_truncated": {"type": "boolean"}, "not_found_entity_ids": {"type": "array"}, "not_found_component_ids": {"type": "array"}, "ligands": {"type": "array"}, "provenance": {"type": "object"}, "limitations": {"type": "array"}},
            "output_required": ["pdb_id", "entry_nonpolymer_entity_count", "returned_count", "records_truncated", "not_found_entity_ids", "not_found_component_ids", "ligands", "provenance", "limitations"],
            "quality": "Entry nonpolymer counts, entity-to-component links, missing records, charge, formula, InChIKey, SMILES, and truncation must remain explicit.",
            "limitations": ["A deposited component does not establish physiological binding, affinity, occupancy, or a design-ready pose."],
            "effect": "grounds-bound-ligand-identity",
        },
        "alphafold-structure-evidence": {
            "verified_at": "2026-07-14",
            "assumption": "Each supplied UniProt accession identifies the intended protein or isoform and predicted models are interpreted within their sequence coverage and confidence limits.",
            "complements": ["structure-search", "structure-evidence", "structure-polymer-entities", "literature-evidence"],
            "tools": ["alphafold"],
            "title": "Retrieve AlphaFold DB structure and confidence evidence",
            "description": "Retrieve bounded AlphaFold DB prediction metadata for one to 40 UniProt accessions while preserving no-model status, model provider and tool, version history, sequence coverage, global and binned pLDDT, and approved coordinate, PAE, MSA, and annotation resource URLs.",
            "entrypoint": "biomed_workbench.capabilities.evidence:alphafold_structure_evidence",
            "intents": ["retrieve AlphaFold DB prediction", "check AlphaFold coverage and pLDDT for UniProt proteins", "检索AlphaFold结构覆盖模型版本和置信度"],
            "questions": ["Which requested UniProt proteins have AlphaFold DB models, and what model, version, sequence-coverage, and confidence limits govern their use?"],
            "input_properties": {
                "uniprot_accessions": {"type": "array", "items": {"type": "string", "minLength": 6, "maxLength": 14}, "minItems": 1, "maxItems": 40, "uniqueItems": True},
                "include_sequence": {"type": "boolean"},
            },
            "input_required": ["uniprot_accessions"],
            "output_properties": {"query": {"type": "object"}, "requested_count": {"type": "integer"}, "covered_count": {"type": "integer"}, "not_covered_count": {"type": "integer"}, "records": {"type": "array"}, "provenance": {"type": "object"}, "limitations": {"type": "array"}},
            "output_required": ["query", "requested_count", "covered_count", "not_covered_count", "records", "provenance", "limitations"],
            "quality": "Every requested accession must reconcile to exactly one explicit coverage record; returned models must preserve accession identity, provider, tool, version, sequence coverage, 0..100 global pLDDT, 0..1 confidence fractions, approved resource hosts, and request provenance.",
            "limitations": ["Predicted coordinates and pLDDT do not validate experimental state, assembly, dynamics, interfaces, ligands, or function; per-residue confidence and PAE require separate inspection."],
            "effect": "grounds-predicted-structure-coverage-and-confidence",
        },
    }


def _case(module_id: str) -> dict[str, object]:
    entry_url = "https://data.rcsb.org/rest/v1/core/entry/4HHB"
    entry = {"rcsb_entry_container_identifiers": {"polymer_entity_ids": ["1"], "non_polymer_entity_ids": ["1"]}}
    if module_id == "structure-search":
        request = {"query": {"type": "terminal", "service": "full_text", "parameters": {"value": "hemoglobin"}}, "request_options": {"paginate": {"rows": 1, "start": 0}, "results_content_type": ["experimental"]}, "return_type": "entry"}
        return {"name": "search-one-entry", "input": {"text": "hemoglobin", "max_records": 1}, "expected_subset": {"total_count": 1, "records": [{"pdb_id": "4HHB", "score": 1.0}]}, "http_fixtures": [{"method": "POST", "url": "https://search.rcsb.org/rcsbsearch/v2/query", "request_json": request, "status": 200, "headers": {"Content-Type": "application/json"}, "json": {"total_count": 1, "result_set": [{"identifier": "4HHB", "score": 1.0}]}}]}
    if module_id == "structure-polymer-entities":
        entity = {"rcsb_id": "4HHB_1", "rcsb_polymer_entity": {"pdbx_description": "Hemoglobin subunit alpha"}, "rcsb_polymer_entity_container_identifiers": {"entry_id": "4HHB", "entity_id": "1", "uniprot_ids": ["P69905"]}, "entity_poly": {"rcsb_entity_polymer_type": "Protein", "rcsb_sample_sequence_length": 141}}
        return {"name": "retrieve-one-polymer-entity", "input": {"pdb_id": "4HHB"}, "expected_subset": {"returned_count": 1, "not_found": []}, "http_fixtures": [{"url": entry_url, "status": 200, "headers": {}, "json": entry}, {"url": "https://data.rcsb.org/rest/v1/core/polymer_entity/4HHB/1", "status": 200, "headers": {}, "json": entity}]}
    if module_id == "alphafold-structure-evidence":
        model = {"modelEntityId": "AF-P04637-F1", "entryId": "AF-P04637-F1", "providerId": "GDM", "toolUsed": "AlphaFold Monomer v2.0 pipeline", "uniprotAccession": "P04637", "uniprotId": "P53_HUMAN", "sequence": "MEEPQ", "uniprotStart": 1, "uniprotEnd": 5, "globalMetricValue": 72.5, "fractionPlddtVeryLow": 0.1, "fractionPlddtLow": 0.2, "fractionPlddtConfident": 0.3, "fractionPlddtVeryHigh": 0.4, "latestVersion": 6, "allVersions": [1, 2, 3, 4, 5, 6], "cifUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-model_v6.cif", "paeDocUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-predicted_aligned_error_v6.json"}
        return {"name": "retrieve-one-alphafold-model", "input": {"uniprot_accessions": ["P04637"], "include_sequence": True}, "expected_subset": {"requested_count": 1, "covered_count": 1, "not_covered_count": 0}, "http_fixtures": [{"url": "https://alphafold.ebi.ac.uk/api/prediction/P04637", "status": 200, "headers": {}, "json": [model]}]}
    entity = {"rcsb_nonpolymer_entity_container_identifiers": {"entity_id": "1", "nonpolymer_comp_id": "HEM"}, "rcsb_nonpolymer_entity": {"pdbx_description": "Heme"}}
    component = {"chem_comp": {"id": "HEM", "name": "Heme", "formula": "C34 H32 Fe N4 O4"}, "rcsb_chem_comp_descriptor": {"InChIKey": "KABFMIBPWCXCRK-RGGAHWMASA-L", "SMILES_stereo": "[Fe]"}}
    return {"name": "retrieve-one-bound-ligand", "input": {"pdb_id": "4HHB"}, "expected_subset": {"returned_count": 1, "not_found_entity_ids": []}, "http_fixtures": [{"url": entry_url, "status": 200, "headers": {}, "json": entry}, {"url": "https://data.rcsb.org/rest/v1/core/nonpolymer_entity/4HHB/1", "status": 200, "headers": {}, "json": entity}, {"url": "https://data.rcsb.org/rest/v1/core/chemcomp/HEM", "status": 200, "headers": {}, "json": component}]}


def generate(check: bool = False) -> list[str]:
    dependency = json.loads((BUILTIN_ROOT / "gene-evidence" / "module.json").read_text())["dependencies"][0]
    changed = []
    for module_id, spec in _specs().items():
        manifest = _manifest(module_id, spec, dependency)
        parse_manifest(manifest)
        files = {"module.json": manifest, "tests/cases.json": {"schema_version": 1, "cases": [_case(module_id)]}}
        for relative, payload in files.items():
            path = BUILTIN_ROOT / module_id / relative
            text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
            if not path.exists() or path.read_text() != text:
                if module_id not in changed:
                    changed.append(module_id)
                if not check:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = generate(args.check)
    print(json.dumps({"changed_modules": changed, "count": len(changed)}, sort_keys=True))
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
