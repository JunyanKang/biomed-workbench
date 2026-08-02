import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.template_quality import validate_code_template
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.template_quality import referenced_template_paths


ROOT = Path(__file__).resolve().parents[2]


class TemplateExecutionAdapterTests(unittest.TestCase):
    def test_thin_cli_is_checked_through_product_owned_implementation(self):
        path = ROOT / "biomed_workbench/modules/builtin/bulk-nascent-transcription/templates/run_nfcore_nascent.py"
        self.assertEqual(validate_code_template(path), [])

    def test_runtime_support_has_a_narrow_compatibility_contract(self):
        path = ROOT / "biomed_workbench/modules/builtin/bulk-ribosome-profiling/templates/ribotish_python314_sitecustomize.py"
        self.assertEqual(validate_code_template(path), [])

    def test_r_execution_adapter_is_not_misclassified_as_an_analysis_notebook(self):
        path = ROOT / "biomed_workbench/modules/builtin/bulk-rbp-rna-binding/templates/run_ripseeker.R"
        self.assertEqual(validate_code_template(path), [])

    def test_missing_delegated_implementation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "biomed_workbench" / "implementations"
            package.mkdir(parents=True)
            adapter = root / "templates" / "run_missing.py"
            adapter.parent.mkdir()
            adapter.write_text(
                "import argparse, json\n"
                "from pathlib import Path\n"
                "from biomed_workbench.implementations.missing import execute_missing\n"
                "def main():\n"
                " p=argparse.ArgumentParser(); p.add_argument('--request', type=Path); a=p.parse_args()\n"
                " return execute_missing(json.loads(a.request.read_text()))\n",
                encoding="utf-8",
            )
            errors = validate_code_template(adapter)
        self.assertTrue(any("delegated implementation is missing" in error for error in errors))

    def test_all_bulk_python_execution_adapters_start_outside_the_repository(self):
        modules = ROOT / "biomed_workbench/modules/builtin"
        adapters = sorted(
            path
            for path in modules.glob("bulk-*/templates/*.py")
            if "from biomed_workbench.implementations" in path.read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(adapters), 15)
        with tempfile.TemporaryDirectory() as temporary:
            for adapter in adapters:
                completed = subprocess.run(
                    [sys.executable, str(adapter), "--help"],
                    cwd=temporary,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(completed.returncode, 0, f"{adapter}: {completed.stderr}")

    def test_agent_python_clis_bootstrap_product_imports_from_their_source_path(self):
        missing = []
        for manifest in ModuleRegistry.discover(BUILTIN_ROOT).all():
            if manifest.access != "agent_generated":
                continue
            for relative in referenced_template_paths(manifest):
                path = BUILTIN_ROOT / manifest.id / relative
                if path.suffix != ".py" or path.name.endswith("sitecustomize.py"):
                    continue
                text = path.read_text(encoding="utf-8")
                if "argparse" in text and "biomed_workbench." in text and "sys.path.insert" not in text:
                    missing.append(f"{manifest.id}/{relative}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
