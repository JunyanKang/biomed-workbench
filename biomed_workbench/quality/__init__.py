"""Scientific quality-report parsers exposed without eager optional imports."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "AlignmentQualityReportError": ("alignment", "AlignmentQualityReportError"),
    "ChromaKeyReportError": ("chroma_key", "ChromaKeyReportError"),
    "FastPReportError": ("fastp", "FastPReportError"),
    "FastQCReportError": ("fastqc", "FastQCReportError"),
    "FastQScreenReportError": ("fastq_screen", "FastQScreenReportError"),
    "IntervalReportError": ("intervals", "IntervalReportError"),
    "MultiQCReportError": ("multiqc", "MultiQCReportError"),
    "NMFReportError": ("nmf", "NMFReportError"),
    "TMBReportError": ("tmb", "TMBReportError"),
    "VCFReportError": ("vcf", "VCFReportError"),
    "parse_bedtools_intersect_report": ("intervals", "parse_bedtools_intersect_report"),
    "parse_bwa_mem_sam": ("alignment", "parse_bwa_mem_sam"),
    "parse_chroma_key_outputs": ("chroma_key", "parse_chroma_key_outputs"),
    "parse_fastp_report": ("fastp", "parse_fastp_report"),
    "parse_fastq_screen_report": ("fastq_screen", "parse_fastq_screen_report"),
    "parse_fastqc_archive": ("fastqc", "parse_fastqc_archive"),
    "parse_multiqc_archive": ("multiqc", "parse_multiqc_archive"),
    "parse_nmf_outputs": ("nmf", "parse_nmf_outputs"),
    "parse_samtools_flagstat_report": ("alignment", "parse_samtools_flagstat_report"),
    "parse_tabix_vcf_query": ("vcf", "parse_tabix_vcf_query"),
    "parse_tmb_report": ("tmb", "parse_tmb_report"),
    "parse_vcf_document": ("vcf", "parse_vcf_document"),
    "parse_vcf_filter_outputs": ("vcf", "parse_vcf_filter_outputs"),
    "probe_bwa_homebrew_bottle": ("alignment", "probe_bwa_homebrew_bottle"),
    "probe_bwa_version": ("alignment", "probe_bwa_version"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    """Load only the parser family requested by the caller."""
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
