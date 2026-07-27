import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / "fixed-period-cosinor" / "templates" / "run_fixed_period_cosinor.py"


def artifact():
    return {
        "port": "time_series",
        "format": "inline-json",
        "format_version": "1",
        "compression": "none",
        "indexes": [],
        "coordinate_system": "elapsed-time",
        "genome_build": None,
        "annotation_release": None,
        "orientation": "observation-by-time-and-value",
        "metadata_fields": ["time-unit", "outcome-unit", "sampling-protocol", "period-declaration"],
        "representation": "structured",
        "sort_order": "ascending-time",
        "reference_sequence_digest": None,
        "identifier_namespace": None,
        "sample_manifest_digest": None,
        "payload_roles": [],
        "processing_level": "measured",
    }


class FixedPeriodCosinorTemplateTests(unittest.TestCase):
    def test_template_executes_declared_period_fit(self):
        request = {
            "parameters": {
                "time": [0.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0, 21.0],
                "values": [12.0, 11.4142135624, 10.0, 8.5857864376, 8.0, 8.5857864376, 10.0, 11.4142135624],
                "period": 24.0,
            },
            "artifacts": [artifact()],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            output_path = root / "result.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(TEMPLATE), "--request", str(request_path), "--output", str(output_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            output = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["module_id"], "fixed-period-cosinor")
        self.assertEqual(output["result"]["observation_count"], 8)
        self.assertAlmostEqual(output["result"]["parameters"]["amplitude"], 2.0, places=6)
        self.assertTrue(output["provenance"]["output_digest"])


if __name__ == "__main__":
    unittest.main()
