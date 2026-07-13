import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.template_quality import (
    is_bioinformatics_module,
    referenced_template_paths,
    validate_module_templates,
)
from tools.audit_bioinformatics_templates import build


ROOT = Path(__file__).resolve().parents[2]


class BioinformaticsTemplateTests(unittest.TestCase):
    def test_every_bioinformatics_module_has_a_passing_code_template(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        modules = [module for module in registry.all() if is_bioinformatics_module(module)]

        self.assertGreaterEqual(len(modules), 38)
        for module in modules:
            self.assertGreaterEqual(len(referenced_template_paths(module)), 1, module.id)
            self.assertEqual(validate_module_templates(BUILTIN_ROOT / module.id, module), [], module.id)

    def test_checked_template_report_exactly_matches_registry(self):
        checked = json.loads((ROOT / "reports/bioinformatics-template-coverage.json").read_text(encoding="utf-8"))

        self.assertEqual(checked, build())
        self.assertTrue(checked["passed"])
        self.assertEqual(checked["bioinformatics_module_count"], checked["covered_module_count"])
        self.assertEqual(checked["covered_module_count"], checked["passing_module_count"])

    def test_deterministic_template_scaffold_is_current(self):
        result = subprocess.run(
            [sys.executable, "tools/scaffold_bioinformatics_templates.py", "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_four_backend_communication_evidence_is_bound_to_registry(self):
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        module = registry.get("single-cell-communication")
        report = json.loads((ROOT / "reports/single-cell-communication-live-verification.json").read_text(encoding="utf-8"))

        self.assertTrue(report["passed"])
        self.assertEqual(report["module_id"], module.id)
        self.assertEqual(report["module_version"], module.version)
        self.assertEqual(report["registry_digest"], registry.digest)
        self.assertEqual(set(report["python_backends"]["methods"]), {"liana-rank-aggregate", "cellphonedb-statistical"})
        self.assertEqual(set(report["r_backends"]["methods"]), {"cellchat", "nichenet"})

    def test_generated_template_executes_from_its_source_path(self):
        request = {
            "parameters": {"sequence": "ACGTACGT", "alphabet": "dna"},
            "artifacts": [
                {
                    "port": "sequence", "format": "inline-json", "format_version": "1",
                    "compression": "none", "indexes": [], "coordinate_system": None,
                    "genome_build": None, "annotation_release": None, "orientation": "request-object",
                    "metadata_fields": [], "representation": "structured", "sort_order": "unsorted",
                    "reference_sequence_digest": None, "identifier_namespace": None,
                    "sample_manifest_digest": None, "payload_roles": [], "processing_level": "declared",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            output_path = root / "result.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "biomed_workbench/modules/builtin/sequence-inspect/templates/run_sequence_inspect.py",
                    "--request", str(request_path), "--output", str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path.is_file() else {}

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload.get("module_id"), "sequence-inspect")
        self.assertEqual(payload.get("result", {}).get("length"), 8)
        self.assertTrue(payload.get("provenance", {}).get("output_digest"))


if __name__ == "__main__":
    unittest.main()
