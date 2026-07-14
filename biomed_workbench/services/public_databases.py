"""Bounded clients for public biomedical evidence databases.

The clients intentionally expose small, database-specific operations instead of
an arbitrary URL fetcher.  That keeps redirects, response size, identifiers,
pagination, and provenance inspectable at the module boundary.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


CROSSREF_CONTRACT_VERSION = "rest-v1-observed-2026-07-13"
EUROPE_PMC_CONTRACT_VERSION = "rest-observed-2026-07-13"
BIORXIV_CONTRACT_VERSION = "details-v1-observed-2026-07-13"
PUBCHEM_CONTRACT_VERSION = "pug-rest-observed-2026-07-13"
CLINICAL_TRIALS_CONTRACT_VERSION = "api-v2-observed-2026-07-13"
RCSB_CONTRACT_VERSION = "data-rest-v1-observed-2026-07-13"
RCSB_SEARCH_CONTRACT_VERSION = "search-v2-observed-2026-07-13"

_MAX_RESPONSE_BYTES = 20 * 1024 * 1024
_MAX_REQUEST_BYTES = 1024 * 1024
_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
_PDB_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
_NCT_RE = re.compile(r"^NCT\d{8}$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CT_PHASES = frozenset({"NA", "EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4"})
_CT_STATUSES = frozenset(
    {
        "ACTIVE_NOT_RECRUITING", "COMPLETED", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING",
        "RECRUITING", "SUSPENDED", "TERMINATED", "WITHDRAWN", "AVAILABLE", "NO_LONGER_AVAILABLE",
        "TEMPORARILY_NOT_AVAILABLE", "APPROVED_FOR_MARKETING", "WITHHELD", "UNKNOWN",
    }
)
_CT_STUDY_TYPES = frozenset({"INTERVENTIONAL", "OBSERVATIONAL", "EXPANDED_ACCESS"})
_CT_SPONSOR_CLASSES = frozenset({"NIH", "FED", "OTHER_GOV", "INDIV", "INDUSTRY", "NETWORK", "AMBIG", "OTHER", "UNKNOWN"})
_RCSB_EXPERIMENTAL_METHODS = frozenset(
    {
        "ELECTRON CRYSTALLOGRAPHY", "ELECTRON MICROSCOPY", "EPR", "FIBER DIFFRACTION",
        "FLUORESCENCE TRANSFER", "INFRARED SPECTROSCOPY", "NEUTRON DIFFRACTION",
        "POWDER DIFFRACTION", "SOLID-STATE NMR", "SOLUTION NMR", "SOLUTION SCATTERING",
        "THEORETICAL MODEL", "X-RAY DIFFRACTION",
    }
)
_ALLOWED_HOSTS = frozenset(
    {
        "api.crossref.org",
        "www.ebi.ac.uk",
        "api.biorxiv.org",
        "pubchem.ncbi.nlm.nih.gov",
        "clinicaltrials.gov",
        "data.rcsb.org",
        "search.rcsb.org",
    }
)


class PublicDatabaseError(RuntimeError):
    """A bounded, secret-free public database request or schema failure."""


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[str, Mapping[str, str], float], HTTPResponse]
PostTransport = Callable[[str, Mapping[str, str], bytes, float], HTTPResponse]


def _default_transport(url: str, headers: Mapping[str, str], timeout: float) -> HTTPResponse:
    request = Request(url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(body) > _MAX_RESPONSE_BYTES:
                raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
            return HTTPResponse(response.status, dict(response.headers.items()), body)
    except HTTPError as exc:
        return HTTPResponse(exc.code, dict(exc.headers.items()), exc.read(64 * 1024))
    except (URLError, TimeoutError, OSError) as exc:
        raise PublicDatabaseError(f"public database request failed: {type(exc).__name__}") from None


def _default_post_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> HTTPResponse:
    request = Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(response_body) > _MAX_RESPONSE_BYTES:
                raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
            return HTTPResponse(response.status, dict(response.headers.items()), response_body)
    except HTTPError as exc:
        return HTTPResponse(exc.code, dict(exc.headers.items()), exc.read(64 * 1024))
    except (URLError, TimeoutError, OSError) as exc:
        raise PublicDatabaseError(f"public database request failed: {type(exc).__name__}") from None


def _clean_text(value: Any, *, limit: int = 20_000) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:limit] if text else None


def _require_doi(value: str) -> str:
    normalized = value.strip()
    if normalized.lower().startswith("https://doi.org/"):
        normalized = normalized[16:]
    if not _DOI_RE.fullmatch(normalized):
        raise ValueError("DOI is not syntactically valid")
    return normalized.lower()


def _require_pdb_id(value: str) -> str:
    normalized = value.strip().upper()
    if not _PDB_RE.fullmatch(normalized):
        raise ValueError("PDB identifier must contain four alphanumeric characters and start with a digit")
    return normalized


class PublicJSONClient:
    """HTTPS-only JSON transport with host allow-listing and bounded retries."""

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        post_transport: PostTransport | None = None,
        timeout: float = 20.0,
        retries: int = 2,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout <= 0 or retries < 0:
            raise ValueError("timeout must be positive and retries non-negative")
        self._transport = transport or _default_transport
        self._post_transport = post_transport or _default_post_transport
        self._timeout = timeout
        self._retries = retries
        self._sleeper = sleeper

    def get_with_metadata(
        self,
        base_url: str,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        query = urlencode({key: value for key, value in (params or {}).items() if value is not None}, doseq=True)
        url = f"{base_url}{path}{'?' + query if query else ''}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)",
        }
        response: HTTPResponse | None = None
        attempts = 0
        for attempt in range(self._retries + 1):
            attempts = attempt + 1
            try:
                response = self._transport(url, headers, self._timeout)
            except PublicDatabaseError:
                if attempt >= self._retries:
                    raise
                self._sleeper(min(2**attempt, 4))
                continue
            if response.status not in {429, 500, 502, 503, 504} or attempt >= self._retries:
                break
            self._sleeper(min(2**attempt, 4))
        assert response is not None
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        if len(response.body) > _MAX_RESPONSE_BYTES:
            raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PublicDatabaseError("public database returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise PublicDatabaseError("public database JSON root must be an object")
        return payload, {
            "url": url,
            "status_code": response.status,
            "bytes": len(response.body),
            "attempts": attempts,
        }

    def get(self, base_url: str, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload, _metadata = self.get_with_metadata(base_url, path, params)
        return payload

    def post_with_metadata(
        self,
        base_url: str,
        path: str,
        payload: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not path.startswith("/") or ".." in path:
            raise ValueError("database path must be absolute and traversal-free")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.path or parsed.query:
            raise ValueError("database base URL is not approved")
        if not isinstance(payload, Mapping):
            raise ValueError("database POST payload must be an object")
        body = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(body) > _MAX_REQUEST_BYTES:
            raise ValueError("public database request exceeded the 1 MiB safety limit")
        url = f"{base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)",
        }
        response: HTTPResponse | None = None
        attempts = 0
        for attempt in range(self._retries + 1):
            attempts = attempt + 1
            try:
                response = self._post_transport(url, headers, body, self._timeout)
            except PublicDatabaseError:
                if attempt >= self._retries:
                    raise
                self._sleeper(min(2**attempt, 4))
                continue
            if response.status not in {429, 500, 502, 503, 504} or attempt >= self._retries:
                break
            self._sleeper(min(2**attempt, 4))
        assert response is not None
        if response.status < 200 or response.status >= 300:
            raise PublicDatabaseError(f"public database request failed with HTTP {response.status}")
        if len(response.body) > _MAX_RESPONSE_BYTES:
            raise PublicDatabaseError("public database response exceeded the 20 MiB safety limit")
        if response.status == 204 and not response.body:
            decoded = {}
        else:
            try:
                decoded = json.loads(response.body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise PublicDatabaseError("public database returned invalid JSON") from None
        if not isinstance(decoded, dict):
            raise PublicDatabaseError("public database JSON root must be an object")
        return decoded, {
            "url": url,
            "status_code": response.status,
            "request_bytes": len(body),
            "response_bytes": len(response.body),
            "attempts": attempts,
        }


def resolve_citation_record(doi: str, *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Resolve one DOI against Crossref and Europe PMC without merging conflicts."""
    doi = _require_doi(doi)
    client = client or PublicJSONClient()
    crossref_payload = client.get("https://api.crossref.org", f"/v1/works/{quote(doi, safe='')}")
    message = crossref_payload.get("message")
    if not isinstance(message, dict) or str(message.get("DOI", "")).lower() != doi:
        raise PublicDatabaseError("Crossref response did not preserve the requested DOI")
    europe_payload = client.get(
        "https://www.ebi.ac.uk",
        "/europepmc/webservices/rest/search",
        {"query": f'DOI:"{doi}"', "format": "json", "resultType": "core", "pageSize": 25},
    )
    result_list = europe_payload.get("resultList", {}).get("result", [])
    if not isinstance(result_list, list):
        raise PublicDatabaseError("Europe PMC search result schema is not recognized")
    europe_records = [record for record in result_list if isinstance(record, dict) and str(record.get("doi", "")).lower() == doi]
    crossref = {
        "doi": doi,
        "title": _clean_text((message.get("title") or [None])[0]),
        "type": _clean_text(message.get("type")),
        "publisher": _clean_text(message.get("publisher")),
        "container_title": _clean_text((message.get("container-title") or [None])[0]),
        "published": message.get("published") or message.get("published-print") or message.get("published-online"),
        "authors": message.get("author") if isinstance(message.get("author"), list) else [],
        "is_referenced_by_count": message.get("is-referenced-by-count"),
        "relation": message.get("relation") if isinstance(message.get("relation"), dict) else {},
        "update_to": message.get("update-to") if isinstance(message.get("update-to"), list) else [],
    }
    return {
        "query": {"doi": doi},
        "crossref": crossref,
        "europe_pmc_records": europe_records,
        "agreement": {
            "doi_confirmed_by_crossref": True,
            "europe_pmc_exact_doi_matches": len(europe_records),
            "title_comparison_required": bool(europe_records and crossref["title"]),
        },
        "provenance": {
            "retrieved_at_runtime": True,
            "services": ["Crossref REST API", "Europe PMC REST API"],
            "contracts": [CROSSREF_CONTRACT_VERSION, EUROPE_PMC_CONTRACT_VERSION],
        },
        "limitations": [
            "Metadata deposits may be incomplete or disagree across services; disagreements must remain explicit.",
            "A resolved DOI does not establish study validity, retraction status, or support for a scientific claim.",
        ],
    }


