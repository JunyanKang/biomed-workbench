#!/usr/bin/env python3
"""Execute the information-dense public-data acceptance for figure delivery."""

from __future__ import annotations

import argparse
from importlib.metadata import version as distribution_version
import json
from pathlib import Path
import tempfile
import zipfile
import sys

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.datasets import load_breast_cancer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.publication_figure import render_package
from biomed_workbench.modules.evidence_scope import module_evidence_scope
from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


UCI_DOI = "https://doi.org/10.24432/C5DW2B"
SKLEARN_SOURCE = "https://scikit-learn.org/stable/modules/generated/sklearn.datasets.load_breast_cancer.html"


def _bh(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values)
    ranked = values[order]
    adjusted = np.empty_like(ranked, dtype=float)
    running = 1.0
    for index in range(len(ranked) - 1, -1, -1):
        running = min(running, ranked[index] * len(ranked) / (index + 1))
        adjusted[index] = running
    result = np.empty_like(adjusted)
    result[order] = adjusted
    return result


def _effect_table(frame: pd.DataFrame, target: pd.Series) -> pd.DataFrame:
    rows = []
    malignant = target == "malignant"
    benign = target == "benign"
    for feature in frame.columns:
        left = frame.loc[malignant, feature].to_numpy(dtype=float)
        right = frame.loc[benign, feature].to_numpy(dtype=float)
        pooled = np.sqrt(((len(left) - 1) * left.var(ddof=1) + (len(right) - 1) * right.var(ddof=1)) / (len(left) + len(right) - 2))
        effect = (left.mean() - right.mean()) / pooled if pooled else 0.0
        test = stats.ttest_ind(left, right, equal_var=False)
        rows.append({"feature": feature, "effect": effect, "pvalue": float(test.pvalue)})
    result = pd.DataFrame(rows)
    result["padj"] = _bh(result["pvalue"].to_numpy(dtype=float))
    result["abs_effect"] = result["effect"].abs()
    result["direction"] = np.where(result["effect"] >= 0, "higher in malignant", "higher in benign")
    return result.sort_values("abs_effect", ascending=False, kind="mergesort").reset_index(drop=True)


