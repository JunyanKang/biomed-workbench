import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.e2e.test_create_module import future_module_request


ROOT = Path(__file__).resolve().parents[2]


class CreateModuleCliEndToEndTests(unittest.TestCase):
    def test_developer_can_atomically_add_a_complete_module_without_editing_registry_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "request.json"
            registry_root = root / "extensions"
            request_path.write_text(json.dumps(future_module_request()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "tools/create_module.py", str(request_path), "--registry-root", str(registry_root)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)

            self.assertEqual(Path(payload["created"]).name, "future-table-profile")
            self.assertTrue((registry_root / "future-table-profile" / "module.json").is_file())
            self.assertTrue((registry_root / "future-table-profile" / "tests" / "cases.json").is_file())
            self.assertTrue((registry_root / "future-table-profile" / "templates" / "run_future_table_profile.py").is_file())


if __name__ == "__main__":
    unittest.main()
