import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/genome-coordinate-liftover/templates/run_crossmap_bed.py"
FIXTURES = ROOT / "tests/fixtures/genome-coordinate-liftover"
CROSSMAP = os.environ.get("BIOMED_WORKBENCH_CROSSMAP") or shutil.which("CrossMap")


@unittest.skipUnless(CROSSMAP, "set BIOMED_WORKBENCH_CROSSMAP or expose CrossMap on PATH")
class GenomeCoordinateLiftoverTemplateTests(unittest.TestCase):
    def test_public_ucsc_chain_prefix_retains_mapped_and_unmapped_records(self):
        self.assertTrue(CROSSMAP, "set BIOMED_WORKBENCH_CROSSMAP or expose CrossMap on PATH")
        chain = FIXTURES / "hg19-to-hg38-public-chain-prefix.chain"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "liftover"
            result = subprocess.run([
                sys.executable, str(TEMPLATE), "--input-bed", str(FIXTURES / "public-hg19-intervals.bed"),
                "--chain", str(chain), "--chain-sha256", hashlib.sha256(chain.read_bytes()).hexdigest(),
                "--output-dir", str(output), "--source-assembly", "hg19", "--target-assembly", "hg38",
                "--crossmap", CROSSMAP, "--split-mapping-policy", "retain-and-flag",
                "--unmapped-policy", "retain-and-report",
            ], text=True, capture_output=True, check=False, timeout=180)
            report = json.loads((output / "liftover-report.json").read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(report["passed"])
        self.assertEqual(report["records"], {"input": 2, "mapped": 1, "unmapped": 1, "split_mapped": 0, "unmapped_ids": ["outside_chain_prefix"], "split_mapped_ids": []})
        self.assertIn("0.7.", report["tool_versions"]["CrossMap"])

    def test_declared_block_if_any_policy_refuses_unmapped_records(self):
        chain = FIXTURES / "hg19-to-hg38-public-chain-prefix.chain"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "liftover"
            result = subprocess.run([
                sys.executable, str(TEMPLATE), "--input-bed", str(FIXTURES / "public-hg19-intervals.bed"),
                "--chain", str(chain), "--chain-sha256", hashlib.sha256(chain.read_bytes()).hexdigest(),
                "--output-dir", str(output), "--source-assembly", "hg19", "--target-assembly", "hg38",
                "--crossmap", CROSSMAP, "--split-mapping-policy", "retain-and-flag",
                "--unmapped-policy", "block-if-any",
            ], text=True, capture_output=True, check=False, timeout=180)
        self.assertEqual(result.returncode, 2)
        self.assertIn("block-if-any", result.stderr)


if __name__ == "__main__":
    unittest.main()
