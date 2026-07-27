import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/assembly-reference-alignment/templates/run_minimap2_assembly.py"
FIXTURE = ROOT / "tests/fixtures/assembly-reference-alignment/ncbi-j01673.1-rho.fasta"


class AssemblyReferenceAlignmentTemplateTests(unittest.TestCase):
    def test_public_ncbi_sequence_aligns_and_reloads_paf(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "alignment"
            result = subprocess.run([
                "python3", str(TEMPLATE), "--reference", str(FIXTURE), "--query", str(FIXTURE),
                "--preset", "asm5", "--minimum-query-coverage", "0.9", "--output-dir", str(output), "--minimap2", "minimap2",
            ], cwd=ROOT, text=True, capture_output=True, check=False, timeout=180)
            report = json.loads((output / "assembly-alignment-report.json").read_text(encoding="utf-8"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(report["passed"])
        self.assertEqual(report["alignment"]["query_records_aligned"], ["J01673.1"])
        self.assertEqual(report["alignment"]["target_records_aligned"], ["J01673.1"])
        self.assertGreater(report["alignment"]["query_coverage"]["J01673.1"], 0.9)
        self.assertEqual(report["alignment"]["query_records_unaligned"], [])
        self.assertIn("2.31", report["tool_versions"]["minimap2"])


if __name__ == "__main__":
    unittest.main()
