#!/usr/bin/env python3
"""Validate scVelo on public mouse-gastrulation erythroid development."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402

MODULE_ID = "single-cell-trajectory-velocity"
ROW_ID = "agent-protocol-1-scvelo-034-scanpy-1115"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "run_velocity.py"
SOURCE = {
    "filename": "erythroid_lineage.h5ad",
    "url": "https://ndownloader.figshare.com/files/27686871",
    "sha256": "0af49504137dc8dc930a19e3534243a121da1ddddbe28ebc5fab0470294d60d4",
}
STAGE_TO_DAY = {
    "E7.0": 7.0,
    "E7.25": 7.25,
    "E7.5": 7.5,
    "E7.75": 7.75,
    "E8.0": 8.0,
    "E8.25": 8.25,
    "E8.5": 8.5,
}
MAX_CELLS_PER_SAMPLE = 60
SEED = 20260723


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def acquire_source(work: Path, source_dir: Path | None) -> Path:
    if source_dir is not None:
        candidate = source_dir.expanduser().resolve(strict=True)
        source = candidate / SOURCE["filename"] if candidate.is_dir() else candidate
        source = source.resolve(strict=True)
    else:
        source = work / SOURCE["filename"]
        urllib.request.urlretrieve(SOURCE["url"], source)
    if sha256(source) != SOURCE["sha256"]:
        raise RuntimeError("public erythroid source digest mismatch")
    return source


def integer_count_layer(adata: ad.AnnData, key: str) -> sparse.csr_matrix:
    if key not in adata.layers:
        raise RuntimeError(f"public source lacks {key} counts")
    matrix = sparse.csr_matrix(adata.layers[key])
    values = matrix.data
    if (
        not values.size
        or not np.isfinite(values).all()
        or float(values.min()) < 0
        or not np.allclose(values, np.rint(values), rtol=0, atol=1e-8)
    ):
        raise RuntimeError(f"public {key} layer is not finite integer-like counts")
    return matrix.astype(np.int64)


def stable_sample_indices(obs: pd.DataFrame) -> np.ndarray:
    sample = obs["sample"].astype(str).to_numpy()
    selected: list[int] = []
    for value in sorted(set(sample)):
        candidates = np.flatnonzero(sample == value)
        ranked = sorted(
            candidates,
            key=lambda index: hashlib.sha256(
                f"{SEED}:{obs.index[index]}".encode()
            ).hexdigest(),
        )
        selected.extend(ranked[:MAX_CELLS_PER_SAMPLE])
    return np.asarray(sorted(selected), dtype=int)


def run_template(
    python: Path,
    input_path: Path,
    output_path: Path,
    report_path: Path,
    environment: dict[str, str],
) -> None:
    completed = subprocess.run(
        [
            str(python),
            str(TEMPLATE),
            "--input-h5ad",
            str(input_path),
            "--output-h5ad",
            str(output_path),
            "--report",
            str(report_path),
            "--spliced-layer",
            "spliced",
            "--unspliced-layer",
            "unspliced",
            "--sample-key",
            "sample_id",
            "--experimental-time-key",
            "embryonic_day",
            "--root-score-key",
            "root_score",
            "--terminal-score-key",
            "terminal_score",
            "--n-top-genes",
            "500",
            "--n-pcs",
            "30",
            "--n-neighbors",
            "30",
            "--max-dynamics-iterations",
            "20",
            "--minimum-modeled-genes",
            "80",
            "--minimum-latent-time-correlation",
            "0.15",
            "--minimum-velocity-pseudotime-correlation",
            "0.10",
            "--minimum-root-terminal-separation",
            "0.15",
            "--minimum-median-velocity-confidence",
            "0.40",
            "--seed",
            str(SEED),
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
            "public erythroid scVelo execution failed:\n"
            + completed.stdout[-1500:]
            + "\n"
            + completed.stderr[-4000:]
        )


def verify(source_dir: Path | None, scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python is not executable")
    with tempfile.TemporaryDirectory(prefix="biomed-public-erythroid-velocity-") as temporary:
        work = Path(temporary)
        source = acquire_source(work, source_dir)
        source_digest_before = sha256(source)
        adata = ad.read_h5ad(source)
        if adata.shape != (9815, 53801):
            raise RuntimeError("public erythroid source shape differs from contract")
        required_obs = {"sample", "stage", "sequencing.batch", "theiler", "celltype"}
        if not required_obs.issubset(adata.obs):
            raise RuntimeError("public erythroid metadata differs from contract")
        spliced = integer_count_layer(adata, "spliced")
        unspliced = integer_count_layer(adata, "unspliced")
        if not adata.obs_names.is_unique or not adata.var_names.is_unique:
            raise RuntimeError("public erythroid identifiers are not unique")

        selected = stable_sample_indices(adata.obs)
        query = adata[selected].copy()
        query.layers["spliced"] = spliced[selected]
        query.layers["unspliced"] = unspliced[selected]
        query.X = query.layers["spliced"].copy()
        query.obs["sample_id"] = query.obs["sample"].astype(str)
        query.obs["embryonic_day"] = (
            query.obs["stage"].astype(str).map(STAGE_TO_DAY).astype(float)
        )
        query.obs["root_score"] = (
            query.obs["celltype"].astype(str) == "Blood progenitors 1"
        ).astype(float)
        query.obs["terminal_score"] = (
            query.obs["celltype"].astype(str) == "Erythroid3"
        ).astype(float)
        if (
            query.shape != (1234, 53801)
            or query.obs["sample_id"].nunique() != 27
            or query.obs["embryonic_day"].nunique() != 7
            or int(query.obs["root_score"].sum()) != 226
            or int(query.obs["terminal_score"].sum()) != 224
        ):
            raise RuntimeError("public erythroid label-blind subset differs from contract")
        input_path = work / "erythroid-velocity-query.h5ad"
        query.write_h5ad(input_path, compression="gzip")

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
        ):
            directory = work / name
            directory.mkdir()
            environment[variable] = str(directory)

        analyses = []
        outputs = []
        for repeat in (1, 2):
            output = work / f"velocity-repeat-{repeat}.h5ad"
            analysis_path = work / f"velocity-repeat-{repeat}.json"
            run_template(python, input_path, output, analysis_path, environment)
            outputs.append(ad.read_h5ad(output))
            analyses.append(json.loads(analysis_path.read_text(encoding="utf-8")))
        first, second = outputs
        repeat_arrays = {
            "latent_time": (
                first.obs["latent_time"].to_numpy(),
                second.obs["latent_time"].to_numpy(),
            ),
            "velocity_pseudotime": (
                first.obs["velocity_pseudotime"].to_numpy(),
                second.obs["velocity_pseudotime"].to_numpy(),
            ),
            "velocity": (
                np.asarray(first.layers["velocity"]),
                np.asarray(second.layers["velocity"]),
            ),
        }
        deterministic_fields = {
            name: {
                "exactly_equal": bool(
                    np.array_equal(left, right, equal_nan=True)
                ),
                "missing_value_mask_equal": bool(
                    np.array_equal(np.isnan(left), np.isnan(right))
                ),
                "maximum_absolute_difference": float(
                    np.max(np.abs(left[~np.isnan(left)] - right[~np.isnan(right)]))
                ),
            }
            for name, (left, right) in repeat_arrays.items()
        }
        analysis = analyses[0]
        source_digest_after = sha256(source)
        quality_gates = {
            "official_source_identity": "pass"
            if source_digest_before == source_digest_after == SOURCE["sha256"]
            else "fail",
            "integer_spliced_and_unspliced_counts": "pass",
            "label_blind_sample_balancing": "pass",
            "multiple_samples_and_stages": "pass",
            "experimental_stage_removed_before_fitting": "pass"
            if analysis["direction_validation"][
                "experimental_time_removed_before_backend_execution"
            ]
            else "fail",
            "minimum_dynamical_gene_coverage": "pass"
            if analysis["model"]["modeled_genes"] >= 80
            and analysis["model"]["finite_fit_genes"] >= 80
            else "fail",
            "withheld_stage_direction": "pass"
            if analysis["direction_validation"]["latent_time_spearman"] >= 0.15
            and analysis["direction_validation"][
                "velocity_pseudotime_spearman"
            ]
            >= 0.10
            else "fail",
            "independent_root_terminal_direction": "pass"
            if analysis["direction_validation"]["root_terminal_separation"] >= 0.15
            else "fail",
            "velocity_confidence": "pass"
            if analysis["confidence"]["median_velocity_confidence"] >= 0.40
            else "fail",
            "exact_repeat": "pass"
            if all(
                value["exactly_equal"]
                for value in deterministic_fields.values()
            )
            else "fail",
            "source_and_output_preservation": "pass"
            if all(
                item["source_immutable"]
                and item["cell_feature_and_source_metadata_identity_preserved"]
                and set(item["quality_gates"].values()) == {True}
                for item in analyses
            )
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "gastrulation-erythroid-scvelo-v1",
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
                "dataset": "mouse gastrulation erythroid lineage",
                "publisher": "Pijuan-Sala et al.; scVelo public dataset",
                **SOURCE,
                "validation": {
                    "source_cells": 9815,
                    "source_genes": 53801,
                    "selected_cells": query.n_obs,
                    "samples": int(query.obs["sample_id"].nunique()),
                    "embryonic_stages": sorted(
                        query.obs["stage"].astype(str).unique().tolist()
                    ),
                    "root_cells": int(query.obs["root_score"].sum()),
                    "terminal_cells": int(query.obs["terminal_score"].sum()),
                    "spliced_integer_like": True,
                    "unspliced_integer_like": True,
                },
            },
            "parameters": {
                "sample_selection": "up to 60 cells per published sample by stable SHA-256 order without stage or cell-type labels",
                "n_top_genes": 500,
                "n_pcs": 30,
                "n_neighbors": 30,
                "max_dynamics_iterations": 20,
                "minimum_modeled_genes": 80,
                "minimum_latent_time_correlation": 0.15,
                "minimum_velocity_pseudotime_correlation": 0.10,
                "minimum_root_terminal_separation": 0.15,
                "minimum_median_velocity_confidence": 0.40,
                "seed": SEED,
            },
            "runtime": analysis["versions"],
            "execution": {
                "model": analysis["model"],
                "direction_validation": analysis["direction_validation"],
                "confidence": analysis["confidence"],
                "exact_repeat_fields": deterministic_fields,
                "independent_template_runs": 2,
                "all_outputs_reloaded": True,
                "source_artifact_immutable": source_digest_before
                == source_digest_after,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "Embryonic stage is physically absent from backend-visible metadata during preprocessing, kinetic fitting, velocity graph construction, and latent-time inference; it is joined only for postfit direction evaluation.",
                "Published Blood progenitors 1 and Erythroid3 annotations provide independent root and terminal anchors for orientation, not labels for kinetic parameter fitting.",
                "The 27 published samples and seven developmental stages support direction validation, but cells are not treated as independent condition-level replicates.",
                "This case validates the recorded erythroid lineage, runtime, parameters, and gates; it does not establish lineage causality or universal scVelo performance.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "public erythroid velocity gates failed: "
                + json.dumps(quality_gates, sort_keys=True)
                + "; repeat="
                + json.dumps(deterministic_fields, sort_keys=True)
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
        / "public-case-gastrulation-erythroid-velocity.json",
    )
    args = parser.parse_args()
    report = verify(args.source_dir, args.scientific_python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": report["passed"],
                "modeled_genes": report["execution"]["model"]["modeled_genes"],
                "latent_time_spearman": report["execution"][
                    "direction_validation"
                ]["latent_time_spearman"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
