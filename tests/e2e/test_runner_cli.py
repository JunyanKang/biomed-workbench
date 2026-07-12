import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RunnerCliTests(unittest.TestCase):
    def test_invalid_input_returns_structured_error_without_traceback(self):
        result = subprocess.run(
            [sys.executable, "tools/run_tool.py", "ncbi-search", "--input", '{"database":"gene"}'],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stderr)

        self.assertEqual(result.returncode, 2)
        self.assertIn("error", payload)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