def preprint_record(doi: str, server: str, *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve versioned bioRxiv or medRxiv metadata and publication links."""
    doi = _require_doi(doi)
    server = server.strip().lower()
    if server not in {"biorxiv", "medrxiv"}:
        raise ValueError("server must be biorxiv or medrxiv")
    client = client or PublicJSONClient()
    # bioRxiv models the DOI as two path segments and rejects an encoded slash.
    payload = client.get("https://api.biorxiv.org", f"/details/{server}/{quote(doi, safe='/')}/na/json")
    collection = payload.get("collection")
    if not isinstance(collection, list):
        raise PublicDatabaseError("bioRxiv details response schema is not recognized")
    versions = [record for record in collection if isinstance(record, dict) and str(record.get("doi", "")).lower() == doi]
    if not versions:
        raise PublicDatabaseError("bioRxiv details response did not contain the requested DOI")
    versions.sort(key=lambda record: (str(record.get("version", "")), str(record.get("date", ""))))
    published = [record.get("published") for record in versions if record.get("published") and record.get("published") != "NA"]
    return {
        "query": {"doi": doi, "server": server},
        "versions": versions,
        "latest_version": versions[-1],
        "published_dois": sorted({str(value).lower() for value in published}),
        "version_count": len(versions),
        "provenance": {
            "retrieved_at_runtime": True,
            "service": f"{server} details API",
            "contract": BIORXIV_CONTRACT_VERSION,
        },
        "limitations": [
            "A preprint is not peer reviewed unless an independently verified publication record is supplied.",
            "Versions must not be collapsed; conclusions and citations must identify the analyzed version.",
        ],
    }


def pubchem_compound(identifier: str, namespace: str = "name", *, client: PublicJSONClient | None = None) -> dict[str, Any]:
    """Retrieve identity-critical PubChem properties and synonyms."""
    value = identifier.strip()
    namespace = namespace.strip().lower()
    if namespace not in {"name", "cid", "inchikey"}:
        raise ValueError("namespace must be name, cid, or inchikey")
    if not value or len(value) > 500 or (namespace == "cid" and not value.isdigit()):
        raise ValueError("compound identifier is invalid")
    client = client or PublicJSONClient()
    encoded = quote(value, safe="")
    properties = "Title,IUPACName,MolecularFormula,MolecularWeight,SMILES,ConnectivitySMILES,InChI,InChIKey,XLogP,TPSA,Charge"
    property_payload = client.get(
        "https://pubchem.ncbi.nlm.nih.gov",
        f"/rest/pug/compound/{namespace}/{encoded}/property/{properties}/JSON",
    )
    rows = property_payload.get("PropertyTable", {}).get("Properties", [])
    if not isinstance(rows, list) or not rows:
        raise PublicDatabaseError("PubChem response contained no compound properties")
    synonym_payload = client.get(
        "https://pubchem.ncbi.nlm.nih.gov",
        f"/rest/pug/compound/cid/{rows[0].get('CID')}/synonyms/JSON",
    )
    information = synonym_payload.get("InformationList", {}).get("Information", [])
    synonyms = information[0].get("Synonym", []) if isinstance(information, list) and information and isinstance(information[0], dict) else []
    return {
        "query": {"identifier": value, "namespace": namespace},
        "compounds": rows,
        "synonyms": synonyms[:200] if isinstance(synonyms, list) else [],
        "identity_checks": {
            "result_count": len(rows),
            "unique_cids": sorted({row.get("CID") for row in rows if isinstance(row, dict) and row.get("CID") is not None}),
            "stereochemistry_fields_retained": all("SMILES" in row and "ConnectivitySMILES" in row and "InChIKey" in row for row in rows if isinstance(row, dict)),
        },
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "PubChem PUG REST",
            "contract": PUBCHEM_CONTRACT_VERSION,
        },
        "limitations": [
            "Name searches can be ambiguous; a scientific claim requires reviewed CID, structure, charge, stereochemistry, and salt form.",
            "Database properties are identifiers and descriptors, not evidence of biological activity or clinical efficacy.",
        ],
    }


def _essie_quote(value: str) -> str:
    if not value.strip() or any(character in value for character in "\r\n"):
        raise ValueError("ClinicalTrials.gov phrase filters must be nonempty single-line strings")
    return '"' + value.replace('"', '\\"') + '"'


def _range_expression(area: str, lower: Any, upper: Any, *, dates: bool = False) -> str:
    if lower is None and upper is None:
        raise ValueError(f"{area} range must contain at least one bound")
    values = []
    for name, value in (("minimum", lower), ("maximum", upper)):
        if value is None:
            values.append("MIN" if name == "minimum" else "MAX")
        elif dates:
            if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
                raise ValueError(f"{area} {name} must use YYYY-MM-DD")
            values.append(value)
        else:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{area} {name} must be a non-negative integer")
            values.append(str(value))
    if lower is not None and upper is not None and lower > upper:
        raise ValueError(f"{area} minimum exceeds maximum")
    return f"AREA[{area}]RANGE[{values[0]},{values[1]}]"


def _clinical_trial_params(query: str | None, filters: Mapping[str, Any], advanced_query: str | None) -> tuple[dict[str, Any], list[str]]:
    allowed = {
        "condition", "intervention", "overall_status", "phase", "study_type", "enrollment_min", "enrollment_max",
        "primary_completion_start", "primary_completion_end", "first_posted_start", "first_posted_end",
        "location_country", "lead_sponsor_class", "investigator", "sex", "healthy_volunteers",
        "minimum_age", "maximum_age", "location_city", "location_state", "location_recruiting_only",
        "sponsor_name", "sponsor_scope", "eligibility_keywords", "investigator_role",
    }
    unknown = sorted(set(filters) - allowed)
    if unknown:
        raise ValueError(f"unsupported ClinicalTrials.gov filters: {', '.join(unknown)}")
    params: dict[str, Any] = {}
    if query:
        if len(query) > 2_000 or any(character in query for character in "\r\n"):
            raise ValueError("query must be a bounded single-line expression")
        params["query.term"] = query
    if filters.get("condition"):
        params["query.cond"] = str(filters["condition"])
    if filters.get("intervention"):
        params["query.intr"] = str(filters["intervention"])
    statuses = list(filters.get("overall_status") or [])
    if any(status not in _CT_STATUSES for status in statuses):
        raise ValueError("overall_status contains an unsupported API v2 enum")
    if statuses:
        params["filter.overallStatus"] = "|".join(statuses)
    advanced = []
    phases = list(filters.get("phase") or [])
    if any(phase not in _CT_PHASES for phase in phases):
        raise ValueError("phase contains an unsupported API v2 enum")
    if phases:
        phase_terms = [f"AREA[Phase]{phase}" for phase in phases]
        advanced.append(phase_terms[0] if len(phase_terms) == 1 else "(" + " OR ".join(phase_terms) + ")")
    study_type = filters.get("study_type")
    if study_type:
        if study_type not in _CT_STUDY_TYPES:
            raise ValueError("study_type contains an unsupported API v2 enum")
        advanced.append(f"AREA[StudyType]{study_type}")
    if filters.get("enrollment_min") is not None or filters.get("enrollment_max") is not None:
        advanced.append(_range_expression("EnrollmentCount", filters.get("enrollment_min"), filters.get("enrollment_max")))
    if filters.get("primary_completion_start") or filters.get("primary_completion_end"):
        advanced.append(_range_expression("PrimaryCompletionDate", filters.get("primary_completion_start"), filters.get("primary_completion_end"), dates=True))
    if filters.get("first_posted_start") or filters.get("first_posted_end"):
        advanced.append(_range_expression("StudyFirstPostDate", filters.get("first_posted_start"), filters.get("first_posted_end"), dates=True))
    sponsor_class = filters.get("lead_sponsor_class")
    if sponsor_class:
        if sponsor_class not in _CT_SPONSOR_CLASSES:
            raise ValueError("lead_sponsor_class contains an unsupported API v2 enum")
        advanced.append(f"AREA[LeadSponsorClass]{sponsor_class}")
    if filters.get("investigator"):
        name = _essie_quote(str(filters["investigator"]))
        role = filters.get("investigator_role", "any")
        if role == "official":
            advanced.append(f"AREA[OverallOfficialName]{name}")
        elif role == "responsible_party":
            advanced.append(f"AREA[ResponsiblePartyInvestigatorFullName]{name}")
        elif role == "any":
            advanced.append(f"(AREA[OverallOfficialName]{name} OR AREA[ResponsiblePartyInvestigatorFullName]{name})")
        else:
            raise ValueError("investigator_role must be any, official, or responsible_party")
    elif filters.get("investigator_role") is not None:
        raise ValueError("investigator_role requires investigator")
    if filters.get("sponsor_name"):
        name = _essie_quote(str(filters["sponsor_name"]))
        scope = filters.get("sponsor_scope", "lead")
        if scope == "lead":
            advanced.append(f"AREA[LeadSponsorName]{name}")
        elif scope == "any":
            advanced.append(f"(AREA[LeadSponsorName]{name} OR AREA[CollaboratorName]{name})")
        else:
            raise ValueError("sponsor_scope must be lead or any")
    elif filters.get("sponsor_scope") is not None:
        raise ValueError("sponsor_scope requires sponsor_name")
    eligibility_keywords = filters.get("eligibility_keywords") or []
    if not isinstance(eligibility_keywords, list) or len(eligibility_keywords) > 20:
        raise ValueError("eligibility_keywords must be a list of at most 20 phrases")
    for keyword in eligibility_keywords:
        advanced.append(f"AREA[EligibilityCriteria]{_essie_quote(str(keyword))}")
    sex = filters.get("sex")
    if sex:
        if sex not in {"FEMALE", "MALE", "ALL"}:
            raise ValueError("sex must be FEMALE, MALE, or ALL")
        advanced.append(f"AREA[Sex]{sex}")
    if filters.get("healthy_volunteers") is not None:
        if not isinstance(filters["healthy_volunteers"], bool):
            raise ValueError("healthy_volunteers must be boolean")
        advanced.append(f"AREA[HealthyVolunteers]{'y' if filters['healthy_volunteers'] else 'n'}")
    if filters.get("minimum_age"):
        advanced.append(f"AREA[MinimumAge]RANGE[{filters['minimum_age']},MAX]")
    if filters.get("maximum_age"):
        advanced.append(f"AREA[MaximumAge]RANGE[MIN,{filters['maximum_age']}]")
    location_terms = []
    for key, area in (("location_city", "LocationCity"), ("location_state", "LocationState")):
        if filters.get(key):
            location_terms.append(f"AREA[{area}]{_essie_quote(str(filters[key]))}")
    if filters.get("location_recruiting_only"):
        if not isinstance(filters["location_recruiting_only"], bool):
            raise ValueError("location_recruiting_only must be boolean")
        location_terms.append("AREA[LocationStatus]RECRUITING")
    if filters.get("location_country"):
        location_terms.append(f"AREA[LocationCountry]{_essie_quote(str(filters['location_country']))}")
    if location_terms:
        advanced.append("SEARCH[Location](" + " AND ".join(location_terms) + ")")
    if advanced_query:
        if len(advanced_query) > 4_000 or any(character in advanced_query for character in "\r\n"):
            raise ValueError("advanced_query must be a bounded single-line Essie expression")
        advanced.append(f"({advanced_query})")
    if advanced:
        params["filter.advanced"] = " AND ".join(advanced)
    if not params:
        raise ValueError("at least one query, filter, or advanced expression is required")
    return params, advanced


def _trim_clinical_trial(study: Mapping[str, Any], *, include_full_record: bool) -> dict[str, Any]:
    protocol = study.get("protocolSection", {}) if isinstance(study, Mapping) else {}
    identification = protocol.get("identificationModule", {}) or {}
    design = protocol.get("designModule", {}) or {}
    status = protocol.get("statusModule", {}) or {}
    conditions = protocol.get("conditionsModule", {}) or {}
    arms = protocol.get("armsInterventionsModule", {}) or {}
    sponsor = (protocol.get("sponsorCollaboratorsModule", {}) or {}).get("leadSponsor", {}) or {}
    contacts = protocol.get("contactsLocationsModule", {}) or {}
    outcomes = protocol.get("outcomesModule", {}) or {}
    eligibility = protocol.get("eligibilityModule", {}) or {}
    nct_id = identification.get("nctId")
    if not isinstance(nct_id, str) or not _NCT_RE.fullmatch(nct_id):
        raise PublicDatabaseError("ClinicalTrials.gov study lacks a valid NCT identifier")
    locations = contacts.get("locations", []) or []
    record = {
        "nct_id": nct_id.upper(),
        "brief_title": _clean_text(identification.get("briefTitle")),
        "official_title": _clean_text(identification.get("officialTitle")),
        "overall_status": status.get("overallStatus"),
        "status_dates": {
            "verified": status.get("statusVerifiedDate"),
            "first_posted": (status.get("studyFirstPostDateStruct") or {}).get("date"),
            "last_update_posted": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
            "primary_completion": (status.get("primaryCompletionDateStruct") or {}).get("date"),
        },
        "study_type": design.get("studyType"),
        "phases": design.get("phases", []) or [],
        "enrollment": design.get("enrollmentInfo", {}) or {},
        "design_info": design.get("designInfo", {}) or {},
        "conditions": conditions.get("conditions", []) or [],
        "interventions": [
            {"type": item.get("type"), "name": item.get("name"), "other_names": item.get("otherNames", []) or []}
            for item in arms.get("interventions", []) or []
            if isinstance(item, Mapping)
        ],
        "lead_sponsor": {"name": sponsor.get("name"), "class": sponsor.get("class")},
        "eligibility": {
            "sex": eligibility.get("sex"),
            "minimum_age": eligibility.get("minimumAge"),
            "maximum_age": eligibility.get("maximumAge"),
            "healthy_volunteers": eligibility.get("healthyVolunteers"),
        },
        "outcome_counts": {
            "primary": len(outcomes.get("primaryOutcomes", []) or []),
            "secondary": len(outcomes.get("secondaryOutcomes", []) or []),
            "other": len(outcomes.get("otherOutcomes", []) or []),
        },
        "locations": [
            {
                "facility": item.get("facility"), "status": item.get("status"), "city": item.get("city"),
                "state": item.get("state"), "country": item.get("country"),
            }
            for item in locations
            if isinstance(item, Mapping)
        ],
        "has_results": bool(study.get("hasResults")),
        "results_section_present": isinstance(study.get("resultsSection"), Mapping),
    }
    if include_full_record:
        record["source_record"] = dict(study)
    return record


def clinical_trial_records(
    query: str | None = None,
    page_size: int = 100,
    filters: Mapping[str, Any] | None = None,
    max_records: int = 1_000,
    advanced_query: str | None = None,
    include_full_record: bool = False,
    *,
    client: PublicJSONClient | None = None,
) -> dict[str, Any]:
    """Retrieve a count-verified, deterministically ordered API v2 cohort."""
    query = query.strip() if query else None
    if not 1 <= page_size <= 1_000 or not 1 <= max_records <= 10_000:
        raise ValueError("page_size must be 1..1000 and max_records must be 1..10000")
    if not isinstance(include_full_record, bool):
        raise ValueError("include_full_record must be boolean")
    declared_filters = dict(filters or {})
    base_params, generated_advanced = _clinical_trial_params(query, declared_filters, advanced_query)
    client = client or PublicJSONClient()
    raw_studies: list[dict[str, Any]] = []
    provenance = []
    total_count: int | None = None
    page_token: str | None = None
    page_index = 0
    while len(raw_studies) < max_records:
        remaining = max_records - len(raw_studies)
        params = {**base_params, "pageSize": min(page_size, remaining), "format": "json"}
        if page_index == 0:
            params["countTotal"] = "true"
        if page_token:
            params["pageToken"] = page_token
        payload, request_meta = client.get_with_metadata("https://clinicaltrials.gov", "/api/v2/studies", params)
        page = payload.get("studies", [])
        if not isinstance(page, list):
            raise PublicDatabaseError("ClinicalTrials.gov response schema is not recognized")
        if page_index == 0:
            try:
                total_count = int(payload["totalCount"])
            except (KeyError, TypeError, ValueError):
                raise PublicDatabaseError("ClinicalTrials.gov first page lacks a valid totalCount") from None
        raw_studies.extend(item for item in page if isinstance(item, dict))
        provenance.append(
            {
                "page_index": page_index,
                "page_token_used": page_token,
                "request": request_meta,
                "parameters": params,
                "studies_in_page": len(page),
                "total_count": total_count if page_index == 0 else None,
            }
        )
        page_token = payload.get("nextPageToken")
        page_index += 1
        if not page_token:
            break
    assert total_count is not None
    by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids = []
    for study in raw_studies:
        record = _trim_clinical_trial(study, include_full_record=include_full_record)
        if record["nct_id"] in by_id:
            duplicate_ids.append(record["nct_id"])
        else:
            by_id[record["nct_id"]] = record
    nct_ids = sorted(by_id)
    records_truncated = total_count > len(nct_ids)
    if not records_truncated and len(nct_ids) != total_count:
        raise PublicDatabaseError("ClinicalTrials.gov completed pagination does not reconcile with totalCount")
    return {
        "query": {
            "term": query,
            "filters": declared_filters,
            "advanced_query": advanced_query,
            "generated_advanced_terms": generated_advanced,
            "page_size": page_size,
            "max_records": max_records,
            "include_full_record": include_full_record,
        },
        "api_total_count": total_count,
        "returned_count": len(nct_ids),
        "nct_ids": nct_ids,
        "studies": [by_id[nct_id] for nct_id in nct_ids],
        "records_truncated": records_truncated,
        "next_page_token_present": bool(page_token),
        "duplicate_nct_ids": sorted(set(duplicate_ids)),
        "local_post_filters_applied": [],
        "provenance": {
            "retrieved_at_runtime": True,
            "service": "ClinicalTrials.gov API v2",
            "contract": CLINICAL_TRIALS_CONTRACT_VERSION,
            "requests": provenance,
        },
        "limitations": [
            "Registry records are sponsor-submitted and require status, dates, protocol, amendments, results, and linked publications to be interpreted together.",
            "A registered or completed study is not evidence of efficacy, and missing results must remain explicit.",
            "When records_truncated is true, the returned cohort is incomplete and cannot support prevalence or exhaustive-review claims.",
        ],
    }


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


def probe_crossref_contract() -> str:
    return CROSSREF_CONTRACT_VERSION


def probe_europe_pmc_contract() -> str:
    return EUROPE_PMC_CONTRACT_VERSION


def probe_biorxiv_contract() -> str:
    return BIORXIV_CONTRACT_VERSION


def probe_pubchem_contract() -> str:
    return PUBCHEM_CONTRACT_VERSION


def probe_clinical_trials_contract() -> str:
    return CLINICAL_TRIALS_CONTRACT_VERSION


def probe_rcsb_contract() -> str:
    return RCSB_CONTRACT_VERSION


def probe_rcsb_search_contract() -> str:
    return RCSB_SEARCH_CONTRACT_VERSION
