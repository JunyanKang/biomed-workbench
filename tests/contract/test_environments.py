import unittest

from biomed_workbench.services.environments import RuntimeState, runtime_status


class EnvironmentContractTests(unittest.TestCase):
    def test_runtime_status_is_generic_and_read_only(self):
        available = {"python3": "/usr/bin/python3", "docker": "/usr/local/bin/docker", "sbatch": "/usr/bin/sbatch"}
        calls = []

        def which(name):
            calls.append(("which", name))
            return available.get(name)

        def probe(command, timeout):
            calls.append(("probe", tuple(command)))
            if command[:2] == ["docker", "version"]:
                return 0, "27.0", ""
            if command[:1] == ["sbatch"]:
                return 0, "slurm 24", ""
            return 1, "", "unavailable"

        status = runtime_status(which=which, probe=probe)

        self.assertEqual(set(status), {"python", "r", "container", "gpu", "slurm", "local_model"})
        self.assertIsInstance(status["python"], RuntimeState)
        self.assertTrue(status["python"].available)
        self.assertTrue(status["container"].available)
        self.assertTrue(status["slurm"].available)
        self.assertFalse(status["gpu"].available)
        self.assertFalse(any("install" in " ".join(call[1]) if isinstance(call[1], tuple) else False for call in calls))

    def test_local_model_status_reports_discovered_commands_without_vendor_endpoints(self):
        available = {"python3": "/usr/bin/python3", "boltz": "/opt/bin/boltz", "foldseek": "/opt/bin/foldseek"}
        status = runtime_status(which=lambda name: available.get(name), probe=lambda _command, _timeout: (1, "", ""))

        self.assertTrue(status["local_model"].available)
        self.assertEqual(status["local_model"].details["commands"], ["boltz", "foldseek"])
        self.assertNotIn("api", repr(status["local_model"]).lower())


if __name__ == "__main__":
    unittest.main()
