"""Codex-callable wrappers around the shared NCBI E-utilities client."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from biomed_workbench.services.eutils import EUtilitiesClient


def info(database: str | None = None) -> dict[str, Any]:
    return EUtilitiesClient().info(database)


def search(
    database: str,
    term: str,
    retmax: int = 20,
    retstart: int = 0,
    sort: str | None = None,
    use_history: bool = False,
    idtype: str | None = None,
) -> dict[str, Any]:
    return asdict(
        EUtilitiesClient().search(
            database,
            term,
            retmax=retmax,
            retstart=retstart,
            sort=sort,
            use_history=use_history,
            idtype=idtype,
        )
    )


def summary(database: str, ids: list[str]) -> dict[str, Any]:
    return asdict(EUtilitiesClient().summary(database, ids))


def fetch(
    database: str,
    ids: list[str],
    rettype: str | None = None,
    retmode: str | None = None,
) -> dict[str, Any]:
    return asdict(EUtilitiesClient().fetch(database, ids, rettype=rettype, retmode=retmode))


def link(
    source_database: str,
    target_database: str,
    ids: list[str],
    linkname: str | None = None,
) -> dict[str, Any]:
    return asdict(EUtilitiesClient().link(source_database, target_database, ids, linkname=linkname))


def search_summary(database: str, term: str, retmax: int = 20) -> dict[str, Any]:
    client = EUtilitiesClient()
    found = client.search(database, term, retmax=retmax)
    summarized = client.summary(database, found.ids) if found.ids else None
    return {
        "search": asdict(found),
        "summary": asdict(summarized) if summarized else {"database": database, "records": ()},
    }
