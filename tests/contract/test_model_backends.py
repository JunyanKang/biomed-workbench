import tempfile
import unittest
from pathlib import Path

from biomed_workbench.services.model_backends import backend_catalog, build_model_command, select_backend
from biomed_workbench.services.model_execution import run_local_model


class ModelBackendContractTests(unittest.TestCase):
    def test_registry_contains_only_open_local_scientific_backends(self):
        catalog = backend_catalog()
        self.assertEqual(set(catalog), {"boltz", "diffdock", "foldseek", "mmseqs", "proteinmpnn"})
        for backend in catalog.values():
            self.assertTrue(backend.code_license)
            self.assertTrue(backend.weight_license)
            self.assertTrue(backend.license_url.startswith("https://github.com/"))
            self.assertNotIn("api_key", repr(backend).lower())
            self.assertNotIn("hosted", repr(backend).lower())

    def test_unavailable_backend_never_falls_back_to_a_hosted_service(self):
        selection = select_backend("structure_prediction", available=set())
        self.assertEqual(selection["status"], "unavailable")
        self.assertFalse(selection["network_fallback"])

    def test_command_builder_uses_registered_input_contract(self):
        command = build_model_command("proteinmpnn", {"structure": "target.pdb", "output": "designs", "sequences": 4})
        self.assertEqual(command[:2], ["protein_mpnn_run.py", "--pdb_path"])
        self.assertIn("4", command)
        with self.assertRaises(ValueError):
            build_model_command("boltz", {"input": "target.yaml", "output": "results", "api_key": "secret"})

    def test_local_model_run_requires_permission_and_confines_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def execute(argv, timeout):
                output = Path(argv[argv.index("--out_dir") + 1])
                output.mkdir(parents=True)
                (output / "prediction.cif").write_text("data_test\n", encoding="utf-8")
                return 0, "done", ""

            with self.assertRaises(PermissionError):
                run_local_model("boltz", {"input": "target.yaml", "output": "results"}, str(root), permission_granted=False, executor=execute)
            result = run_local_model("boltz", {"input": "target.yaml", "output": "results"}, str(root), permission_granted=True, executor=execute)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["artifacts"][0]["path"], str((root / "results" / "prediction.cif").resolve()))
            self.assertTrue(Path(result["manifest_path"]).exists())
            with self.assertRaises(ValueError):
                run_local_model("boltz", {"input": "target.yaml", "output": "../escape"}, str(root), permission_granted=True, executor=execute)


if __name__ == "__main__":
    unittest.main()
