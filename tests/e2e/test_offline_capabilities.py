import json
import math
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def execute(capability_id, payload):
    result = subprocess.run(
        [sys.executable, "tools/run_tool.py", capability_id, "--input", json.dumps(payload)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    parsed = json.loads(result.stdout)
    if parsed["status"] != "completed":
        raise AssertionError(parsed)
    return parsed["output"]


class OfflineCapabilityE2ETests(unittest.TestCase):
    def test_sequence_inspect(self):
        output = execute("sequence-inspect", {"sequence": "ATGCGC", "alphabet": "dna"})
        self.assertAlmostEqual(output["gc_percent"], 66.666667)

    def test_data_profile(self):
        output = execute("data-profile", {"rows": [{"sample": "A", "count": 1}, {"sample": "B", "count": None}]})
        self.assertEqual(output["columns"]["count"]["missing_count"], 1)

    def test_primer_design(self):
        output = execute(
            "primer-design",
            {"template": "GCGTACGATCGATGCTAGCTAGGCTAACGTTAGCGATCGTACGATCGATGCTAGCATCGATGCGTACGATCG", "max_pairs": 2},
        )
        self.assertEqual(len(output["pairs"]), 2)

    def test_crispr_design(self):
        output = execute("crispr-design", {"sequence": "AAAGACTGACTGACTGACTGACTTGGTTT"})
        self.assertGreaterEqual(len(output["guides"]), 1)

    def test_restriction_plan(self):
        output = execute("restriction-plan", {"sequence": "AAAAGAATTCTTT", "enzymes": ["EcoRI"]})
        self.assertEqual(output["sites"][0]["start"], 5)

    def test_sequence_back_translate(self):
        output = execute("sequence-back-translate", {"protein": "MKW", "organism": "human"})
        self.assertEqual(output["dna"], "ATGAAGTGG")

    def test_dilution_plan(self):
        output = execute(
            "dilution-plan",
            {"initial_concentration": 100, "dilution_factor": 10, "steps": 2, "final_volume_ul": 1000},
        )
        self.assertEqual(output["steps"][-1]["concentration"], 1.0)

    def test_pcr_plan(self):
        output = execute(
            "pcr-plan",
            {
                "reactions": 8,
                "reaction_volume_ul": 20,
                "components": {"master_mix": 10, "forward_primer": 1, "reverse_primer": 1, "template": 2},
                "overage_percent": 10,
            },
        )
        self.assertAlmostEqual(output["master_mix"]["water"], 52.8)

    def test_dose_response(self):
        output = execute(
            "dose-response",
            {"concentrations": [0.1, 1, 10, 100], "responses": [98, 80, 20, 2], "direction": "decreasing"},
        )
        self.assertTrue(output["monotonic"])

    def test_growth_curve(self):
        output = execute(
            "growth-curve",
            {"times": [0, 1, 2, 3], "values": [0.05 * math.exp(0.7 * time) for time in range(4)], "window": 3},
        )
        self.assertAlmostEqual(output["max_growth_rate_per_time"], 0.7, places=6)

    def test_container_plan(self):
        output = execute(
            "container-plan",
            {"image": "ghcr.io/example/model:1.0", "command": ["predict", "input.fa"], "gpu": True},
        )
        self.assertIn("--gpus", output["argv"])
        self.assertFalse(output["executes"])

    def test_slurm_plan(self):
        output = execute(
            "slurm-plan",
            {"command": ["python", "run.py"], "job_name": "fold", "cpus": 4, "memory_gb": 16, "time_minutes": 60, "gpus": 1},
        )
        self.assertIn("#SBATCH --gres=gpu:1", output["script"])
        self.assertFalse(output["submits"])

    def test_local_model_plan(self):
        output = execute("local-model-plan", {"backend": "boltz", "inputs": {"input": "target.yaml", "output": "results"}})
        self.assertEqual(output["argv"][:2], ["boltz", "predict"])
        self.assertFalse(output["executes"])


if __name__ == "__main__":
    unittest.main()
