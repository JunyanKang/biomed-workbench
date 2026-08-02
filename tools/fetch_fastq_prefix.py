#!/usr/bin/env python3
"""Stream a declared prefix of a remote gzipped FASTQ with provenance."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--accession", required=True)
    parser.add_argument("--reads", type=int, required=True)
    parser.add_argument("--source-md5", required=True)
    parser.add_argument("--source-bytes", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.reads < 1 or args.source_bytes < 1 or len(args.source_md5) != 32:
        raise ValueError("reads, source bytes, or source MD5 is invalid")
    if args.output.exists() or args.report.exists():
        raise ValueError("output and report paths must be new")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(args.url, headers={"User-Agent": "Biomed-Workbench/1"})
    with urllib.request.urlopen(request, timeout=180) as response:
        resolved_url = response.geturl()
        with gzip.GzipFile(fileobj=response, mode="rb") as source, args.output.open("wb") as raw_output:
            with gzip.GzipFile(filename="", fileobj=raw_output, mode="wb", mtime=0) as output:
                for index in range(args.reads):
                    record = [source.readline() for _ in range(4)]
                    if any(not line for line in record):
                        raise ValueError(f"remote FASTQ ended after {index} complete reads")
                    if not record[0].startswith(b"@") or not record[2].startswith(b"+"):
                        raise ValueError(f"remote FASTQ record {index + 1} is malformed")
                    if len(record[1].rstrip(b"\r\n")) != len(record[3].rstrip(b"\r\n")):
                        raise ValueError(f"remote FASTQ record {index + 1} has unequal sequence and quality lengths")
                    output.writelines(record)
    report = {
        "schema_version": 1,
        "passed": True,
        "accession": args.accession,
        "selection": {"kind": "first_n_reads", "reads": args.reads},
        "source": {
            "requested_url": args.url,
            "resolved_url": resolved_url,
            "full_object_bytes": args.source_bytes,
            "full_object_md5": args.source_md5,
        },
        "output": {
            "name": args.output.name,
            "bytes": args.output.stat().st_size,
            "sha256": sha256(args.output),
        },
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"accession": args.accession, "bytes": args.output.stat().st_size, "reads": args.reads, "sha256": report["output"]["sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
