"""Pinned nf-core execution with schema, provenance, and output-reload gates.

This implementation deliberately owns only workflow execution and evidence
capture. It never installs Nextflow, starts a container service, edits a
pipeline, or turns a failed workflow into a successful scientific result.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class NfCoreExecutionError(ValueError):
    """Raised when an nf-core request or observed output violates the contract."""


@dataclass(frozen=True)
class NfCorePipelineSpec:
    module_id: str
    assays: tuple[str, ...]
    pipeline: str
    revision: str
    revision_commit: str
    minimum_nextflow_version: str
    schema_url: str
    schema_sha256: str
    samplesheet_columns: tuple[str, ...]
    samplesheet_required_columns: tuple[str, ...]
    samplesheet_enum_columns: dict[str, tuple[str, ...]]
    result_groups: dict[str, tuple[str, ...]]
    source_columns: tuple[str, ...] = ("fastq_1", "fastq_2")
    engine_profiles: tuple[str, ...] = (
        "docker",
        "mamba",
        "conda",
        "singularity",
        "apptainer",
        "podman",
    )


RIBOSEQ = NfCorePipelineSpec(
    module_id="bulk-ribosome-profiling",
    assays=("ribo-seq",),
    pipeline="nf-core/riboseq",
    revision="1.2.0",
    revision_commit="74ab1ea2668ee9a221a5c96c86b2a6ee1b2d2f2f",
    minimum_nextflow_version="25.04.8",
    schema_url="https://raw.githubusercontent.com/nf-core/riboseq/1.2.0/nextflow_schema.json",
    schema_sha256="7166a8dcb945059868333d3ffd56cbc794a07ad1c2e2e999283d32fda68e116e",
    samplesheet_columns=("sample", "fastq_1", "fastq_2", "strandedness", "type"),
    samplesheet_required_columns=("sample", "fastq_1", "strandedness", "type"),
    samplesheet_enum_columns={
        "strandedness": ("forward", "reverse", "unstranded", "auto"),
        "type": ("riboseq", "rnaseq", "tiseq"),
    },
    result_groups={
        "multiqc": ("multiqc/**/multiqc_report.html",),
        "pipeline_info": ("pipeline_info/*",),
        "ribo_qc": ("riboseq_qc/ribotish/*_qual.txt", "ribowaltz/*.best_offset.txt"),
        "orf_calls": ("orf_predictions/ribotish/*_pred.txt", "orf_predictions/ribotricer/*_translating_ORFs.tsv"),
        "quantification": ("quantification/**/*",),
    },
)


NASCENT = NfCorePipelineSpec(
    module_id="bulk-nascent-transcription",
    assays=("gro-seq", "pro-seq"),
    pipeline="nf-core/nascent",
    revision="2.3.0",
    revision_commit="7d4fe61975015f652c271886e661764b05cfd3bf",
    minimum_nextflow_version="24.04.2",
    schema_url="https://raw.githubusercontent.com/nf-core/nascent/2.3.0/nextflow_schema.json",
    schema_sha256="4ba0638668088b749c93a6036ec6373f42aeb4e9775ae91b7318b8e4f2cc9958",
    samplesheet_columns=("sample", "fastq_1", "fastq_2"),
    samplesheet_required_columns=("sample", "fastq_1"),
    samplesheet_enum_columns={},
    result_groups={
        "multiqc": ("multiqc/multiqc_report.html",),
        "pipeline_info": ("pipeline_info/*",),
        "coverage": ("coverage_graphs/*.bigWig",),
        "transcription_units": (
            "transcript_identification/homer/**/*",
            "transcript_identification/grohmm/**/*",
            "transcript_identification/pints/**/*",
        ),
        "quantification": (
            "quantification/gene/*.featureCounts.txt",
            "quantification/nascent/*.featureCounts.txt",
        ),
    },
)


CLIPSEQ = NfCorePipelineSpec(
    module_id="bulk-rbp-rna-binding",
    assays=("eclip", "iclip", "hits-clip", "par-clip"),
    pipeline="nf-core/clipseq",
    revision="1.0.0",
    revision_commit="45ae3c0b9b16206b687f4a645e1643c85b3f1ab4",
    minimum_nextflow_version="20.04.0",
    schema_url="https://raw.githubusercontent.com/nf-core/clipseq/1.0.0/nextflow_schema.json",
    schema_sha256="1b499a1b3c7aad66212839f278b3fea2b163526589f719110d94dde31a1d2a4d",
    samplesheet_columns=("sample", "fastq"),
    samplesheet_required_columns=("sample", "fastq"),
    samplesheet_enum_columns={},
    result_groups={
        "multiqc": ("multiqc/*multiqc_report.html",),
        "pipeline_info": ("pipeline_info/*",),
        "crosslinks": ("xlinks/*.xl.bed.gz", "xlinks/*.xl.bedgraph.gz"),
        "clip_qc": ("clipqc/*.tsv", "rseqc/*.read_distribution.txt"),
        "peaks": (
            "icount/*.peaks.bed.gz",
            "paraclu/*.peaks.bed.gz",
            "pureclip/*.peaks.bed.gz",
            "piranha/*.peaks.bed.gz",
        ),
    },
    source_columns=("fastq",),
)


METHYLSEQ = NfCorePipelineSpec(
    module_id="bulk-dna-methylation",
    assays=("wgbs", "rrbs", "em-seq"),
    pipeline="nf-core/methylseq",
    revision="4.2.0",
    revision_commit="5aa56467a85a5e2d6795ea72dfa5a5f0c9babc23",
    minimum_nextflow_version="25.04.0",
    schema_url="https://raw.githubusercontent.com/nf-core/methylseq/4.2.0/nextflow_schema.json",
    schema_sha256="d36c0badea1d18fe483a5736d5f36add86e34b03bc8fd7bd958769a89581239f",
    samplesheet_columns=("sample", "fastq_1", "fastq_2", "genome"),
    samplesheet_required_columns=("sample", "fastq_1"),
    samplesheet_enum_columns={},
    result_groups={
        "multiqc": ("multiqc/*/multiqc_report.html", "multiqc/*multiqc_report.html"),
        "pipeline_info": ("pipeline_info/*",),
        "methylation_calls": (
            "bismark/methylation_calls/**/*",
            "methyldackel/**/*",
            "rastair/call/**/*",
            "rastair/methylkit/**/*",
        ),
        "mbias": (
            "bismark/methylation_calls/mbias/**/*",
            "methyldackel/mbias/**/*",
            "rastair/mbias/**/*",
        ),
        "alignment_qc": (
            "bismark/alignments/logs/*",
            "bwameth/alignments/samtools_stats/*",
            "bwamem/alignments/samtools_stats/*",
        ),
    },
)


HIC = NfCorePipelineSpec(
    module_id="bulk-three-dimensional-genome",
    assays=("hi-c", "micro-c"),
    pipeline="nf-core/hic",
    revision="2.1.0",
    revision_commit="fe4ac656317d24c37e81e7940a526ed9ea812f8e",
    minimum_nextflow_version="22.10.1",
    schema_url="https://raw.githubusercontent.com/nf-core/hic/2.1.0/nextflow_schema.json",
    schema_sha256="430d2bb74c6e2d151591d476c872e54415e420b0b5d62d293a1ba947d44ebce5",
    samplesheet_columns=("sample", "fastq_1", "fastq_2"),
    samplesheet_required_columns=("sample", "fastq_1", "fastq_2"),
    samplesheet_enum_columns={},
    result_groups={
        "multiqc": ("multiqc/*multiqc_report.html", "multiqc/**/*multiqc_report.html"),
        "pipeline_info": ("pipeline_info/*",),
        "valid_pairs": ("hicpro/valid_pairs/**/*",),
        "contact_matrices": (
            "contact_maps/cool/*.cool",
            "contact_maps/cool/*.mcool",
            "hicpro/matrix/raw/**/*",
            "hicpro/matrix/iced/**/*",
        ),
        "distance_decay": ("distance_decay/**/*",),
    },
)


SPECS = {
    spec.module_id: spec
    for spec in (RIBOSEQ, NASCENT, CLIPSEQ, METHYLSEQ, HIC)
}
_SAFE_VALUE = (str, int, float, bool, type(None), list)
_FILE_PARAMETER_NAMES = {
    "input",
    "contrasts",
    "fasta",
    "gtf",
    "gff",
    "transcript_fasta",
    "ribo_database_manifest",
    "bbsplit_fasta_list",
    "filter_bed",
    "intersect_bed",
    "gene_bed",
    "hisat2_index",
}
_RIBOSEQ_TEST_DATA_COMMIT = "49d698638283eadf3f1305c2ba3c710d7e8038b2"
_MODULE_TEST_DATA_COMMIT = "4aec2497eb3a8d0f9ecdd7a6294320abfa93ddcc"
_SORTMERNA_TEST_DATA_COMMIT = "90cdf6ce459e9477c5d0de9a5daab025f49f3cc6"
_NASCENT_TEST_DATA_COMMIT = "a9010a0c5ff942987cb06f77d09c2b1dbebddb0c"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_symlink() or not resolved.is_file():
        raise NfCoreExecutionError(f"{label} must be a readable, non-symlink regular file: {resolved}")
    return resolved


def fetch_official_schema(spec: NfCorePipelineSpec, *, timeout_seconds: int = 60) -> dict[str, Any]:
    request = urllib.request.Request(
        spec.schema_url,
        headers={"User-Agent": "biomed-workbench/0.2 nf-core-schema-verifier"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()
    observed = _sha256_bytes(payload)
    if observed != spec.schema_sha256:
        raise NfCoreExecutionError(
            f"official schema digest changed for {spec.pipeline} {spec.revision}: "
            f"expected {spec.schema_sha256}, observed {observed}"
        )
    schema = json.loads(payload)
    if not isinstance(schema, dict):
        raise NfCoreExecutionError("official nf-core parameter schema is not a JSON object")
    return schema


def _download(url: str, destination: Path, *, timeout_seconds: int = 180) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "biomed-workbench/0.2 public-workflow-fixture"},
    )
    temporary = destination.with_name(destination.name + ".part")
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response, temporary.open("wb") as handle:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            handle.write(block)
            digest.update(block)
            size += len(block)
    if size == 0:
        temporary.unlink(missing_ok=True)
        raise NfCoreExecutionError(f"public fixture download was empty: {url}")
    temporary.replace(destination)
    return {
        "source_url": url,
        "path": str(destination),
        "bytes": size,
        "sha256": digest.hexdigest(),
    }


def _pinned_test_url(url: str) -> str:
    prefix = "https://raw.githubusercontent.com/nf-core/test-datasets/"
    if not url.startswith(prefix):
        return url
    remainder = url[len(prefix):]
    branch, separator, path = remainder.partition("/")
    if not separator:
        raise NfCoreExecutionError(f"invalid nf-core test-data URL: {url}")
    commits = {
        "riboseq": _RIBOSEQ_TEST_DATA_COMMIT,
        "modules": _MODULE_TEST_DATA_COMMIT,
        "nascent": _NASCENT_TEST_DATA_COMMIT,
    }
    commit = commits.get(branch)
    if not commit:
        raise NfCoreExecutionError(f"unreviewed nf-core test-data branch: {branch}")
    return f"{prefix}{commit}/{path}"


def materialize_riboseq_official_test(
    destination: Path,
    *,
    gffread: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze the official 1.2.0 test fixture as local checksum-bound inputs.

    nf-core/riboseq 1.2.0 declares remote URLs in ``conf/test.config``.
    Materializing them avoids proxy- and filesystem-provider-dependent URL
    validation while retaining the exact official fixture at pinned commits.
    """
    destination.mkdir(parents=True, exist_ok=False)
    downloads: list[dict[str, Any]] = []
    samplesheet_url = (
        "https://raw.githubusercontent.com/nf-core/test-datasets/"
        f"{_RIBOSEQ_TEST_DATA_COMMIT}/samplesheet/samplesheet.csv"
    )
    with urllib.request.urlopen(
        urllib.request.Request(samplesheet_url, headers={"User-Agent": "biomed-workbench/0.2"}),
        timeout=60,
    ) as response:
        samplesheet_bytes = response.read()
    if _sha256_bytes(samplesheet_bytes) != "5c5752b994205ff3efa76d27d9505ed4eaaebd44618fa9a0bb90ae7c4097789c":
        raise NfCoreExecutionError("pinned nf-core/riboseq samplesheet digest differs from reviewed fixture")
    rows = list(csv.DictReader(io.StringIO(samplesheet_bytes.decode("utf-8-sig"))))
    if not rows:
        raise NfCoreExecutionError("official nf-core/riboseq samplesheet is empty")
    fastq_dir = destination / "fastq"
    fastq_dir.mkdir()
    for row in rows:
        for column in ("fastq_1", "fastq_2"):
            original = str(row.get(column, "")).strip()
            if not original:
                continue
            pinned = _pinned_test_url(original)
            target = fastq_dir / Path(urllib.parse.urlparse(pinned).path).name
            if not target.exists():
                downloads.append(_download(pinned, target))
            row[column] = str(target.resolve())
    samplesheet = destination / "samplesheet.csv"
    with samplesheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    contrasts_url = (
        "https://raw.githubusercontent.com/nf-core/test-datasets/"
        f"{_RIBOSEQ_TEST_DATA_COMMIT}/contrasts.csv"
    )
    contrasts = destination / "contrasts.csv"
    downloads.append(_download(contrasts_url, contrasts))
    fasta_url = (
        "https://raw.githubusercontent.com/nf-core/test-datasets/"
        f"{_MODULE_TEST_DATA_COMMIT}/data/genomics/homo_sapiens/riboseq_expression/"
        "Homo_sapiens.GRCh38.dna.chromosome.20.fa.gz"
    )
    fasta = destination / "Homo_sapiens.GRCh38.dna.chromosome.20.fa.gz"
    downloads.append(_download(fasta_url, fasta))
    gtf_url = (
        "https://raw.githubusercontent.com/nf-core/test-datasets/"
        f"{_MODULE_TEST_DATA_COMMIT}/data/genomics/homo_sapiens/riboseq_expression/"
        "Homo_sapiens.GRCh38.111_chr20.gtf"
    )
    gtf = destination / "Homo_sapiens.GRCh38.111_chr20.gtf"
    downloads.append(_download(gtf_url, gtf))
    rrna_url = (
        "https://raw.githubusercontent.com/biocore/sortmerna/"
        f"{_SORTMERNA_TEST_DATA_COMMIT}/data/rRNA_databases/rfam-5.8s-database-id98.fasta"
    )
    rrna = destination / "rfam-5.8s-database-id98.fasta"
    downloads.append(_download(rrna_url, rrna))
    rrna_manifest = destination / "rrna-db.txt"
    rrna_manifest.write_text(str(rrna.resolve()) + "\n", encoding="utf-8")
    transcript_fasta = None
    derived_tools: list[dict[str, Any]] = []
    if gffread:
        resolved_gffread = shutil.which(gffread) if os.sep not in gffread else str(_stable_file(Path(gffread), "gffread"))
        if not resolved_gffread:
            raise NfCoreExecutionError(f"gffread executable not found: {gffread}")
        version = subprocess.run(
            [resolved_gffread, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if version.returncode != 0:
            raise NfCoreExecutionError("gffread version detection failed")
        genome_fasta = destination / "Homo_sapiens.GRCh38.dna.chromosome.20.fa"
        import gzip

        with gzip.open(fasta, "rb") as source, genome_fasta.open("wb") as target:
            shutil.copyfileobj(source, target)
        transcript_fasta = destination / "Homo_sapiens.GRCh38.111_chr20.transcripts.fa"
        completed = subprocess.run(
            [resolved_gffread, str(gtf), "-g", str(genome_fasta), "-w", str(transcript_fasta)],
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        if completed.returncode != 0 or not transcript_fasta.is_file() or transcript_fasta.stat().st_size == 0:
            raise NfCoreExecutionError(f"gffread transcript FASTA derivation failed: {completed.stderr[-3000:]}")
        derived_tools.append({
            "name": "gffread",
            "version": (version.stdout + version.stderr).strip(),
            "path": resolved_gffread,
            "command_argv": [
                resolved_gffread,
                str(gtf),
                "-g",
                str(genome_fasta),
                "-w",
                str(transcript_fasta),
            ],
            "output": {
                "path": str(transcript_fasta),
                "bytes": transcript_fasta.stat().st_size,
                "sha256": sha256(transcript_fasta),
            },
        })
    downloads.extend([
        {
            "source_url": samplesheet_url,
            "path": str(samplesheet),
            "bytes": samplesheet.stat().st_size,
            "sha256": sha256(samplesheet),
            "rewritten_to_local_immutable_paths": True,
        },
        {
            "source_url": (
                "https://raw.githubusercontent.com/nf-core/test-datasets/"
                f"{_RIBOSEQ_TEST_DATA_COMMIT}/testdata/rrna-db.txt"
            ),
            "path": str(rrna_manifest),
            "bytes": rrna_manifest.stat().st_size,
            "sha256": sha256(rrna_manifest),
            "rewritten_to_local_immutable_paths": True,
        },
    ])
    parameters = {
        "input": str(samplesheet.resolve()),
        "contrasts": str(contrasts.resolve()),
        "ribo_database_manifest": str(rrna_manifest.resolve()),
        "fasta": str(fasta.resolve()),
        "gtf": str(gtf.resolve()),
        "min_trimmed_reads": 1000,
        "skip_ribotricer": True,
        "extra_fqlint_args": "--disable-validator P001 --disable-validator S007",
        "igenomes_ignore": True,
    }
    if transcript_fasta is not None:
        parameters["transcript_fasta"] = str(transcript_fasta.resolve())
    fixture = {
        "pipeline_revision": RIBOSEQ.revision,
        "pipeline_commit": RIBOSEQ.revision_commit,
        "test_data_commits": {
            "riboseq": _RIBOSEQ_TEST_DATA_COMMIT,
            "modules": _MODULE_TEST_DATA_COMMIT,
            "sortmerna": _SORTMERNA_TEST_DATA_COMMIT,
        },
        "download_count": len(downloads),
        "downloads": sorted(downloads, key=lambda item: item["path"]),
        "derived_tools": derived_tools,
    }
    return parameters, fixture


def materialize_nascent_official_test(
    destination: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze the nf-core/nascent 2.3.0 minimal GRO-seq test as local inputs."""
    destination.mkdir(parents=True, exist_ok=False)
    downloads: list[dict[str, Any]] = []
    pipeline_base = (
        "https://raw.githubusercontent.com/nf-core/nascent/"
        f"{NASCENT.revision_commit}"
    )
    samplesheet_url = f"{pipeline_base}/assets/samplesheet.csv"
    with urllib.request.urlopen(
        urllib.request.Request(samplesheet_url, headers={"User-Agent": "biomed-workbench/0.2"}),
        timeout=60,
    ) as response:
        samplesheet_bytes = response.read()
    if _sha256_bytes(samplesheet_bytes) != "2f2fc467d5b6a69fdd72423fa11acd58aa0267f9336bc01ec937fcdb017c735a":
        raise NfCoreExecutionError("pinned nf-core/nascent samplesheet digest differs from reviewed fixture")
    rows = list(csv.DictReader(io.StringIO(samplesheet_bytes.decode("utf-8-sig"))))
    if not rows:
        raise NfCoreExecutionError("official nf-core/nascent samplesheet is empty")
    fastq_dir = destination / "fastq"
    fastq_dir.mkdir()
    for row in rows:
        for column in ("fastq_1", "fastq_2"):
            original = str(row.get(column, "")).strip()
            if not original:
                continue
            pinned = _pinned_test_url(original)
            target = fastq_dir / Path(urllib.parse.urlparse(pinned).path).name
            if not target.exists():
                downloads.append(_download(pinned, target))
            row[column] = str(target.resolve())
    samplesheet = destination / "samplesheet.csv"
    with samplesheet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    reference_base = (
        "https://raw.githubusercontent.com/nf-core/test-datasets/"
        f"{_NASCENT_TEST_DATA_COMMIT}/reference"
    )
    reference_files = {
        "fasta": ("GRCh38_chr21.fa", f"{reference_base}/GRCh38_chr21.fa"),
        "gtf": ("genes_chr21.gtf", f"{reference_base}/genes_chr21.gtf"),
        "hisat2_index": (
            "GRCh38_chr21_hisat2.tar.gz",
            f"{reference_base}/GRCh38_chr21_hisat2.tar.gz",
        ),
        "filter_bed": (
            "unwanted_region.bed",
            f"{pipeline_base}/tests/config/unwanted_region.bed",
        ),
        "intersect_bed": (
            "wanted_region.bed",
            f"{pipeline_base}/tests/config/wanted_region.bed",
        ),
    }
    resolved: dict[str, Path] = {}
    for parameter, (filename, url) in reference_files.items():
        target = destination / filename
        downloads.append(_download(url, target))
        resolved[parameter] = target.resolve()
    expected_bed_digests = {
        "filter_bed": "4c63b4f2d8fa2f5f6fc1e84568b37642813e5f79cf2e879a1f1b1142292911a3",
        "intersect_bed": "666b0f04525011660cebea40c5f82681677b793f514556fdb2b4cc0636e6b9b0",
    }
    for parameter, expected in expected_bed_digests.items():
        if sha256(resolved[parameter]) != expected:
            raise NfCoreExecutionError(f"pinned nf-core/nascent {parameter} digest differs from reviewed fixture")
    downloads.append({
        "source_url": samplesheet_url,
        "path": str(samplesheet),
        "bytes": samplesheet.stat().st_size,
        "sha256": sha256(samplesheet),
        "rewritten_to_local_immutable_paths": True,
    })
    parameters = {
        "input": str(samplesheet.resolve()),
        **{name: str(path) for name, path in resolved.items()},
        "assay_type": "GROseq",
        "skip_grohmm": True,
        "grohmm_min_uts": 5,
        "grohmm_max_uts": 10,
        "grohmm_min_ltprobb": -100,
        "grohmm_max_ltprobb": -150,
        "igenomes_ignore": True,
    }
    fixture = {
        "pipeline_revision": NASCENT.revision,
        "pipeline_commit": NASCENT.revision_commit,
        "test_data_commits": {"nascent": _NASCENT_TEST_DATA_COMMIT},
        "download_count": len(downloads),
        "downloads": sorted(downloads, key=lambda item: item["path"]),
        "derived_tools": [],
    }
    return parameters, fixture


def schema_parameters(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    definitions = schema.get("$defs") or schema.get("definitions")
    if not isinstance(definitions, dict):
        raise NfCoreExecutionError("official nf-core parameter schema has no definitions object")
    parameters: dict[str, dict[str, Any]] = {}
    for group in definitions.values():
        if not isinstance(group, dict) or not isinstance(group.get("properties"), dict):
            continue
        for name, definition in group["properties"].items():
            if not isinstance(name, str) or not isinstance(definition, dict):
                raise NfCoreExecutionError("official nf-core parameter schema contains an invalid property")
            if name in parameters and parameters[name] != definition:
                raise NfCoreExecutionError(f"official nf-core schema defines parameter twice: {name}")
            parameters[name] = definition
    if not parameters:
        raise NfCoreExecutionError("official nf-core parameter schema exposes no adjustable parameters")
    return parameters


def _validate_scalar_type(name: str, value: Any, definition: dict[str, Any]) -> None:
    if not isinstance(value, _SAFE_VALUE) or isinstance(value, dict):
        raise NfCoreExecutionError(f"pipeline parameter {name} has an unsupported nested value")
    expected = definition.get("type")
    valid = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "array": isinstance(value, list),
    }.get(str(expected), True)
    if not valid:
        raise NfCoreExecutionError(f"pipeline parameter {name} does not match official type {expected}")
    if "enum" in definition and value not in definition["enum"]:
        raise NfCoreExecutionError(f"pipeline parameter {name} is outside the official enum")


def validate_pipeline_parameters(
    spec: NfCorePipelineSpec,
    parameters: dict[str, Any],
    schema: dict[str, Any],
    *,
    official_test_profile: bool,
) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        raise NfCoreExecutionError("pipeline_params must be an object")
    definitions = schema_parameters(schema)
    forbidden = {"outdir", "help", "help_full", "version", "show_hidden"}
    unknown = sorted(set(parameters) - set(definitions))
    if unknown:
        raise NfCoreExecutionError("unknown parameter(s) for the pinned official schema: " + ", ".join(unknown))
    blocked = sorted(set(parameters) & forbidden)
    if blocked:
        raise NfCoreExecutionError("runner-owned or non-scientific parameter(s) cannot be supplied: " + ", ".join(blocked))
    for name, value in parameters.items():
        _validate_scalar_type(name, value, definitions[name])
    if not official_test_profile and "input" not in parameters:
        raise NfCoreExecutionError("project execution requires pipeline_params.input")
    if official_test_profile and "input" in parameters:
        raise NfCoreExecutionError("official test-profile execution must use the pipeline-owned test samplesheet")
    normalized = dict(parameters)
    for name in sorted(set(normalized) & _FILE_PARAMETER_NAMES):
        value = normalized[name]
        if not isinstance(value, str) or value.startswith(("http://", "https://", "ftp://")):
            raise NfCoreExecutionError(
                f"project parameter {name} must be a local immutable file; remote inputs are reserved for the pinned official test profile"
            )
        normalized[name] = str(_stable_file(Path(value), name))
    return normalized


def validate_samplesheet(path: Path, spec: NfCorePipelineSpec) -> dict[str, Any]:
    path = _stable_file(path, "samplesheet")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = tuple(reader.fieldnames or ())
        missing = sorted(set(spec.samplesheet_required_columns) - set(headers))
        if missing:
            raise NfCoreExecutionError("samplesheet is missing required column(s): " + ", ".join(missing))
        rows = list(reader)
    if not rows:
        raise NfCoreExecutionError("samplesheet has no sample rows")
    sample_ids: set[str] = set()
    source_files: dict[str, dict[str, Any]] = {}
    type_counts: dict[str, int] = {}
    for index, row in enumerate(rows, start=2):
        sample = str(row.get("sample", "")).strip()
        if not sample or re.search(r"\s", sample):
            raise NfCoreExecutionError(f"samplesheet row {index} has an invalid sample identifier")
        sample_ids.add(sample)
        for column in spec.samplesheet_required_columns:
            if not str(row.get(column, "")).strip():
                raise NfCoreExecutionError(f"samplesheet row {index} has an empty required value: {column}")
        for column, allowed in spec.samplesheet_enum_columns.items():
            value = str(row.get(column, "")).strip()
            if value not in allowed:
                raise NfCoreExecutionError(f"samplesheet row {index} has unsupported {column}: {value}")
            if column == "type":
                type_counts[value] = type_counts.get(value, 0) + 1
        for column in spec.source_columns:
            value = str(row.get(column, "")).strip()
            if not value:
                continue
            if value.startswith(("http://", "https://", "ftp://")):
                raise NfCoreExecutionError(
                    f"samplesheet row {index} uses a remote FASTQ; project runs require local immutable FASTQ files"
                )
            source = _stable_file(Path(value), f"samplesheet row {index} {column}")
            if not source.name.endswith((".fastq.gz", ".fq.gz")):
                raise NfCoreExecutionError(f"samplesheet row {index} {column} is not a gzipped FASTQ")
            source_files[str(source)] = {
                "path": str(source),
                "bytes": source.stat().st_size,
                "sha256": sha256(source),
            }
    if spec is RIBOSEQ and type_counts.get("riboseq", 0) == 0:
        raise NfCoreExecutionError("Ribo-seq samplesheet contains no type=riboseq rows")
    return {
        "path": str(path),
        "sha256": sha256(path),
        "row_count": len(rows),
        "unique_sample_count": len(sample_ids),
        "type_counts": dict(sorted(type_counts.items())),
        "source_files": list(source_files.values()),
    }


def _parse_version(text: str) -> tuple[int, ...]:
    match = re.search(r"version\s+([0-9]+(?:\.[0-9]+)+)", text, flags=re.IGNORECASE)
    if not match:
        raise NfCoreExecutionError(f"could not parse Nextflow version from: {text[-500:]}")
    return tuple(int(part) for part in match.group(1).split("."))


def inspect_runtime(nextflow: str, profile: str, minimum_version: str) -> dict[str, Any]:
    resolved = shutil.which(nextflow) if os.sep not in nextflow else str(_stable_file(Path(nextflow), "Nextflow"))
    if not resolved:
        raise NfCoreExecutionError(f"Nextflow executable not found: {nextflow}")
    completed = subprocess.run(
        [resolved, "-version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()
    if completed.returncode != 0:
        raise NfCoreExecutionError(f"Nextflow version detection failed: {output[-1000:]}")
    observed = _parse_version(output)
    required = tuple(int(part) for part in minimum_version.split("."))
    if observed < required:
        raise NfCoreExecutionError(
            f"Nextflow {'.'.join(map(str, observed))} is below required {minimum_version}"
        )
    runtime: dict[str, Any] = {
        "nextflow_path": resolved,
        "nextflow_version": ".".join(map(str, observed)),
        "engine_profile": profile,
    }
    probe_by_profile = {
        "docker": ("docker", ["info", "--format", "{{.ServerVersion}}"]),
        "podman": ("podman", ["info", "--format", "json"]),
        "mamba": ("mamba", ["--version"]),
        "conda": ("conda", ["--version"]),
        "singularity": ("singularity", ["--version"]),
        "apptainer": ("apptainer", ["--version"]),
    }
    executable, probe = probe_by_profile[profile]
    dependency = shutil.which(executable)
    if not dependency:
        raise NfCoreExecutionError(f"{profile} execution profile is unavailable: {executable} not found")
    checked = subprocess.run(
        [dependency, *probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if checked.returncode != 0:
        raise NfCoreExecutionError(
            f"{profile} runtime is installed but not operational: {(checked.stdout + checked.stderr)[-1200:]}"
        )
    runtime["profile_runtime_path"] = dependency
    runtime["profile_runtime_version"] = (checked.stdout + checked.stderr).strip().splitlines()[0]
    return runtime


def validate_host_execution_path(
    output_dir: Path,
    *,
    spec: NfCorePipelineSpec,
    profile: str,
    architecture_profile: str | None,
) -> None:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        if spec is RIBOSEQ and profile in {"mamba", "conda"}:
            raise NfCoreExecutionError(
                "nf-core/riboseq 1.2.0 cannot use Conda/Mamba on macOS ARM64 because its pinned "
                "SortMeRNA 4.3.7 environment has no compatible build; use Docker with "
                "container_architecture=linux/arm64"
            )
        if spec is RIBOSEQ and profile == "docker" and architecture_profile != "arm64":
            raise NfCoreExecutionError(
                "nf-core/riboseq 1.2.0 on macOS ARM64 requires the official arm64/Wave profile"
            )
    if profile == "docker":
        context = subprocess.run(
            ["docker", "context", "show"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if context.returncode == 0 and context.stdout.strip() == "colima":
            resolved = output_dir.expanduser().resolve()
            try:
                resolved.relative_to(Path.home().resolve())
            except ValueError as exc:
                raise NfCoreExecutionError(
                    "Colima can execute only from a shared user-directory workspace; "
                    f"the requested output is not shared: {resolved}"
                ) from exc


def _validate_request(request: dict[str, Any], spec: NfCorePipelineSpec) -> tuple[str, bool, bool, str | None]:
    if request.get("schema_version") != 1:
        raise NfCoreExecutionError("request.schema_version must be 1")
    if request.get("module_id") != spec.module_id:
        raise NfCoreExecutionError("request.module_id does not match the packaged workflow")
    assay = str(request.get("assay", "")).strip().lower()
    if assay not in spec.assays:
        raise NfCoreExecutionError(f"assay {assay!r} is not implemented by this pinned workflow")
    profile = str(request.get("engine_profile", "")).strip().lower()
    if profile not in spec.engine_profiles:
        raise NfCoreExecutionError(f"unsupported execution profile: {profile}")
    official_test = request.get("official_test_profile", False)
    resume = request.get("resume", False)
    if not isinstance(official_test, bool) or not isinstance(resume, bool):
        raise NfCoreExecutionError("official_test_profile and resume must be booleans")
    container_architecture = request.get("container_architecture")
    if container_architecture not in (None, "linux/amd64", "linux/arm64"):
        raise NfCoreExecutionError("container_architecture must be omitted, linux/amd64, or linux/arm64")
    if container_architecture and profile != "docker":
        raise NfCoreExecutionError("container_architecture override is supported only with the Docker profile")
    if container_architecture and spec not in (RIBOSEQ, NASCENT):
        raise NfCoreExecutionError(
            f"container_architecture override is not validated for {spec.pipeline} {spec.revision}"
        )
    if spec is NASCENT:
        requested_assay_type = request.get("pipeline_params", {}).get("assay_type")
        expected = {"gro-seq": "GROseq", "pro-seq": "PROseq"}[assay]
        if not official_test and requested_assay_type != expected:
            raise NfCoreExecutionError(f"{assay} requires pipeline_params.assay_type={expected!r}")
        if official_test and assay != "gro-seq":
            raise NfCoreExecutionError("nf-core/nascent 2.3.0 official minimal test profile is GRO-seq")
    elif spec is METHYLSEQ:
        parameters = request.get("pipeline_params", {})
        if assay == "rrbs" and parameters.get("rrbs") is not True:
            raise NfCoreExecutionError("rrbs requires pipeline_params.rrbs=true")
        if assay == "em-seq" and parameters.get("em_seq") is not True:
            raise NfCoreExecutionError("em-seq requires pipeline_params.em_seq=true")
        if assay == "wgbs" and (parameters.get("rrbs") is True or parameters.get("em_seq") is True):
            raise NfCoreExecutionError("wgbs cannot enable RRBS or EM-seq presets")
    elif spec is HIC and assay == "micro-c":
        parameters = request.get("pipeline_params", {})
        if parameters.get("dnase") is not True:
            raise NfCoreExecutionError(
                "micro-c preprocessing requires pipeline_params.dnase=true so restriction-fragment filters are disabled"
            )
        if not isinstance(parameters.get("min_cis_dist"), int) or parameters["min_cis_dist"] < 0:
            raise NfCoreExecutionError("micro-c requires an explicit nonnegative pipeline_params.min_cis_dist")
    architecture_profile = None
    if container_architecture == "linux/amd64":
        architecture_profile = "emulate_amd64" if spec is RIBOSEQ else "arm"
    elif container_architecture == "linux/arm64":
        # riboseq ships a pipeline-specific arm64 profile. The pinned nascent
        # workflow does not; only FastQC receives a digest-pinned native image
        # because that process can hang under amd64 emulation.
        architecture_profile = "arm64" if spec is RIBOSEQ else "fastqc_arm64"
    return profile, official_test, resume, architecture_profile


def _build_command(
    spec: NfCorePipelineSpec,
    nextflow_path: str,
    profile: str,
    architecture_profile: str | None,
    official_test: bool,
    resume: bool,
    params_path: Path,
    outdir: Path,
    workdir: Path,
    log_path: Path,
    runtime_config_path: Path | None = None,
) -> list[str]:
    profiles = f"test,{profile}" if official_test else profile
    if architecture_profile and architecture_profile != "fastqc_arm64":
        profiles += f",{architecture_profile}"
    command = [
        nextflow_path,
        "-log",
        str(log_path),
    ]
    if runtime_config_path is not None:
        command.extend(["-c", str(runtime_config_path)])
    command.extend([
        "run",
        spec.pipeline,
        "-r",
        spec.revision,
        "-profile",
        profiles,
        "-params-file",
        str(params_path),
        "-work-dir",
        str(workdir),
    ])
    if resume:
        command.append("-resume")
    return command


def _prepare_runtime_compatibility(
    provenance_dir: Path,
    *,
    spec: NfCorePipelineSpec,
    profile: str,
    architecture_profile: str | None,
    resource_limits: dict[str, Any] | None = None,
) -> tuple[Path | None, list[dict[str, Any]]]:
    """Create narrowly scoped, checksum-bound runtime compatibility controls."""
    blocks: list[str] = []
    records: list[dict[str, Any]] = []
    if resource_limits is not None:
        if not isinstance(resource_limits, dict) or set(resource_limits) != {"cpus", "memory", "time"}:
            raise NfCoreExecutionError("resource_limits must contain exactly cpus, memory, and time")
        cpus = resource_limits["cpus"]
        memory = resource_limits["memory"]
        time = resource_limits["time"]
        if not isinstance(cpus, int) or isinstance(cpus, bool) or cpus < 1:
            raise NfCoreExecutionError("resource_limits.cpus must be a positive integer")
        if not isinstance(memory, str) or re.fullmatch(r"[1-9][0-9]*(?:\.[0-9]+)?\.(?:KB|MB|GB|TB)", memory) is None:
            raise NfCoreExecutionError("resource_limits.memory must use Nextflow units such as 30.GB")
        if not isinstance(time, str) or re.fullmatch(r"[1-9][0-9]*(?:\.[0-9]+)?\.(?:ms|s|m|h|d)", time) is None:
            raise NfCoreExecutionError("resource_limits.time must use Nextflow units such as 6.h")
        blocks.append(
            "process {\n"
            "  resourceLimits = [\n"
            f"    cpus: {cpus},\n"
            f"    memory: {json.dumps(memory)},\n"
            f"    time: {json.dumps(time)}\n"
            "  ]\n"
            "}\n"
        )
        records.append({
            "id": "nfcore-workstation-resource-limits",
            "scope": f"all processes in {spec.pipeline} {spec.revision}",
            "reason": "Cap scheduler reservations to the declared workstation capacity using the official nf-core resourceLimits mechanism.",
            "scientific_parameters_changed": False,
            "limits": dict(resource_limits),
        })
    if spec is NASCENT and profile == "docker" and architecture_profile == "fastqc_arm64":
        fastqc_container = (
            "community.wave.seqera.io/library/fastqc@"
            "sha256:c7cdf1bd0bd7557ba7d0a986f1e907bed45cd54a484f3a81dc5a472abdf318ba"
        )
        container_options = (
            "--platform linux/arm64 "
            "-e MPLCONFIGDIR=/tmp/matplotlib "
            "-e XDG_CACHE_HOME=/tmp/xdg-cache"
        )
        blocks.append(
            "process {\n"
            "  withName: FASTQC {\n"
            f"    container = {json.dumps(fastqc_container)}\n"
            f"    containerOptions = {json.dumps(container_options)}\n"
            "  }\n"
            "}\n"
        )
        records.append({
            "id": "nfcore-nascent-fastqc-arm64-container",
            "scope": "nf-core/nascent 2.3.0 FASTQC processes on ARM64 Docker only",
            "reason": (
                "FastQC 0.12.1 can remain CPU-bound indefinitely under amd64 emulation "
                "for a valid official fixture FASTQ; the same pinned FastQC version in "
                "the nf-core-generated ARM64 image completes the file successfully."
            ),
            "scientific_parameters_changed": False,
            "container": fastqc_container,
        })
    if spec is RIBOSEQ and profile == "docker" and architecture_profile == "arm64":
        source = (
            Path(__file__).resolve().parents[1]
            / "modules"
            / "builtin"
            / RIBOSEQ.module_id
            / "templates"
            / "ribotish_python314_sitecustomize.py"
        )
        source = _stable_file(source, "Ribo-TISH Python 3.14 compatibility shim")
        compat_dir = provenance_dir / "runtime_compat" / "ribotish_python314"
        compat_dir.mkdir(parents=True)
        copied = compat_dir / "sitecustomize.py"
        shutil.copy2(source, copied)
        python_path = str(compat_dir.resolve())
        if "\n" in python_path or "\r" in python_path:
            raise NfCoreExecutionError("runtime compatibility path contains unsupported characters")
        container_options = (
            "--platform linux/arm64 "
            f"-e PYTHONPATH={shlex.quote(python_path)} "
            "-e MPLCONFIGDIR=/tmp/matplotlib "
            "-e XDG_CACHE_HOME=/tmp/xdg-cache"
        )
        blocks.append(
            "process {\n"
            "  withName: /.*RIBOTISH_.*/ {\n"
            f"    containerOptions = {json.dumps(container_options)}\n"
            "  }\n"
            "}\n"
        )
        records.append({
            "id": "ribotish-0.2.7-python-3.14-posix-fork",
            "scope": "nf-core/riboseq 1.2.0 RIBOTISH processes on native ARM64 Docker only",
            "reason": (
                "Python 3.14 changed the POSIX multiprocessing default to forkserver; "
                "Ribo-TISH 0.2.7 prediction workers require inherited parent genome state."
            ),
            "scientific_parameters_changed": False,
            "sitecustomize_sha256": sha256(copied),
        })
    if not blocks:
        return None, []
    config_path = provenance_dir / "runtime_compat.config"
    config_path.write_text("\n".join(blocks), encoding="utf-8")
    config_sha256 = sha256(config_path)
    for record in records:
        record["nextflow_config_sha256"] = config_sha256
    return config_path, records


def _text_rows(path: Path) -> int:
    opener = path.open
    if path.suffix == ".gz":
        import gzip

        opener = lambda mode, encoding: gzip.open(path, mode, encoding=encoding)  # type: ignore[assignment]
    with opener("rt", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip() and not line.startswith("#"))


def reload_output(path: Path) -> dict[str, Any]:
    suffixes = "".join(path.suffixes).lower()
    evidence: dict[str, Any] = {
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }
    if evidence["bytes"] == 0:
        raise NfCoreExecutionError(f"workflow produced an empty output: {path}")
    if suffixes.endswith(".json"):
        json.loads(path.read_text(encoding="utf-8"))
        evidence["reload"] = "json"
    elif suffixes.endswith((".tsv", ".csv", ".txt", ".bed", ".narrowpeak", ".broadpeak", ".tsv.gz", ".csv.gz")):
        evidence["row_count"] = _text_rows(path)
        evidence["reload"] = "delimited-text"
    elif suffixes.endswith((".html", ".htm")):
        head = path.read_text(encoding="utf-8", errors="replace")[:20000].lower()
        if "<html" not in head and "<!doctype html" not in head:
            raise NfCoreExecutionError(f"HTML output failed reload: {path}")
        evidence["reload"] = "html"
    elif suffixes.endswith(".pdf"):
        if path.read_bytes()[:4] != b"%PDF":
            raise NfCoreExecutionError(f"PDF output failed signature validation: {path}")
        evidence["reload"] = "pdf-signature"
    elif suffixes.endswith(".png"):
        if path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            raise NfCoreExecutionError(f"PNG output failed signature validation: {path}")
        evidence["reload"] = "png-signature"
    elif suffixes.endswith((".yml", ".yaml")):
        if ":" not in path.read_text(encoding="utf-8", errors="strict"):
            raise NfCoreExecutionError(f"YAML output failed structural validation: {path}")
        evidence["reload"] = "yaml-structure"
    elif suffixes.endswith((".bigwig", ".bw")):
        if path.read_bytes()[:4] not in (b"\x26\xfc\x8f\x88", b"\x88\x8f\xfc\x26"):
            raise NfCoreExecutionError(f"bigWig output failed signature validation: {path}")
        evidence["reload"] = "bigwig-signature"
    else:
        evidence["reload"] = "nonempty-binary-or-text"
    return evidence


def collect_outputs(outdir: Path, spec: NfCorePipelineSpec) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    groups: dict[str, Any] = {}
    scientific_paths: set[Path] = set()
    for group, patterns in spec.result_groups.items():
        matches: list[Path] = []
        for pattern in patterns:
            matches.extend(path for path in outdir.glob(pattern) if path.is_file())
        matches = sorted(set(matches))
        groups[group] = {
            "patterns": list(patterns),
            "file_count": len(matches),
            "paths": [str(path.relative_to(outdir)) for path in matches],
        }
        scientific_paths.update(matches)
    required = ("multiqc", "pipeline_info")
    missing_required = [group for group in required if groups[group]["file_count"] == 0]
    assay_groups = [group for group in spec.result_groups if group not in required]
    if missing_required:
        raise NfCoreExecutionError("workflow completed without required output group(s): " + ", ".join(missing_required))
    if not any(groups[group]["file_count"] for group in assay_groups):
        raise NfCoreExecutionError("workflow completed without an assay-specific scientific output")
    reloaded = []
    for path in sorted(scientific_paths):
        reloaded.append({"path": str(path.relative_to(outdir)), **reload_output(path)})
    return groups, reloaded


def execute_nfcore(
    request: dict[str, Any],
    *,
    spec: NfCorePipelineSpec,
    output_dir: Path,
    report_path: Path,
    nextflow: str = "nextflow",
    schema: dict[str, Any] | None = None,
    timeout_seconds: int = 172800,
) -> dict[str, Any]:
    # Nextflow runs with ``cwd=output_dir``. Resolve both destinations before
    # constructing config, work, result, and log paths so a caller-supplied
    # relative path cannot be interpreted a second time below that directory.
    output_dir = output_dir.expanduser().resolve()
    report_path = report_path.expanduser().resolve()
    implementation_path = Path(__file__).resolve()
    implementation_sha256 = sha256(implementation_path)
    profile, official_test, resume, architecture_profile = _validate_request(request, spec)
    if output_dir.exists() or output_dir.is_symlink():
        raise NfCoreExecutionError("output-dir must be a new, non-symlink path")
    if report_path.exists() or report_path.is_symlink():
        raise NfCoreExecutionError("report must be a new, non-symlink path")
    schema = schema or fetch_official_schema(spec)
    parameters = validate_pipeline_parameters(
        spec,
        request.get("pipeline_params", {}),
        schema,
        official_test_profile=official_test,
    )
    samplesheet = None
    if not official_test:
        samplesheet = validate_samplesheet(Path(parameters["input"]), spec)
    validate_host_execution_path(
        output_dir,
        spec=spec,
        profile=profile,
        architecture_profile=architecture_profile,
    )
    runtime = inspect_runtime(nextflow, profile, spec.minimum_nextflow_version)

    output_dir.mkdir(parents=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    result_dir = output_dir / "results"
    work_dir = output_dir / "work"
    provenance_dir = output_dir / "provenance"
    provenance_dir.mkdir()
    public_fixture = None
    if official_test:
        if spec is RIBOSEQ:
            fixture_gffread = request.get("fixture_gffread")
            if fixture_gffread is not None and not isinstance(fixture_gffread, str):
                raise NfCoreExecutionError("fixture_gffread must be an executable path string")
            parameters, public_fixture = materialize_riboseq_official_test(
                provenance_dir / "public_test_inputs",
                gffread=fixture_gffread,
            )
        elif spec is NASCENT:
            if request.get("fixture_gffread") is not None:
                raise NfCoreExecutionError("fixture_gffread applies only to the Ribo-seq fixture")
            parameters, public_fixture = materialize_nascent_official_test(
                provenance_dir / "public_test_inputs",
            )
        else:
            raise NfCoreExecutionError(
                f"local materialization of the {spec.pipeline} official test fixture is not implemented"
            )
        definitions = schema_parameters(schema)
        for name, value in parameters.items():
            if name not in definitions:
                raise NfCoreExecutionError(f"official test fixture uses unknown pinned parameter: {name}")
            _validate_scalar_type(name, value, definitions[name])
        samplesheet = validate_samplesheet(Path(parameters["input"]), spec)
    parameters = {**parameters, "outdir": str(result_dir.resolve())}
    params_path = provenance_dir / "nfcore_params.json"
    params_path.write_text(json.dumps(parameters, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    request_path = provenance_dir / "request.json"
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    schema_path = provenance_dir / "official_nextflow_schema.json"
    schema_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log_path = provenance_dir / "nextflow.log"
    runtime_config_path, runtime_compatibility = _prepare_runtime_compatibility(
        provenance_dir,
        spec=spec,
        profile=profile,
        architecture_profile=architecture_profile,
        resource_limits=request.get("resource_limits"),
    )
    command = _build_command(
        spec,
        str(runtime["nextflow_path"]),
        profile,
        architecture_profile,
        official_test,
        resume,
        params_path,
        result_dir,
        work_dir,
        log_path,
        runtime_config_path,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=output_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise NfCoreExecutionError(
            f"{spec.pipeline} {spec.revision} exceeded the declared {timeout_seconds}-second limit"
        ) from exc
    stdout_path = provenance_dir / "stdout.txt"
    stderr_path = provenance_dir / "stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        diagnostic = (completed.stdout + "\n" + completed.stderr)[-12000:]
        raise NfCoreExecutionError(
            f"{spec.pipeline} {spec.revision} failed with exit code {completed.returncode}: "
            f"{diagnostic}"
        )
    if not result_dir.is_dir():
        raise NfCoreExecutionError("Nextflow returned success without creating the declared result directory")
    groups, reloaded = collect_outputs(result_dir, spec)
    if samplesheet is not None:
        current = sha256(Path(samplesheet["path"]))
        if current != samplesheet["sha256"]:
            raise NfCoreExecutionError("samplesheet changed during workflow execution")
        for source in samplesheet["source_files"]:
            if sha256(Path(source["path"])) != source["sha256"]:
                raise NfCoreExecutionError(f"FASTQ changed during workflow execution: {source['path']}")
    if sha256(implementation_path) != implementation_sha256:
        raise NfCoreExecutionError("nf-core executor implementation changed during workflow execution")

    report = {
        "schema_version": 1,
        "passed": True,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "module_id": spec.module_id,
        "assay": request["assay"],
        "execution_evidence_level": "observed_scientific_workflow",
        "execution": {
            "external_workflow_executed": True,
            "outputs_reloaded": True,
            "biological_result_generated": not official_test,
            "official_public_test_profile": official_test,
        },
        "workflow": {
            "name": spec.pipeline,
            "revision": spec.revision,
            "revision_commit": spec.revision_commit,
            "official_schema_url": spec.schema_url,
            "official_schema_sha256": spec.schema_sha256,
        },
        "implementation": {
            "path": "biomed_workbench/implementations/nfcore.py",
            "sha256": implementation_sha256,
        },
        "runtime": runtime,
        "runtime_compatibility": runtime_compatibility,
        "command": {
            "argv": command,
            "returncode": completed.returncode,
            "stdout_sha256": sha256(stdout_path),
            "stderr_sha256": sha256(stderr_path),
            "nextflow_log_sha256": sha256(log_path) if log_path.is_file() else None,
        },
        "input": {
            "request_sha256": sha256(request_path),
            "parameters_sha256": sha256(params_path),
            "samplesheet": samplesheet,
            "public_fixture": public_fixture,
        },
        "outputs": {
            "groups": groups,
            "scientific_file_count": len(reloaded),
            "reloaded_files": reloaded,
        },
        "claim_boundary": (
            "The official minimal test profile proves executable workflow integration and output reload only."
            if official_test
            else "Biological interpretation remains conditional on design, assay-specific quality gates, replicate-aware inference, and project review."
        ),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
