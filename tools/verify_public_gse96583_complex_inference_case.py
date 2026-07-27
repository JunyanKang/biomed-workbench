#!/usr/bin/env python3
"""Validate paired dream expression and composition inference on public GSE96583."""

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
    IFN_RESPONSE_GENES,
    SOURCES,
    acquire_sources,
    extract_members,
    read_condition,
    unique_gene_names,
)

MODULE_ID = "single-cell-complex-inference"
ROW_ID = "agent-protocol-1-dream-1325-speckle-120"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
PREPARE = MODULE_ROOT / "templates" / "prepare_inference_inputs.py"
DREAM = MODULE_ROOT / "templates" / "fit_dream_longitudinal.R"
COMPOSITION = MODULE_ROOT / "templates" / "fit_composition_models.R"
CELL_TYPES = (
    "B cells",
    "CD4 T cells",
    "CD8 T cells",
    "CD14+ Monocytes",
    "FCGR3A+ Monocytes",
    "NK cells",
)
REFERENCE_TYPES = ("B cells", "CD4 T cells", "CD14+ Monocytes")
N_FEATURES = 1200


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: list[str],
    environment: dict[str, str],
    timeout: int = 1800,
) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "public GSE96583 complex inference failed:\n"
            + completed.stdout[-2000:]
            + "\n"
            + completed.stderr[-5000:]
        )


