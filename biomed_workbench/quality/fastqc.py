"""Bounded parser for versioned FastQC report archives."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path, PurePosixPath


_VERSION_RE = re.compile(r"^##FastQC\t([0-9]+(?:\.[0-9]+)+)$")
_MODULE_RE = re.compile(r"^>>([^\t]+)\t(pass|warn|fail)$")
_REQUIRED_MODULES = frozenset(
    {
        "Basic Statistics",
        "Per base sequence quality",
        "Per sequence quality scores",
        "Per base sequence content",
        "Per sequence GC content",
        "Per base N content",
        "Sequence Length Distribution",
        "Sequence Duplication Levels",
        "Overrepresented sequences",
        "Adapter Content",
    }
)


class FastQCReportError(ValueError):
    """Raised when a FastQC archive is unsafe, incomplete, or incompatible."""


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if not members or len(members) > 200:
        raise FastQCReportError("FastQC archive entry count is invalid")
    if sum(item.file_size for item in members) > 20_000_000:
        raise FastQCReportError("FastQC archive exceeds the uncompressed size limit")
    for item in members:
        path = PurePosixPath(item.filename)
        mode = item.external_attr >> 16
        if path.is_absolute() or ".." in path.parts or (mode & 0o170000) == 0o120000:
            raise FastQCReportError("FastQC archive contains an unsafe entry")
    return members


def _parse_data(text: str, expected_version: str) -> tuple[dict[str, str], dict[str, str]]:
    lines = text.splitlines()
    if not lines:
        raise FastQCReportError("FastQC data file is empty")
    version_match = _VERSION_RE.fullmatch(lines[0])
    if not version_match or version_match.group(1) != expected_version:
        raise FastQCReportError("FastQC report version is incompatible")
    statuses: dict[str, str] = {}
    basic: dict[str, str] = {}
    current = None
    for line in lines[1:]:
        module_match = _MODULE_RE.fullmatch(line)
        if module_match:
            current = module_match.group(1)
            if current in statuses:
                raise FastQCReportError("FastQC report contains duplicate modules")
            statuses[current] = module_match.group(2)
            continue
        if line == ">>END_MODULE":
            current = None
            continue
        if current == "Basic Statistics" and line and not line.startswith("#"):
            key, separator, value = line.partition("\t")
            if not separator or not key or not value:
                raise FastQCReportError("FastQC basic statistics are malformed")
            basic[key] = value
    missing = sorted(_REQUIRED_MODULES - set(statuses))
    if missing:
        raise FastQCReportError(f"FastQC report omits required modules: {', '.join(missing)}")
    for field in ("Filename", "File type", "Encoding", "Total Sequences", "Sequence length", "%GC"):
        if field not in basic:
            raise FastQCReportError(f"FastQC basic statistics omit {field}")
    try:
        if int(basic["Total Sequences"]) <= 0:
            raise ValueError
        gc_percent = float(basic["%GC"])
        if not 0 <= gc_percent <= 100:
            raise ValueError
    except ValueError:
        raise FastQCReportError("FastQC basic statistics contain invalid numeric values") from None
    return statuses, basic


def parse_fastqc_archive(path: Path | str, *, expected_version: str = "0.12.1") -> dict[str, object]:
    """Validate one FastQC archive and return a deterministic scientific summary."""
    archive_path = Path(path)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = _safe_members(archive)
            data_members = [item for item in members if item.filename.endswith("/fastqc_data.txt")]
            summary_members = [item for item in members if item.filename.endswith("/summary.txt")]
            if len(data_members) != 1 or len(summary_members) != 1:
                raise FastQCReportError("FastQC archive must contain one data file and one summary")
            statuses, basic = _parse_data(archive.read(data_members[0]).decode("utf-8"), expected_version)
            summary_lines = archive.read(summary_members[0]).decode("utf-8").splitlines()
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise FastQCReportError("FastQC archive cannot be read") from exc
    summary_statuses = {}
    for line in summary_lines:
        status, separator, remainder = line.partition("\t")
        module, separator2, _filename = remainder.partition("\t")
        normalized = status.lower()
        if not separator or not separator2 or normalized not in {"pass", "warn", "fail"}:
            raise FastQCReportError("FastQC summary is malformed")
        summary_statuses[module] = normalized
    if any(summary_statuses.get(name) != status for name, status in statuses.items()):
        raise FastQCReportError("FastQC summary and data module statuses differ")
    counts = {status: sum(value == status for value in statuses.values()) for status in ("pass", "warn", "fail")}
    flagged = [
        {"module": name, "status": status}
        for name, status in sorted(statuses.items())
        if status != "pass"
    ]
    readiness = "requires-assay-aware-review" if flagged else "technically-ready-pending-design-review"
    return {
        "schema_version": 1,
        "fastqc_version": expected_version,
        "basic_statistics": {
            "file_type": basic["File type"],
            "quality_encoding": basic["Encoding"],
            "total_sequences": int(basic["Total Sequences"]),
            "sequence_length": basic["Sequence length"],
            "gc_percent": float(basic["%GC"]),
        },
        "module_statuses": dict(sorted(statuses.items())),
        "status_counts": counts,
        "flagged_modules": flagged,
        "downstream_readiness": readiness,
        "interpretation_policy": "FastQC flags require assay, library-design, organism, and downstream-method context.",
    }
