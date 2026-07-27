import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / "xenograft-tumor-growth" / "templates" / "run_xenograft_tumor_growth.py"


class XenograftTemplateTests(unittest.TestCase):
    def test_template_executes_animal_level_endpoint_summary(self):
        artifact = {
            "port": "xenograft_observations", "format": "inline-json", "format_version": "1", "compression": "none",
            "indexes": [], "coordinate_system": "elapsed-days", "genome_build": None, "annotation_release": None,
            "orientation": "animal-by-time-and-volume",
            "metadata_fields": ["study-design", "volume-method", "randomization-and-blinding-policy", "endpoint-policy", "treatment-exposure"],
            "representation": "structured", "sort_order": "ascending-time", "reference_sequence_digest": None,
            "identifier_namespace": None, "sample_manifest_digest": None, "payload_roles": [], "processing_level": "animal-level",
        }
        request = {"parameters": {"observations": [
            {"animal_id": "c1", "group": "vehicle", "time_days": 0.0, "tumor_volume_mm3": 100.0},
            {"animal_id": "c1", "group": "vehicle", "time_days": 10.0, "tumor_volume_mm3": 300.0},
            {"animal_id": "t1", "group": "drug", "time_days": 0.0, "tumor_volume_mm3": 100.0},
            {"animal_id": "t1", "group": "drug", "time_days": 10.0, "tumor_volume_mm3": 150.0},
        ], "control_group": "vehicle"}, "artifacts": [artifact]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path, output_path = root / "request.json", root / "result.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(TEMPLATE), "--request", str(request_path), "--output", str(output_path)], cwd=ROOT, capture_output=True, text=True, check=False)
            output = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {}
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["module_id"], "xenograft-tumor-growth")
        drug = next(row for row in output["result"]["endpoint_group_summary"] if row["group"] == "drug")
        self.assertAlmostEqual(drug["tumor_growth_inhibition_percent_vs_control"], 75.0)
        self.assertTrue(output["provenance"]["output_digest"])


if __name__ == "__main__":
    unittest.main()