def verify(
    source_dir: Path | None,
    scientific_python: Path,
    rscript: Path,
    r_library: Path,
) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    r_executable = rscript.expanduser().absolute()
    library = r_library.expanduser().resolve(strict=True)
    if (
        not python.is_file()
        or not os.access(python, os.X_OK)
        or not r_executable.is_file()
        or not os.access(r_executable, os.X_OK)
    ):
        raise RuntimeError("scientific Python and Rscript must be executable")

    with tempfile.TemporaryDirectory(
        prefix="biomed-public-gse96583-complex-"
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
        population_mask = obs["cell_type"].isin(CELL_TYPES).to_numpy()
        counts = counts[population_mask]
        obs = obs.iloc[np.flatnonzero(population_mask)].copy()
        detected = np.asarray((counts > 0).sum(axis=0)).ravel()
        totals = np.asarray(counts.sum(axis=0)).ravel()
        ranked_features = np.lexsort(
            (np.arange(counts.shape[1]), -totals, -detected)
        )
        selected_features = np.sort(ranked_features[:N_FEATURES])
        gene_names = np.asarray(unique_gene_names(genes), dtype=object)
        feature_ranks = np.empty(len(ranked_features), dtype=np.int64)
        feature_ranks[ranked_features] = np.arange(
            1, len(ranked_features) + 1, dtype=np.int64
        )
        ifn_indices = np.flatnonzero(
            np.isin(gene_names, sorted(IFN_RESPONSE_GENES))
        )
        if len(ifn_indices) != len(IFN_RESPONSE_GENES):
            raise RuntimeError("public source lacks predeclared IFN controls")
        maximum_ifn_rank = int(feature_ranks[ifn_indices].max())
        if maximum_ifn_rank > N_FEATURES:
            raise RuntimeError(
                "label-blind feature set does not retain every IFN control"
            )
        counts = counts[:, selected_features]
        obs["sample"] = obs["biological_sample"].astype(str)
        obs["subject"] = obs["donor"].astype(str)
        obs["time"] = obs["condition"].map({"ctrl": 0.0, "stim": 1.0})
        var = pd.DataFrame(
            {
                "ensembl_id": genes.iloc[selected_features, 0]
                .astype(str)
                .to_numpy()
            },
            index=gene_names[selected_features],
        )
        adata = ad.AnnData(X=counts.copy(), obs=obs, var=var)
        adata.layers["counts"] = counts.copy()
        input_path = work / "gse96583-paired-inference.h5ad"
        adata.write_h5ad(input_path, compression="gzip")
        sample_cell_counts = obs.groupby(
            ["sample", "cell_type"], observed=True
        ).size()
        if (
            set(obs["subject"]) != EXPECTED_DONORS
            or obs["sample"].nunique() != 16
            or set(obs["condition"]) != {"ctrl", "stim"}
            or set(obs["cell_type"]) != set(CELL_TYPES)
            or int(sample_cell_counts.min()) < 15
        ):
            raise RuntimeError("GSE96583 paired complex design differs from contract")

        environment = dict(os.environ)
        environment.update(
            {
                "PATH": str(python.parent)
                + os.pathsep
                + str(r_executable.parent)
                + os.pathsep
                + os.environ.get("PATH", ""),
                "PYTHONHASHSEED": "0",
                "R_LIBS_USER": str(library),
                "LANG": "C",
                "LC_ALL": "C",
            }
        )
        for name, variable in (
            ("home", "HOME"),
            ("cache", "XDG_CACHE_HOME"),
        ):
            directory = work / name
            directory.mkdir()
            environment[variable] = str(directory)

        counts_path = work / "pseudobulk-counts.tsv"
        pseudobulk_path = work / "pseudobulk-metadata.tsv"
        composition_path = work / "composition.tsv"
        prepare_report_path = work / "prepare.json"
        run(
            [
                str(python),
                str(PREPARE),
                "--input-h5ad",
                str(input_path),
                "--raw-count-location",
                "layers.counts",
                "--sample-key",
                "sample",
                "--subject-key",
                "subject",
                "--cell-type-key",
                "cell_type",
                "--condition-key",
                "condition",
                "--time-key",
                "time",
                "--categorical-covariates",
                "none",
                "--continuous-covariates",
                "none",
                "--require-longitudinal",
                "true",
                "--min-cells-per-pseudobulk",
                "15",
                "--min-library-size",
                "100",
                "--output-counts",
                str(counts_path),
                "--output-pseudobulk-metadata",
                str(pseudobulk_path),
                "--output-composition",
                str(composition_path),
                "--report",
                str(prepare_report_path),
            ],
            environment,
        )
        dream_results_path = work / "dream-results.tsv"
        variance_results_path = work / "variance-results.tsv"
        dream_report_path = work / "dream.json"
        run(
            [
                str(r_executable),
                str(DREAM),
                "--counts",
                str(counts_path),
                "--metadata",
                str(pseudobulk_path),
                "--results",
                str(dream_results_path),
                "--variance-results",
                str(variance_results_path),
                "--diagnostics",
                str(dream_report_path),
                "--formula",
                "~ condition + (1 | subject)",
                "--variance-formula",
                "~ (1 | subject)",
                "--coefficient-pattern",
                "^conditionstim$",
                "--ddf",
                "adaptive",
                "--min-count",
                "2",
                "--min-samples-expressed",
                "4",
                "--min-subjects",
                "8",
                "--min-repeated-subjects",
                "8",
                "--fdr-threshold",
                "0.05",
            ],
            environment,
        )
        composition_results_path = work / "composition-results.tsv"
        alr_path = work / "composition-alr.tsv"
        composition_report_path = work / "composition.json"
        run(
            [
                str(r_executable),
                str(COMPOSITION),
                "--composition",
                str(composition_path),
                "--results",
                str(composition_results_path),
                "--alr-results",
                str(alr_path),
                "--diagnostics",
                str(composition_report_path),
                "--formula",
                "~ condition + (1 | subject)",
                "--coefficient-pattern",
                "^conditionstim$",
                "--ddf",
                "adaptive",
                "--reference-cell-types",
                ",".join(REFERENCE_TYPES),
                "--min-total-cells",
                "100",
                "--min-samples",
                "16",
                "--min-subjects",
                "8",
                "--min-repeated-subjects",
                "8",
                "--min-reference-support",
                "2",
                "--fdr-threshold",
                "0.05",
            ],
            environment,
        )

        prepared = json.loads(prepare_report_path.read_text())
        dream = json.loads(dream_report_path.read_text())
        composition = json.loads(composition_report_path.read_text())
        dream_results = pd.read_csv(dream_results_path, sep="\t")
        variance_results = pd.read_csv(variance_results_path, sep="\t")
        composition_results = pd.read_csv(composition_results_path, sep="\t")
        alr_results = pd.read_csv(alr_path, sep="\t")
        ifn = dream_results.loc[
            dream_results["gene_id"].isin(IFN_RESPONSE_GENES)
            & dream_results["test_type"].eq("coefficient")
        ].copy()
        ifn_by_cell_type = {
            str(cell_type): {
                "genes_tested": int(len(frame)),
                "positive_effects": int((frame["log2_effect"] > 0).sum()),
                "fdr_below_0_05": int((frame["fdr"] <= 0.05).sum()),
                "median_log2_effect": float(frame["log2_effect"].median()),
            }
            for cell_type, frame in ifn.groupby("cell_type", observed=True)
        }
        stability_items = composition["reference_stability"]
        if isinstance(stability_items, dict):
            stability_items = list(stability_items.values())
        stability_items = [
            item
            for group in stability_items
            for item in (group if isinstance(group, list) else [group])
        ]
        source_digests_after = {
            name: sha256(path) for name, path in paths.items()
        }
        analyses = dream["analyses"]
        quality_gates = {
            "official_sources_immutable": "pass"
            if source_digests_before == source_digests_after
            else "fail",
            "paired_eight_subject_design_established": "pass"
            if prepared["design"]["subjects"] == 8
            and len(prepared["design"]["repeated_subjects"]) == 8
            else "fail",
            "all_cells_counts_and_compositions_accounted": "pass"
            if all(
                prepared["accounting"][key]
                for key in (
                    "all_cells_accounted",
                    "raw_counts_conserved",
                    "composition_grid_complete",
                    "sample_compositions_sum_to_one",
                    "serialized_outputs_reloaded",
                )
            )
            else "fail",
            "dream_uses_samples_and_subject_random_effect": "pass"
            if dream["quality"]["biological_samples_are_model_rows"]
            and dream["quality"]["subject_random_effect_required"]
            and dream["quality"]["all_fixed_designs_full_rank"]
            and set(analyses) == set(CELL_TYPES)
            else "fail",
            "paired_ifn_response_direction_recovered": "pass"
            if set(ifn_by_cell_type) == set(CELL_TYPES)
            and all(
                item["genes_tested"] >= 6
                and item["positive_effects"] / item["genes_tested"] >= 0.8
                and item["median_log2_effect"] > 0
                for item in ifn_by_cell_type.values()
            )
            else "fail",
            "composition_closure_and_repeated_measure_model_passed": "pass"
            if composition["quality"]["complete_composition_grid"]
            and composition["quality"]["closure_checked"]
            and composition["quality"]["subject_random_effect_required"]
            and composition["quality"]["fixed_only_propeller_is_sensitivity"]
            else "fail",
            "multi_reference_alr_completed_without_forced_concordance": "pass"
            if composition["quality"]["alr_reference_sensitivity_completed"]
            and len(stability_items) >= len(CELL_TYPES) - 1
            else "fail",
            "all_statistical_outputs_reloaded": "pass"
            if dream["quality"]["all_outputs_reloaded"]
            and composition["quality"]["outputs_reloaded"]
            and not dream_results.empty
            and not variance_results.empty
            and not composition_results.empty
            and not alr_results.empty
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "gse96583-paired-complex-inference-v1",
            "case_type": "public-data-end-to-end",
            "passed": set(quality_gates.values()) == {"pass"},
            "module": {
                "id": MODULE_ID,
                "version": registry.get(MODULE_ID).version,
                "compatibility_row_id": ROW_ID,
                "manifest_sha256": sha256(MANIFEST),
                "template_sha256": {
                    path.name: sha256(path)
                    for path in (PREPARE, DREAM, COMPOSITION)
                },
                "registry_digest": registry.digest,
            },
            "source": {
                "accession": "GSE96583",
                "files": SOURCES,
                "validation": {
                    "selected_cells": adata.n_obs,
                    "genes": adata.n_vars,
                    "feature_selection": {
                        "method": "label-blind detected-cell count, then total count",
                        "selected_features": N_FEATURES,
                        "maximum_predeclared_ifn_control_rank": maximum_ifn_rank,
                        "all_predeclared_ifn_controls_retained": bool(
                            set(IFN_RESPONSE_GENES).issubset(set(adata.var_names))
                        ),
                    },
                    "subjects": int(obs["subject"].nunique()),
                    "biological_samples": int(obs["sample"].nunique()),
                    "conditions": int(obs["condition"].nunique()),
                    "cell_types": list(CELL_TYPES),
                    "minimum_cells_per_sample_cell_type": int(
                        sample_cell_counts.min()
                    ),
                    "metadata_barcode_normalizations": barcode_normalizations,
                },
            },
            "parameters": {
                "expression_formula": "~ condition + (1 | subject)",
                "variance_formula": "~ (1 | subject)",
                "composition_formula": "~ condition + (1 | subject)",
                "coefficient": "conditionstim",
                "minimum_cells_per_pseudobulk": 15,
                "feature_selection": (
                    f"{N_FEATURES} genes ranked by detection count then total "
                    "count without condition labels"
                ),
                "composition_references": list(REFERENCE_TYPES),
                "minimum_predeclared_ifn_estimable_fraction": 0.6,
                "minimum_predeclared_ifn_positive_fraction": 0.8,
                "fdr": 0.05,
            },
            "runtime": {
                "prepare": prepared["versions"],
                "dream": dream["versions"],
                "composition": composition["versions"],
            },
            "execution": {
                "pseudobulks": prepared["accounting"]["pseudobulks"],
                "eligible_pseudobulks": prepared["accounting"][
                    "eligible_pseudobulks"
                ],
                "expression_result_rows": len(dream_results),
                "variance_result_rows": len(variance_results),
                "composition_result_rows": len(composition_results),
                "alr_result_rows": len(alr_results),
                "ifn_response_by_cell_type": ifn_by_cell_type,
                "composition_reference_stability": stability_items,
                "source_artifacts_immutable": source_digests_before
                == source_digests_after,
                "outputs_reloaded": True,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "GSE96583 supplies two paired conditions per donor, not a multi-timepoint longitudinal trajectory; the public case therefore tests a paired condition effect only.",
                "The subject random intercept accounts for donor pairing, and biological samples rather than cells are model rows.",
                "The IFN gene set is a predeclared external direction sanity check and does not tune the model, coefficient, filtering, or FDR threshold.",
                "Primary composition inference uses dream; propeller is retained only as fixed-effect sensitivity evidence.",
                "Additive-log-ratio reference discordance is preserved rather than forced into a consensus direction.",
                "Expression, variance, and composition results remain source-, model-, reference-, and design-specific associations rather than causal effects.",
            ],
        }
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-library", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "reports"
        / "public-case-gse96583-complex-inference.json",
    )
    args = parser.parse_args()
    report = verify(
        args.source_dir,
        args.scientific_python,
        args.rscript,
        args.r_library,
    )
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
                "pseudobulks": report["execution"]["pseudobulks"],
                "expression_rows": report["execution"][
                    "expression_result_rows"
                ],
            },
            sort_keys=True,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
