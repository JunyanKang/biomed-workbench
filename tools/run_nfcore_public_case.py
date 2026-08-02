#!/usr/bin/env python3
"""Run checksum-bound nf-core public cases through product-owned executors.

The public fixtures are the minimal datasets declared by the pinned pipeline
releases.  Remote files are materialized locally at explicit test-data commits
before the normal project-data execution path is invoked.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.nfcore import (  # noqa: E402
    CLIPSEQ,
    HIC,
    METHYLSEQ,
    NfCorePipelineSpec,
    execute_nfcore,
)


TEST_DATA_COMMITS = {
    "methylseq": "e7e1fb8940fc14e2336101147a31ce8e0eda6264",
    "clipseq": "f87bd7f5de9c8ab85fc0be7ba64f346163a49312",
    "hic": "bdf213098d5cef814c0eeb84d2b04f7aa90f3a9f",
}


class PublicCaseError(ValueError):
    """Raised when a public fixture cannot be frozen or executed safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise PublicCaseError(f"fixture path already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "biomed-workbench/0.2 checksum-bound-public-case"},
    )
    temporary = destination.with_name(destination.name + ".part")
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=300) as response, temporary.open("wb") as handle:
        while block := response.read(1024 * 1024):
            handle.write(block)
            digest.update(block)
            size += len(block)
    if size == 0:
        temporary.unlink(missing_ok=True)
        raise PublicCaseError(f"public fixture was empty: {url}")
    temporary.replace(destination)
    return {
        "source_url": url,
        "path": str(destination.resolve()),
        "bytes": size,
        "sha256": digest.hexdigest(),
    }


def _raw_url(branch: str, relative: str) -> str:
    commit = TEST_DATA_COMMITS[branch]
    return f"https://raw.githubusercontent.com/nf-core/test-datasets/{commit}/{relative}"


def _rewrite_samplesheet(
    source_url: str,
    destination: Path,
    *,
    url_columns: tuple[str, ...],
    branch: str,
    downloads: list[dict[str, Any]],
) -> None:
    request = urllib.request.Request(source_url, headers={"User-Agent": "biomed-workbench/0.2"})
    with urllib.request.urlopen(request, timeout=120) as response:
        source_bytes = response.read()
    rows = list(csv.DictReader(io.StringIO(source_bytes.decode("utf-8-sig"))))
    if not rows:
        raise PublicCaseError(f"official samplesheet is empty: {source_url}")
    for row in rows:
        for column in url_columns:
            value = str(row.get(column, "")).strip()
            if not value:
                continue
            parsed = urllib.parse.urlparse(value)
            marker = f"/nf-core/test-datasets/raw/{branch}/"
            if marker in parsed.path:
                relative = parsed.path.split(marker, 1)[1]
            else:
                marker = f"/nf-core/test-datasets/{branch}/"
                if marker not in parsed.path:
                    raise PublicCaseError(f"unreviewed public fixture URL: {value}")
                relative = parsed.path.split(marker, 1)[1]
            target = destination.parent / "reads" / Path(relative).name
            downloads.append(_download(_raw_url(branch, relative), target))
            row[column] = str(target.resolve())
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    downloads.append({
        "source_url": source_url,
        "path": str(destination.resolve()),
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
        "rewritten_to_local_immutable_paths": True,
        "official_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "row_count": len(rows),
    })


def _methylseq_fixture(root: Path) -> tuple[NfCorePipelineSpec, str, dict[str, Any], dict[str, Any]]:
    downloads: list[dict[str, Any]] = []
    samplesheet = root / "samplesheet.csv"
    source = (
        "https://raw.githubusercontent.com/nf-core/methylseq/"
        f"{METHYLSEQ.revision_commit}/assets/samplesheet.csv"
    )
    _rewrite_samplesheet(
        source,
        samplesheet,
        url_columns=("fastq_1", "fastq_2"),
        branch="methylseq",
        downloads=downloads,
    )
    fasta = root / "genome.fa.gz"
    fasta_index = root / "genome.fa.fai"
    downloads.append(_download(_raw_url("methylseq", "reference/genome.fa.gz"), fasta))
    downloads.append(_download(_raw_url("methylseq", "reference/genome.fa.fai"), fasta_index))
    params = {
        "input": str(samplesheet.resolve()),
        "fasta": str(fasta.resolve()),
        "fasta_index": str(fasta_index.resolve()),
        "igenomes_ignore": True,
        # The pinned minimal fixture already contains analysis-ready reads.
        # Skipping adapter trimming keeps the official workflow within a
        # 36-GB workstation while preserving alignment, methylation calling,
        # assay QC, aggregation, and output reload.
        "skip_trimming": True,
    }
    return METHYLSEQ, "wgbs", params, {"downloads": downloads}


