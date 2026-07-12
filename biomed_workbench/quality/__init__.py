"""Scientific quality-report parsers and interpretation contracts."""

from .fastqc import FastQCReportError, parse_fastqc_archive
from .multiqc import MultiQCReportError, parse_multiqc_archive

__all__ = ["FastQCReportError", "MultiQCReportError", "parse_fastqc_archive", "parse_multiqc_archive"]
