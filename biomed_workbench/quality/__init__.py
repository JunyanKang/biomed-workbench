"""Scientific quality-report parsers and interpretation contracts."""

from .alignment import AlignmentQualityReportError, parse_bwa_mem_sam, parse_samtools_flagstat_report, probe_bwa_homebrew_bottle, probe_bwa_version
from .chroma_key import ChromaKeyReportError, parse_chroma_key_outputs
from .fastqc import FastQCReportError, parse_fastqc_archive
from .fastp import FastPReportError, parse_fastp_report
from .fastq_screen import FastQScreenReportError, parse_fastq_screen_report
from .intervals import IntervalReportError, parse_bedtools_intersect_report
from .multiqc import MultiQCReportError, parse_multiqc_archive
from .nmf import NMFReportError, parse_nmf_outputs
from .tmb import TMBReportError, parse_tmb_report
from .vcf import VCFReportError, parse_tabix_vcf_query, parse_vcf_document, parse_vcf_filter_outputs

__all__ = [
    "AlignmentQualityReportError",
    "ChromaKeyReportError",
    "FastPReportError",
    "FastQCReportError",
    "FastQScreenReportError",
    "IntervalReportError",
    "MultiQCReportError",
    "NMFReportError",
    "TMBReportError",
    "VCFReportError",
    "parse_fastp_report",
    "parse_fastq_screen_report",
    "parse_fastqc_archive",
    "parse_bedtools_intersect_report",
    "parse_bwa_mem_sam",
    "parse_chroma_key_outputs",
    "parse_multiqc_archive",
    "parse_nmf_outputs",
    "parse_samtools_flagstat_report",
    "parse_tabix_vcf_query",
    "parse_tmb_report",
    "parse_vcf_document",
    "parse_vcf_filter_outputs",
    "probe_bwa_homebrew_bottle",
    "probe_bwa_version",
]
