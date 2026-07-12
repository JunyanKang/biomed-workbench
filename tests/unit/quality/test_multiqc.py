import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from biomed_workbench.quality import MultiQCReportError, parse_multiqc_archive


def archive(path: Path, *, version="1.35", unsafe=False) -> Path:
    data = {
        "config_version": version,
        "report_general_stats_data": {
            "fastqc": {
                "sample-a": {"total_sequences": 100, "percent_gc": 48, "avg_sequence_length": 150, "percent_duplicates": 12, "percent_fails": 0},
                "sample-b": {"total_sequences": 90, "percent_gc": 52, "avg_sequence_length": 150, "percent_duplicates": 40, "percent_fails": 20},
            }
        },
    }
    with zipfile.ZipFile(path, "w") as output:
        output.writestr("multiqc_data.json", json.dumps(data))
        output.writestr("multiqc_software_versions.json", json.dumps({"FastQC": ["0.12.1"]}))
        if unsafe:
            output.writestr("../escape.txt", "unsafe")
    return path


class MultiQCParserTests(unittest.TestCase):
    def test_parses_cross_sample_metrics_and_flags_without_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = parse_multiqc_archive(archive(Path(temporary) / "multiqc.zip"))

        self.assertEqual(result["multiqc_version"], "1.35")
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["flagged_samples"], ["sample-b"])
        self.assertEqual(result["downstream_readiness"], "requires-assay-aware-review")

    def test_rejects_version_drift_and_unsafe_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = ((archive(root / "old.zip", version="1.34"), "version"), (archive(root / "unsafe.zip", unsafe=True), "unsafe"))
            for path, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(MultiQCReportError, message):
                    parse_multiqc_archive(path)


if __name__ == "__main__":
    unittest.main()
