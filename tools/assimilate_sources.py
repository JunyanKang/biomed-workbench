#!/usr/bin/env python3
"""Create or verify exhaustive local source-assimilation evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.assimilation import (  # noqa: E402
    assimilate_source,
    public_summary,
    verify_manifest,
    write_private_manifest,
)


def _source(value: str) -> tuple[str, Path]:
    alias, separator, root = value.partition("=")
    if not separator or not alias or not root:
        raise argparse.ArgumentTypeError("source must use ALIAS=PATH")
    path = Path(root).expanduser()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"source root is not a directory: {root}")
    return alias, path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", type=_source, default=[], metavar="ALIAS=PATH")
    parser.add_argument("--private-manifest", type=Path)
    parser.add_argument("--public-summary", type=Path)
    parser.add_argument("--verify", type=Path, metavar="MANIFEST")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify:
        summaries = verify_manifest(args.verify)
        print(json.dumps({"verified": [summary.to_dict() for summary in summaries]}, sort_keys=True))
        return 0
    if not args.source or not args.private_manifest or not args.public_summary:
        raise SystemExit("scan mode requires --source, --private-manifest, and --public-summary")
    roots = dict(args.source)
    if len(roots) != len(args.source):
        raise SystemExit("source aliases must be unique")
    results = []
    for alias, root in roots.items():
        print(f"Reading every file in {alias}...", file=sys.stderr, flush=True)
        result = assimilate_source(root, alias)
        results.append(result)
        print(
            f"Completed {alias}: {result.summary.file_count} files, "
            f"{result.summary.total_bytes} bytes",
            file=sys.stderr,
            flush=True,
        )
    write_private_manifest(args.private_manifest, roots, results)
    args.public_summary.parent.mkdir(parents=True, exist_ok=True)
    args.public_summary.write_text(
        json.dumps(public_summary(results), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
