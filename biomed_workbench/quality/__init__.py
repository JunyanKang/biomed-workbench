"""Scientific quality-report parsers and interpretation contracts."""

from .alignment import AlignmentQualityReportError, parse_samtools_flagstat_report
from .fastqc import FastQCReportError, parse_fastqc_archive
from .fastp import FastPReportError, parse_fastp_report
from .fastq_screen import FastQScreenReportError, parse_fastq_screen_report
from .multiqc import MultiQCReportError, parse_multiqc_archive

__all__ = [
    "AlignmentQualityReportError",
    "FastPReportError",
    "FastQCReportError",
    "FastQScreenReportError",
    "MultiQCReportError",
    "parse_fastp_report",
    "parse_fastq_screen_report",
    "parse_fastqc_archive",
    "parse_multiqc_archive",
    "parse_samtools_flagstat_report",
]
