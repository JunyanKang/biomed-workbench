import tempfile
import unittest
from pathlib import Path

from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.orchestration.graph import build_capability_graph, consumers, producers
from tests.unit.test_module_contract import valid_manifest_payload
from tests.unit.test_module_registry import write_manifest


class FutureModuleGraphEndToEndTests(unittest.TestCase):
    def test_unknown_domain_and_artifact_types_enter_graph_without_kernel_edits(self):
        source_path = Path(__file__).resolve().parents[2] / "biomed_workbench" / "orchestration" / "graph.py"
        source_before = source_path.read_bytes()
        payload = valid_manifest_payload()
        payload.update(
            {
                "id": "future-biomarker-validator",
                "title": "Validate future biomarker evidence",
                "description": "Validate a future biomarker from a quality report and emit a versioned biomarker table.",
                "module_type": "validation",
                "domains": ["systems_biology"],
                "intents": ["validate future biomarker"],
                "questions": ["Does the future biomarker pass its independent validation criteria?"],
            }
        )
        payload["input_artifacts"][0]["artifact_type"] = "quality_report"
        payload["output_artifacts"][0]["artifact_type"] = "novel_biomarker_table"

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_manifest(root, payload)
            graph = build_capability_graph(ModuleRegistry.discover(root))

        self.assertEqual(graph.module_ids, ("future-biomarker-validator",))
        self.assertEqual(producers(graph, "novel_biomarker_table"), ("future-biomarker-validator",))
        self.assertEqual(consumers(graph, "quality_report"), ("future-biomarker-validator",))
        self.assertIn("validates", {edge.relation for edge in graph.edges})
        self.assertEqual(source_path.read_bytes(), source_before)


if __name__ == "__main__":
    unittest.main()
