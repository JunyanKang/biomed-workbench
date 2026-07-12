import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class AddCapabilityE2ETests(unittest.TestCase):
    def test_developer_can_add_a_validated_contract_without_editing_registry_code(self):
        with tempfile.TemporaryDirectory() as directory:
            specifications = Path(directory) / "specifications"
            shutil.copytree(ROOT / "biomed_workbench" / "capability_specs", specifications)
            command = [
                sys.executable,
                "tools/add_capability.py",
                "sequence-fixture",
                "--workflow",
                "omics",
                "--title",
                "Inspect a fixture sequence",
                "--description",
                "Validate the extension path with an existing bounded scientific callable.",
                "--entrypoint",
                "biomed_workbench.capabilities.data:sequence_inspect",
                "--specification-root",
                str(specifications),
                "--no-build",
            ]
            result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout)
            specification = json.loads((specifications / "omics.json").read_text(encoding="utf-8"))

            self.assertEqual(payload["capability"], "sequence-fixture")
            self.assertIn("sequence-fixture", {row["id"] for row in specification["capabilities"]})


if __name__ == "__main__":
    unittest.main()
