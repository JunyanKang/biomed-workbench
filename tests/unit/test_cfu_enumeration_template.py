import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/cfu-enumeration/templates/run_cfu_enumeration.py"


def artifact():
    return {
        "port": "dilution_plate_observations",
        "format": "inline-json",
        "format_version": "1",
        "compression": "none",
        "indexes": [],
        "coordinate_system": None,
        "genome_build": None,
        "annotation_release": None,
        "orientation": "plate-by-observed-colony-count",
        "metadata_fields": [
            "sample-identity",
            "dilution-definition",
            "plated-volume-unit",
            "medium-and-incubation",
            "plate-identity",
            "replicate-level",
        ],
        "representation": "structured",
        "sort_order": "unsorted",
        "reference_sequence_digest": None,
        "identifier_namespace": None,
        "sample_manifest_digest": None,
        "payload_roles": [],
        "processing_level": "reviewed",
    }


class CfuEnumerationTemplateTests(unittest.TestCase):
    def test_template_executes_plate_bound_estimate(self):
        request = {
            "parameters": {
                "replicate_level": "biological",
                "plates": [
                    {"plate_id": "d4-a", "replicate_id": "culture-a", "dilution_factor": 10000, "plated_volume_ml": 0.1, "count_status": "counted", "colony_count": 92},
                    {"plate_id": "d4-b", "replicate_id": "culture-b", "dilution_factor": 10000, "plated_volume_ml": 0.1, "count_status": "counted", "colony_count": 96},
                ],
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
        self.assertEqual(output["module_id"], "cfu-enumeration")
        self.assertTrue(output["result"]["estimate_admissible"])
        self.assertAlmostEqual(output["result"]["cfu_per_ml"], 9_400_000.0)
        self.assertTrue(output["provenance"]["output_digest"])


if __name__ == "__main__":
    unittest.main()