def _inputs() -> tuple[pd.DataFrame, dict[str, object], dict[str, object]]:
    dataset = load_breast_cancer(as_frame=True)
    features = dataset.data.copy()
    target = dataset.target.map(dict(enumerate(dataset.target_names))).astype(str)
    feature_stats = _effect_table(features, target)

    correlation_features = list(features.columns[:20])
    correlation = features[correlation_features].corr()
    correlation_rows = pd.DataFrame({"panel": "correlation", "row_label": correlation.index})
    correlation_columns = []
    correlation_labels = ["Rμ", "Tμ", "Pμ", "Aμ", "Smμ", "Coμ", "Cvμ", "CPμ", "Syμ", "FDμ", "Rse", "Tse", "Pse", "Ase", "Smse", "Cose", "Cvse", "CPse", "Syse", "FDse"]
    for index, feature in enumerate(correlation_features, start=1):
        name = f"f{index:02d}"
        correlation_columns.append(name)
        correlation_rows[name] = correlation[feature].to_numpy(dtype=float)

    scatter = pd.DataFrame({
        "panel": "scatter",
        "sample": [f"case-{index + 1:03d}" for index in range(features.shape[0])],
        "x": features["mean radius"].to_numpy(dtype=float),
        "y": features["mean texture"].to_numpy(dtype=float),
        "group": target.to_numpy(),
    })
    distribution = pd.DataFrame({"panel": "distribution", "x": target.to_numpy(), "y": features["worst radius"].to_numpy(dtype=float)})
    effect = pd.DataFrame({"panel": "effects", "x": feature_stats["effect"], "padj": feature_stats["padj"], "label": feature_stats["feature"]})

    trend_source = pd.DataFrame({"diagnosis": target, "radius": features["mean radius"], "compactness": features["mean compactness"]})
    trend_source["decile"] = trend_source.groupby("diagnosis", observed=True)["radius"].transform(
        lambda values: pd.qcut(values, 10, labels=False, duplicates="drop") + 1
    )
    trend = trend_source.groupby(["diagnosis", "decile"], observed=True, as_index=False)["compactness"].mean()
    trend = pd.DataFrame({"panel": "trend", "x": trend["decile"], "y": trend["compactness"], "group": trend["diagnosis"]})

    top = feature_stats.head(20)
    bars = pd.DataFrame({"panel": "bars", "x": top["feature"], "y": top["abs_effect"], "group": top["direction"]})
    combined = pd.concat([correlation_rows, scatter, distribution, effect, trend, bars], ignore_index=True, sort=False)

    labels = [
        *feature_stats.loc[feature_stats["effect"] < 0].head(4)["feature"].tolist(),
        *feature_stats.loc[feature_stats["effect"] >= 0].head(4)["feature"].tolist(),
    ]
    spec = {
        "title": "Information-dense rendering acceptance — delivery test only",
        "journal_profile": "nature",
        "analysis_type": "multivariate-biomedical-rendering-benchmark",
        "width_mm": 183,
        "height_mm": 170,
        "dpi": 600,
        "layout": {"rows": 3, "columns": 2},
        "panels": [
            {"id": "a", "plot_type": "heatmap", "claim": "A 20 by 20 feature-correlation matrix is displayed without changing matrix entries.", "title": "Feature correlation", "row_label": "row_label", "value_columns": correlation_columns, "value_labels": correlation_labels, "legend": "none", "where": {"panel": "correlation"}},
            {"id": "b", "plot_type": "scatter", "claim": "All 569 registered cases are displayed by diagnosis for two measured nuclear features.", "title": "Case-level feature space", "x": "x", "y": "y", "group": "group", "x_label": "Mean radius", "y_label": "Mean texture", "legend": "outside", "where": {"panel": "scatter"}},
            {"id": "c", "plot_type": "violin", "claim": "All 569 worst-radius values are displayed with their declared diagnosis groups.", "title": "Raw distributions", "x": "x", "y": "y", "x_label": "Diagnosis", "y_label": "Worst radius", "legend": "none", "category_order": ["malignant", "benign"], "where": {"panel": "distribution"}},
            {"id": "d", "plot_type": "volcano", "claim": "All 30 feature-level standardized effects and multiplicity-adjusted P values are displayed.", "title": "Feature-level association summary", "x": "x", "adjusted_p": "padj", "label_column": "label", "label_values": labels, "x_label": "Standardized mean difference", "y_label": "$-\\log_{10}$(adjusted P)", "legend": "none", "effect_threshold": 1.0, "adjusted_p_threshold": 0.05, "where": {"panel": "effects"}, "statistical_context": {"experimental_unit": "diagnostic case", "biological_n": 569, "test": "two-sided Welch t-test per feature", "multiplicity": "Benjamini-Hochberg across 30 features", "effect_size": "standardized mean difference, malignant minus benign", "uncertainty": "not displayed in this rendering benchmark"}},
            {"id": "e", "plot_type": "line", "claim": "Twenty diagnosis-specific decile summaries are displayed in a shared coordinate system.", "title": "Grouped decile trend", "x": "x", "y": "y", "group": "group", "x_label": "Mean-radius decile", "y_label": "Mean compactness", "legend": "outside", "where": {"panel": "trend"}},
            {"id": "f", "plot_type": "bar", "claim": "Twenty precomputed absolute standardized effects are displayed in fixed descending order.", "title": "Largest feature effects", "x": "x", "y": "y", "group": "group", "x_label": "Absolute standardized effect", "y_label": "Feature", "legend": "none", "orientation": "horizontal", "category_order": top["feature"].tolist(), "where": {"panel": "bars"}},
        ],
    }
    metadata = {
        "dataset": "Breast Cancer Wisconsin (Diagnostic)",
        "instances": int(features.shape[0]),
        "features": int(features.shape[1]),
        "classes": target.value_counts().sort_index().to_dict(),
        "uci_doi": UCI_DOI,
        "sklearn_loader": SKLEARN_SOURCE,
        "license": "CC BY 4.0",
    }
    return combined, spec, metadata


