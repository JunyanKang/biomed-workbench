#!/usr/bin/env python3
"""Query NCBI Entrez databases through one structured E-utilities interface."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.services.eutils import CORE_DATABASES, EUtilitiesClient, EUtilitiesError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("databases", help="List the validated core Entrez database names")

    info = subparsers.add_parser("info", help="Inspect Entrez database metadata")
    info.add_argument("database", nargs="?")

    search = subparsers.add_parser("search", help="Search one Entrez database")
    search.add_argument("database")
    search.add_argument("term")
    search.add_argument("--retmax", type=int, default=20)
    search.add_argument("--retstart", type=int, default=0)
    search.add_argument("--sort")
    search.add_argument("--use-history", action="store_true")
    search.add_argument("--idtype")

    summary = subparsers.add_parser("summary", help="Retrieve normalized document summaries")
    summary.add_argument("database")
    summary.add_argument("ids", nargs="+")

    fetch = subparsers.add_parser("fetch", help="Fetch database-native records")
    fetch.add_argument("database")
    fetch.add_argument("ids", nargs="+")
    fetch.add_argument("--rettype")
    fetch.add_argument("--retmode")

    link = subparsers.add_parser("link", help="Resolve links between Entrez databases")
    link.add_argument("source_database")
    link.add_argument("target_database")
    link.add_argument("ids", nargs="+")
    link.add_argument("--linkname")

    pipeline = subparsers.add_parser("search-summary", help="Search then summarize the returned IDs")
    pipeline.add_argument("database")
    pipeline.add_argument("term")
    pipeline.add_argument("--retmax", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "databases":
        payload = {"databases": sorted(CORE_DATABASES)}
    else:
        client = EUtilitiesClient()
        try:
            if args.command == "info":
                payload = client.info(args.database)
            elif args.command == "search":
                payload = asdict(
                    client.search(
                        args.database,
                        args.term,
                        retmax=args.retmax,
                        retstart=args.retstart,
                        sort=args.sort,
                        use_history=args.use_history,
                        idtype=args.idtype,
                    )
                )
            elif args.command == "summary":
                payload = asdict(client.summary(args.database, args.ids))
            elif args.command == "fetch":
                payload = asdict(client.fetch(args.database, args.ids, rettype=args.rettype, retmode=args.retmode))
            elif args.command == "link":
                payload = asdict(
                    client.link(args.source_database, args.target_database, args.ids, linkname=args.linkname)
                )
            else:
                search = client.search(args.database, args.term, retmax=args.retmax)
                summary = client.summary(args.database, search.ids) if search.ids else None
                payload = {
                    "search": asdict(search),
                    "summary": asdict(summary) if summary else {"database": args.database, "records": []},
                }
        except (EUtilitiesError, ValueError) as exc:
            print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
            return 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
