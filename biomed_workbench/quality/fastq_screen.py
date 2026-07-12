"""FastQ Screen runtime probes and deterministic contamination summary parser."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


class FastQScreenReportError(ValueError):
    """Raised when FastQ Screen evidence is incomplete or internally inconsistent."""


def _conda_record(executable_name: str, package_name: str) -> dict[str, object]:
    executable = shutil.which(executable_name)
    if executable is None:
        raise RuntimeError(f"{executable_name} is unavailable")
    records = sorted((Path(executable).resolve().parent.parent / "conda-meta").glob(f"{package_name}-*.json"))
    if len(records) != 1:
        raise RuntimeError(f"{package_name} Bioconda record is unavailable or ambiguous")
    return json.loads(records[0].read_text(encoding="utf-8"))


def probe_bowtie2_bioconda_build(*, timeout_seconds: int) -> str:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    payload = _conda_record("bowtie2", "bowtie2")
    return f"{payload['version']}-{payload['build']}"


def probe_fastq_screen_perl(*, timeout_seconds: int) -> str:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    executable = shutil.which("perl")
    if executable is None:
        raise RuntimeError("Perl is unavailable")
    completed = subprocess.run([executable, "-e", "print $^V"], text=True, capture_output=True, check=True, timeout=timeout_seconds)
    return completed.stdout.lstrip("v")


def parse_fastq_screen_report(
    path: Path | str,
    *,
    expected_version: str = "0.16.0",
    expected_references: tuple[str, ...],
    max_unexpected_percent: float,
) -> dict[str, object]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise FastQScreenReportError("FastQ Screen report cannot be read") from exc
    if len(lines) < 4:
        raise FastQScreenReportError("FastQ Screen report is incomplete")
    header = re.fullmatch(r"#Fastq_screen version: ([0-9]+(?:\.[0-9]+)+)\t#Aligner: ([A-Za-z0-9._-]+)\t#(.+)", lines[0])
    if not header or header.group(1) != expected_version or header.group(2) != "bowtie2":
        raise FastQScreenReportError("FastQ Screen version or aligner is incompatible")
    columns = lines[1].split("\t")
    required_columns = {
        "Genome", "#Reads_processed", "%Unmapped", "%One_hit_one_genome", "%Multiple_hits_one_genome",
        "%One_hit_multiple_genomes", "%Multiple_hits_multiple_genomes",
    }
    if not required_columns <= set(columns):
        raise FastQScreenReportError("FastQ Screen report columns are incomplete")
    references = {}
    processed_counts = set()
    for line in lines[2:]:
        if not line or line.startswith("%Hit_no_genomes"):
            continue
        values = line.split("\t")
        if len(values) != len(columns):
            raise FastQScreenReportError("FastQ Screen result row is malformed")
        row = dict(zip(columns, values))
        name = row["Genome"]
        if not name or name in references:
            raise FastQScreenReportError("FastQ Screen reference names are invalid")
        processed = int(row["#Reads_processed"])
        unmapped = float(row["%Unmapped"])
        categories = sum(float(row[key]) for key in required_columns if key.startswith("%") and key != "%Unmapped")
        if processed <= 0 or not 99.99 <= unmapped + categories <= 100.01:
            raise FastQScreenReportError("FastQ Screen percentages or read counts are inconsistent")
        processed_counts.add(processed)
        references[name] = {"reads_processed": processed, "mapped_any_percent": round(100 - unmapped, 6), "unmapped_percent": unmapped}
    if not references or len(processed_counts) != 1:
        raise FastQScreenReportError("FastQ Screen reference rows do not share one read denominator")
    missing_expected = sorted(set(expected_references) - set(references))
    if missing_expected:
        raise FastQScreenReportError("FastQ Screen report omits expected references")
    unexpected = {name: values["mapped_any_percent"] for name, values in references.items() if name not in expected_references}
    flagged = sorted(name for name, percent in unexpected.items() if percent > max_unexpected_percent)
    return {
        "schema_version": 1,
        "fastq_screen_version": expected_version,
        "aligner": "bowtie2",
        "reads_processed": next(iter(processed_counts)),
        "references": dict(sorted(references.items())),
        "expected_references": sorted(expected_references),
        "unexpected_reference_percentages": dict(sorted(unexpected.items())),
        "max_unexpected_percent": float(max_unexpected_percent),
        "flagged_unexpected_references": flagged,
        "contamination_screening": {"status": "flagged" if flagged else "passed", "reference_count": len(references)},
        "downstream_readiness": "requires-contamination-review" if flagged else "technically-ready-pending-design-review",
        "interpretation_policy": "Screening is limited to the declared reference bundle and cannot rule out unrepresented contaminants.",
    }
