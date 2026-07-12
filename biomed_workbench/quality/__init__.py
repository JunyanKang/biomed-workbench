"""Scientific quality-report parsers and interpretation contracts."""

from .fastqc import FastQCReportError, parse_fastqc_archive

__all__ = ["FastQCReportError", "parse_fastqc_archive"]
