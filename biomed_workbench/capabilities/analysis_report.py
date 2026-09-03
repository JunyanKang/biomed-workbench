"""Formal delivery of reviewed scientific analysis reports."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from ..reporting.analysis_html import assert_primary_html_delivery, write_analysis_report


def deliver_analysis_report_html(
    report: dict[str, Any],
    output_directory: str,
    title: str = "",
    language: str = "auto",
    markdown_companion: bool = True,
) -> dict[str, Any]:
    """Write, reopen, and verify HTML as the primary outward report artifact."""
    if not isinstance(report, dict):
        raise ValueError("report must be an object")
    if not isinstance(output_directory, str) or not output_directory.strip():
        raise ValueError("output_directory is required")
    target = (
        Path(tempfile.mkdtemp(prefix="biomed-analysis-report-fixture-"))
        if output_directory == ":temporary:"
        else Path(output_directory)
    )
    files = write_analysis_report(
        report,
        target,
        title=title,
        language=language,
        markdown_companion=markdown_companion,
    )
    assert_primary_html_delivery(files)
    return {
        "ready_for_delivery": True,
        "primary_delivery_format": "html",
        "markdown_is_companion_only": True,
        "report_files": files,
    }
