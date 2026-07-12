import unittest
from pathlib import Path

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.orchestration.graph import build_capability_graph, consumers, producers


ROOT = Path(__file__).resolve().parents[3]


class CapabilityGraphTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModuleRegistry.discover(BUILTIN_ROOT)
        self.graph = build_capability_graph(self.registry)

    def test_graph_is_deterministic_and_contains_all_manifest_relationships(self):
        repeated = build_capability_graph(self.registry)
        relations = set(self.graph.relation_types)

        self.assertEqual(self.graph, repeated)
        self.assertEqual(len(self.graph.module_ids), 56)
        self.assertRegex(self.graph.digest, r"^[0-9a-f]{64}$")
        self.assertTrue({"consumes", "produces", "validates", "alternative-to", "complements", "addresses-intent", "addresses-question"} <= relations)
        self.assertIn("complements", {edge.relation for edge in self.graph.edges})
        alternative_edges = {(edge.source, edge.target) for edge in self.graph.edges if edge.relation == "alternative-to"}
        self.assertIn(("module_read-quality-fastqc", "module_read-quality-fastp"), alternative_edges)
        self.assertIn(("module_read-quality-fastp", "module_read-quality-fastqc"), alternative_edges)
        self.assertEqual(self.graph.module_ids, tuple(sorted(self.graph.module_ids)))
        self.assertEqual(self.graph.artifact_types, tuple(sorted(self.graph.artifact_types)))

    def test_producer_and_consumer_queries_use_artifact_contracts(self):
        quality_producers = producers(self.graph, "quality_report")
        matrix_consumers = consumers(self.graph, "expression_matrix")

        self.assertIn("data-profile", quality_producers)
        self.assertIn("expression-qc", quality_producers)
        self.assertIn("differential-expression", matrix_consumers)
        self.assertIn("expression-qc", matrix_consumers)

    def test_graph_source_has_no_module_specific_registration(self):
        source = (ROOT / "biomed_workbench" / "orchestration" / "graph.py").read_text(encoding="utf-8")

        self.assertNotIn("single-cell-qc", source)
        self.assertNotIn("ncbi-search", source)
        self.assertNotIn("manuscript-audit", source)
        self.assertNotIn("MODULE_IDS", source)


if __name__ == "__main__":
    unittest.main()
