from __future__ import annotations

import json
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import sys

from biomed_workbench.implementations.publication_figure import FROZEN_COLORBLIND_SAFE, FROZEN_DIVERGING, FROZEN_STYLE_VERSION, render_package
from biomed_workbench.kernel.artifact_store import ProjectArtifactStore
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.modules.scientific_command import execute_scientific_command
from biomed_workbench.visualization import COLORBLIND_SAFE, DIVERGING, STYLE_VERSION


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "publication_figure"


class PublicationFigurePackageTests(unittest.TestCase):
    def test_standalone_command_style_snapshot_matches_shared_contract(self) -> None:
        self.assertEqual(FROZEN_STYLE_VERSION, STYLE_VERSION)
        self.assertEqual(FROZEN_COLORBLIND_SAFE, COLORBLIND_SAFE)
        self.assertEqual(FROZEN_DIVERGING, DIVERGING)

    def test_renders_and_reloads_all_outputs_without_signal_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "package.zip"
            report_path = Path(temp) / "report.json"
            report = render_package(
                FIXTURES / "controlled_biomedical_data.tsv",
                FIXTURES / "controlled_figure_spec.json",
                package,
                report_path,
                "tsv",
            )
            self.assertTrue(report["ready"])
            self.assertEqual(report["quality_gates"]["negative-result-preservation"], "not-signal-gated")
            self.assertEqual([row["row_count"] for row in report["panels"]], [12, 12, 12, 12])
            self.assertTrue(report["reload_validation"]["source_data"]["all_panels_reloaded_without_row_loss"])
            with zipfile.ZipFile(package) as archive:
                names = set(archive.namelist())
                self.assertTrue({"figure.pdf", "figure.svg", "figure.png", "manifest.json", "figure-specification.json"} <= names)
                self.assertEqual(len([name for name in names if name.startswith("source-data/")]), 4)
            self.assertEqual(json.loads(report_path.read_text(encoding="utf-8"))["package"]["sha256"], report["package"]["sha256"])

    def test_rejects_unverified_target_journal_profile(self) -> None:
        spec = json.loads((FIXTURES / "controlled_figure_spec.json").read_text(encoding="utf-8"))
        spec["journal_profile"] = "cell"
        with tempfile.TemporaryDirectory() as temp:
            spec_path = Path(temp) / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "current target-journal guide"):
                render_package(FIXTURES / "controlled_biomedical_data.tsv", spec_path, Path(temp) / "package.zip", Path(temp) / "report.json", "tsv")

    def test_rejects_missing_values_in_plotted_columns(self) -> None:
        data = (FIXTURES / "controlled_biomedical_data.tsv").read_text(encoding="utf-8").replace("S01\tcontrol\t0\t1.02", "S01\tcontrol\t0\t")
        with tempfile.TemporaryDirectory() as temp:
            data_path = Path(temp) / "data.tsv"
            data_path.write_text(data, encoding="utf-8")
            spec = json.loads((FIXTURES / "controlled_figure_spec.json").read_text(encoding="utf-8"))
            digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
            spec["source_table_sha256"] = digest
            for panel in spec["panels"]:
                panel["source_table_sha256"] = digest
            spec_path = Path(temp) / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing plotted values"):
                render_package(data_path, spec_path, Path(temp) / "package.zip", Path(temp) / "report.json", "tsv")

    def test_registered_scientific_command_executes_content_addressed_outputs(self) -> None:
        manifest = ModuleRegistry.discover(ROOT / "biomed_workbench" / "modules" / "builtin").get("publication-figure-package")
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectArtifactStore(Path(temp) / "artifacts")
            data = store.import_file(FIXTURES / "controlled_biomedical_data.tsv", role="data", media_type="text/tab-separated-values")
            spec = store.import_file(FIXTURES / "controlled_figure_spec.json", role="specification", media_type="application/json")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"data": data, "spec": spec},
                parameters={"data-format": "tsv"},
                tool_versions={"python3": "3.14.3"},
                dependency_versions={"matplotlib": "3.10.8", "pandas": "2.3.3", "numpy": "2.4.4", "Pillow": "10.4.0", "PyMuPDF": "1.27.2"},
                compatibility_row_id="python314-matplotlib310-publication-figure-v1",
                executable_resolver=lambda _name: Path(sys.executable),
            )
            self.assertEqual({payload.role for payload in result.output_payloads}, {"package", "report"})
            package = next(payload for payload in result.output_payloads if payload.role == "package")
            report = next(payload for payload in result.output_payloads if payload.role == "report")
            with zipfile.ZipFile(store.resolve(package)) as archive:
                self.assertIn("figure.pdf", archive.namelist())
            self.assertTrue(json.loads(store.resolve(report).read_text(encoding="utf-8"))["ready"])


if __name__ == "__main__":
    unittest.main()
