import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


RUNNER = (
    Path(__file__).resolve().parents[2]
    / "biomed_workbench/modules/builtin/alphafold3-complex-prediction/templates/run_alphafold3_complex_prediction.py"
)
SPEC = importlib.util.spec_from_file_location("alphafold3_workflow", RUNNER)
assert SPEC and SPEC.loader
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


def request() -> dict:
    return {
        "name": "protein_dna_ligand",
        "model_seeds": [7],
        "entities": [
            {"protein": {"id": ["A", "B"], "sequence": "ACDEFGHIK"}},
            {"dna": {"id": "C", "sequence": "ACGT"}},
            {"ligand": {"id": "D", "ccdCodes": ["ATP"]}},
        ],
    }


class AlphaFold3WorkflowTests(unittest.TestCase):
    def test_server_package_uses_official_v1_dialect_and_preserves_copy_counts(self):
        prepared, assets = workflow.prepare(request())
        self.assertEqual(assets, [])
        jobs, mapping = workflow.prepare_server_submission(prepared)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["dialect"], "alphafoldserver")
        self.assertEqual(jobs[0]["version"], 1)
        self.assertEqual(jobs[0]["sequences"][0]["proteinChain"]["count"], 2)
        self.assertEqual(jobs[0]["sequences"][1]["dnaSequence"]["count"], 1)
        self.assertEqual(jobs[0]["sequences"][2]["ligand"]["ligand"], "CCD_ATP")
        self.assertNotIn("id", json.dumps(jobs))
        self.assertEqual(mapping[0]["source_chain_ids"], ["A", "B"])

    def test_server_package_blocks_features_that_cannot_be_preserved(self):
        smiles = request()
        smiles["entities"][-1] = {"ligand": {"id": "D", "smiles": "CCO"}}
        prepared, _ = workflow.prepare(smiles)
        with self.assertRaisesRegex(ValueError, "CCD"):
            workflow.prepare_server_submission(prepared)

        custom_msa = request()
        custom_msa["entities"][0]["protein"]["unpairedMsa"] = ">q\nACDEFGHIK\n"
        prepared, _ = workflow.prepare(custom_msa)
        with self.assertRaisesRegex(ValueError, "custom MSA"):
            workflow.prepare_server_submission(prepared)

    def test_submission_package_reports_access_and_terms_gate(self):
        prepared, _ = workflow.prepare(request())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            blocked = workflow.write_server_package(
                prepared,
                output,
                access_state="not-configured",
                terms_reviewed=False,
            )
            self.assertFalse(blocked["submission_ready"])
            self.assertTrue(blocked["manual_submission_required"])
            self.assertFalse(blocked["undocumented_api_used"])
            ready = workflow.write_server_package(
                prepared,
                output,
                access_state="ready",
                terms_reviewed=True,
            )
            self.assertTrue(ready["submission_ready"])
            payload = json.loads((output / "alphafold_server_submission.json").read_text())
            self.assertIsInstance(payload, list)

    def test_local_resource_gate_reserves_half_of_current_headroom(self):
        gib = 1024**3
        eligible_gpu = [
            {
                "name": "A100",
                "memory_mib": 81920,
                "memory_free_mib": 81920,
                "compute_capability": 8.0,
                "driver_version": "570",
            }
        ]
        with (
            patch.object(workflow.platform, "system", return_value="Linux"),
            patch.object(workflow.platform, "machine", return_value="x86_64"),
            patch.object(workflow, "_memory_bytes", return_value=256 * gib),
            patch.object(workflow, "_available_memory_bytes", return_value=192 * gib),
            patch.object(workflow, "_nvidia_gpus", return_value=eligible_gpu),
            patch.object(workflow.shutil, "disk_usage", return_value=SimpleNamespace(total=3_000 * gib, used=1_000 * gib, free=2_000 * gib)),
            patch.object(workflow.os, "cpu_count", return_value=64),
            patch.object(workflow.os, "getloadavg", return_value=(2.0, 2.0, 2.0)),
        ):
            report = workflow.probe_host(Path.cwd())
        self.assertTrue(report["recommended_local_inference_ready"])
        self.assertEqual(report["thresholds"]["reserve_fraction"], 0.5)

        eligible_gpu[0]["memory_free_mib"] = 60 * 1024
        with (
            patch.object(workflow.platform, "system", return_value="Linux"),
            patch.object(workflow.platform, "machine", return_value="x86_64"),
            patch.object(workflow, "_memory_bytes", return_value=256 * gib),
            patch.object(workflow, "_available_memory_bytes", return_value=100 * gib),
            patch.object(workflow, "_nvidia_gpus", return_value=eligible_gpu),
            patch.object(workflow.shutil, "disk_usage", return_value=SimpleNamespace(total=3_000 * gib, used=2_000 * gib, free=1_000 * gib)),
            patch.object(workflow.os, "cpu_count", return_value=16),
            patch.object(workflow.os, "getloadavg", return_value=(4.0, 4.0, 4.0)),
        ):
            report = workflow.probe_host(Path.cwd())
        self.assertFalse(report["recommended_local_inference_ready"])
        self.assertFalse(report["checks"]["half_available_gpu_memory_preserved"])
        self.assertFalse(report["checks"]["half_available_disk_preserved"])

    def test_server_outputs_cannot_flow_to_automated_docking(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = workflow._downstream_handoff(
                {"top_model": {"path": "model.cif"}, "chain_ids": ["A", "B"]},
                Path(temporary),
                result_origin="alphafold-server",
            )
            payload = json.loads(target.read_text())
            self.assertFalse(payload["automated_docking_allowed"])
            self.assertNotIn("protein-complex-docking", payload["eligible_next_modules"])


if __name__ == "__main__":
    unittest.main()
