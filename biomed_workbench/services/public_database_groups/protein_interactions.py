"""Internal protein interactions public database operations."""

from __future__ import annotations

from ..public_databases import (
    Any,
    PublicDatabaseError,
    PublicJSONClient,
    STRING_BASE_URL,
    STRING_CONTRACT_VERSION,
    _clean_text,
    math,
    re,
)

__all__ = ['string_protein_interaction_evidence']

def string_protein_interaction_evidence(
    identifiers: list[str],
    species: int,
    network_type: str = "functional",
    required_score: int = 700,
    add_nodes: int = 0,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Resolve identifiers and retrieve a bounded, version-pinned STRING network.

    STRING's functional network represents associations; its physical network is
    restricted to evidence compatible with physical interaction but still does
    not establish an interaction in the user's biological system.
    """
    if not isinstance(identifiers, list) or not 2 <= len(identifiers) <= 100:
        raise ValueError("identifiers must contain 2..100 protein identifiers")
    normalized = [str(value).strip() for value in identifiers]
    if any(not value or len(value) > 100 or re.search(r"[\r\n]", value) for value in normalized):
        raise ValueError("protein identifiers must be nonempty single-line values up to 100 characters")
    if len(set(normalized)) != len(normalized):
        raise ValueError("protein identifiers must be unique")
    if not isinstance(species, int) or not 1 <= species <= 9_999_999:
        raise ValueError("species must be a positive NCBI taxonomy identifier")
    if network_type not in {"functional", "physical"}:
        raise ValueError("network_type must be functional or physical")
    if not isinstance(required_score, int) or not 0 <= required_score <= 1000:
        raise ValueError("required_score must be an integer from 0 to 1000")
    if not isinstance(add_nodes, int) or not 0 <= add_nodes <= 50:
        raise ValueError("add_nodes must be an integer from 0 to 50")

    client = client or PublicJSONClient()
    joined = "\r".join(normalized)
    mapping_raw, mapping_transport = client.post_form_array_with_metadata(
        STRING_BASE_URL,
        "/api/json/get_string_ids",
        {"identifiers": joined, "species": str(species), "limit": "1", "echo_query": "1"},
    )
    mapping_by_index: dict[int, dict[str, Any]] = {}
    for raw in mapping_raw:
        if not isinstance(raw, dict):
            raise PublicDatabaseError("STRING identifier mapping contains a non-object record")
        query_index, string_id = raw.get("queryIndex"), _clean_text(raw.get("stringId"), limit=100)
        if not isinstance(query_index, int) or not 0 <= query_index < len(normalized) or not string_id:
            raise PublicDatabaseError("STRING identifier mapping does not preserve query index and STRING ID")
        if query_index in mapping_by_index:
            raise PublicDatabaseError("STRING returned more than one primary mapping for a query identifier")
        if int(raw.get("ncbiTaxonId", -1)) != species:
            raise PublicDatabaseError("STRING mapped an identifier outside the requested species")
        mapping_by_index[query_index] = {
            "query_index": query_index,
            "query_identifier": normalized[query_index],
            "string_id": string_id,
            "preferred_name": _clean_text(raw.get("preferredName"), limit=500),
            "taxon_id": species,
            "taxon_name": _clean_text(raw.get("taxonName"), limit=500),
            "annotation": _clean_text(raw.get("annotation"), limit=5_000),
        }
    mappings = [mapping_by_index[index] for index in sorted(mapping_by_index)]
    unmapped = [value for index, value in enumerate(normalized) if index not in mapping_by_index]
    if len(mappings) < 2:
        raise PublicDatabaseError("fewer than two requested identifiers mapped uniquely in STRING")

    mapped_ids = "\r".join(record["string_id"] for record in mappings)
    network_raw, network_transport = client.post_form_array_with_metadata(
        STRING_BASE_URL,
        "/api/json/network",
        {
            "identifiers": mapped_ids,
            "species": str(species),
            "required_score": str(required_score),
            "network_type": network_type,
            "add_nodes": str(add_nodes),
        },
    )
    score_fields = ("score", "nscore", "fscore", "pscore", "ascore", "escore", "dscore", "tscore")
    edges = []
    for raw in network_raw:
        if not isinstance(raw, dict):
            raise PublicDatabaseError("STRING network contains a non-object edge")
        string_a, string_b = _clean_text(raw.get("stringId_A"), limit=100), _clean_text(raw.get("stringId_B"), limit=100)
        if not string_a or not string_b or string_a == string_b:
            raise PublicDatabaseError("STRING network contains an invalid edge identity")
        scores: dict[str, float] = {}
        for field in score_fields:
            value = raw.get(field, 0.0)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
                raise PublicDatabaseError(f"STRING edge {field} is outside 0..1")
            scores[field] = float(value)
        edge = {
            "string_id_a": string_a,
            "string_id_b": string_b,
            "preferred_name_a": _clean_text(raw.get("preferredName_A"), limit=500),
            "preferred_name_b": _clean_text(raw.get("preferredName_B"), limit=500),
            "taxon_id": int(raw.get("ncbiTaxonId", species)),
            **scores,
        }
        edges.append(edge)
    edges.sort(key=lambda row: (-row["score"], row["string_id_a"], row["string_id_b"]))

    enrichment_raw, enrichment_transport = client.post_form_array_with_metadata(
        STRING_BASE_URL,
        "/api/json/ppi_enrichment",
        {"identifiers": mapped_ids, "species": str(species)},
    )
    if len(enrichment_raw) != 1 or not isinstance(enrichment_raw[0], dict):
        raise PublicDatabaseError("STRING PPI enrichment response must contain one summary record")
    enrichment = enrichment_raw[0]
    return {
        "query": {
            "identifiers": normalized,
            "species": species,
            "network_type": network_type,
            "required_score": required_score,
            "add_nodes": add_nodes,
        },
        "mappings": mappings,
        "mapped_count": len(mappings),
        "unmapped_identifiers": unmapped,
        "edges": edges,
        "edge_count": len(edges),
        "ppi_enrichment": {
            "number_of_nodes": int(enrichment.get("number_of_nodes", 0)),
            "number_of_edges": int(enrichment.get("number_of_edges", 0)),
            "expected_number_of_edges": float(enrichment.get("expected_number_of_edges", 0)),
            "p_value": float(enrichment.get("p_value", 1)),
            "average_node_degree": float(enrichment.get("average_node_degree", 0)),
            "local_clustering_coefficient": float(enrichment.get("local_clustering_coefficient", 0)),
        },
        "provenance": {
            "service": "STRING database API",
            "release": "12.0",
            "contract": STRING_CONTRACT_VERSION,
            "requests": [mapping_transport, network_transport, enrichment_transport],
        },
        "limitations": [
            "A STRING functional edge is an association supported by one or more evidence channels, not necessarily a physical interaction.",
            "A STRING physical edge is database evidence compatible with physical interaction, not proof of binding in the user's tissue, cell state, condition, or assay.",
            "PPI enrichment tests whether the submitted proteins have more STRING edges than expected; it does not establish pathway activation, causality, direct binding, affinity, or direction.",
        ],
    }
