import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench" / "modules" / "builtin" / "western-blot-densitometry" / "templates" / "run_western_blot_densitometry.py"


def artifact():
    return {
        "port": "reviewed_blot_rois",
        "format": "inline-json",
        "format_version": "1",
        "compression": "none",
        "indexes": [],
        "coordinate_system": "image-pixel-roi",
        "genome_build": None,
        "annotation_release": None,
        "orientation": "lane-by-target-and-control-measurement",
        "metadata_fields": [
            "original-image-digest",
            "target-antibody",
            "exposure-and-saturation-review",
            "roi-review-policy",
            "sample-provenance",
        ],
        "representation": "structured",
        "sort_order": "lane-identity",
        "reference_sequence_digest": None,
        "identifier_namespace": None,
        "sample_manifest_digest": None,
        "payload_roles": [],
        "processing_level": "roi-reviewed",
    }


class WesternBlotTemplateTests(unittest.TestCase):
    def test_template_executes_reviewed_roi_normalization(self):
        request = {
            "parameters": {
                "measurements": [
                    {
                        "lane_id": "control-1",
                        "condition": "control",
                        "target_integrated_intensity": 1200.0,
                        "target_background_per_pixel": 2.0,
                        "target_area_pixels": 100.0,
                        "loading_control_integrated_intensity": 1000.0,
                        "loading_control_background_per_pixel": 2.0,
                        "loading_control_area_pixels": 100.0,
                    },
                    {
                        "lane_id": "treated-1",
                        "condition": "treated",
                        "target_integrated_intensity": 2200.0,
                        "target_background_per_pixel": 2.0,
                        "target_area_pixels": 100.0,
                        "loading_control_integrated_intensity": 1000.0,
                        "loading_control_background_per_pixel": 2.0,
                        "loading_control_area_pixels": 100.0,
                    },
                ],
                "reference_lane_ids": ["control-1"],
                "replicate_level": "biological",
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
        self.assertEqual(output["module_id"], "western-blot-densitometry")
        self.assertAlmostEqual(output["result"]["lanes"][1]["fold_change_vs_reference"], 2.0)
        self.assertTrue(output["provenance"]["output_digest"])


if __name__ == "__main__":
    unittest.main()
