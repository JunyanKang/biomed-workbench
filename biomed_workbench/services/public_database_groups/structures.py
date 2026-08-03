"""Internal structures public database operations."""

from __future__ import annotations

from ..public_databases import (
    ALPHAFOLD_CONTRACT_VERSION,
    Any,
    IUPRED2A_CONTRACT_VERSION,
    Mapping,
    PublicDatabaseError,
    PublicJSONClient,
    RCSB_CONTRACT_VERSION,
    RCSB_SEARCH_CONTRACT_VERSION,
    _PDB_RE,
    _RCSB_EXPERIMENTAL_METHODS,
    _UNIPROT_ACCESSION_RE,
    _clean_text,
    _require_pdb_id,
    math,
    quote,
    re,
    urlsplit,
)

__all__ = ['_alphafold_model_record', '_iupred2a_disordered_spans', '_rcsb_text_node', '_require_uniprot_accession', 'alphafold_structure_records', 'iupred2a_disorder_prediction', 'rcsb_ligand_records', 'rcsb_polymer_entity_records', 'rcsb_structure_records', 'rcsb_structure_search']

def rcsb_structure_records(pdb_ids: list[str], *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve entry-level RCSB PDB metadata without inferring biological validity."""
    if not 1 <= len(pdb_ids) <= 25:
        raise ValueError("one to 25 PDB identifiers are required")
    normalized = [_require_pdb_id(value) for value in pdb_ids]
    if len(normalized) != len(set(normalized)):
        raise ValueError("PDB identifiers must be unique")
    client = client or PublicJSONClient()
    records = []
    for pdb_id in normalized:
        payload = client.get("https://data.rcsb.org", f"/rest/v1/core/entry/{pdb_id}")
        returned_id = str(payload.get("rcsb_id", "")).upper()
        if returned_id != pdb_id:
            raise PublicDatabaseError("RCSB response did not preserve the requested PDB identifier")
        records.append(
            {
                "pdb_id": pdb_id,
                "title": _clean_text(payload.get("struct", {}).get("title")),
                "experimental_methods": [record.get("method") for record in payload.get("exptl", []) if isinstance(record, dict)],
                "resolution_combined": payload.get("rcsb_entry_info", {}).get("resolution_combined", []),
                "release": payload.get("rcsb_accession_info", {}),
                "primary_citation": payload.get("rcsb_primary_citation", {}),
                "entity_ids": payload.get("rcsb_entry_container_identifiers", {}),
                "deposition": payload.get("pdbx_database_status", {}),
            }
        )
    return {
        "query": {"pdb_ids": normalized},
        "structures": records,
        "returned_count": len(records),
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "RCSB PDB Data API",
            "contract": RCSB_CONTRACT_VERSION,
            "data_model": "PDBx/mmCIF-derived JSON",
        },
        "limitations": [
            "A deposited structure requires review of construct, assembly, model quality, ligands, experimental method, resolution, and biological context.",
            "Entry-level metadata does not establish interaction affinity, conformational relevance, or suitability for molecular design.",
        ],
    }


def _rcsb_text_node(attribute: str, operator: str, value: Any) -> dict[str, Any]:
    return {"type": "terminal", "service": "text", "parameters": {"attribute": attribute, "operator": operator, "value": value}}


def rcsb_structure_search(
    text: str | None = None,
    organism: str | None = None,
    taxonomy_id: int | None = None,
    uniprot_accession: str | None = None,
    experimental_method: str | None = None,
    max_resolution: float | None = None,
    ligand_comp_id: str | None = None,
    include_computed_models: bool = False,
    max_records: int = 100,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Run a bounded, count-verified RCSB attribute search."""
    if not 1 <= max_records <= 1_000:
        raise ValueError("max_records must be 1..1000")
    if taxonomy_id is not None and taxonomy_id <= 0:
        raise ValueError("taxonomy_id must be positive")
    if max_resolution is not None and max_resolution <= 0:
        raise ValueError("max_resolution must be positive")
    nodes = []
    if text:
        nodes.append({"type": "terminal", "service": "full_text", "parameters": {"value": _clean_text(text, limit=1000)}})
    if organism:
        nodes.append(_rcsb_text_node("rcsb_entity_source_organism.taxonomy_lineage.name", "exact_match", _clean_text(organism, limit=300)))
    if taxonomy_id is not None:
        nodes.append(_rcsb_text_node("rcsb_entity_source_organism.ncbi_taxonomy_id", "equals", taxonomy_id))
    if uniprot_accession:
        nodes.extend(
            [
                _rcsb_text_node("rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession", "exact_match", _clean_text(uniprot_accession, limit=100)),
                _rcsb_text_node("rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_name", "exact_match", "UniProt"),
            ]
        )
    if experimental_method:
        method = experimental_method.strip().upper()
        if method not in _RCSB_EXPERIMENTAL_METHODS:
            raise ValueError("experimental_method is not in the supported RCSB vocabulary")
        nodes.append(_rcsb_text_node("exptl.method", "exact_match", method))
    if max_resolution is not None:
        nodes.append(_rcsb_text_node("rcsb_entry_info.resolution_combined", "less_or_equal", float(max_resolution)))
    if ligand_comp_id:
        nodes.append(_rcsb_text_node("rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id", "exact_match", ligand_comp_id.strip().upper()))
    if not nodes:
        raise ValueError("at least one RCSB search criterion is required")
    query = nodes[0] if len(nodes) == 1 else {"type": "group", "logical_operator": "and", "nodes": nodes}
    client = client or PublicJSONClient()
    records = []
    requests = []
    total_count: int | None = None
    start = 0
    while len(records) < max_records:
        rows = min(100, max_records - len(records))
        request_payload = {
            "query": query,
            "return_type": "entry",
            "request_options": {
                "paginate": {"start": start, "rows": rows},
                "results_content_type": ["experimental", "computational"] if include_computed_models else ["experimental"],
            },
        }
        response, metadata = client.post_with_metadata("https://search.rcsb.org", "/rcsbsearch/v2/query", request_payload)
        if metadata["status_code"] == 204:
            if start != 0:
                raise PublicDatabaseError("RCSB search returned HTTP 204 after pagination began")
            total_count = 0
            requests.append({"start": start, "rows": rows, "results_in_page": 0, "request": metadata})
            break
        try:
            page_total = int(response["total_count"])
        except (KeyError, TypeError, ValueError):
            raise PublicDatabaseError("RCSB search response lacks a valid total_count") from None
        if total_count is None:
            total_count = page_total
        elif page_total != total_count:
            raise PublicDatabaseError("RCSB search total_count changed during pagination")
        page = response.get("result_set", [])
        if not isinstance(page, list):
            raise PublicDatabaseError("RCSB search result_set schema is not recognized")
        requests.append({"start": start, "rows": rows, "results_in_page": len(page), "request": metadata})
        for item in page:
            if not isinstance(item, Mapping) or not _PDB_RE.fullmatch(str(item.get("identifier", ""))):
                raise PublicDatabaseError("RCSB search returned an invalid entry identifier")
            records.append({"pdb_id": str(item["identifier"]).upper(), "score": item.get("score")})
        start += len(page)
        if len(records) >= min(total_count, max_records):
            break
        if not page:
            raise PublicDatabaseError("RCSB search returned an empty page before total_count was reached")
    assert total_count is not None
    duplicate_ids = sorted({item["pdb_id"] for item in records if sum(row["pdb_id"] == item["pdb_id"] for row in records) > 1})
    if duplicate_ids:
        raise PublicDatabaseError("RCSB search returned duplicate entry identifiers")
    truncated = total_count > len(records)
    if not truncated and len(records) != total_count:
        raise PublicDatabaseError("RCSB search pagination does not reconcile with total_count")
    return {
        "query": {
            "text": text, "organism": organism, "taxonomy_id": taxonomy_id, "uniprot_accession": uniprot_accession,
            "experimental_method": experimental_method, "max_resolution": max_resolution, "ligand_comp_id": ligand_comp_id,
            "include_computed_models": include_computed_models, "max_records": max_records,
        },
        "total_count": total_count,
        "returned_count": len(records),
        "records_truncated": truncated,
        "records": records,
        "provenance": {"service": "RCSB PDB Search API", "contract": RCSB_SEARCH_CONTRACT_VERSION, "requests": requests},
        "limitations": [
            "Search relevance and metadata are discovery signals, not validation of biological assembly or model quality.",
            "A truncated result set cannot support exhaustive structure availability claims.",
        ],
    }


def rcsb_polymer_entity_records(
    pdb_id: str,
    entity_ids: list[str] | None = None,
    include_sequences: bool = False,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve polymer entity metadata with explicit truncation and not-found state."""
    pdb_id = _require_pdb_id(pdb_id)
    if not isinstance(include_sequences, bool):
        raise ValueError("include_sequences must be boolean")
    client = client or PublicJSONClient()
    if entity_ids is None:
        entry = client.get("https://data.rcsb.org", f"/rest/v1/core/entry/{pdb_id}")
        all_ids = (entry.get("rcsb_entry_container_identifiers") or {}).get("polymer_entity_ids") or []
    else:
        if not 1 <= len(entity_ids) <= 25 or any(not str(value).strip() for value in entity_ids):
            raise ValueError("entity_ids must contain one to 25 nonempty identifiers")
        all_ids = list(dict.fromkeys(str(value).strip() for value in entity_ids))
    selected = all_ids[:25]
    records = []
    not_found = []
    for entity_id in selected:
        try:
            raw = client.get("https://data.rcsb.org", f"/rest/v1/core/polymer_entity/{pdb_id}/{quote(str(entity_id), safe='')}")
        except PublicDatabaseError as exc:
            if "HTTP 404" not in str(exc):
                raise
            not_found.append(str(entity_id))
            continue
        entity = raw.get("rcsb_polymer_entity", {}) or {}
        identifiers = raw.get("rcsb_polymer_entity_container_identifiers", {}) or {}
        polymer = raw.get("entity_poly", {}) or {}
        record = {
            "rcsb_id": raw.get("rcsb_id"), "entry_id": identifiers.get("entry_id"), "entity_id": identifiers.get("entity_id"),
            "description": entity.get("pdbx_description"), "polymer_type": polymer.get("rcsb_entity_polymer_type"),
            "sequence_length": polymer.get("rcsb_sample_sequence_length"), "mutation_count": polymer.get("rcsb_mutation_count"),
            "uniprot_ids": identifiers.get("uniprot_ids") or [], "source_organisms": raw.get("rcsb_entity_source_organism", []) or [],
        }
        if include_sequences:
            record["sequence"] = polymer.get("pdbx_seq_one_letter_code_can")
        records.append(record)
    return {
        "pdb_id": pdb_id, "requested_entity_ids": selected, "entry_polymer_entity_count": len(all_ids) if entity_ids is None else None,
        "returned_count": len(records), "records_truncated": len(all_ids) > len(selected), "not_found": not_found, "entities": records,
        "provenance": {"service": "RCSB PDB Data API", "contract": RCSB_CONTRACT_VERSION},
        "limitations": ["Entity metadata and canonical sequence do not establish construct completeness, assembly state, or experimental relevance."],
    }


def rcsb_ligand_records(
    pdb_id: str,
    max_ligands: int = 25,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Walk entry, nonpolymer entities, and chemical components for bound ligands."""
    pdb_id = _require_pdb_id(pdb_id)
    if not 1 <= max_ligands <= 25:
        raise ValueError("max_ligands must be 1..25")
    client = client or PublicJSONClient()
    entry = client.get("https://data.rcsb.org", f"/rest/v1/core/entry/{pdb_id}")
    all_entity_ids = (entry.get("rcsb_entry_container_identifiers") or {}).get("non_polymer_entity_ids") or []
    selected = all_entity_ids[:max_ligands]
    entities = []
    not_found_entities = []
    for entity_id in selected:
        try:
            raw = client.get("https://data.rcsb.org", f"/rest/v1/core/nonpolymer_entity/{pdb_id}/{quote(str(entity_id), safe='')}")
        except PublicDatabaseError as exc:
            if "HTTP 404" not in str(exc):
                raise
            not_found_entities.append(str(entity_id))
            continue
        identifiers = raw.get("rcsb_nonpolymer_entity_container_identifiers", {}) or {}
        entity = raw.get("rcsb_nonpolymer_entity", {}) or {}
        entities.append(
            {
                "entity_id": identifiers.get("entity_id") or str(entity_id),
                "comp_id": identifiers.get("nonpolymer_comp_id"),
                "description": entity.get("pdbx_description"),
                "copy_count": entity.get("pdbx_number_of_molecules"),
                "auth_asym_ids": identifiers.get("auth_asym_ids") or [],
            }
        )
    component_records = {}
    missing_components = []
    for comp_id in sorted({str(item["comp_id"]).upper() for item in entities if item.get("comp_id")}):
        try:
            raw = client.get("https://data.rcsb.org", f"/rest/v1/core/chemcomp/{quote(comp_id, safe='')}")
        except PublicDatabaseError as exc:
            if "HTTP 404" not in str(exc):
                raise
            missing_components.append(comp_id)
            continue
        component = raw.get("chem_comp", {}) or {}
        descriptors = raw.get("rcsb_chem_comp_descriptor", {}) or {}
        component_records[comp_id] = {
            "comp_id": component.get("id") or comp_id,
            "name": component.get("name"),
            "formula": component.get("formula"),
            "formula_weight": component.get("formula_weight"),
            "formal_charge": component.get("pdbx_formal_charge"),
            "type": component.get("type"),
            "inchikey": descriptors.get("InChIKey"),
            "smiles": descriptors.get("SMILES_stereo") or descriptors.get("SMILES"),
        }
    ligands = [{**entity, "chemical_component": component_records.get(str(entity.get("comp_id", "")).upper())} for entity in entities]
    return {
        "pdb_id": pdb_id,
        "entry_nonpolymer_entity_count": len(all_entity_ids),
        "returned_count": len(ligands),
        "records_truncated": len(all_entity_ids) > len(selected),
        "not_found_entity_ids": not_found_entities,
        "not_found_component_ids": missing_components,
        "ligands": ligands,
        "provenance": {"service": "RCSB PDB Data API", "contract": RCSB_CONTRACT_VERSION},
        "limitations": [
            "A deposited bound component does not establish physiological binding, affinity, occupancy, or a design-ready pose.",
            "Chemical-component identity must be reconciled with protonation, charge, stereochemistry, covalent state, and experimental density.",
        ],
    }


_ALPHAFOLD_URL_FIELDS = {
    "cif": "cifUrl",
    "bcif": "bcifUrl",
    "pdb": "pdbUrl",
    "pae_image": "paeImageUrl",
    "pae_json": "paeDocUrl",
    "plddt_json": "plddtDocUrl",
    "msa": "msaUrl",
    "alphamissense_csv": "amAnnotationsUrl",
}


def _require_uniprot_accession(value: str) -> str:
    accession = value.strip().upper()
    if not _UNIPROT_ACCESSION_RE.fullmatch(accession):
        raise ValueError("UniProt accession must be a valid 6- or 10-character accession with an optional isoform suffix")
    return accession


def _alphafold_model_record(raw: Mapping[str, Any], *, include_sequence: bool) -> dict[str, Any]:
    accession = _require_uniprot_accession(str(raw.get("uniprotAccession", "")))
    global_plddt = raw.get("globalMetricValue")
    if global_plddt is not None and (not isinstance(global_plddt, (int, float)) or not 0 <= float(global_plddt) <= 100):
        raise PublicDatabaseError("AlphaFold globalMetricValue is outside the declared pLDDT range")
    fractions = {
        "very_low": raw.get("fractionPlddtVeryLow"),
        "low": raw.get("fractionPlddtLow"),
        "confident": raw.get("fractionPlddtConfident"),
        "very_high": raw.get("fractionPlddtVeryHigh"),
    }
    observed_fractions = [float(value) for value in fractions.values() if value is not None]
    if any(value < 0 or value > 1 for value in observed_fractions):
        raise PublicDatabaseError("AlphaFold pLDDT fractions are outside 0..1")
    if len(observed_fractions) == 4 and abs(sum(observed_fractions) - 1.0) > 0.02:
        raise PublicDatabaseError("AlphaFold pLDDT fractions do not reconcile to one")
    urls = {}
    for name, field in _ALPHAFOLD_URL_FIELDS.items():
        value = raw.get(field)
        if value is None:
            continue
        parsed = urlsplit(str(value))
        if parsed.scheme != "https" or parsed.hostname != "alphafold.ebi.ac.uk":
            raise PublicDatabaseError("AlphaFold resource URL is outside the approved HTTPS host")
        urls[name] = str(value)
    sequence = str(raw.get("sequence") or "").replace("\n", "").replace(" ", "")
    if sequence and re.fullmatch(r"[A-Z]+", sequence) is None:
        raise PublicDatabaseError("AlphaFold sequence is not an uppercase protein sequence")
    start = raw.get("uniprotStart")
    end = raw.get("uniprotEnd")
    if start is not None and end is not None and int(end) < int(start):
        raise PublicDatabaseError("AlphaFold UniProt coordinate range is inverted")
    record = {
        "model_entity_id": raw.get("modelEntityId"),
        "entry_id": raw.get("entryId"),
        "provider_id": raw.get("providerId"),
        "tool_used": raw.get("toolUsed"),
        "uniprot_accession": accession,
        "uniprot_id": raw.get("uniprotId"),
        "uniprot_description": _clean_text(raw.get("uniprotDescription")),
        "gene": raw.get("gene"),
        "organism_scientific_name": raw.get("organismScientificName"),
        "tax_id": raw.get("taxId"),
        "is_uniprot_reviewed": raw.get("isUniProtReviewed"),
        "is_reference_proteome": raw.get("isReferenceProteome"),
        "is_complex": raw.get("isComplex"),
        "sequence_length": len(sequence) if sequence else None,
        "uniprot_start": start,
        "uniprot_end": end,
        "global_plddt": float(global_plddt) if global_plddt is not None else None,
        "fraction_plddt": fractions,
        "fraction_plddt_sum": sum(observed_fractions) if len(observed_fractions) == 4 else None,
        "latest_version": raw.get("latestVersion"),
        "all_versions": raw.get("allVersions") or [],
        "model_created_date": raw.get("modelCreatedDate"),
        "urls": urls,
    }
    if include_sequence:
        record["sequence"] = sequence or None
    return record


def alphafold_structure_records(
    uniprot_accessions: list[str],
    include_sequence: bool = False,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve AlphaFold DB model metadata with explicit coverage accounting."""
    if not 1 <= len(uniprot_accessions) <= 40:
        raise ValueError("one to 40 UniProt accessions are required")
    if not isinstance(include_sequence, bool):
        raise ValueError("include_sequence must be boolean")
    normalized = [_require_uniprot_accession(value) for value in uniprot_accessions]
    if len(normalized) != len(set(normalized)):
        raise ValueError("UniProt accessions must be unique")
    client = client or PublicJSONClient()
    records = []
    requests = []
    for requested in normalized:
        payload, metadata = client.get_array_with_metadata(
            "https://alphafold.ebi.ac.uk",
            f"/api/prediction/{quote(requested, safe='')}",
            not_found_as_empty=True,
        )
        requests.append(metadata)
        models = []
        for raw in payload:
            if not isinstance(raw, Mapping):
                raise PublicDatabaseError("AlphaFold prediction array contains a non-object record")
            model = _alphafold_model_record(raw, include_sequence=include_sequence)
            returned = model["uniprot_accession"]
            if returned != requested and not returned.startswith(f"{requested}-"):
                raise PublicDatabaseError("AlphaFold response does not preserve the requested UniProt accession")
            models.append(model)
        records.append(
            {
                "requested_uniprot_accession": requested,
                "has_model": bool(models),
                "model_count": len(models),
                "models": models,
            }
        )
    return {
        "query": {"uniprot_accessions": normalized, "include_sequence": include_sequence},
        "requested_count": len(normalized),
        "covered_count": sum(record["has_model"] for record in records),
        "not_covered_count": sum(not record["has_model"] for record in records),
        "records": records,
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "AlphaFold Protein Structure Database API",
            "contract": ALPHAFOLD_CONTRACT_VERSION,
            "requests": requests,
        },
        "limitations": [
            "Predicted coordinates and confidence are model evidence, not experimental validation of structure, state, assembly, dynamics, or function.",
            "Global and binned pLDDT do not establish domain orientation, interface accuracy, ligand pose, or biological relevance; inspect per-residue confidence and PAE before interpretation.",
            "This operation returns metadata and approved resource URLs only; coordinate, PAE, MSA, and annotation payloads are not silently downloaded.",
        ],
    }


_IUPRED2A_PREDICTION_TYPES = frozenset({"long", "short", "glob"})


def _iupred2a_disordered_spans(scores: list[float], threshold: float, minimum_span: int) -> list[dict[str, Any]]:
    """Call contiguous score-threshold spans without smoothing the server profile."""
    spans: list[dict[str, Any]] = []
    start: int | None = None
    for position, score in enumerate(scores, start=1):
        if score >= threshold and start is None:
            start = position
        elif score < threshold and start is not None:
            end = position - 1
            if end - start + 1 >= minimum_span:
                values = scores[start - 1:end]
                spans.append({"start": start, "end": end, "length": len(values), "mean_score": sum(values) / len(values)})
            start = None
    if start is not None:
        end = len(scores)
        if end - start + 1 >= minimum_span:
            values = scores[start - 1:end]
            spans.append({"start": start, "end": end, "length": len(values), "mean_score": sum(values) / len(values)})
    return spans


def iupred2a_disorder_prediction(
    uniprot_accessions: list[str],
    prediction_type: str = "long",
    score_threshold: float = 0.5,
    minimum_span_length: int = 20,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve bounded IUPred2A residue-level disorder tendencies by accession.

    The service accepts stable UniProt accessions.  It deliberately does not
    submit arbitrary sequences or infer any structural, mechanistic, or
    functional conclusion from a score profile.
    """
    if not 1 <= len(uniprot_accessions) <= 20:
        raise ValueError("one to 20 UniProt accessions are required")
    normalized = [_require_uniprot_accession(value) for value in uniprot_accessions]
    if len(normalized) != len(set(normalized)):
        raise ValueError("UniProt accessions must be unique")
    normalized_type = prediction_type.strip().lower()
    if normalized_type not in _IUPRED2A_PREDICTION_TYPES:
        raise ValueError("prediction_type must be long, short, or glob")
    if not isinstance(score_threshold, (int, float)) or not math.isfinite(float(score_threshold)) or not 0 <= float(score_threshold) <= 1:
        raise ValueError("score_threshold must be a finite value from 0 through 1")
    if not isinstance(minimum_span_length, int) or not 1 <= minimum_span_length <= 500:
        raise ValueError("minimum_span_length must be an integer from 1 through 500")
    active = client or PublicJSONClient()
    records = []
    requests = []
    for accession in normalized:
        payload, transport = active.get_with_metadata(
            "https://iupred2a.elte.hu",
            f"/iupred2a/{normalized_type}/{quote(accession, safe='')}.json",
            not_found_as_empty_object=True,
        )
        requests.append(transport)
        if transport.get("not_found"):
            records.append({"requested_uniprot_accession": accession, "found": False, "prediction_type": normalized_type})
            continue
        sequence = str(payload.get("sequence") or "").strip().upper()
        returned_type = str(payload.get("type") or "").strip().lower()
        raw_scores = payload.get("iupred2")
        if not sequence or re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]+", sequence) is None:
            raise PublicDatabaseError("IUPred2A response lacks a valid protein sequence")
        if returned_type != normalized_type:
            raise PublicDatabaseError("IUPred2A response does not preserve the requested prediction type")
        if not isinstance(raw_scores, list) or len(raw_scores) != len(sequence):
            raise PublicDatabaseError("IUPred2A score profile does not reconcile with the returned sequence")
        try:
            scores = [float(value) for value in raw_scores]
        except (TypeError, ValueError):
            raise PublicDatabaseError("IUPred2A score profile contains a non-numeric value") from None
        if any(not math.isfinite(score) or score < 0 or score > 1 for score in scores):
            raise PublicDatabaseError("IUPred2A score profile contains a value outside 0..1")
        records.append(
            {
                "requested_uniprot_accession": accession,
                "found": True,
                "prediction_type": normalized_type,
                "sequence_length": len(sequence),
                "scores": scores,
                "score_count": len(scores),
                "score_threshold": float(score_threshold),
                "minimum_span_length": minimum_span_length,
                "threshold_spans": _iupred2a_disordered_spans(scores, float(score_threshold), minimum_span_length),
            }
        )
    return {
        "query": {
            "uniprot_accessions": normalized,
            "prediction_type": normalized_type,
            "score_threshold": float(score_threshold),
            "minimum_span_length": minimum_span_length,
        },
        "requested_count": len(normalized),
        "found_count": sum(record["found"] for record in records),
        "not_found_count": sum(not record["found"] for record in records),
        "records": records,
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "IUPred2A REST API",
            "contract": IUPRED2A_CONTRACT_VERSION,
            "requests": requests,
        },
        "limitations": [
            "IUPred2A scores are a sequence-based disorder tendency prediction, not experimental structural evidence.",
            "Threshold spans are a transparent score summary, not validated protein domains, binding sites, functional regions, or mechanisms.",
            "The module accepts accession-based requests only and does not transmit arbitrary protein sequences to a third-party service.",
        ],
    }
