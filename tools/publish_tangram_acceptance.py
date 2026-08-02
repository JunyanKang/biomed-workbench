#!/usr/bin/env python3
"""Publish path-neutral Tangram evidence after reopening every observed artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.evidence_scope import module_evidence_scope  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


MODULE_ID = "spatial-multimethod-inference"
UPSTREAM_COMMIT = "4c68995a418f41dc8caef567598c4d9b47781a13"
EXPECTED_INPUTS = {
    "test_ad_sc.h5ad": "fa49de9d37a2cfcc57e28e4c4b341aa040b000568f91a931099e5e5364ece3e4",
    "test_ad_sp.h5ad": "4a66814ab1d714cf6105a860188ee1155e6aec0b2f65c6ee957bec4c7778914d",
}
TEMPLATE = ROOT / "biomed_workbench/modules/builtin/spatial-multimethod-inference/templates/run_deconvolution.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return value


def build(workspace: Path) -> tuple[dict, dict]:
    workspace = workspace.expanduser().resolve()
    inputs = workspace / "inputs"
    results = workspace / "results"
    execution_path = results / "tangram_execution.json"
    abundance_path = results / "tangram_abundance.tsv"
    model_path = results / "tangram_mapping.h5ad"
    diagnostics_path = results / "tangram_diagnostics.json"
    for name, expected in EXPECTED_INPUTS.items():
        path = inputs / name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"official Tangram input is absent or changed: {name}")
    execution = load_json(execution_path)
    diagnostics = load_json(diagnostics_path)
    if execution.get("backend") != "tangram" or execution.get("outputs", {}).get("reloaded") is not True:
        raise ValueError("Tangram execution report is not a passing reloaded run")
    if execution.get("implementation", {}).get("sha256") != sha256(TEMPLATE):
        raise ValueError("Tangram execution does not match the current template")
    for key, path in (("abundance", abundance_path), ("model", model_path), ("diagnostics", diagnostics_path)):
        if sha256(path) != execution["outputs"][key]["sha256"]:
            raise ValueError(f"Tangram {key} changed after execution")
    abundance = pd.read_csv(abundance_path, sep="\t")
    model = ad.read_h5ad(model_path)
    values = abundance.drop(columns=["location_id"]).to_numpy(dtype=float)
    if (
        abundance.shape != (9852, 19)
        or model.shape != (18, 9852)
        or not np.isfinite(values).all()
        or (values < 0).any()
        or not np.allclose(values.sum(axis=1), 1.0)
    ):
        raise ValueError("Tangram outputs failed independent shape or normalization checks")
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    manifest = registry.get(MODULE_ID)
    manifest_path = BUILTIN_ROOT / MODULE_ID / "module.json"
    observed_at = datetime.now(timezone.utc).isoformat()
    tangram_execution = {
        "backend": "Tangram",
        "backend_version": execution["versions"]["tangram"],
        "official_source_commit": UPSTREAM_COMMIT,
        "reference_cells": execution["inputs"]["reference_cells"],
        "reference_cell_types": execution["cell_types"],
        "spatial_locations": execution["inputs"]["spatial_locations"],
        "shared_genes": execution["shared_genes"],
        "epochs": execution["parameters"]["epochs"],
        "seed": execution["seed"],
        "mapping_mode": diagnostics["mapping_mode"],
        "density_prior": diagnostics["density_prior"],
        "abundance_shape": [int(abundance.shape[0]), int(abundance.shape[1] - 1)],
        "mapping_shape": [int(model.n_obs), int(model.n_vars)],
        "finite_normalized_abundance": True,
        "native_model_reloaded": True,
        "execution_report_sha256": sha256(execution_path),
        "abundance_sha256": sha256(abundance_path),
        "native_model_sha256": sha256(model_path),
    }
    source_files = [
        {
            "name": name,
            "source_url": f"https://raw.githubusercontent.com/broadinstitute/Tangram/{UPSTREAM_COMMIT}/data/{name}",
            "bytes": (inputs / name).stat().st_size,
            "sha256": digest,
        }
        for name, digest in sorted(EXPECTED_INPUTS.items())
    ]
    common = {
        "schema_version": 1,
        "passed": True,
        "observed_at": observed_at,
        "module_id": MODULE_ID,
        "module_version": manifest.version,
        "evidence_scope": module_evidence_scope(registry, [MODULE_ID]).to_dict(),
        "execution_evidence_level": "observed_scientific_workflow",
        "execution": tangram_execution,
        "implementation": {
            "manifest_sha256": sha256(manifest_path),
            "template_path": str(TEMPLATE.relative_to(ROOT)),
            "template_sha256": sha256(TEMPLATE),
            "backend_templates": {
                "Tangram": {
                    "path": str(TEMPLATE.relative_to(ROOT)),
                    "sha256": sha256(TEMPLATE),
                },
                "RCTD": {
                    "path": "biomed_workbench/modules/builtin/spatial-multimethod-inference/templates/run_rctd_spotlight.R",
                    "sha256": sha256(
                        ROOT / "biomed_workbench/modules/builtin/spatial-multimethod-inference/templates/run_rctd_spotlight.R"
                    ),
                },
            },
            "publisher_sha256": sha256(Path(__file__).resolve()),
        },
        "runtime": execution["versions"],
        "source": {
            "repository": "https://github.com/broadinstitute/Tangram",
            "commit": UPSTREAM_COMMIT,
            "files": source_files,
        },
        "quality_gates": {
            "official_inputs_checksum_bound": True,
            "current_template_executed": True,
            "native_mapping_model_reloaded": True,
            "all_spatial_locations_retained": True,
            "finite_nonnegative_abundance": True,
            "abundance_rows_sum_to_one": True,
            "output_checksums_reverified_at_publication": True,
        },
        "scientific_scope": (
            "Tangram cluster-mode mapping probabilities were generated from the upstream repository's "
            "complete test AnnData pair using an RNA-count-based spatial density prior. Mapping "
            "probabilities are not observed cell counts or a count-model deconvolution estimate."
        ),
    }
    public = {
        **common,
        "case_id": "tangram-1.0.4-official-repository-test-data-v1",
        "case_type": "official-public-data-end-to-end",
    }
    live_path = ROOT / "reports/spatial-multimethod-inference-live-verification.json"
    prior = load_json(live_path)
    executions = [item for item in prior.get("executions", []) if item.get("backend") != "Tangram"]
    executions.insert(0, tangram_execution)
    live = {
        "schema_version": 1,
        "passed": True,
        "observed_at": observed_at,
        "module_id": MODULE_ID,
        "module_version": manifest.version,
        "compatibility_row_id": "method-isolated-runtime-contract-v2",
        "registry_digest": registry.digest,
        "evidence_scope": common["evidence_scope"],
        "execution_evidence_level": "observed_scientific_workflow",
        "executions": executions,
        "implementation": common["implementation"],
        "quality_gates": {
            **prior.get("quality_gates", {}),
            "current_tangram_template_executed": "pass",
            "official_tangram_inputs_checksum_bound": "pass",
        },
        "scientific_scope": prior.get("scientific_scope"),
    }
    return live, public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    live, public = build(args.workspace)
    targets = (
        (ROOT / "reports/spatial-multimethod-inference-live-verification.json", live),
        (ROOT / "reports/public-case-tangram-official-test-data.json", public),
    )
    for path, payload in targets:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "public_case": targets[1][0].name, "spatial_locations": 9852}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
