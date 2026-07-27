import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / "accelerated-stability" / "templates" / "run_accelerated_stability.py"


class AcceleratedStabilityTemplateTests(unittest.TestCase):
    def test_template_executes_bounded_arrhenius_fit(self):
        artifact = {"port": "stability_observations", "format": "inline-json", "format_version": "1", "compression": "none", "indexes": [], "coordinate_system": "elapsed-days", "genome_build": None, "annotation_release": None, "orientation": "temperature-by-time-and-potency", "metadata_fields": ["assay-method", "storage-condition", "container-closure", "sampling-schedule", "acceptance-specification"], "representation": "structured", "sort_order": "ascending-time", "reference_sequence_digest": None, "identifier_namespace": None, "sample_manifest_digest": None, "payload_roles": [], "processing_level": "assay-qualified"}
        request = {"parameters": {"observations": [
            {"temperature_c": 25.0, "time_days": 0.0, "potency_percent": 100.0},
            {"temperature_c": 25.0, "time_days": 10.0, "potency_percent": 90.0},
            {"temperature_c": 25.0, "time_days": 20.0, "potency_percent": 81.0},
            {"temperature_c": 40.0, "time_days": 0.0, "potency_percent": 100.0},
            {"temperature_c": 40.0, "time_days": 10.0, "potency_percent": 80.0},
            {"temperature_c": 40.0, "time_days": 20.0, "potency_percent": 64.0},
        ], "target_temperature_c": 30.0, "specification_percent": 90.0}, "artifacts": [artifact]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path, output_path = root / "request.json", root / "result.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(TEMPLATE), "--request", str(request_path), "--output", str(output_path)], cwd=ROOT, capture_output=True, text=True, check=False)
            output = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["module_id"], "accelerated-stability")
        self.assertEqual(output["result"]["selected_kinetic_model"], "first-order")
        self.assertTrue(output["provenance"]["output_digest"])


if __name__ == "__main__":
    unittest.main()
