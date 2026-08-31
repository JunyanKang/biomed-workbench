"""Product-owned NGS intake, readiness, and external-run recovery.

The functions deliberately separate three questions that are often conflated:
what the files are, whether the runtime and reference resources are ready, and
whether an external workflow actually completed with reloadable outputs.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, BinaryIO


_ASSAYS = {
    "bulk-rna", "single-cell-rna", "atac", "chip", "cutrun", "cuttag",
    "germline-variant", "somatic-variant", "amplicon", "metagenomics",
    "riboseq", "clipseq", "methylseq", "hic", "unspecified",
}
_READ_EXTENSIONS = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
_REFERENCE_ROLES = {
    "genome_fasta", "annotation", "aligner_index", "blacklist", "known_sites",
    "taxonomy_database", "transcriptome_index", "intervals", "barcode_whitelist",
}
_COMPLETED_STATES = {"completed", "succeeded", "success"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_maybe_gzip(path: Path) -> BinaryIO:
    return gzip.open(path, "rb") if path.name.lower().endswith(".gz") else path.open("rb")


def _classify(path: Path) -> tuple[str, list[str]]:
    name = path.name.lower()
    warnings: list[str] = []
    if any(name.endswith(ext) for ext in _READ_EXTENSIONS):
        try:
            with _open_maybe_gzip(path) as handle:
                lines = [handle.readline(16_384) for _ in range(4)]
            if len(lines) != 4 or not lines[0].startswith(b"@") or not lines[2].startswith(b"+"):
                warnings.append("FASTQ extension is present but the first four-line record is not valid")
        except (OSError, EOFError):
            warnings.append("FASTQ content could not be decompressed and inspected")
        return "fastq", warnings
    with path.open("rb") as handle:
        prefix = handle.read(8)
    if prefix.startswith(b"BAM\x01") or (prefix[:2] == b"\x1f\x8b" and name.endswith(".bam")):
        return "bam", warnings
    if prefix.startswith(b"CRAM"):
        return "cram", warnings
    if name.endswith((".vcf", ".vcf.gz", ".bcf")):
        return "variant", warnings
    if name.endswith((".h5ad", ".h5", ".hdf5", ".loom")):
        return "single-cell-matrix", warnings
    if name.endswith((".mtx", ".mtx.gz")):
        return "matrix-market", warnings
    if name.endswith((".csv", ".tsv", ".txt")):
        return "tabular", warnings
    if name.endswith((".bed", ".bed.gz", ".gtf", ".gtf.gz", ".gff", ".gff3", ".fa", ".fasta", ".fna")):
        return "reference-or-interval", warnings
    return "unknown", warnings


def _paired_key(name: str) -> tuple[str, str | None]:
    base = re.sub(r"(?:\.fastq|\.fq)(?:\.gz)?$", "", name, flags=re.IGNORECASE)
    match = re.search(r"(?:^|[._-])R?([12])(?:$|[._-])", base, re.IGNORECASE)
    if not match:
        return base, None
    start, end = match.span()
    key = f"{base[:start]}{base[end:]}".strip("._-")
    return key, match.group(1)


def inspect_sequencing_inputs(
    paths: list[str],
    assay: str = "unspecified",
    sample_sheet: str | None = None,
) -> dict[str, Any]:
    """Inspect local sequencing inputs without reading whole datasets."""
    if assay not in _ASSAYS:
        raise ValueError("assay is not supported")
    if not isinstance(paths, list) or not 1 <= len(paths) <= 10_000:
        raise ValueError("paths must contain 1..10000 local files")
    records, missing, duplicates, seen = [], [], [], set()
    types: Counter[str] = Counter()
    fastq_pairs: dict[str, set[str]] = {}
    for raw in paths:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("every path must be nonempty text")
        path = Path(raw).expanduser().resolve()
        key = str(path)
        if key in seen:
            duplicates.append(key)
            continue
        seen.add(key)
        if not path.is_file():
            missing.append(key)
            continue
        file_type, warnings = _classify(path)
        types[file_type] += 1
        record = {
            "path": key,
            "name": path.name,
            "file_type": file_type,
            "size_bytes": path.stat().st_size,
            "warnings": warnings,
        }
        records.append(record)
        if file_type == "fastq":
            pair_key, mate = _paired_key(path.name)
            if mate:
                fastq_pairs.setdefault(pair_key, set()).add(mate)

    incomplete_pairs = sorted(key for key, mates in fastq_pairs.items() if mates != {"1", "2"})
    sheet = None
    sheet_errors: list[str] = []
    if sample_sheet is not None:
        sheet_path = Path(sample_sheet).expanduser().resolve()
        if not sheet_path.is_file():
            sheet_errors.append("declared sample sheet is missing")
        else:
            delimiter = "\t" if sheet_path.suffix.lower() in {".tsv", ".txt"} else ","
            with sheet_path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                rows = list(reader)
                fields = list(reader.fieldnames or [])
            if not rows or not fields:
                sheet_errors.append("sample sheet has no header or data rows")
            sample_field = next((value for value in ("sample", "sample_id", "sample_name") if value in fields), None)
            if sample_field:
                values = [str(row.get(sample_field, "")).strip() for row in rows]
                if any(not value for value in values) or len(set(values)) != len(values):
                    sheet_errors.append("sample identifiers are empty or duplicated")
            else:
                sheet_errors.append("sample sheet lacks sample, sample_id, or sample_name")
            sheet = {"path": str(sheet_path), "row_count": len(rows), "columns": fields}

    route = []
    if types["fastq"]:
        route.append("raw-read quality control")
    if assay in {"bulk-rna", "riboseq"} and types["fastq"]:
        route.append("read alignment or transcript quantification followed by count-level inference")
    if assay == "single-cell-rna" and types["fastq"]:
        route.append("chemistry-aware barcode, UMI, and gene-count generation before cell-level QC")
    if assay in {"atac", "chip", "cutrun", "cuttag"} and (types["fastq"] or types["bam"]):
        route.append("assay-aware alignment, fragment QC, control handling, and peak calling")
    if assay in {"germline-variant", "somatic-variant"} and (types["fastq"] or types["bam"] or types["cram"]):
        route.append("design-specific variant calling with reference and interval validation")
    if assay in {"amplicon", "metagenomics"} and types["fastq"]:
        route.append("contamination-aware taxonomic processing with a versioned reference database")
    if types["single-cell-matrix"] or types["matrix-market"]:
        route.append("post-count single-cell analysis; raw-read QC cannot be reconstructed from the matrix alone")

    blocking = bool(missing or duplicates or incomplete_pairs or sheet_errors or types["unknown"])
    return {
        "assay": assay,
        "input_count": len(records),
        "type_counts": dict(sorted(types.items())),
        "records": records,
        "sample_sheet": sheet,
        "missing_paths": missing,
        "duplicate_paths": duplicates,
        "incomplete_fastq_pairs": incomplete_pairs,
        "sample_sheet_errors": sheet_errors,
        "route_candidates": route,
        "admissible_for_planning": not blocking,
        "interpretation": (
            "The inspected files are structurally sufficient to select a workflow." if not blocking
            else "Input identity or pairing remains unresolved; workflow execution is blocked."
        ),
        "claim_boundary": "File recognition and lightweight structure checks do not establish read quality, biological validity, or successful analysis.",
    }


def assess_sequencing_readiness(
    assay: str,
    tools: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> dict[str, Any]:
    """Separate executable readiness from reference-resource readiness."""
    if assay not in _ASSAYS - {"unspecified"}:
        raise ValueError("a specific supported assay is required")
    if not isinstance(tools, list) or not tools or not isinstance(references, list):
        raise ValueError("tools must be nonempty and references must be a list")
    tool_rows, missing_tools = [], []
    for item in tools:
        if not isinstance(item, dict) or set(item) != {"name", "required"}:
            raise ValueError("each tool must contain exactly name and required")
        name, required = item["name"], item["required"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,80}", name) or not isinstance(required, bool):
            raise ValueError("tool name or required flag is invalid")
        executable = shutil.which(name)
        tool_rows.append({"name": name, "required": required, "available": executable is not None, "executable": executable})
        if required and executable is None:
            missing_tools.append(name)
    reference_rows, missing_references, invalid_references = [], [], []
    for item in references:
        if not isinstance(item, dict) or set(item) != {"role", "path", "required"}:
            raise ValueError("each reference must contain exactly role, path, and required")
        role, raw, required = item["role"], item["path"], item["required"]
        if role not in _REFERENCE_ROLES or not isinstance(raw, str) or not isinstance(required, bool):
            raise ValueError("reference role, path, or required flag is invalid")
        path = Path(raw).expanduser().resolve()
        exists = path.is_file() or path.is_dir()
        nonempty = exists and (path.is_dir() or path.stat().st_size > 0)
        reference_rows.append({"role": role, "path": str(path), "required": required, "available": bool(nonempty)})
        if required and not exists:
            missing_references.append(role)
        elif required and not nonempty:
            invalid_references.append(role)
    return {
        "assay": assay,
        "tool_readiness": not missing_tools,
        "reference_readiness": not missing_references and not invalid_references,
        "ready_to_execute": not missing_tools and not missing_references and not invalid_references,
        "tools": tool_rows,
        "references": reference_rows,
        "missing_required_tools": sorted(missing_tools),
        "missing_required_references": sorted(missing_references),
        "invalid_required_references": sorted(invalid_references),
        "next_action": "execute with the recorded environment" if not (missing_tools or missing_references or invalid_references) else "reuse or repair the declared environment and resources before execution",
        "claim_boundary": "Executable and resource availability does not establish compatibility, successful execution, output quality, or biological validity.",
    }


def ingest_sequencing_run_package(run_directory: str) -> dict[str, Any]:
    """Reload a bounded external NGS run package and verify its declared artifacts."""
    root = Path(run_directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("run_directory must be an existing directory")
    manifest_path = root / "manifest.json"
    artifact_index_path = root / "artifact_index.json"
    if not manifest_path.is_file() or not artifact_index_path.is_file():
        raise ValueError("run package requires manifest.json and artifact_index.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    index = json.loads(artifact_index_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(index, dict):
        raise ValueError("run package documents must be JSON objects")
    status = str(manifest.get("status", "")).strip().lower()
    artifacts = index.get("artifacts")
    if status not in _COMPLETED_STATES or not isinstance(artifacts, list) or not artifacts:
        return {
            "run_directory": str(root), "status": status or "unknown", "accepted": False,
            "reason": "run status is not completed or the artifact index is empty",
            "artifacts": [], "claim_boundary": "Prepared, blocked, failed, or empty packages are not completed analyses.",
        }
    checked, errors = [], []
    for position, item in enumerate(artifacts, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append(f"artifact {position} lacks a path")
            continue
        candidate = (root / item["path"]).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"artifact {position} escapes the run directory")
            continue
        if not candidate.is_file():
            errors.append(f"artifact {position} is missing")
            continue
        declared = item.get("sha256")
        observed = _sha256(candidate)
        if declared is not None and (not isinstance(declared, str) or declared.lower() != observed):
            errors.append(f"artifact {position} checksum differs")
        checked.append({
            "path": str(candidate), "relative_path": candidate.relative_to(root).as_posix(),
            "size_bytes": candidate.stat().st_size, "sha256": observed,
            "role": str(item.get("role", "unspecified")),
        })
    environment = manifest.get("environment")
    if not isinstance(environment, dict) or not environment.get("identity"):
        errors.append("manifest lacks a recorded analysis environment identity")
    return {
        "run_directory": str(root),
        "status": status,
        "accepted": not errors,
        "reason": "completed outputs were reloaded and verified" if not errors else "run package failed reload verification",
        "workflow": manifest.get("workflow"),
        "environment": environment if isinstance(environment, dict) else None,
        "artifacts": checked,
        "errors": errors,
        "claim_boundary": "Acceptance confirms declared completion and artifact integrity; assay-specific QC and scientific review remain required before interpretation.",
    }
