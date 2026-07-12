import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.catalog import CapabilitySpecificationError, all_capabilities, load_capabilities


ROOT = Path(__file__).resolve().parents[2]
SPEC_ROOT = ROOT / "biomed_workbench" / "capability_specs"
WORKFLOWS = {"evidence", "omics", "molecular_design", "imaging", "clinical", "wetlab", "publication"}


class RegistryLayoutTests(unittest.TestCase):
    def test_each_workflow_has_one_versioned_specification(self):
        files = sorted(SPEC_ROOT.glob("*.json"))
        self.assertEqual({path.stem for path in files}, WORKFLOWS)
        count = 0
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["workflow"], path.stem)
            self.assertTrue(payload["capabilities"])
            self.assertTrue(all(row["workflow"] == path.stem for row in payload["capabilities"]))
            count += len(payload["capabilities"])
        self.assertEqual(count, len(all_capabilities()))

    def test_loader_rejects_duplicate_ids_across_domain_files(self):
        row = {
            "id": "duplicate",
            "workflow": "evidence",
            "kind": "python",
            "title": "Duplicate fixture",
            "description": "A valid duplicate capability fixture for registry validation.",
            "entrypoint": "biomed_workbench.capabilities.data:sequence_inspect",
            "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            "requirements": [],
            "access": "offline",
            "mutability": "read_only",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for workflow in ("evidence", "omics"):
                workflow_row = {**row, "workflow": workflow}
                payload = {"schema_version": 1, "workflow": workflow, "capabilities": [workflow_row]}
                (root / f"{workflow}.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(CapabilitySpecificationError):
                load_capabilities(root)

    def test_central_registry_contains_no_builtin_capability_definitions(self):
        text = (ROOT / "biomed_workbench" / "catalog.py").read_text(encoding="utf-8")
        self.assertNotIn("def _register_builtins", text)
        self.assertNotIn("Capability(\n", text)


if __name__ == "__main__":
    unittest.main()