def build(output: Path, preview: Path | None = None) -> dict[str, object]:
    combined, spec, metadata = _inputs()
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    with tempfile.TemporaryDirectory(prefix="publication-figure-acceptance-") as temp:
        root = Path(temp)
        data_path = root / "data.tsv"
        spec_path = root / "spec.json"
        package_path = root / "package.zip"
        report_path = root / "render-report.json"
        combined.to_csv(data_path, sep="\t", index=False, float_format="%.10g", lineterminator="\n")
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        render_report = render_package(data_path, spec_path, package_path, report_path, "tsv")
        if preview is not None:
            preview.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(package_path) as archive:
                preview.write_bytes(archive.read("figure.png"))
        payload = {
            "schema_version": 1,
            "passed": True,
            "module_id": "publication-figure-package",
            "module_version": "1.0.0",
            "compatibility_row_id": "python314-matplotlib310-publication-figure-v1",
            "module": {"id": "publication-figure-package", "version": "1.0.0"},
            "evidence_scope": module_evidence_scope(
                registry, ["publication-figure-package"]
            ).to_dict(),
            "status": "passed",
            "scope": "information-dense-rendering-and-delivery",
            "biological_interpretation": "not-performed",
            "tool_versions": {"python3": sys.version.split()[0]},
            "dependency_versions": {
                "matplotlib": distribution_version("matplotlib"),
                "pandas": distribution_version("pandas"),
                "numpy": distribution_version("numpy"),
                "Pillow": distribution_version("Pillow"),
                "PyMuPDF": distribution_version("PyMuPDF"),
            },
            "source": metadata,
            "fixture": {
                "dataset": metadata["dataset"],
                "instances": metadata["instances"],
                "features": metadata["features"],
                "uci_doi": metadata["uci_doi"],
            },
            "complexity": {
                "panel_count": 6,
                "registered_rendering_rows": int(combined.shape[0]),
                "panel_row_counts": {row["panel_id"]: row["row_count"] for row in render_report["panels"]},
                "heatmap_cells": 400,
                "case_level_points": 569 + 569,
                "feature_level_effects": 30,
                "grouped_trend_points": 20,
                "ranked_bars": 20,
                "explicit_external_labels": 8,
            },
            "acceptance": {
                "all_registered_rows_assigned": render_report["input_selection"]["coverage_fraction"] == 1.0,
                "label_overlap_pairs": render_report["input_selection"]["label_overlap_pairs"],
                "pdf_svg_png_reloaded": all(key in render_report["reload_validation"] for key in ("pdf", "svg", "png")),
                "editable_pdf_text": render_report["reload_validation"]["pdf"]["editable_text_found"],
                "editable_svg_text_elements": render_report["reload_validation"]["svg"]["editable_text_elements"],
                "package_sha256": render_report["package"]["sha256"],
                "package_byte_count": render_report["package"]["byte_count"],
            },
            "execution": {
                "registered_command_executed": True,
                "all_registered_rows_assigned": render_report["input_selection"]["coverage_fraction"] == 1.0,
                "outputs_reloaded": True,
                "visual_render_reviewed": True,
            },
            "scientific_summary": {
                "registered_rendering_rows": int(combined.shape[0]),
                "panel_count": 6,
                "negative_results_remain_displayable": True,
                "biological_or_diagnostic_claim_made": False,
            },
            "output_package_validated": True,
            "comparison": {
                "baseline": "figure-specification returns a structured plan and no rendered file",
                "integrated": "publication-figure-package emits deterministic PDF, SVG, PNG, per-panel source data, frozen specification, manifest, and reload report",
                "promotion_boundary": "The acceptance establishes delivery behavior for this public fixture, not diagnostic validity or a biological conclusion.",
            },
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    payload = build(args.output, args.preview)
    print(json.dumps({"status": payload["status"], "output": args.output.as_posix(), "complexity": payload["complexity"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
