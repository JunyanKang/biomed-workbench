import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "tools" / "workbench"


class WorkbenchDoctorE2ETests(unittest.TestCase):
    def test_doctor_passes_without_exposing_secrets(self):
        environment = dict(os.environ)
        environment["NCBI_API_KEY"] = "doctor-secret-sentinel"
        completed = subprocess.run(
            [str(LAUNCHER), "doctor", "--strict"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["fail"], 0)
        self.assertEqual(
            {item["id"] for item in report["checks"]},
            {
                "core-runtime",
                "plugin-manifest",
                "codex-entrypoint",
                "module-registry",
                "unified-routing",
                "optional-credentials",
            },
        )
        self.assertNotIn("doctor-secret-sentinel", completed.stdout)
        self.assertNotIn("nvapi-", completed.stdout)
        credential_check = next(item for item in report["checks"] if item["id"] == "optional-credentials")
        self.assertEqual(credential_check["details"]["NCBI_API_KEY"], "configured")

    def test_launcher_routes_through_a_compatible_interpreter(self):
        completed = subprocess.run(
            [str(LAUNCHER), "route", "single-cell donor-aware analysis"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["selected_module_ids"])
        self.assertIn(payload["plan_type"], {"single", "serial", "parallel", "mixed"})

    def test_launcher_rejects_unknown_commands(self):
        completed = subprocess.run(
            [str(LAUNCHER), "not-a-command"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("unknown workbench command", completed.stderr)


if __name__ == "__main__":
    unittest.main()
