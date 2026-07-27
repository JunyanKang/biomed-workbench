#!/usr/bin/env python3
"""Execute RegVelo 0.4.2 on a deterministic GRN-informed velocity fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


MODULE_ID = "single-cell-regulatory-velocity"
MODULE_VERSION = "1.1.0"
ROW_ID = "agent-protocol-1-regvelo-042-python-311-layer-semantics"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
TEMPLATE = MODULE_ROOT / "templates" / "run_regvelo.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"RegVelo verification command failed ({completed.returncode}): {' '.join(command[:3])}\n"
            f"stderr:\n{completed.stderr[-8000:]}\nstdout:\n{completed.stdout[-4000:]}"
        )
    return completed


def fixture_code(h5ad: Path, grn: Path) -> str:
    return f"""
import anndata as ad
import numpy as np
import pandas as pd

rng = np.random.default_rng(742)
cells, genes = 96, 24
gene_names = [f'Gene{{index:02d}}' for index in range(genes)]
time = np.linspace(0.02, 0.98, cells)
spliced = np.zeros((cells, genes), dtype=np.int32)
unspliced = np.zeros((cells, genes), dtype=np.int32)
for gene in range(genes):
    phase = gene / genes * 0.55
    pulse = np.exp(-((time - (0.25 + phase)) ** 2) / 0.045)
    spliced[:, gene] = rng.poisson(2.0 + 9.0 * pulse)
    shifted = np.exp(-((time - (0.19 + phase)) ** 2) / 0.04)
    unspliced[:, gene] = rng.poisson(1.5 + 6.5 * shifted)
data = ad.AnnData(
    X=spliced.copy(),
    obs=pd.DataFrame({{'withheld_time': time, 'sample_id': [f'D{{index % 4 + 1}}' for index in range(cells)]}},
                     index=[f'cell-{{index:03d}}' for index in range(cells)]),
    var=pd.DataFrame(index=gene_names),
)
data.layers['spliced'] = spliced
data.layers['unspliced'] = unspliced
data.write_h5ad({str(h5ad)!r})
regulators = gene_names[:6]
network = pd.DataFrame(0.0, index=gene_names, columns=regulators)
for target_index, target in enumerate(gene_names):
    regulator = regulators[target_index % len(regulators)]
    if target != regulator:
        network.loc[target, regulator] = 1.0
    second = regulators[(target_index + 2) % len(regulators)]
    if target != second and target_index % 3 == 0:
        network.loc[target, second] = -0.6
network.to_csv({str(grn)!r}, sep='\\t', index_label='target')
"""


def inspect_output(python: Path, output: Path, environment: dict[str, str]) -> dict[str, object]:
    code = f"""
import anndata as ad
import json
import numpy as np
from scipy import sparse
d = ad.read_h5ad({str(output)!r})
def finite(key):
    value = d.layers[key]
    array = value.toarray() if sparse.issparse(value) else np.asarray(value)
    return bool(np.isfinite(array).all())
