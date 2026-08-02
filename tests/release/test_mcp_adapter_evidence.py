from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.verify_mcp_adapter import validate_report


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "mcp-adapter-live-verification.json"


class McpAdapterEvidenceTests(unittest.TestCase):
    def test_observed_adapter_report_matches_current_sources(self) -> None:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertTrue(validate_report(report))


if __name__ == "__main__":
    unittest.main()
