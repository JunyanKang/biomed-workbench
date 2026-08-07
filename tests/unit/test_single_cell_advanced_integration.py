import json
import subprocess
import sys
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd

from biomed_workbench.capabilities.single_cell_integration import (
    build_orthology_ledger,
    leave_one_species_out_validation,
    require_complete_scib_metrics,
    validate_inference_input,
)


ROOT = Path(__file__).resolve().parents[2]
MOSAIC = ROOT / "biomed_workbench/modules/builtin/single-cell-mosaic-integration"
CROSS_SPECIES = (
    ROOT / "biomed_workbench/modules/builtin/single-cell-cross-species-integration"
)


def test_orthology_ledger_retains_relation_classes_and_provenance():
    records = pd.DataFrame(
        {
            "source_species": ["human", "human", "human"],
            "source_gene": ["A", "B", "C"],
            "target_species": ["mouse", "mouse", "mouse"],
            "target_gene": ["a", "b1", "c1"],
            "orthogroup_id": ["og1", "og2", "og3"],
            "relation": ["one-to-one", "one-to-many", "many-to-many"],
            "confidence": [1.0, 0.9, 0.8],
            "evidence_source": ["Ensembl Compara"] * 3,
            "release": ["release-1"] * 3,
        }
    )
    result = build_orthology_ledger(records)
    assert set(result["relation"]) == {"one-to-one", "one-to-many", "many-to-many"}
    assert set(result["evidence_source"]) == {"Ensembl Compara"}
    assert set(result["release"]) == {"release-1"}


def test_scib_completeness_and_inference_boundary_are_enforced():
    complete = {
        key: 0.5
        for key in (
            "batch_asw",
            "graph_connectivity",
            "ilisi",
            "kbet",
            "pcr_comparison",
            "ari",
            "cell_cycle_conservation",
            "clisi",
            "hvg_conservation",
            "isolated_label_asw",
            "isolated_label_f1",
            "label_asw",
            "nmi",
            "trajectory_conservation",
        )
    }
    require_complete_scib_metrics(complete)
    validate_inference_input(
        expression_semantics="raw_counts",
        sample_key="sample_id",
        donor_key="donor_id",
        species_key="species",
    )
    try:
        validate_inference_input(
            expression_semantics="integrated_expression",
            sample_key="sample_id",
            donor_key=None,
            species_key="species",
        )
    except ValueError as error:
        assert "forbidden" in str(error)
    else:
        raise AssertionError("integrated expression must be rejected for inference")


def test_leave_one_species_out_lists_unsupported_states():
    rng = np.random.default_rng(4)
    embedding = rng.normal(size=(24, 4))
    species = np.array(["human"] * 12 + ["mouse"] * 12)
    labels = np.array(
        ["shared-a"] * 6
        + ["shared-b"] * 6
        + ["shared-a"] * 4
        + ["shared-b"] * 4
        + ["mouse-only"] * 4
    )
    result = leave_one_species_out_validation(
        embedding, species=species, labels=labels, n_neighbors=3
    )
    mouse_fold = next(
        fold for fold in result["folds"] if fold["held_out_species"] == "mouse"
    )
    assert mouse_fold["unsupported_truth_labels"] == ["mouse-only"]


def test_mosaic_evaluator_reports_paired_anchor_and_no_winner_score(tmp_path):
    cells = [f"cell-{index}" for index in range(12)]
    latent = pd.DataFrame(
        {
            "cell_id": cells,
            "latent_1": np.linspace(-1, 1, 12),
            "latent_2": np.tile([0.0, 0.2, 0.4], 4),
        }
    )
    metadata = pd.DataFrame(
        {
            "cell_id": cells,
            "modality": ["rna", "atac"] * 6,
            "cell_type": ["a", "a", "b", "b"] * 3,
            "batch": ["one"] * 6 + ["two"] * 6,
            "pair_id": [f"pair-{index // 2}" for index in range(12)],
        }
    )
    latent_path = tmp_path / "latent.tsv"
    metadata_path = tmp_path / "metadata.tsv"
    report_path = tmp_path / "report.json"
    latent.to_csv(latent_path, sep="\t", index=False)
    metadata.to_csv(metadata_path, sep="\t", index=False)
    subprocess.run(
        [
            sys.executable,
            str(MOSAIC / "templates/evaluate_mosaic.py"),
            "--latent-tsv",
            str(latent_path),
            "--metadata-tsv",
            str(metadata_path),
            "--label-column",
            "cell_type",
            "--batch-column",
            "batch",
            "--paired-id-column",
            "pair_id",
            "--neighbors",
            "3",
            "--report",
            str(report_path),
        ],
        cwd=ROOT,
        check=True,
    )
    payload = json.loads(report_path.read_text())
    assert payload["metrics"]["paired_anchor"]["paired_anchors"] == 6
    assert payload["scientific_validation"]["no_single_winner_score"]