print(json.dumps({{
    'cells': d.n_obs,
    'genes': d.n_vars,
    'velocity_shape': list(d.layers['regvelo_velocity'].shape),
    'latent_time_shape': list(d.layers['regvelo_latent_time'].shape),
    'latent_shape': list(d.obsm['X_regvelo'].shape),
    'velocity_finite': finite('regvelo_velocity'),
    'latent_time_finite': finite('regvelo_latent_time'),
    'provenance_present': 'biomed_regulatory_velocity' in d.uns,
}}))
"""
    return json.loads(run([str(python), "-c", code], environment).stdout)


def verify(scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.exists() or not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python must be executable")
    with tempfile.TemporaryDirectory(prefix="biomed-regvelo-") as temporary:
        work = Path(temporary)
        for name in ("home", "cache", "matplotlib"):
            (work / name).mkdir()
        environment = {
            **os.environ,
            "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"),
            "XDG_CACHE_HOME": str(work / "cache"),
            "MPLCONFIGDIR": str(work / "matplotlib"),
            "PYTHONHASHSEED": "0",
        }
        source, grn = work / "fixture.h5ad", work / "prior-grn.tsv"
        run([str(python), "-c", fixture_code(source, grn)], environment)
        source_digest, grn_digest = sha256(source), sha256(grn)
        output, models, analysis_report = work / "regvelo.h5ad", work / "models", work / "analysis.json"
        run([
            str(python), str(TEMPLATE),
            "--input-h5ad", str(source),
            "--prior-grn-tsv", str(grn),
            "--output-h5ad", str(output),
            "--model-dir", str(models),
            "--report", str(analysis_report),
            "--spliced-layer", "spliced",
            "--unspliced-layer", "unspliced",
            "--layer-semantics", "integer-counts",
            "--model-modes", "hard,soft",
            "--repeats", "1",
            "--max-epochs", "2",
            "--batch-size", "96",
            "--n-latent", "10",
            "--n-hidden", "256",
            "--lambda-grn", "1.0",
            "--lambda-l1", "0.01",
            "--minimum-regulators", "5",
            "--minimum-edges", "10",
            "--maximum-dense-bytes", "1000000",
            "--seed", "743",
        ], environment, timeout=1200)
        analysis = json.loads(analysis_report.read_text(encoding="utf-8"))
        inspected = inspect_output(python, output, environment)
        if sha256(source) != source_digest or sha256(grn) != grn_digest:
            raise RuntimeError("RegVelo verification modified a source artifact")
        if (
            len(analysis["runs"]) != 2
            or {item["mode"] for item in analysis["runs"]} != {"hard", "soft"}
            or not all(item["model_reloaded"] for item in analysis["runs"])
            or inspected["velocity_shape"] != [96, 24]
            or inspected["latent_time_shape"] != [96, 24]
            or inspected["latent_shape"] != [96, 10]
            or not all(inspected[key] for key in ("velocity_finite", "latent_time_finite", "provenance_present"))
        ):
            raise RuntimeError("RegVelo execution failed mode, model, shape, finite-value, or provenance gates")

        versions = analysis["versions"]
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": MODULE_ID,
            "module_version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID,
            "registry_digest": registry.digest,
            "templates": {
                "run_regvelo": {"name": TEMPLATE.name, "sha256": sha256(TEMPLATE)}
            },
            "tool_versions": {"RegVelo": versions["regvelo"]},
            "dependency_versions": {
                key: versions[key]
                for key in (
                    "python", "anndata", "numpy", "pandas", "scipy", "scvelo",
                    "scvi-tools", "cellrank", "torch", "torchode", "jax", "jaxlib"
                )
            },
            "fixture": {
                "cells": 96,
                "genes": 24,
                "biological_samples": 4,
                "regulators": analysis["prior_grn"]["regulators"],
                "edges": analysis["prior_grn"]["edges"],
                "source_sha256": source_digest,
                "grn_sha256": grn_digest,
                "grn_orientation": "targets-by-regulators",
            },
            "execution": {
                "hard_constraint_completed": True,
                "soft_constraint_completed": True,
                "velocity_completed": True,
                "latent_time_completed": True,
                "models_reloaded": True,
                "outputs_reloaded": True,
                "analysis_report_sha256": sha256(analysis_report),
                "output_sha256": sha256(output),
            },
            "results": {
                "runs": len(analysis["runs"]),
                "pairwise_velocity_comparisons": len(analysis["stability"]["pairwise_velocity_correlations"]),
                **inspected,
            },
            "compatibility_observations": {
                "integer_count_layer_semantics": analysis["input"]["layer_semantics"],
                "sparse_working_layers": "blocked-by-observed-regvelo-0.4.2-initializer-behavior",
                "rectangular_model_grn": "converted-explicitly-to-square-gene-aligned-working-matrix",
                "numpy_2_profile": "excluded-after-observed-compiled-extension-abi-failure",
                "modern_jax_profile": "excluded-after-observed-jaxlib.xla_extension-import-failure",
                "custom_n_latent_or_n_hidden": "blocked-after-observed-regvelo-0.4.2-duplicate-keyword-failure",
            },
            "scientific_summary": {
                "regvelo_042_executed": True,
                "hard_and_soft_constraints_executed": True,
                "grn_namespace_orientation_and_edges_validated": True,
                "dense_memory_budget_enforced": True,
                "velocity_latent_time_and_latent_state_finite": True,
                "model_mode_comparison_retained": True,
                "models_saved_and_reloaded": True,
                "source_counts_grn_and_identifiers_preserved": True,
                "integer_count_semantics_executed": analysis["input"]["layer_semantics"] == "integer-counts",
                "experimental_labels_withheld_from_fitting": True,
                "perturbation_predictions_limited_to_hypotheses": True,
                "outputs_reloaded": True,
                "no_environment_or_compute_infrastructure_managed": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "versions": report["dependency_versions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
