"""Scientific quality-report parsers and interpretation contracts."""

from .fastqc import FastQCReportError, parse_fastqc_archive
from .fastp import FastPReportError, parse_fastp_report
from .multiqc import MultiQCReportError, parse_multiqc_archive

__all__ = ["FastPReportError", "FastQCReportError", "MultiQCReportError", "parse_fastp_report", "parse_fastqc_archive", "parse_multiqc_archive"]
