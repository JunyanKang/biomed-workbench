"""NCBI Entrez E-utilities client shared across biomedical databases."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .credentials import optional_credential


BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CORE_DATABASES = frozenset(
    {
        "pubmed",
        "pmc",
        "gene",
        "protein",
        "nuccore",
        "nucleotide",
        "sra",
        "gds",
        "biosample",
        "bioproject",
        "clinvar",
        "taxonomy",
        "mesh",
        "pccompound",
        "pcassay",
    }
)
_DATABASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_UTILITY_RE = re.compile(r"^[a-z]+$")


class EUtilitiesError(RuntimeError):
    """A bounded, secret-free NCBI request failure."""


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class SearchResult:
    database: str
    count: int
    ids: tuple[str, ...]
    query_translation: str | None
    webenv: str | None
    query_key: str | None


@dataclass(frozen=True)
class SummaryResult:
    database: str
    records: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class FetchResult:
    database: str
    rettype: str | None
    retmode: str | None
    content_type: str
    text: str


@dataclass(frozen=True)
class LinkResult:
    source_database: str
    target_database: str
    source_ids: tuple[str, ...]
    links: tuple[str, ...]
    link_names: tuple[str, ...]


Transport = Callable[[str, bytes | None, Mapping[str, str], float], HTTPResponse]


def _default_transport(url: str, data: bytes | None, headers: Mapping[str, str], timeout: float) -> HTTPResponse:
    request = Request(url, data=data, headers=dict(headers), method="POST" if data is not None else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(20 * 1024 * 1024 + 1)
            if len(body) > 20 * 1024 * 1024:
                raise EUtilitiesError("NCBI response exceeded the 20 MiB safety limit")
            return HTTPResponse(response.status, dict(response.headers.items()), body)
    except HTTPError as exc:
        body = exc.read(64 * 1024)
        return HTTPResponse(exc.code, dict(exc.headers.items()), body)
    except (URLError, TimeoutError, OSError) as exc:
        raise EUtilitiesError(f"NCBI request failed: {type(exc).__name__}") from None


class _RateLimiter:
    def __init__(self, requests_per_second: float, sleeper: Callable[[float], None]) -> None:
        self._interval = 1.0 / requests_per_second
        self._sleeper = sleeper
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._last + self._interval - now
            if delay > 0:
                self._sleeper(delay)
                now = time.monotonic()
            self._last = now


def _validate_database(database: str) -> str:
    normalized = database.strip().lower()
    if not _DATABASE_RE.fullmatch(normalized):
        raise ValueError(f"invalid Entrez database name: {database!r}")
    return normalized


def _normalize_ids(ids: Iterable[str | int] | None) -> tuple[str, ...]:
    values = tuple(str(value).strip() for value in (ids or ()))
    if any(not value or not re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in values):
        raise ValueError("Entrez identifiers may contain only letters, digits, dot, underscore, and hyphen")
    if len(values) > 10_000:
        raise ValueError("at most 10,000 identifiers are accepted per request")
    return values


class EUtilitiesClient:
    """Composable EInfo/ESearch/ESummary/EFetch/ELink access.

    `NCBI_API_KEY` is optional and read only when a request is made. The same
    key accelerates every Entrez database. `NCBI_EMAIL` is optional contact
    metadata, not a credential.
    """

    def __init__(
        self,
        *,
        transport: Transport | None = None,
        timeout: float = 20.0,
        retries: int = 2,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout <= 0 or retries < 0:
            raise ValueError("timeout must be positive and retries non-negative")
        self._transport = transport or _default_transport
        self._timeout = timeout
        self._retries = retries
        self._sleeper = sleeper
        self._limiters: dict[bool, _RateLimiter] = {}

    def _limiter(self, has_key: bool) -> _RateLimiter:
        if has_key not in self._limiters:
            self._limiters[has_key] = _RateLimiter(10.0 if has_key else 3.0, self._sleeper)
        return self._limiters[has_key]

    def _request(self, utility: str, params: Mapping[str, Any], *, expect_json: bool) -> tuple[HTTPResponse, Any]:
        if not _UTILITY_RE.fullmatch(utility):
            raise ValueError("invalid E-utility name")
        api_key = optional_credential("NCBI_API_KEY") or ""
        email = os.environ.get("NCBI_EMAIL", "").strip()
        request_params = {key: value for key, value in params.items() if value is not None}
        request_params["tool"] = "biomed_workbench"
        if email:
            request_params["email"] = email
        if api_key:
            request_params["api_key"] = api_key
        encoded = urlencode(request_params, doseq=True).encode("utf-8")
        endpoint = f"{BASE_URL}/{utility}.fcgi"
        use_post = len(encoded) > 1800 or len(_normalize_ids(str(request_params.get("id", "")).split(",") if request_params.get("id") else ())) > 200
        url = endpoint if use_post else f"{endpoint}?{encoded.decode('ascii')}"
        data = encoded if use_post else None
        headers = {
            "Accept": "application/json" if expect_json else "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "biomed-workbench/0.2 (+https://github.com/JunyanKang/biomed-workbench)",
        }
        response: HTTPResponse | None = None
        for attempt in range(self._retries + 1):
            self._limiter(bool(api_key)).wait()
            try:
                response = self._transport(url, data, headers, self._timeout)
            except EUtilitiesError:
                if attempt >= self._retries:
                    raise
                self._sleeper(min(2**attempt, 4))
                continue
            if response.status not in {429, 500, 502, 503, 504} or attempt >= self._retries:
                break
            self._sleeper(min(2**attempt, 4))
        assert response is not None
        if response.status < 200 or response.status >= 300:
            raise EUtilitiesError(f"NCBI {utility} request failed with HTTP {response.status}")
        if not expect_json:
            return response, response.body
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise EUtilitiesError(f"NCBI {utility} returned invalid JSON") from None
        if isinstance(payload, dict) and payload.get("error"):
            raise EUtilitiesError(f"NCBI {utility} rejected the request")
        return response, payload

    def info(self, database: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"retmode": "json"}
        if database is not None:
            params["db"] = _validate_database(database)
        _response, payload = self._request("einfo", params, expect_json=True)
        return payload

    def search(
        self,
        database: str,
        term: str,
        *,
        retmax: int = 20,
        retstart: int = 0,
        sort: str | None = None,
        use_history: bool = False,
        idtype: str | None = None,
    ) -> SearchResult:
        database = _validate_database(database)
        if not term.strip():
            raise ValueError("search term must not be empty")
        if not 0 <= retmax <= 100_000 or retstart < 0:
            raise ValueError("retmax must be 0..100000 and retstart must be non-negative")
        params = {
            "db": database,
            "term": term,
            "retmode": "json",
            "retmax": retmax,
            "retstart": retstart,
            "sort": sort,
            "usehistory": "y" if use_history else None,
            "idtype": idtype,
        }
        _response, payload = self._request("esearch", params, expect_json=True)
        result = payload.get("esearchresult", {})
        try:
            count = int(result.get("count", 0))
        except (TypeError, ValueError):
            raise EUtilitiesError("NCBI esearch returned an invalid count") from None
        return SearchResult(
            database=database,
            count=count,
            ids=tuple(map(str, result.get("idlist", ()))),
            query_translation=result.get("querytranslation"),
            webenv=result.get("webenv"),
            query_key=result.get("querykey"),
        )

    def summary(
        self,
        database: str,
        ids: Iterable[str | int] | None = None,
        *,
        webenv: str | None = None,
        query_key: str | int | None = None,
        retstart: int = 0,
        retmax: int = 500,
    ) -> SummaryResult:
        database = _validate_database(database)
        values = _normalize_ids(ids)
        if not values and not (webenv and query_key is not None):
            raise ValueError("summary requires ids or both webenv and query_key")
        if retstart < 0 or not 1 <= retmax <= 10_000:
            raise ValueError("invalid summary pagination")
        params = {
            "db": database,
            "id": ",".join(values) if values else None,
            "WebEnv": webenv,
            "query_key": query_key,
            "retmode": "json",
            "version": "2.0",
            "retstart": retstart,
            "retmax": retmax,
        }
        _response, payload = self._request("esummary", params, expect_json=True)
        result = payload.get("result", {})
        uids = tuple(map(str, result.get("uids", ())))
        records = tuple(result[uid] for uid in uids if isinstance(result.get(uid), dict))
        return SummaryResult(database=database, records=records)

    def fetch(
        self,
        database: str,
        ids: Iterable[str | int] | None = None,
        *,
        webenv: str | None = None,
        query_key: str | int | None = None,
        rettype: str | None = None,
        retmode: str | None = None,
        retstart: int | None = None,
        retmax: int | None = None,
    ) -> FetchResult:
        database = _validate_database(database)
        values = _normalize_ids(ids)
        if not values and not (webenv and query_key is not None):
            raise ValueError("fetch requires ids or both webenv and query_key")
        params = {
            "db": database,
            "id": ",".join(values) if values else None,
            "WebEnv": webenv,
            "query_key": query_key,
            "rettype": rettype,
            "retmode": retmode,
            "retstart": retstart,
            "retmax": retmax,
        }
        response, body = self._request("efetch", params, expect_json=False)
        content_type = next((value for key, value in response.headers.items() if key.lower() == "content-type"), "application/octet-stream")
        return FetchResult(
            database=database,
            rettype=rettype,
            retmode=retmode,
            content_type=content_type,
            text=body.decode("utf-8", errors="replace"),
        )

    def link(
        self,
        source_database: str,
        target_database: str,
        ids: Iterable[str | int],
        *,
        linkname: str | None = None,
    ) -> LinkResult:
        source_database = _validate_database(source_database)
        target_database = _validate_database(target_database)
        values = _normalize_ids(ids)
        if not values:
            raise ValueError("link requires at least one identifier")
        params = {
            "dbfrom": source_database,
            "db": target_database,
            "id": ",".join(values),
            "linkname": linkname,
            "retmode": "json",
        }
        _response, payload = self._request("elink", params, expect_json=True)
        links: list[str] = []
        names: list[str] = []
        for linkset in payload.get("linksets", ()):
            for linksetdb in linkset.get("linksetdbs", ()):
                names.append(str(linksetdb.get("linkname", "")))
                links.extend(map(str, linksetdb.get("links", ())))
        return LinkResult(
            source_database=source_database,
            target_database=target_database,
            source_ids=values,
            links=tuple(dict.fromkeys(links)),
            link_names=tuple(dict.fromkeys(name for name in names if name)),
        )
