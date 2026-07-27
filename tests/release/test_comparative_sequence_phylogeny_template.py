import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/comparative-sequence-phylogeny/templates/run_mafft_iqtree.py"
FIXTURE_ROOT = ROOT / "tests/fixtures/comparative-sequence-phylogeny"


class ComparativeSequencePhylogenyTemplateTests(unittest.TestCase):
    def test_real_uniprot_cytochrome_c_records_align_tree_and_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "phylogeny"
            command = [
                sys.executable,
                str(TEMPLATE),
                "--input-fasta", str(FIXTURE_ROOT / "cytochrome-c-uniprot.fasta"),
                "--metadata", str(FIXTURE_ROOT / "cytochrome-c-uniprot.tsv"),
                "--output-dir", str(output),
                "--sequence-type", "protein",
                "--substitution-model", "LG+G4",
                "--support-method", "ultrafast-bootstrap",
                "--support-replicates", "1000",
                "--outgroup-id", "yeast_cyc1",
                "--threads", "1",
                "--seed", "17",
            ]
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=180)
            report_path = output / "comparative-phylogeny-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(report.get("passed"))
        self.assertEqual(report["alignment"]["record_count"], 4)
        self.assertEqual(report["tree"]["tip_count"], 4)
        self.assertEqual(report["tree"]["outgroups_present"], ["yeast_cyc1"])
        self.assertEqual(report["parameters"]["support_replicates"], 1000)
        self.assertIn("7.526", report["tool_versions"]["mafft"])
        self.assertIn("3.1.2", report["tool_versions"]["iqtree"])


if __name__ == "__main__":
    unittest.main()
