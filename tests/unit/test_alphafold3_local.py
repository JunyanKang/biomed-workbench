import json
import tempfile
import unittest
from pathlib import Path

from biomed_workbench.implementations.alphafold3_local import (
    build_local_command,
    execute_alphafold3_local,
)


class AlphaFold3LocalExecutorTests(unittest.TestCase):
    def request(self, root: Path, executable: Path) -> dict[str, object]:
        input_path = root / "alphafold3_input.json"
        input_path.write_text(
            json.dumps(
                {
                    "name": "test",
                    "modelSeeds": [1],
                    "sequences": [{"protein": {"id": "A", "sequence": "ACDE"}}],
                    "dialect": "alphafold3",
                    "version": 4,
                }
            ),
            encoding="utf-8",
        )
        model = root / "models"
        database = root / "databases"
        output = root / "output"
        model.mkdir()
        database.mkdir()
        return {
            "backend": "local-native",
            "input_path": str(input_path),
            "output_directory": str(output),
            "model_directory": str(model),
            "database_directory": str(database),
            "container_image": "alphafold3:3.0.3",
            "local_executable": str(executable),
            "container_runtime_executable": None,
            "portable_runtime_executable": None,
            "run_data_pipeline": True,
            "run_inference": True,
            "num_recycles": 10,
            "num_diffusion_samples": 5,
            "num_seeds": 1,
            "save_distogram": False,
            "save_embeddings": False,
            "compress_large_output_files": False,
            "jax_compilation_cache_dir": None,
            "timeout_seconds": 3600,
        }

    def test_native_command_is_closed_and_version_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "run_alphafold.py"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            command, provenance = build_local_command(self.request(root, executable))
            self.assertEqual(command[0], str(executable.resolve()))
            self.assertIn("--run_inference=true", command)
            self.assertEqual(provenance["alphafold3_release"], "3.0.3")
            self.assertEqual(len(provenance["input_sha256"]), 64)

    def test_executor_runs_only_the_prevalidated_command_and_reloads_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "run_alphafold.py"
            executable.write_text("#!/bin/sh\nprintf 'controlled local fixture\\n'\n", encoding="utf-8")
            executable.chmod(0o755)
            report = execute_alphafold3_local(self.request(root, executable))
            self.assertEqual(report["state"], "completed")
            log = root / "output" / report["runtime_log"]["path"]
            self.assertIn("controlled local fixture", log.read_text(encoding="utf-8"))
            self.assertEqual(len(report["runtime_log"]["sha256"]), 64)

    def test_unknown_fields_and_wrong_dialect_are_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "run_alphafold.py"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
            payload = self.request(root, executable)
            payload["unreviewed"] = True
            with self.assertRaisesRegex(ValueError, "closed execution contract"):
                build_local_command(payload)


if __name__ == "__main__":
    unittest.main()