def test_cross_species_evaluator_runs_and_retains_unsupported_labels(tmp_path):
    rng = np.random.default_rng(9)
    species = np.array(["human"] * 20 + ["mouse"] * 20)
    labels = np.array(
        ["shared-a"] * 10
        + ["shared-b"] * 10
        + ["shared-a"] * 8
        + ["shared-b"] * 8
        + ["mouse-only"] * 4
    )
    adata = ad.AnnData(np.ones((40, 3)))
    adata.obs_names = [f"cell-{index}" for index in range(40)]
    adata.obs["species"] = species
    adata.obs["cell_type"] = labels
    adata.obs["sample"] = [f"sample-{index // 5}" for index in range(40)]
    adata.obsm["X_integrated"] = rng.normal(size=(40, 5))
    input_path = tmp_path / "cross.h5ad"
    report_path = tmp_path / "report.json"
    adata.write_h5ad(input_path)
    subprocess.run(
        [
            sys.executable,
            str(CROSS_SPECIES / "templates/evaluate_cross_species.py"),
            "--integrated-h5ad",
            str(input_path),
            "--embedding-key",
            "X_integrated",
            "--species-key",
            "species",
            "--label-key",
            "cell_type",
            "--sample-key",
            "sample",
            "--n-neighbors",
            "5",
            "--seed",
            "9",
            "--report",
            str(report_path),
        ],
        cwd=ROOT,
        check=True,
    )
    payload = json.loads(report_path.read_text())
    assert payload["unsupported_labels_by_held_out_species"]["mouse"] == ["mouse-only"]
    assert 0 <= payload["species_predictability"] <= 1
    assert "species-specific populations" in " ".join(payload["interpretation"]).lower()


def test_mosaic_and_cross_species_manifests_expose_native_methods_and_templates():
    mosaic = json.loads((MOSAIC / "module.json").read_text())
    cross = json.loads((CROSS_SPECIES / "module.json").read_text())
    mosaic_text = json.dumps(mosaic).lower()
    cross_text = json.dumps(cross).lower()
    for method in ("totalvi", "multivi", "scglue"):
        assert method in mosaic_text
    for method in ("samap", "saturn", "came", "scvi", "scanvi", "harmony", "cca", "rpca"):
        assert method in cross_text
    for manifest, directory in ((mosaic, MOSAIC), (cross, CROSS_SPECIES)):
        template_paths = {item["path"] for item in manifest["code_templates"]}
        assert template_paths
        assert all((directory / path).is_file() for path in template_paths)


def test_english_integration_guide_declares_method_scenes_and_count_inference_boundary():
    guide = (
        ROOT
        / "docs/capabilities/single-cell-integration-reference-cross-species.md"
    ).read_text()
    for method in (
        "Seurat v5 CCA",
        "FastMNN",
        "scIB",
        "sysVI",
        "scArches",
        "Symphony",
        "totalVI",
        "MultiVI",
        "GLUE",
        "SAMap",
        "SATURN",
        "CAME",
        "JSD",
    ):
        assert method in guide
    assert "one-to-one, one-to-many, or many-to-many" in guide
    assert "sample, donor, or species-level" in guide
    assert "Method-versus-method JSD" in guide


def test_chinese_integration_guide_declares_method_scenes_and_count_inference_boundary():
    guide = (
        ROOT
        / "docs/capabilities/single-cell-integration-reference-cross-species.zh-CN.md"
    ).read_text()
    for method in (
        "Seurat v5 CCA",
        "FastMNN",
        "scIB",
        "sysVI",
        "scArches",
        "Symphony",
        "totalVI",
        "MultiVI",
        "GLUE",
        "SAMap",
        "SATURN",
        "CAME",
        "JSD",
    ):
        assert method in guide
    assert "一对一/一对多/多对多" in guide
    assert "sample/donor/species" in guide
    assert "method-vs-method JSD" in guide
