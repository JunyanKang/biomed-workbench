import unittest

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
from biomed_workbench.visualization import scientific_figure_standard


class MolecularStructureNetworkProfilesTests(unittest.TestCase):
    def test_new_analysis_profiles_share_publication_export_contract(self):
        expected = {
            "protein-interaction-network": "ppi_network",
            "protein-complex-docking": "structure_complex",
            "alphafold3-complex": "structure_confidence",
            "metascape-msbio": "enrichment_similarity_network",
        }
        for analysis_type, required_plot in expected.items():
            with self.subTest(analysis_type=analysis_type):
                contract = scientific_figure_standard(analysis_type)
                self.assertEqual(contract["style"]["version"], "1.2.0")
                self.assertIn(required_plot, contract["required_plots"])
                self.assertEqual(contract["style"]["export"]["raster_dpi"], 600)
                self.assertEqual(contract["style"]["export"]["primary"], ["pdf", "svg"])
                self.assertGreaterEqual(contract["style"]["typography_pt"]["minimum"], 5.0)
                self.assertGreaterEqual(contract["style"]["strokes_pt"]["minimum"], 0.5)

    def test_metascape_contract_closes_only_task_owned_cytoscape(self):
        manifest = ModuleRegistry.discover(BUILTIN_ROOT).get("metascape-msbio-network-analysis")
        protocol = manifest.agent_protocol
        self.assertIsNotNone(protocol)
        postflight = " ".join(protocol.postflight_checks)
        forbidden = " ".join(protocol.forbidden_actions)
        self.assertIn("task-owned process terminated", postflight)
        self.assertIn("never close", postflight)
        self.assertIn("Do not leave a task-launched Cytoscape process running", forbidden)
        self.assertIn("do not terminate a pre-existing user-owned", forbidden)


if __name__ == "__main__":
    unittest.main()
