from __future__ import annotations

import json
from pathlib import Path
import unittest

from tools.audit_adapter_boundaries import build


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports" / "adapter-boundary-audit.json"


class AdapterBoundaryTests(unittest.TestCase):
    def test_codex_first_adapters_are_isolated(self) -> None:
        observed = json.loads(REPORT.read_text(encoding="utf-8"))
        expected = build()
        self.assertEqual(observed, expected)
        self.assertTrue(observed["passed"])
        self.assertEqual(observed["scientific_module_reverse_dependencies"], [])


if __name__ == "__main__":
    unittest.main()
