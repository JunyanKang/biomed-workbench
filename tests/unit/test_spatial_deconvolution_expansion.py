import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from biomed_workbench.capabilities.single_cell_integration import projection_jsd


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "biomed_workbench/modules/builtin/spatial-multimethod-inference"
CORE_METHODS = {
    "cell2location",
    "rctd",
    "stereoscope",
    "spotlight",
    "card",
    "spatialdwls",
    "destvi",
    "tangram",
}


def test_projection_jsd_is_bounded_and_identity_is_zero():
    matrix = pd.DataFrame(
        [[0.7, 0.3], [0.2, 0.8]],
        index=["spot-1", "spot-2"],
        columns=["type-a", "type-b"],
    )
    identical = projection_jsd(matrix, matrix.copy())
    assert identical["mean_spot_jsd"] == 0
    shifted = projection_jsd(matrix, matrix.iloc[:, ::-1].set_axis(matrix.columns, axis=1))
    assert 0 < shifted["mean_spot_jsd"] <= 1
    assert shifted["range"] == [0.0, 1.0]


def test_spatial_module_exposes_core_methods_and_resolution_gate():
    manifest = json.loads((MODULE / "module.json").read_text())
    text = json.dumps(manifest).lower()
    assert CORE_METHODS <= {method for method in CORE_METHODS if method in text}
    gate_ids = {gate["id"] for gate in manifest["quality_gates"]}
    assert "deconvolution-reference-contract" in gate_ids
    assert "projection-truth-and-resolution-contract" in gate_ids
    paths = {item["path"] for item in manifest["code_templates"]}
    assert "templates/run_scvi_spatial_deconvolution.py" in paths
    assert "templates/run_card_spatialdwls.R" in paths
    assert "templates/evaluate_deconvolution.py" in paths
    assert all((MODULE / path).is_file() for path in paths)


def test_deconvolution_evaluator_distinguishes_truth_from_concordance(tmp_path):
    method_a = pd.DataFrame(
        {
            "location_id": ["s1", "s2", "s3"],
            "type-a": [0.8, 0.2, 0.5],
            "type-b": [0.2, 0.8, 0.5],
        }
    )
    method_b = pd.DataFrame(
        {
            "location_id": ["s1", "s2", "s3"],
            "type-a": [0.7, 0.3, 0.4],
            "type-b": [0.3, 0.7, 0.6],
        }
    )
    a_path = tmp_path / "a.tsv"
    b_path = tmp_path / "b.tsv"
    report = tmp_path / "report.json"
    method_a.to_csv(a_path, sep="\t", index=False)
    method_b.to_csv(b_path, sep="\t", index=False)
    subprocess.run(
        [
            sys.executable,
            str(MODULE / "templates/evaluate_deconvolution.py"),
            "--method",
            f"rctd={a_path}",
            "--method",
            f"cell2location={b_path}",
            "--report",
            str(report),
        ],
        cwd=ROOT,
        check=True,
    )
    payload = json.loads(report.read_text())
    comparison = payload["pairwise_concordance"]["rctd__vs__cell2location"]
    assert comparison["interpretation"] == "method concordance, not accuracy"
    assert payload["truth_based_accuracy"] == {}
    assert not payload["scientific_validation"]["accuracy_available"]


def test_method_guide_names_output_semantics_and_single_cell_platform_boundary():
    guide = (
        ROOT / "docs/capabilities/spatial-deconvolution-projection-methods.md"
    ).read_text()
    for method in (
        "RCTD",
        "cell2location",
        "Stereoscope",
        "SPOTlight",
        "CARD",
        "SpatialDWLS",
        "DestVI",
        "Tangram",
    ):
        assert method in guide
    assert "映射概率不是细胞比例" in guide
    assert "不应默认再做 spot 解卷积" in guide
    assert "JSD" in guide and "一致性" in guide
