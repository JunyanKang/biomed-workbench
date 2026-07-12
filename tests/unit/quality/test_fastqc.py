import tempfile
import unittest
import zipfile
from pathlib import Path

from biomed_workbench.quality import FastQCReportError, parse_fastqc_archive


MODULES = {
    "Basic Statistics": "pass",
    "Per base sequence quality": "pass",
    "Per sequence quality scores": "pass",
    "Per base sequence content": "warn",
    "Per sequence GC content": "pass",
    "Per base N content": "pass",
    "Sequence Length Distribution": "pass",
    "Sequence Duplication Levels": "fail",
    "Overrepresented sequences": "warn",
    "Adapter Content": "pass",
}


def archive(path: Path, *, version="0.12.1", unsafe=False) -> Path:
    data = [f"##FastQC\t{version}"]
    for name, status in MODULES.items():
        data.append(f">>{name}\t{status}")
        if name == "Basic Statistics":
            data.extend(
                [
                    "#Measure\tValue",
                    "Filename\treads.fastq",
                    "File type\tConventional base calls",
                    "Encoding\tSanger / Illumina 1.9",
                    "Total Sequences\t12",
                    "Sequence length\t50",
                    "%GC\t50",
                ]
            )
        data.append(">>END_MODULE")
    summary = "\n".join(f"{status.upper()}\t{name}\treads.fastq" for name, status in MODULES.items()) + "\n"
    with zipfile.ZipFile(path, "w") as output:
        output.writestr("reads_fastqc/fastqc_data.txt", "\n".join(data) + "\n")
        output.writestr("reads_fastqc/summary.txt", summary)
        if unsafe:
            output.writestr("../escape.txt", "unsafe")
    return path


class FastQCParserTests(unittest.TestCase):
    def test_parses_complete_versioned_report_without_overinterpreting_flags(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = parse_fastqc_archive(archive(Path(temporary) / "report.zip"))

        self.assertEqual(result["fastqc_version"], "0.12.1")
        self.assertEqual(result["basic_statistics"]["total_sequences"], 12)
        self.assertEqual(result["status_counts"], {"pass": 7, "warn": 2, "fail": 1})
        self.assertEqual(result["downstream_readiness"], "requires-assay-aware-review")

    def test_rejects_version_drift_unsafe_archives_and_summary_disagreement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (
                (archive(root / "old.zip", version="0.11.9"), "version"),
                (archive(root / "unsafe.zip", unsafe=True), "unsafe"),
            )
            for path, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(FastQCReportError, message):
                    parse_fastqc_archive(path)


if __name__ == "__main__":
    unittest.main()
