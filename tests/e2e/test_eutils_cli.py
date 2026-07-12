import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class EUtilitiesCliTests(unittest.TestCase):
    def test_database_inventory_command_is_structured_and_nonempty(self):
        result = subprocess.run(
            [sys.executable, "tools/eutils.py", "databases"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertIn("pubmed", payload["databases"])
        self.assertIn("clinvar", payload["databases"])


if __name__ == "__main__":
    unittest.main()
