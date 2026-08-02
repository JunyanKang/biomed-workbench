import importlib.util
import json
import tempfile
import unittest
import zipfile
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

    def test_server_job_round_trip_recovers_local_request(self):
        prepared, _ = workflow.prepare(request())
        jobs, _ = workflow.prepare_server_submission(prepared)
        recovered = workflow.prepare_from_server_job(jobs, job_name=prepared["name"])
        reparsed, _ = workflow.prepare(recovered)
        self.assertEqual(reparsed["sequences"], prepared["sequences"])
        self.assertEqual(reparsed["modelSeeds"], prepared["modelSeeds"])

    def test_observed_server_archive_layout_is_parsed_without_msa_extraction(self):
        prepared, _ = workflow.prepare(request())
        jobs, _ = workflow.prepare_server_submission(prepared)
        job_name = "server_fixture"
        jobs[0]["name"] = job_name
        prefix = f"{job_name}/fold_{job_name}"
        full = {
            "atom_chain_ids": ["A", "A", "B", "B"],
            "atom_plddts": [80.0, 82.0, 70.0, 72.0],
            "contact_probs": [[0.0, 0.1, 0.8, 0.3], [0.1, 0.0, 0.2, 0.7], [0.8, 0.2, 0.0, 0.1], [0.3, 0.7, 0.1, 0.0]],
            "pae": [[1.0, 2.0, 5.0, 8.0], [2.0, 1.0, 9.0, 6.0], [5.0, 9.0, 1.0, 2.0], [8.0, 6.0, 2.0, 1.0]],
            "token_chain_ids": ["A", "A", "B", "B"],
            "token_res_ids": [1, 2, 1, 2],
        }
        cif = """data_test
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.B_iso_or_equiv
_atom_site.auth_seq_id
_atom_site.auth_asym_id
_atom_site.pdbx_PDB_model_num
ATOM 1 C CA . ALA A 1 1 ? 0 0 0 1 80 1 A 1
ATOM 2 C CA . GLY A 1 2 ? 1 0 0 1 82 2 A 1
ATOM 3 C CA . ALA B 2 1 ? 0 2 0 1 70 1 B 1
ATOM 4 C CA . GLY B 2 2 ? 1 2 0 1 72 2 B 1
#
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "fold.zip"
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("terms_of_use.md", "fixture terms")
                archive.writestr(f"{prefix}_job_request.json", json.dumps(jobs))
                for index, score in enumerate((0.2, 0.4)):
                    summary = {
                        "ranking_score": score,
                        "ptm": 0.5,
                        "iptm": 0.4,
                        "fraction_disordered": 0.1,
                        "has_clash": 0.0,
                        "chain_ids": ["A", "A", "B", "B"],
                        "chain_ptm": [0.5, 0.5],
                        "chain_iptm": [0.4, 0.4],
                        "chain_pair_iptm": [[0.5, 0.4], [0.4, 0.5]],
                        "chain_pair_pae_min": [[1.0, 5.0], [5.0, 1.0]],
                    }
                    archive.writestr(f"{prefix}_summary_confidences_{index}.json", json.dumps(summary))
                    archive.writestr(f"{prefix}_full_data_{index}.json", json.dumps(full))
                    archive.writestr(f"{prefix}_model_{index}.cif", cif)
                archive.writestr(f"{job_name}/msas/large_unused.a3m", ">unused\nAAAA\n")
            output = root / "report"
            parsed = workflow.parse_alphafold_server_archive(archive_path, output, job_name=job_name)
            self.assertEqual(parsed["model_count"], 2)
            self.assertEqual(parsed["top_model_index"], 1)
            self.assertEqual(parsed["chain_ids"], ["A", "B"])
            self.assertTrue((output / "pae_binned.tsv").is_file())
            self.assertTrue((output / "top_cross_chain_contacts.tsv").is_file())
            self.assertFalse((output / "msas").exists())


if __name__ == "__main__":
    unittest.main()
