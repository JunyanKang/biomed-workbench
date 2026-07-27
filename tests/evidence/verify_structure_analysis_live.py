#!/usr/bin/env python3
"""Execute six structural-analysis templates on real and adversarial fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.request
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlsplit

from rdkit import Chem
from rdkit.Chem import AllChem


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from tools.validate_module import validate_module  # noqa: E402


EXPERIMENTAL_URL = "https://files.rcsb.org/download/1CRN.pdb"
ALPHAFOLD_URL = "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-model_v6.pdb"
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
MODULES = (
    "structure-quality-assessment",
    "structure-chain-comparison",
    "docking-pose-review",
    "chemical-substructure-filter",
    "protein-secondary-structure",
    "structure-interactive-visualization",
)
REPORT_NAMES = {module_id: f"{module_id}-live-verification.json" for module_id in MODULES}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url: str, output: Path) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"files.rcsb.org", "alphafold.ebi.ac.uk"}:
        raise RuntimeError("structure fixture URL is outside the approved HTTPS hosts")
    request = urllib.request.Request(url, headers={"User-Agent": "biomed-workbench-structure-verifier/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(content) > MAX_DOWNLOAD_BYTES or b"ATOM" not in content:
        raise RuntimeError("downloaded coordinate fixture is oversized or not a PDB coordinate document")
    output.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def transform_pdb(source: Path, output: Path) -> None:
    lines = []
    for line in source.read_text(encoding="utf-8").splitlines(keepends=True):
        if line.startswith(("ATOM  ", "HETATM")):
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
            line = line[:30] + f"{-y + 10:8.3f}{x - 5:8.3f}{z + 3:8.3f}" + line[54:]
        lines.append(line)
    output.write_text("".join(lines), encoding="utf-8")


def write_chemical_fixture(path: Path) -> None:
    path.write_text(
        "compound_id,smiles\n"
        "aspirin,CC(=O)OC1=CC=CC=C1C(=O)O\n"
        "benzene,c1ccccc1\n"
        "benzoyl_chloride,O=C(Cl)c1ccccc1\n"
        "invalid,not_a_smiles\n",
        encoding="utf-8",
    )


def receptor_centroid(path: Path) -> tuple[float, float, float]:
    receptor = Chem.MolFromPDBFile(str(path), sanitize=False, removeHs=False, proximityBonding=False)
    if receptor is None or receptor.GetNumConformers() != 1:
        raise RuntimeError("live fixture receptor could not be parsed")
    conformer = receptor.GetConformer()
    coordinates = []
    for atom in receptor.GetAtoms():
        if atom.GetAtomicNum() > 1:
            point = conformer.GetAtomPosition(atom.GetIdx())
            coordinates.append((float(point.x), float(point.y), float(point.z)))
    if not coordinates:
        raise RuntimeError("live fixture receptor has no heavy atoms")
    return tuple(sum(point[index] for point in coordinates) / len(coordinates) for index in range(3))


def write_docking_fixture(receptor: Path, output_directory: Path) -> None:
    base = Chem.AddHs(Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O"))
    if AllChem.EmbedMolecule(base, randomSeed=20260715) != 0:
        raise RuntimeError("deterministic docking ligand embedding failed")
    AllChem.UFFOptimizeMolecule(base, maxIters=200)
    center = receptor_centroid(receptor)
    base_conformer = base.GetConformer()
    base_center = tuple(
        sum(float(base_conformer.GetAtomPosition(index)[axis]) for index in range(base.GetNumAtoms())) / base.GetNumAtoms()
        for axis in range(3)
    )
    for rank, confidence, offset in ((1, 0.9, (0.0, 0.0, 0.0)), (2, 0.4, (30.0, 30.0, 30.0))):
        pose = Chem.Mol(base)
        conformer = pose.GetConformer()
        shift = tuple(center[axis] + offset[axis] - base_center[axis] for axis in range(3))
        for atom_index in range(pose.GetNumAtoms()):
            point = conformer.GetAtomPosition(atom_index)
            conformer.SetAtomPosition(atom_index, tuple(float(point[axis]) + shift[axis] for axis in range(3)))
        writer = Chem.SDWriter(str(output_directory / f"rank{rank}_confidence{confidence:.3f}.sdf"))
        writer.write(pose)
        writer.close()
    (output_directory / "rank3_confidence0.100.sdf").write_text("invalid sdf\n$$$$\n", encoding="utf-8")


def write_docking_preparation_fixture(inputs: Path) -> tuple[Path, Path]:
    ligand = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    if AllChem.EmbedMolecule(ligand, randomSeed=20260716) != 0:
        raise RuntimeError("deterministic preparation ligand embedding failed")
    writer = Chem.SDWriter(str(inputs / "ethanol.sdf"))
    writer.write(ligand)
    writer.close()
    manifest = inputs / "diffdock_batch.csv"
    manifest.write_text(
        "complex_name,protein_path,ligand_description,protein_sequence\n"
        "crambin_aspirin,1CRN.pdb,CC(=O)OC1=CC=CC=C1C(=O)O,\n"
        "sequence_ethanol,,ethanol.sdf,ACDEFGHIKLMNPQRSTVWY\n",
        encoding="utf-8",
    )
    config = inputs / "diffdock_config.json"
    config.write_text(
        json.dumps(
            {
                "old_score_model": False,
                "old_filtering_model": True,
                "inference_steps": 20,
                "actual_steps": 19,
                "no_final_step_noise": True,
                "samples_per_complex": 10,
                "sigma_schedule": "expbeta",
                "initial_noise_std_proportion": 1.46,
                "temp_sampling_tr": 1.17,
                "temp_sampling_rot": 2.06,
                "temp_sampling_tor": 7.04,
                "temp_psi_tr": 0.73,
                "temp_psi_rot": 0.90,
                "temp_psi_tor": 0.59,
                "temp_sigma_data_tr": 0.93,
                "temp_sigma_data_rot": 0.75,
                "temp_sigma_data_tor": 0.69,
                "no_random": False,
                "ode": False,
                "different_schedules": False,
                "limit_failures": 5,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest, config


def run_template(
    module_id: str,
    template_filename: str,
    arguments: list[str],
    output_paths: dict[str, Path],
    registry: ModuleRegistry,
) -> tuple[dict[str, object], dict[str, object]]:
    manifest = registry.get(module_id)
    candidates = [item for item in manifest.code_templates if Path(item.path).name == template_filename]
    if len(candidates) != 1:
        raise RuntimeError(f"{module_id} does not expose exactly one {template_filename} template")
    template = BUILTIN_ROOT / module_id / candidates[0].path
    completed = subprocess.run(
        [sys.executable, str(template), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + "\n" + completed.stderr).splitlines()[-12:])
        raise RuntimeError(f"{module_id} live execution failed:\n{tail}")
    report_path = output_paths["report"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("module_id") != module_id or report.get("module_version") != manifest.version:
        raise RuntimeError(f"{module_id} output identity differs from its manifest")
    outputs = {
        label: {"sha256": sha256(path), "bytes": path.stat().st_size}
        for label, path in sorted(output_paths.items())
    }
    return report, {
        "template_completed": True,
        "outputs_reloaded": True,
        "outputs": outputs,
        "template": {"name": template.name, "sha256": sha256(template)},
    }


def tool_versions(module_id: str, dssp_version: str) -> dict[str, str]:
    values = {
        "structure-quality-assessment": {"biopython": version("biopython")},
        "structure-chain-comparison": {"biopython": version("biopython")},
        "docking-pose-review": {"biopython": version("biopython"), "rdkit": version("rdkit")},
        "chemical-substructure-filter": {"rdkit": version("rdkit")},
        "protein-secondary-structure": {"biopython": version("biopython"), "matplotlib": version("matplotlib"), "mkdssp": dssp_version},
        "structure-interactive-visualization": {"biopython": version("biopython"), "py3dmol": version("py3Dmol")},
    }
    return values[module_id]


def probe_dssp(executable: Path) -> str:
    completed = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=10, check=False)
    match = re.search(r"([0-9]+(?:\.[0-9]+)+)", completed.stdout + completed.stderr)
    if completed.returncode != 0 or match is None:
        raise RuntimeError("mkdssp version probe failed")
    return match.group(1)


def scientific_assertions(results: dict[str, dict[str, object]]) -> dict[str, dict[str, bool]]:
    quality = results["structure-quality-assessment"]
    comparison = results["structure-chain-comparison"]
    docking = results["docking-pose-review"]
    docking_preparation = results["docking-pose-review-preparation"]
    substructure = results["chemical-substructure-filter"]
    secondary = results["protein-secondary-structure"]
    secondary_diagram = results["protein-secondary-structure-diagram"]
    visualization = results["structure-interactive-visualization"]
    quality_summary = quality["summary"]
    comparison_summary = comparison["superposition"]
    docking_summary = docking["summary"]
    substructure_summary = substructure["summary"]
    secondary_summary = secondary["summary"]
    return {
        "structure-quality-assessment": {
            "plddt_semantics_explicit": quality_summary["confidence_semantics"] == "alphafold-plddt",
            "coordinate_accounting_reconciled": quality_summary["residue_count"] == sum(quality_summary["plddt_class_counts"].values()),
            "confidence_range_validated": 0 <= quality_summary["mean_residue_b_or_confidence"] <= 100,
        },
        "structure-chain-comparison": {
            "chain_mapping_explicit": comparison["chain_map"] == [{"reference": "A", "moving": "A"}],
            "sequence_correspondence_used": comparison["chain_results"][0]["matched_ca_atoms"] == 46,
            "rigid_transform_recovered": comparison_summary["rmsd_angstrom"] < 1e-4 and abs(comparison_summary["rotation_determinant"] - 1.0) < 1e-6,
            "tm_score_not_fabricated": comparison["tm_score"]["status"] == "not_computed" and comparison["tm_score"]["value"] is None,
        },
        "docking-pose-review": {
            "batch_rows_accounted": docking_preparation["summary"]["input_row_count"] == docking_preparation["summary"]["validated_row_count"] == 2,
            "protein_sources_exclusive": docking_preparation["summary"]["path_protein_count"] == 1 and docking_preparation["summary"]["sequence_protein_count"] == 1,
            "ligand_sources_validated": docking_preparation["summary"]["sdf_ligand_count"] == 1 and docking_preparation["summary"]["smiles_ligand_count"] == 1,
            "inference_config_bounded": all(docking_preparation["quality_gates"].values()),
            "all_pose_files_accounted": docking_summary["observed_pose_file_count"] == 3 and docking_summary["reviewable_pose_count"] + docking_summary["invalid_pose_count"] == 3,
            "invalid_sdf_retained": docking_summary["invalid_pose_count"] == 1,
            "confidence_not_affinity": "not affinity" in docking["score_semantics"],
            "receptor_clashes_computed": docking_summary["reviewable_poses_with_severe_clashes"] >= 1,
        },
        "chemical-substructure-filter": {
            "all_records_accounted": substructure_summary["input_count"] == substructure_summary["accepted_count"] + substructure_summary["rejected_count"] == 4,
            "invalid_molecule_retained": substructure_summary["parse_or_sanitization_failure_count"] == 1,
            "include_and_exclude_smarts_executed": len(substructure["queries"]["include"]) == 1 and len(substructure["queries"]["exclude"]) == 1,
        },
        "protein-secondary-structure": {
            "mkdssp_executed": secondary["versions"]["mkdssp"] == "4.6.1",
            "dssp_resources_digested": len(secondary["dssp_resources"]) == 3 and all(re.fullmatch(r"[0-9a-f]{64}", value) for value in secondary["dssp_resources"].values()),
            "full_dssp_alphabet_retained": set(secondary_summary["dssp_code_counts"]) == {"H", "B", "E", "G", "I", "T", "S", "-"},
            "residue_accounting_reconciled": secondary_summary["assigned_residue_count"] + secondary_summary["unresolved_residue_count"] == secondary_summary["selected_amino_acid_residue_count"] == 46,
            "diagram_residues_reconciled": secondary_diagram["diagram"]["selected_residue_count"] == secondary_summary["assigned_residue_count"],
            "diagram_segments_reconciled": sum(segment["residue_count"] for segment in secondary_diagram["diagram"]["segments"]) == secondary_diagram["diagram"]["selected_residue_count"],
            "diagram_svg_nonblank": secondary_diagram["diagram"]["svg_bytes"] > 1000 and secondary_diagram["quality_gates"]["svg_nonblank_and_parseable"],
        },
        "structure-interactive-visualization": {
            "html_nonblank": visualization["html_output"]["bytes"] > 1000,
            "plddt_provenance_explicit": visualization["view"]["confidence_provenance"] == "alphafold-b-column-plddt",
            "selected_chains_explicit": visualization["input"]["selected_chains"] == ["A"],
            "rendering_not_analysis": "not evidence" in visualization["interpretation_boundary"],
        },
    }


def verify(dssp_executable: Path, dssp_data_directory: Path, output_directory: Path) -> list[Path]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    dssp_version = probe_dssp(dssp_executable)
    with tempfile.TemporaryDirectory(prefix="biomed-structure-live-") as temporary:
        workspace = Path(temporary)
        inputs = workspace / "inputs"
        outputs = workspace / "outputs"
        poses = workspace / "poses"
        inputs.mkdir()
        outputs.mkdir()
        poses.mkdir()
        experimental = inputs / "1CRN.pdb"
        predicted = inputs / "AF-P04637-F1-model_v6.pdb"
        experimental_digest = download(EXPERIMENTAL_URL, experimental)
        predicted_digest = download(ALPHAFOLD_URL, predicted)
        transformed = inputs / "1CRN_transformed.pdb"
        transform_pdb(experimental, transformed)
        library = inputs / "library.csv"
        write_chemical_fixture(library)
        write_docking_fixture(experimental, poses)
        docking_manifest, docking_config = write_docking_preparation_fixture(inputs)

        runs = {
            "structure-quality-assessment": (
                "assess_structure_quality.py",
                ["--input", str(predicted), "--format", "pdb", "--confidence-semantics", "alphafold-plddt", "--model-index", "0", "--chains", "A", "--json-output", str(outputs / "quality.json"), "--residue-output", str(outputs / "quality.tsv")],
                {"report": outputs / "quality.json", "residues": outputs / "quality.tsv"},
            ),
            "structure-chain-comparison": (
                "compare_structure_chains.py",
                ["--reference", str(experimental), "--moving", str(transformed), "--format", "pdb", "--reference-model-index", "0", "--moving-model-index", "0", "--chain-map", "A:A", "--minimum-aligned-residues", "30", "--report-output", str(outputs / "comparison.json"), "--coordinate-output", str(outputs / "superposed.pdb")],
                {"report": outputs / "comparison.json", "superposed_coordinates": outputs / "superposed.pdb"},
            ),
            "chemical-substructure-filter": (
                "filter_chemical_substructures.py",
                ["--input", str(library), "--format", "csv", "--smiles-column", "smiles", "--identifier-column", "compound_id", "--include-smarts", "c1ccccc1", "--exclude-smarts", "C(=O)[Cl,Br,I]", "--report-output", str(outputs / "substructure.json"), "--records-output", str(outputs / "substructure.tsv")],
                {"report": outputs / "substructure.json", "records": outputs / "substructure.tsv"},
            ),
            "protein-secondary-structure": (
                "assign_secondary_structure.py",
                ["--input", str(experimental), "--format", "pdb", "--model-index", "0", "--chains", "A", "--dssp-executable", str(dssp_executable), "--dssp-data-directory", str(dssp_data_directory), "--report-output", str(outputs / "secondary.json"), "--residue-output", str(outputs / "secondary.tsv")],
                {"report": outputs / "secondary.json", "residues": outputs / "secondary.tsv"},
            ),
            "structure-interactive-visualization": (
                "render_structure_view.py",
                ["--input", str(predicted), "--format", "pdb", "--model-index", "0", "--chains", "A", "--style", "cartoon", "--color-semantics", "alphafold-plddt", "--confidence-provenance", "alphafold-b-column-plddt", "--html-output", str(outputs / "view.html"), "--manifest-output", str(outputs / "view.json")],
                {"report": outputs / "view.json", "html": outputs / "view.html"},
            ),
            "docking-pose-review": (
                "review_docking_poses.py",
                ["--receptor", str(experimental), "--results-directory", str(poses), "--diffdock-version", "fixture-producer-1", "--ligand-smiles", "CC(=O)OC1=CC=CC=C1C(=O)O", "--severe-clash-distance", "1.2", "--contact-distance", "2.0", "--report-output", str(outputs / "docking.json"), "--pose-output", str(outputs / "docking.tsv")],
                {"report": outputs / "docking.json", "poses": outputs / "docking.tsv"},
            ),
        }
        results = {}
        executions = {}
        preparation_arguments = [
            "--manifest", str(docking_manifest),
            "--base-directory", str(inputs),
            "--config-json", str(docking_config),
            "--batch-output", str(outputs / "validated_diffdock_batch.csv"),
            "--config-output", str(outputs / "validated_diffdock_config.yaml"),
            "--report-output", str(outputs / "docking_preparation.json"),
        ]
        preparation_outputs = {
            "report": outputs / "docking_preparation.json",
            "validated_batch": outputs / "validated_diffdock_batch.csv",
            "validated_config": outputs / "validated_diffdock_config.yaml",
        }
        results["docking-pose-review-preparation"], preparation_execution = run_template(
            "docking-pose-review", "prepare_docking_batch.py", preparation_arguments, preparation_outputs, registry
        )
        for module_id, (template_filename, arguments, output_paths) in runs.items():
            results[module_id], executions[module_id] = run_template(module_id, template_filename, arguments, output_paths, registry)
        diagram_arguments = [
            "--residue-table", str(outputs / "secondary.tsv"),
            "--chain", "A",
            "--title", "1CRN chain A secondary structure",
            "--show-residue-numbers",
            "--svg-output", str(outputs / "secondary.svg"),
            "--manifest-output", str(outputs / "secondary_diagram.json"),
        ]
        diagram_outputs = {"report": outputs / "secondary_diagram.json", "svg": outputs / "secondary.svg"}
        results["protein-secondary-structure-diagram"], diagram_execution = run_template(
            "protein-secondary-structure", "render_secondary_structure_diagram.py", diagram_arguments, diagram_outputs, registry
        )
        secondary_execution = executions["protein-secondary-structure"]
        executions["protein-secondary-structure"] = {
            "template_completed": secondary_execution["template_completed"] and diagram_execution["template_completed"],
            "outputs_reloaded": secondary_execution["outputs_reloaded"] and diagram_execution["outputs_reloaded"],
            "outputs": {
                **{f"assignment_{name}": value for name, value in secondary_execution["outputs"].items()},
                **{f"diagram_{name}": value for name, value in diagram_execution["outputs"].items()},
            },
            "templates": {"assignment": secondary_execution["template"], "diagram": diagram_execution["template"]},
        }
        review_execution = executions["docking-pose-review"]
        executions["docking-pose-review"] = {
            "template_completed": preparation_execution["template_completed"] and review_execution["template_completed"],
            "outputs_reloaded": preparation_execution["outputs_reloaded"] and review_execution["outputs_reloaded"],
            "outputs": {
                **{f"preparation_{name}": value for name, value in preparation_execution["outputs"].items()},
                **{f"review_{name}": value for name, value in review_execution["outputs"].items()},
            },
            "templates": {"preparation": preparation_execution["template"], "review": review_execution["template"]},
        }
        for module_id in MODULES:
            if module_id not in {"docking-pose-review", "protein-secondary-structure"}:
                executions[module_id]["templates"] = {"primary": executions[module_id]["template"]}
        assertions = scientific_assertions(results)
        if any(not all(values.values()) for values in assertions.values()):
            raise RuntimeError("one or more structural scientific assertions failed")
        output_directory.mkdir(parents=True, exist_ok=True)
        written = []
        for module_id in MODULES:
            manifest = registry.get(module_id)
            row = manifest.compatibility_matrix[0]
            package = validate_module(BUILTIN_ROOT / module_id, require_tests=True, execute_tests=True)
            report = {
                "schema_version": 1,
                "passed": True,
                "module_id": module_id,
                "module_version": manifest.version,
                "compatibility_row_id": row.id,
                "registry_digest": registry.digest,
                "fixtures": {
                    "experimental_structure": {"id": "1CRN", "sha256": experimental_digest, "source": EXPERIMENTAL_URL},
                    "predicted_structure": {"id": "AF-P04637-F1-model_v6", "sha256": predicted_digest, "source": ALPHAFOLD_URL},
                },
                "templates": executions[module_id]["templates"],
                "tool_versions": tool_versions(module_id, dssp_version),
                "dependency_versions": {"python": platform.python_version()},
                "execution": {
                    "template_completed": executions[module_id]["template_completed"],
                    "outputs_reloaded": executions[module_id]["outputs_reloaded"],
                    "output_artifacts": executions[module_id]["outputs"],
                },
                "scientific_summary": assertions[module_id],
                "module_package_validation": {
                    "valid": package["valid"],
                    "executed_test_cases": package["executed_test_cases"],
                    "module_version": package["module_version"],
                },
                "no_environment_or_compute_infrastructure_managed": True,
            }
            serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
            if any(marker in serialized for marker in ("/Users/", "/private/", "/Volumes/", "file://", "API_KEY", "ACCESS_TOKEN")):
                raise RuntimeError(f"{module_id} public report contains a local path or credential marker")
            target = output_directory / REPORT_NAMES[module_id]
            target.write_text(serialized, encoding="utf-8")
            written.append(target)
        return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dssp-executable", required=True, type=Path)
    parser.add_argument("--dssp-data-directory", required=True, type=Path)
    parser.add_argument("--output-directory", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    written = verify(args.dssp_executable.resolve(), args.dssp_data_directory.resolve(), args.output_directory)
    print(json.dumps({"passed": True, "report_count": len(written), "reports": [path.name for path in written]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
