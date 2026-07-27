import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / "radiotracer-biodistribution" / "templates" / "run_radiotracer_biodistribution.py"


class RadiotracerBiodistributionTemplateTests(unittest.TestCase):
    def test_template_executes_declared_measurement_accounting(self):
        artifact = {
            "port": "biodistribution_measurements", "format": "inline-json", "format_version": "1",
            "compression": "none", "indexes": [], "coordinate_system": "elapsed-time",
            "genome_build": None, "annotation_release": None,
            "orientation": "sample-organ-by-activity-and-mass",
            "metadata_fields": ["radionuclide", "injected-dose-calibration", "decay-correction-reference-time", "counting-efficiency", "sample-provenance"],
            "representation": "structured", "sort_order": "ascending-time",
            "reference_sequence_digest": None, "identifier_namespace": None, "sample_manifest_digest": None,
            "payload_roles": [], "processing_level": "calibrated",
        }
        request = {
            "parameters": {
                "measurements": [
                    {"sample_id": "m1", "organ": "tumor", "time_hours": 1.0, "injected_dose_bq": 1000.0, "tissue_activity_bq": 20.0, "tissue_mass_g": 0.2},
                    {"sample_id": "m1", "organ": "blood", "time_hours": 1.0, "injected_dose_bq": 1000.0, "tissue_activity_bq": 10.0, "tissue_mass_g": 0.5},
                ],
                "tumor_organ": "tumor", "blood_organ": "blood", "replicate_level": "biological",
            },
            "artifacts": [artifact],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path, output_path = root / "request.json", root / "result.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(TEMPLATE), "--request", str(request_path), "--output", str(output_path)], cwd=ROOT, capture_output=True, text=True, check=False)
            output = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["module_id"], "radiotracer-biodistribution")
        self.assertAlmostEqual(output["result"]["measurements"][0]["percent_injected_dose_per_gram"], 10.0)
        self.assertTrue(output["provenance"]["output_digest"])


if __name__ == "__main__":
    unittest.main()
