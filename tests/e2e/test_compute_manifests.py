import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def executable(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ComputeManifestE2ETests(unittest.TestCase):
    def run_capability(self, capability_id, payload, path):
        environment = os.environ.copy()
        environment["PATH"] = f"{path}{os.pathsep}{environment.get('PATH', '')}"
        process = subprocess.run(
            [sys.executable, "tools/run_tool.py", capability_id, "--input", json.dumps(payload), "--allow-mutation"],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(process.stdout)["output"]

    def test_container_run_reaches_fake_engine_and_persists_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable(root / "docker", "printf 'container-complete\\n'\n")
            result = self.run_capability(
                "container-run",
                {"image": "example/model:1", "command": ["predict"], "output_directory": str(root / "results")},
                root,
            )
            self.assertEqual(result["status"], "completed")
            self.assertTrue(Path(result["manifest_path"]).exists())

    def test_slurm_submit_reaches_fake_scheduler_and_persists_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable(root / "sbatch", "printf '9001;test-cluster\\n'\n")
            result = self.run_capability(
                "slurm-submit",
                {
                    "command": ["python", "run.py"],
                    "job_name": "fold",
                    "cpus": 2,
                    "memory_gb": 8,
                    "time_minutes": 30,
                    "output_directory": str(root / "jobs"),
                },
                root,
            )
            self.assertEqual(result["job_id"], "9001")
            self.assertTrue(Path(result["manifest_path"]).exists())

    def test_local_model_run_reaches_registered_backend_and_hashes_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable(
                root / "boltz",
                "while [ \"$1\" != \"--out_dir\" ]; do shift; done\nshift\nmkdir -p \"$1\"\nprintf 'data_prediction\\n' > \"$1/prediction.cif\"\n",
            )
            result = self.run_capability(
                "local-model-run",
                {"backend": "boltz", "inputs": {"input": "target.yaml", "output": "predictions"}, "output_directory": str(root / "run")},
                root,
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(result["artifacts"][0]["sha256"]), 64)
            self.assertTrue(Path(result["manifest_path"]).exists())


if __name__ == "__main__":
    unittest.main()
