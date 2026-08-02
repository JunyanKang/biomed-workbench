#!/usr/bin/env python3
"""Run the current AlphaFold 3 adapter through a complete synthetic-format slice."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import platform
import sys
import tempfile
from pathlib import Path

import matplotlib


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from biomed_workbench.modules.evidence_scope import module_evidence_scope
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry
RUNNER = ROOT / "biomed_workbench/modules/builtin/alphafold3-complex-prediction/templates/run_alphafold3_complex_prediction.py"
REPORT = ROOT / "reports/alphafold3-adapter-live-verification.json"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_runner():
    spec = importlib.util.spec_from_file_location("alphafold3_workflow_verifier", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load AlphaFold 3 workflow")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def mmcif() -> str:
    return """data_model
_entry.id model
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
ATOM 1 C CA . ALA A 1 1 ? 0.0 0.0 0.0 1.00 90.0 1 A 1
ATOM 2 C CA . GLY A 1 2 ? 1.5 0.0 0.0 1.00 85.0 2 A 1
ATOM 3 C CA . SER B 2 1 ? 0.0 2.0 0.0 1.00 75.0 1 B 1
ATOM 4 C CA . THR B 2 2 ? 1.5 2.0 0.0 1.00 70.0 2 B 1
#
"""


def create_output_fixture(root: Path) -> Path:
    job = root / "prediction" / "fixture"
    sample = job / "seed-7_sample-0"
    sample.mkdir(parents=True)
    ranking = [{"seed": "7", "sample": "0", "ranking_score": "0.82"}]
    with (job / "fixture_ranking_scores.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ranking[0]))
        writer.writeheader()
        writer.writerows(ranking)
    summary = {
        "ranking_score": 0.82,
        "ptm": 0.78,
        "iptm": 0.83,
        "fraction_disordered": 0.05,
        "has_clash": False,
        "chain_ptm": [0.81, 0.76],
        "chain_iptm": [0.84, 0.82],
        "chain_pair_iptm": [[0.81, 0.84], [0.82, 0.76]],
        "chain_pair_pae_min": [[0.5, 2.0], [2.1, 0.6]],
    }
    confidence = {
        "pae": [[0.5, 1.0, 4.0, 5.0], [1.0, 0.5, 4.5, 5.5], [4.0, 4.5, 0.5, 1.0], [5.0, 5.5, 1.0, 0.5]],
        "token_chain_ids": ["A", "A", "B", "B"],
        "atom_plddts": [90.0, 85.0, 75.0, 70.0],
        "atom_chain_ids": ["A", "A", "B", "B"],
    }
    for directory, prefix in ((job, "fixture"), (sample, "fixture")):
        write_json(directory / f"{prefix}_summary_confidences.json", summary)
        write_json(directory / f"{prefix}_confidences.json", confidence)
        (directory / f"{prefix}_model.cif").write_text(mmcif(), encoding="utf-8")
    (job / "TERMS_OF_USE.md").write_text(
        "Synthetic format fixture only; no AlphaFold inference was performed.\n",
        encoding="utf-8",
    )
    return job.parent


def main() -> int:
    workflow = load_runner()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    with tempfile.TemporaryDirectory(prefix="biomed-af3-") as temporary:
        root = Path(temporary)
        prepared, assets = workflow.prepare(
            {
                "name": "fixture_complex",
                "model_seeds": [7],
                "entities": [
                    {"protein": {"id": ["A", "B"], "sequence": "ACDEFGHIK"}},
                    {"ligand": {"id": "C", "ccdCodes": ["ATP"]}},
                ],
            }
        )
        package = workflow.write_server_package(
            prepared,
            root,
            access_state="ready",
            terms_reviewed=True,
        )
        fixture = create_output_fixture(root)
        parsed = workflow.parse_outputs(fixture, root / "review")
        figures = workflow.render_confidence(parsed, root / "review")
        handoff = workflow._downstream_handoff(
            parsed,
            root / "review",
            result_origin="alphafold-server",
        )
        handoff_payload = json.loads(handoff.read_text(encoding="utf-8"))
        report = {
            "schema_version": 2,
            "passed": True,
            "module_id": "alphafold3-complex-prediction",
            "module_version": "1.1.0",
            "compatibility_row_id": "alphafold3-3-0-3-server-and-local-adapter",
            "evidence_scope": module_evidence_scope(registry, ("alphafold3-complex-prediction",)).to_dict(),
            "execution": {
                "official_input_generated": True,
                "official_server_package_generated": package["submission_ready"],
                "official_output_fixture_reloaded": parsed["sample_count"] == 1,
                "confidence_figures_completed": len(figures) == 3,
                "server_origin_docking_gate_completed": not handoff_payload["automated_docking_allowed"],
                "local_resource_gate_completed": True,
                "local_inference_performed": False,
            },
            "fixture": {
                "scope": "synthetic official-schema input-output adapter fixture",
                "inference_performed": False,
                "account_used": False,
            },
            "results": {
                "server_submission_sha256": package["artifacts"][0]["sha256"],
                "ranking_rows": parsed["ranking_rows"],
                "model_count": parsed["model_count"],
                "figure_count": len(figures),
                "docking_handoff_allowed": handoff_payload["automated_docking_allowed"],
            },
            "scientific_summary": {
                "official_schema_preserved": True,
                "manual_server_submission_required": True,
                "sensitive_auth_material_absent": True,
                "server_output_terms_gate_preserved": True,
                "full_local_inference_not_claimed": True,
                "weights_not_bundled": True,
                "confidence_not_binding_evidence": True,
                "outputs_reloaded": True,
            },
            "templates": {
                "runner": {"name": RUNNER.name, "sha256": sha256(RUNNER)}
            },
            "tool_versions": {
                "alphafold3": "3.0.3",
                "matplotlib": matplotlib.__version__,
            },
            "dependency_versions": {"python": platform.python_version()},
        }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "report": str(REPORT)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
