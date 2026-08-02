import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.evidence_scope import evidence_scope_is_current
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
        self.assertTrue(evidence_scope_is_current(report, registry))
        self.assertEqual(
            set(report["python_backends"]["methods"]),
            {"liana-cellphonedb", "cellphonedb-statistical"},
        )
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

    def test_pairwise_alignment_template_executes_with_declared_two_sequence_contract(self):
        artifact = {
            "format": "inline-json", "format_version": "1", "compression": "none", "indexes": [],
            "coordinate_system": None, "genome_build": None, "annotation_release": None,
            "orientation": "request-object", "metadata_fields": [], "representation": "structured",
            "sort_order": "unsorted", "reference_sequence_digest": None, "identifier_namespace": None,
            "sample_manifest_digest": None, "payload_roles": [], "processing_level": "declared",
        }
        request = {
            "parameters": {"reference": "ACGT", "query": "AGT", "alphabet": "dna", "mode": "global"},
            "artifacts": [{"port": "reference", **artifact}, {"port": "query", **artifact}],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            output_path = root / "result.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "biomed_workbench/modules/builtin/sequence-pairwise-alignment/templates/run_sequence_pairwise_alignment.py",
                    "--request", str(request_path), "--output", str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path.is_file() else {}

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload.get("module_id"), "sequence-pairwise-alignment")
        self.assertEqual(payload.get("result", {}).get("query_aligned"), "A-GT")
        self.assertEqual(payload.get("result", {}).get("identity_fraction"), 1.0)

    def test_orf_annotation_template_executes_with_declared_genetic_code(self):
        artifact = {
            "port": "sequence", "format": "inline-json", "format_version": "1", "compression": "none",
            "indexes": [], "coordinate_system": None, "genome_build": None, "annotation_release": None,
            "orientation": "request-object", "metadata_fields": [], "representation": "structured",
            "sort_order": "unsorted", "reference_sequence_digest": None, "identifier_namespace": None,
            "sample_manifest_digest": None, "payload_roles": [], "processing_level": "declared",
        }
        request = {
            "parameters": {"sequence": "ATGAAATAATTATTTCAT", "min_length": 9, "search_reverse": True, "filter_nested": False},
            "artifacts": [artifact],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            output_path = root / "result.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "biomed_workbench/modules/builtin/open-reading-frame-annotation/templates/run_open_reading_frame_annotation.py",
                    "--request", str(request_path), "--output", str(output_path),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path.is_file() else {}

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(payload.get("module_id"), "open-reading-frame-annotation")
        self.assertEqual(payload.get("result", {}).get("summary", {}).get("total_orf_count"), 2)


if __name__ == "__main__":
    unittest.main()
