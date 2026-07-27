#!/usr/bin/env python3
"""Validate sample-aware LIANA CellPhoneDB communication on public GSE96583 PBMCs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from tools.verify_public_gse96583_donor_case import (  # noqa: E402
    EXPECTED_DONORS,
    SOURCES,
    acquire_sources,
    extract_members,
    read_condition,
    unique_gene_names,
)

MODULE_ID = "single-cell-communication"
ROW_ID = "agent-protocol-1-python-communication"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "run_liana_cellphonedb.py"
CELL_TYPES = ("B cells", "CD4 T cells", "CD14+ Monocytes", "NK cells")
MAX_CELLS_PER_STRATUM = 100
MINIMUM_GENE_DETECTION = 20
MINIMUM_CELLS = 10
MINIMUM_SAMPLES = 6
PERMUTATIONS = 100
FDR = 0.05
SEED = 551


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_stratified_indices(obs: pd.DataFrame) -> np.ndarray:
    selected: list[int] = []
    samples = obs["sample"].astype(str).to_numpy()
    cell_types = obs["cell_type"].astype(str).to_numpy()
    for sample in sorted(set(samples)):
        for cell_type in CELL_TYPES:
            candidates = np.flatnonzero(
                (samples == sample) & (cell_types == cell_type)
            )
            ranked = sorted(
                candidates,
                key=lambda index: hashlib.sha256(
                    f"{SEED}:{obs.index[index]}".encode()
                ).hexdigest(),
            )
            selected.extend(ranked[:MAX_CELLS_PER_STRATUM])
    return np.asarray(sorted(selected), dtype=int)


def run_template(
    python: Path,
    input_path: Path,
    output_directory: Path,
    report_path: Path,
    environment: dict[str, str],
) -> None:
    completed = subprocess.run(
        [
            str(python),
            str(TEMPLATE),
            "--input-h5ad",
            str(input_path),
            "--output-directory",
            str(output_directory),
            "--report",
            str(report_path),
            "--method",
            "liana",
            "--cell-type-key",
            "cell_type",
            "--sample-key",
            "sample",
            "--condition-key",
            "condition",
            "--raw-count-location",
            "layers.counts",
            "--species",
            "human",
            "--minimum-cells",
            str(MINIMUM_CELLS),
            "--minimum-samples",
            str(MINIMUM_SAMPLES),
            "--expression-proportion",
            "0.1",
            "--permutations",
            str(PERMUTATIONS),
            "--fdr",
            str(FDR),
            "--seed",
            str(SEED),
            "--jobs",
            "1",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "public GSE96583 communication execution failed:\n"
            + completed.stdout[-1500:]
            + "\n"
            + completed.stderr[-4000:]
        )


def verify(source_dir: Path | None, scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python is not executable")
    with tempfile.TemporaryDirectory(
        prefix="biomed-public-gse96583-communication-"
    ) as temporary:
        work = Path(temporary)
        paths = acquire_sources(
            work,
            source_dir.expanduser().resolve(strict=True) if source_dir else None,
        )
        source_digests_before = {
            name: sha256(path) for name, path in paths.items()
        }
        members = extract_members(paths["archive"], work / "raw")
        metadata = pd.read_csv(paths["metadata"], sep="\t", index_col=0)
        genes = pd.read_csv(paths["genes"], sep="\t", header=None)

        matrices, observations = [], []
        barcode_normalizations = {}
        for condition in ("ctrl", "stim"):
            matrix, obs, normalized_count = read_condition(
                members[f"{condition}_matrix"],
                members[f"{condition}_barcodes"],
                metadata,
                condition,
            )
            matrices.append(matrix)
            observations.append(obs)
            barcode_normalizations[condition] = normalized_count
        counts = sparse.vstack(matrices, format="csr", dtype=np.int64)
        obs = pd.concat(observations)
        obs["donor"] = obs["donor"].astype(str)
        obs["sample"] = obs["biological_sample"].astype(str)
        population_mask = obs["cell_type"].isin(CELL_TYPES).to_numpy()
        counts = counts[population_mask]
        obs = obs.iloc[np.flatnonzero(population_mask)].copy()

        selected = stable_stratified_indices(obs)
        obs = obs.iloc[selected].copy()
        counts = counts[selected]
        detected = np.asarray((counts > 0).sum(axis=0)).ravel()
        selected_genes = np.flatnonzero(detected >= MINIMUM_GENE_DETECTION)
        counts = counts[:, selected_genes]
        var_names = np.asarray(unique_gene_names(genes), dtype=object)[
            selected_genes
        ]
        var = pd.DataFrame(index=var_names)
        communication_obs = obs.loc[
            :, ["cell_type", "sample", "condition", "donor"]
        ].copy()
        adata = ad.AnnData(X=counts.copy(), obs=communication_obs, var=var)
        adata.layers["counts"] = counts.copy()
        input_path = work / "gse96583-communication-input.h5ad"
        adata.write_h5ad(input_path, compression="gzip")

        stratum_counts = communication_obs.groupby(
            ["sample", "cell_type"], observed=True
        ).size()
        if (
            set(communication_obs["donor"]) != EXPECTED_DONORS
            or communication_obs["sample"].nunique() != 16
            or set(communication_obs["condition"]) != {"ctrl", "stim"}
            or set(communication_obs["cell_type"]) != set(CELL_TYPES)
            or int(stratum_counts.min()) < MINIMUM_CELLS
            or int(stratum_counts.max()) > MAX_CELLS_PER_STRATUM
            or adata.n_obs != 5857
            or adata.n_vars < 9000
        ):
            raise RuntimeError("GSE96583 communication design differs from contract")

        environment = dict(os.environ)
        environment["PYTHONHASHSEED"] = "0"
        for variable in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            environment[variable] = "1"
        for name, variable in (
            ("numba", "NUMBA_CACHE_DIR"),
            ("matplotlib", "MPLCONFIGDIR"),
            ("cache", "XDG_CACHE_HOME"),
            ("home", "HOME"),
        ):
            directory = work / name
            directory.mkdir()
            environment[variable] = str(directory)

        output_directory = work / "communication-output"
        template_report_path = work / "communication-report.json"
        run_template(
            python,
            input_path,
            output_directory,
            template_report_path,
            environment,
        )
        template_report = json.loads(
            template_report_path.read_text(encoding="utf-8")
        )
        interactions = pd.read_csv(
            output_directory / "sample_interactions.tsv", sep="\t"
        )
        summaries = pd.read_csv(
            output_directory / "replicated_interactions.tsv", sep="\t"
        )
        replicated = summaries.loc[summaries["replicated"]].copy()
        source_digests_after = {
            name: sha256(path) for name, path in paths.items()
        }

        expected_p_grid = np.rint(interactions["p_value"] * PERMUTATIONS)
        p_values_are_permutation_resolved = bool(
            interactions["p_value"].between(0, 1).all()
            and np.allclose(
                interactions["p_value"] * PERMUTATIONS,
                expected_p_grid,
                rtol=0,
                atol=1e-8,
            )
            and interactions["p_value"].nunique() >= 50
        )
        replicated_by_condition = {
            str(key): int(value)
            for key, value in replicated.groupby(
                "condition", observed=True
            ).size().items()
        }
        sample_run_count = sum(
            record.get("status") == "observed"
            for record in template_report["sample_runs"]
        )
        support_contract_valid = bool(
            not replicated.empty
            and (
                replicated["sample_support"] >= MINIMUM_SAMPLES
            ).all()
            and (
                replicated["significant_sample_support"] >= MINIMUM_SAMPLES
            ).all()
            and (replicated["fdr"] <= FDR).all()
        )
        sanity_mask = (
            replicated["condition"].eq("stim")
            & replicated["ligand"].eq("CXCL10")
            & replicated["receptor"].eq("CXCR3")
        )
        chemokine_mask = (
            replicated["ligand"].eq("CCL2")
            & replicated["receptor"].isin(["CCR1", "CCR5"])
        )
        quality_gates = {
            "official_sources_immutable": "pass"
            if source_digests_before == source_digests_after
            else "fail",
            "published_singlets_and_annotations_accounted": "pass"
            if set(communication_obs["donor"]) == EXPECTED_DONORS
            else "fail",
            "sample_cell_type_design_predeclared": "pass"
            if int(stratum_counts.min()) >= MINIMUM_CELLS
            else "fail",
            "all_biological_samples_executed": "pass"
            if sample_run_count == 16
            else "fail",
            "true_permutation_p_values_observed": "pass"
            if p_values_are_permutation_resolved
            and set(interactions["method"]) == {"liana-cellphonedb"}
            else "fail",
            "replication_requires_independent_sample_significance": "pass"
            if support_contract_valid
            else "fail",
            "both_conditions_retain_replicated_evidence": "pass"
            if set(replicated_by_condition) == {"ctrl", "stim"}
            and min(replicated_by_condition.values()) >= 1
            else "fail",
            "source_and_outputs_reload": "pass"
            if template_report["quality"]["source_counts_preserved"]
            and template_report["quality"]["source_immutable"]
            and len(interactions)
            == template_report["outputs"]["sample_interactions"]["rows"]
            and len(summaries)
            == template_report["outputs"]["replicated_interactions"]["rows"]
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "gse96583-sample-aware-communication-v1",
            "case_type": "public-data-end-to-end",
            "passed": set(quality_gates.values()) == {"pass"},
            "module": {
                "id": MODULE_ID,
                "version": registry.get(MODULE_ID).version,
                "compatibility_row_id": ROW_ID,
                "manifest_sha256": sha256(MANIFEST),
                "template_sha256": sha256(TEMPLATE),
                "registry_digest": registry.digest,
            },
            "source": {
                "accession": "GSE96583",
                "files": SOURCES,
                "validation": {
                    "selected_cells": adata.n_obs,
                    "selected_genes": adata.n_vars,
                    "donors": int(communication_obs["donor"].nunique()),
                    "conditions": int(
                        communication_obs["condition"].nunique()
                    ),
                    "biological_samples": int(
                        communication_obs["sample"].nunique()
                    ),
                    "cell_types": list(CELL_TYPES),
                    "minimum_cells_per_sample_cell_type": int(
                        stratum_counts.min()
                    ),
                    "maximum_cells_per_sample_cell_type": int(
                        stratum_counts.max()
                    ),
                    "metadata_barcode_normalizations": barcode_normalizations,
                },
            },
            "parameters": {
                "cell_selection": "up to 100 cells per donor-condition-cell-type stratum by stable SHA-256 order",
                "feature_selection": "genes detected in at least 20 selected cells without condition-based ranking",
                "minimum_cells": MINIMUM_CELLS,
                "minimum_samples": MINIMUM_SAMPLES,
                "expression_proportion": 0.1,
                "permutations": PERMUTATIONS,
                "p_value_floor_for_combination": 1 / (PERMUTATIONS + 1),
                "fdr": FDR,
                "seed": SEED,
            },
            "runtime": template_report["versions"],
            "execution": {
                "method": "liana-cellphonedb",
                "observed_sample_runs": sample_run_count,
                "sample_interaction_rows": len(interactions),
                "replicate_summary_rows": len(summaries),
                "replicated_interactions": len(replicated),
                "replicated_by_condition": replicated_by_condition,
                "minimum_significant_sample_support": int(
                    replicated["significant_sample_support"].min()
                ),
                "p_value_unique_count": int(
                    interactions["p_value"].nunique()
                ),
                "p_value_minimum": float(interactions["p_value"].min()),
                "p_value_maximum": float(interactions["p_value"].max()),
                "posthoc_biological_sanity": {
                    "stimulated_cxcl10_cxcr3_observed": bool(
                        sanity_mask.any()
                    ),
                    "ccl2_ccr1_or_ccr5_observed": bool(
                        chemokine_mask.any()
                    ),
                    "used_for_threshold_selection": False,
                    "used_as_quality_gate": False,
                },
                "source_artifacts_immutable": source_digests_before
                == source_digests_after,
                "outputs_reloaded": True,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "Publisher cell types define the communication populations and are not treated as validation truth for interaction significance.",
                "Each donor-condition sample is analyzed independently; cells are never used as condition-level replicates.",
                "Replicated interactions require within-sample FDR support in at least six independent samples plus BH-controlled Fisher combination within condition.",
                "Zero permutation p values are conservatively floored at 1/(permutations+1) before cross-sample combination.",
                "The public case validates the LIANA CellPhoneDB method; direct CellPhoneDB, CellChat, and NicheNet backends retain separate executable fixture evidence.",
                "Ligand-receptor coexpression supports communication hypotheses but does not establish physical contact, signal direction in vivo, or causality.",
                "Control and stimulated results are summarized separately; this case does not perform a formal between-condition interaction test.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "GSE96583 communication public gates failed: "
                + json.dumps(quality_gates, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "reports"
        / "public-case-gse96583-communication.json",
    )
    args = parser.parse_args()
    report = verify(args.source_dir, args.scientific_python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": report["passed"],
                "replicated_interactions": report["execution"][
                    "replicated_interactions"
                ],
                "replicated_by_condition": report["execution"][
                    "replicated_by_condition"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