def _clipseq_fixture(root: Path) -> tuple[NfCorePipelineSpec, str, dict[str, Any], dict[str, Any]]:
    downloads: list[dict[str, Any]] = []
    samplesheet = root / "metadata.csv"
    source = _raw_url("clipseq", "metadata.csv")
    _rewrite_samplesheet(
        source,
        samplesheet,
        url_columns=("fastq",),
        branch="clipseq",
        downloads=downloads,
    )
    fasta = root / "chr20.fa.gz"
    downloads.append(_download(_raw_url("clipseq", "reference/chr20.fa.gz"), fasta))
    params = {
        "input": str(samplesheet.resolve()),
        "fasta": str(fasta.resolve()),
        "smrna_org": "human",
        "max_cpus": 2,
        "max_memory": "6.GB",
        "max_time": "6.h",
    }
    return CLIPSEQ, "iclip", params, {"downloads": downloads}


def _hic_fixture(root: Path) -> tuple[NfCorePipelineSpec, str, dict[str, Any], dict[str, Any]]:
    downloads: list[dict[str, Any]] = []
    samplesheet = root / "samplesheet.csv"
    source = (
        "https://raw.githubusercontent.com/nf-core/hic/"
        f"{HIC.revision_commit}/assets/samplesheet.csv"
    )
    _rewrite_samplesheet(
        source,
        samplesheet,
        url_columns=("fastq_1", "fastq_2"),
        branch="hic",
        downloads=downloads,
    )
    fasta = root / "W303_SGD_2015_JRIU00000000.fsa"
    downloads.append(
        _download(_raw_url("hic", "reference/W303_SGD_2015_JRIU00000000.fsa"), fasta)
    )
    params = {
        "input": str(samplesheet.resolve()),
        "fasta": str(fasta.resolve()),
        "digestion": "hindiii",
        "min_mapq": 10,
        "min_restriction_fragment_size": 100,
        "max_restriction_fragment_size": 100000,
        "min_insert_size": 100,
        "max_insert_size": 600,
        "bin_size": "2000,1000",
        "res_dist_decay": "1000",
        "res_tads": "1000",
        "tads_caller": "insulation,hicexplorer",
        "res_compartments": "2000",
        "max_cpus": 2,
        "max_memory": "4.GB",
        "max_time": "1.h",
    }
    return HIC, "hi-c", params, {"downloads": downloads}


CASES = {
    "methylseq": _methylseq_fixture,
    "clipseq": _clipseq_fixture,
    "hic": _hic_fixture,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=sorted(CASES))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--nextflow")
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    if workspace.exists():
        raise PublicCaseError(f"workspace must be new: {workspace}")
    workspace.mkdir(parents=True)
    fixture_root = workspace / "fixture"
    fixture_root.mkdir()
    spec, assay, params, fixture = CASES[args.case](fixture_root)
    request = {
        "schema_version": 1,
        "module_id": spec.module_id,
        "assay": assay,
        "engine_profile": "docker",
        "official_test_profile": False,
        "resume": False,
        "resource_limits": {"cpus": 4, "memory": "30.GB", "time": "6.h"},
        "pipeline_params": params,
    }
    raw_report_path = workspace / "raw-execution-report.json"
    nextflow = args.nextflow
    if nextflow is None:
        runtime = "22.10.8" if args.case in {"clipseq", "hic"} else "25.04.8"
        nextflow = str(Path.home() / f".cache/biomed-workbench/nextflow-runtime-{runtime}/nextflow")
    report = execute_nfcore(
        request,
        spec=spec,
        output_dir=workspace / "run",
        report_path=raw_report_path,
        nextflow=nextflow,
    )
    report["public_fixture"] = {
        "pipeline_revision": spec.revision,
        "pipeline_commit": spec.revision_commit,
        "test_data_commits": {args.case: TEST_DATA_COMMITS[args.case]},
        **fixture,
    }
    report["public_case_id"] = f"nfcore-{args.case}-{spec.revision}-checksum-bound-minimal-v1"
    raw_report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": report.get("passed"),
        "case": args.case,
        "module_id": spec.module_id,
        "assay": assay,
        "report": str(raw_report_path),
        "scientific_file_count": report.get("outputs", {}).get("scientific_file_count"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
