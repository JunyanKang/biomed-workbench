import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/flow-immunophenotype-summary/templates/run_flow_immunophenotype_summary.py"


def artifact(port, orientation, metadata_fields, processing_level):
    return {
        "port": port,
        "format": "inline-json",
        "format_version": "1",
        "compression": "none",
        "indexes": [],
        "coordinate_system": None,
        "genome_build": None,
        "annotation_release": None,
        "orientation": orientation,
        "metadata_fields": metadata_fields,
        "representation": "structured",
        "sort_order": "unsorted",
        "reference_sequence_digest": None,
        "identifier_namespace": None,
        "sample_manifest_digest": None,
        "payload_roles": [],
        "processing_level": processing_level,
    }


class FlowImmunophenotypeTemplateTests(unittest.TestCase):
    def test_template_executes_reviewed_marker_pattern_contract(self):
        request = {
            "parameters": {
                "events": [{"CD3": 12.0, "CD4": 8.0}, {"CD3": 14.0, "CD4": 2.0}],
                "gates": [{"name": "live_singlets", "event_indices": [0, 1]}],
                "population_rules": [{"name": "cd3_cd4_pattern", "parent_gate": "live_singlets", "conditions": {"CD3": {"min": 10.0}, "CD4": {"min": 5.0}}}],
                "control_review": {"panel_identity": "panel-a", "sample_identity": "sample-1", "compensation_reviewed": True, "transformation_declared": True, "threshold_basis_reviewed": True},
            },
            "artifacts": [
                artifact("events", "event-by-channel", ["source_name"], "parsed"),
                artifact("gates", "module-output", ["module_version", "compatibility_row_id", "gate_order", "event_indices"], "derived"),
            ],
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
        self.assertEqual(output["module_id"], "flow-immunophenotype-summary")
        self.assertEqual(output["result"]["population_patterns"][0]["event_count"], 1)
        self.assertTrue(output["provenance"]["output_digest"])


if __name__ == "__main__":
    unittest.main()
