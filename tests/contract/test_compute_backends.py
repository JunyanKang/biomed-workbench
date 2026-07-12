import tempfile
import unittest
from pathlib import Path

from biomed_workbench.services.containers import run_container
from biomed_workbench.services.schedulers import monitor_slurm, submit_slurm


class ComputeBackendContractTests(unittest.TestCase):
    def test_container_execution_requires_permission_and_records_bounded_result(self):
        calls = []

        def execute(argv, timeout):
            calls.append((argv, timeout))
            return 0, "completed\n", ""

        with self.assertRaises(PermissionError):
            run_container("example/model:1", ["predict"], permission_granted=False, executor=execute)
        result = run_container("example/model:1", ["predict"], permission_granted=True, executor=execute)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(calls[0][0][:3], ["docker", "run", "--rm"])
        self.assertNotIn("environment", result)
        with self.assertRaises(ValueError):
            run_container("example/model:1", ["predict", "--token=secret"], permission_granted=True, executor=execute)

    def test_slurm_submission_writes_script_and_parses_job_id(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            def submit(argv, timeout):
                self.assertEqual(argv[0], "sbatch")
                self.assertTrue(Path(argv[-1]).exists())
                return 0, "4123;research\n", ""

            result = submit_slurm(
                ["python", "run.py"],
                "fold",
                2,
                8,
                30,
                output_directory=str(output),
                permission_granted=True,
                submitter=submit,
            )
            self.assertEqual(result["job_id"], "4123")
            self.assertTrue(Path(result["script_path"]).exists())
            self.assertTrue(Path(result["manifest_path"]).exists())

    def test_slurm_monitor_normalizes_scheduler_state(self):
        result = monitor_slurm("4123", query=lambda argv, timeout: (0, "RUNNING|00:02|node1\n", ""))
        self.assertEqual(result["state"], "RUNNING")
        self.assertEqual(result["elapsed"], "00:02")

    def test_scheduler_rejects_credentials_in_command_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                submit_slurm(
                    ["python", "run.py", "--api-key", "secret"],
                    "fold",
                    1,
                    1,
                    1,
                    output_directory=directory,
                    permission_granted=True,
                )


if __name__ == "__main__":
    unittest.main()
