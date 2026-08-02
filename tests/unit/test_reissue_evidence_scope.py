import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.reissue_evidence_scope import reissue


class ReissueEvidenceScopeTests(unittest.TestCase):
    def test_rejects_non_report_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_text(json.dumps({"passed": True}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "direct child"):
                reissue(
                    path,
                    registry=object(),
                    changed_fields=("maturity",),
                    reason="A sufficiently detailed reviewed metadata-only change reason.",
                )

    def test_allow_list_excludes_scientific_method_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "report.json"
            path.write_text(json.dumps({"passed": True}), encoding="utf-8")
            with patch("tools.reissue_evidence_scope.ROOT", Path(temporary).parent):
                with self.assertRaises(RuntimeError):
                    reissue(
                        path,
                        registry=object(),
                        changed_fields=("parameters",),
                        reason="A sufficiently detailed reviewed metadata-only change reason.",
                    )


if __name__ == "__main__":
    unittest.main()
