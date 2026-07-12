import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.quality import FastPReportError, parse_fastp_report


COMMAND = "fastp --disable_adapter_trimming --disable_quality_filtering --disable_length_filtering --disable_trim_poly_g"


def report(path: Path, *, version="1.3.6", changed=False) -> Path:
    metrics = {"total_reads": 12, "total_bases": 600, "q20_rate": 1, "q30_rate": 1, "read1_mean_length": 50, "gc_content": 0.5}
    payload = {
        "summary": {
            "fastp_version": version,
            "sequencing": "single end (50 cycles)",
            "before_filtering": metrics,
            "after_filtering": {**metrics, "total_reads": 11 if changed else 12},
        },
        "duplication": {"rate": 0.83},
        "command": COMMAND,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class FastPParserTests(unittest.TestCase):
    def test_parses_qc_only_metrics_and_states_contamination_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = parse_fastp_report(report(Path(temporary) / "fastp.json"))

        self.assertTrue(result["qc_only_read_accounting_passed"])
        self.assertEqual(result["metrics"]["total_reads"], 12)
        self.assertEqual(result["contamination_screening"]["status"], "not-assessed")
        self.assertIn("high-duplication-rate", result["flagged_metrics"])

    def test_rejects_version_drift_and_non_qc_only_read_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = ((report(root / "old.json", version="1.3.5"), "version"), (report(root / "changed.json", changed=True), "changed"))
            for path, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(FastPReportError, message):
                    parse_fastp_report(path)


if __name__ == "__main__":
    unittest.main()
