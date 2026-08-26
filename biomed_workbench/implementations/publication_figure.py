"""Render a source-data-bound, publication-size scientific figure package.

The implementation is deliberately source neutral.  It consumes an explicit
column mapping and never edits a plotting template, guesses scientific roles,
filters rows silently, performs undeclared statistics, or substitutes example
pixels for a real rendering.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import textwrap
import zipfile
from xml.etree import ElementTree

import fitz
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.text import Text
import numpy as np
import pandas as pd
from PIL import Image


FROZEN_STYLE_VERSION = "1.2.0"
FROZEN_COLORBLIND_SAFE = {
    "blue": "#0072B2", "orange": "#E69F00", "green": "#009E73", "vermillion": "#D55E00",
    "sky": "#56B4E9", "purple": "#CC79A7", "yellow": "#F0E442", "black": "#000000",
    "grey": "#7A7A7A", "light_grey": "#D9D9D9",
}
FROZEN_DIVERGING = {"negative": "#3B4CC0", "midpoint": "#F7F7F7", "positive": "#B40426"}
FROZEN_TYPOGRAPHY = {
    "font_family": ["Arial", "Helvetica", "Noto Sans CJK SC", "sans-serif"],
    "axis_title": 7.0, "axis_tick": 6.0, "legend_title": 6.0, "legend_text": 6.0,
}
FROZEN_STROKES = {"axis": 0.5, "data": 0.5}

try:
    from biomed_workbench.visualization import COLORBLIND_SAFE, DIVERGING, STYLE_VERSION, scientific_figure_standard
except ModuleNotFoundError:
    COLORBLIND_SAFE = FROZEN_COLORBLIND_SAFE
    DIVERGING = FROZEN_DIVERGING
    STYLE_VERSION = FROZEN_STYLE_VERSION

    def scientific_figure_standard(analysis_type: str | None = None, journal_profile: str = "nature") -> dict[str, object]:
        del analysis_type
        status = {
            "nature": "official-current-guide",
            "screen": "workbench-accessibility-profile",
            "cell": "target-journal-guide-required",
            "science": "target-journal-guide-required",
        }.get(journal_profile)
        if status is None:
            raise ValueError(f"unsupported journal_profile: {journal_profile}")
        typography = dict(FROZEN_TYPOGRAPHY)
        if journal_profile == "screen":
            typography.update({"axis_title": 10.0, "axis_tick": 9.0, "legend_title": 9.0, "legend_text": 9.0})
        return {
            "style": {
                "version": FROZEN_STYLE_VERSION,
                "typography_pt": typography,
                "strokes_pt": dict(FROZEN_STROKES),
                "journal": {"status": status, "ready_for_submission_export": status != "target-journal-guide-required"},
            }
        }


MODULE_ID = "publication-figure-package"
MODULE_VERSION = "1.0.0"
SUPPORTED_PLOTS = frozenset({"scatter", "line", "bar", "box", "violin", "heatmap", "volcano"})
PANEL_FIELDS = frozenset({
    "id", "plot_type", "claim", "title", "x", "y", "group", "x_label", "y_label",
    "legend", "error", "row_label", "value_columns", "adjusted_p", "label_column",
    "label_values", "effect_threshold", "adjusted_p_threshold", "statistical_context",
    "x_limits", "y_limits", "reference_lines", "category_order", "group_order", "where", "orientation", "value_labels",
    "upstream_result_ids", "allowed_conclusion", "story_role", "source_table", "source_table_sha256", "vector_required",
})
STATISTICAL_FIELDS = frozenset({"experimental_unit", "biological_n", "test", "multiplicity", "effect_size", "uncertainty"})
PALETTE = tuple(COLORBLIND_SAFE[key] for key in ("blue", "orange", "green", "purple", "vermillion", "sky", "yellow", "black"))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _safe_text(value: object, field: str, *, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(f"{field} must be meaningful text")
    return value.strip()


def _read_spec(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("figure specification is not readable JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("figure specification must be an object")
    allowed = {
        "contract_version", "figure_id", "delivery_class", "story_position", "caption", "reference_dois",
        "renderer", "source_table_sha256", "project_lock_digest", "result_status",
        "title", "journal_profile", "analysis_type", "width_mm", "height_mm", "dpi", "layout", "panels",
    }
    if set(value) - allowed:
        raise ValueError(f"unsupported figure specification fields: {', '.join(sorted(set(value) - allowed))}")
    _safe_text(value.get("title"), "title")
    if value.get("contract_version") != "1.0.0":
        raise ValueError("figure contract_version must be 1.0.0")
    _safe_text(value.get("figure_id"), "figure_id")
    _safe_text(value.get("story_position"), "story_position", minimum=12)
    _safe_text(value.get("caption"), "caption", minimum=24)
    delivery_class = value.get("delivery_class")
    if delivery_class not in {"controlled-acceptance", "project-formal"}:
        raise ValueError("delivery_class must be controlled-acceptance or project-formal")
    renderer_contract = value.get("renderer")
    if renderer_contract != {"id": MODULE_ID, "version": MODULE_VERSION}:
        raise ValueError("figure renderer identity differs from the registered renderer")
    source_digest = value.get("source_table_sha256")
    if not isinstance(source_digest, str) or len(source_digest) != 64 or set(source_digest) - set("0123456789abcdef"):
        raise ValueError("source_table_sha256 must be lowercase SHA-256")
    dois = value.get("reference_dois")
    if (
        not isinstance(dois, list)
        or not dois
        or len(set(dois)) != len(dois)
        or any(not isinstance(item, str) or not item.startswith("https://doi.org/") for item in dois)
    ):
        raise ValueError("reference_dois must contain unique DOI URLs")
    if delivery_class == "project-formal":
        lock_digest = value.get("project_lock_digest")
        if not isinstance(lock_digest, str) or len(lock_digest) != 64 or set(lock_digest) - set("0123456789abcdef"):
            raise ValueError("project-formal figures require a project-lock digest")
        if value.get("result_status") != "FORMAL":
            raise ValueError("project-formal figures require FORMAL result status")
    elif value.get("result_status") not in {"CANDIDATE", "SENSITIVITY"} or value.get("project_lock_digest") is not None:
        raise ValueError("controlled acceptance must remain non-FORMAL and cannot claim a project lock")
    profile = value.get("journal_profile")
    if profile not in {"nature", "science", "cell", "screen"}:
        raise ValueError("journal_profile is unsupported")
    standard = scientific_figure_standard(None, str(profile))
    if not standard["style"]["journal"]["ready_for_submission_export"]:
        raise ValueError(f"{profile} export requires a current target-journal guide profile")
    width = value.get("width_mm")
    height = value.get("height_mm")
    dpi = value.get("dpi")
    if not isinstance(width, (int, float)) or not 50 <= float(width) <= 183:
        raise ValueError("width_mm must be between 50 and 183")
    if not isinstance(height, (int, float)) or not 40 <= float(height) <= 170:
        raise ValueError("height_mm must be between 40 and 170")
    if not isinstance(dpi, int) or isinstance(dpi, bool) or not 300 <= dpi <= 1200:
        raise ValueError("dpi must be an integer between 300 and 1200")
    layout = value.get("layout")
    if not isinstance(layout, dict) or set(layout) != {"rows", "columns"}:
        raise ValueError("layout must contain only rows and columns")
    rows, columns = layout["rows"], layout["columns"]
    if not all(isinstance(item, int) and not isinstance(item, bool) and 1 <= item <= 4 for item in (rows, columns)):
        raise ValueError("layout rows and columns must be integers between 1 and 4")
    panels = value.get("panels")
    if not isinstance(panels, list) or not panels or len(panels) != rows * columns:
        raise ValueError("every declared layout cell must contain exactly one panel")
    identifiers: set[str] = set()
    for index, panel in enumerate(panels):
        if not isinstance(panel, dict) or set(panel) - PANEL_FIELDS:
            extra = sorted(set(panel) - PANEL_FIELDS) if isinstance(panel, dict) else []
            raise ValueError(f"panel {index + 1} has unsupported fields: {', '.join(extra)}")
        identifier = _safe_text(panel.get("id"), f"panel {index + 1} id")
        if identifier in identifiers or not identifier.replace("-", "").replace("_", "").isalnum():
            raise ValueError("panel identifiers must be unique safe labels")
        identifiers.add(identifier)
        if panel.get("plot_type") not in SUPPORTED_PLOTS:
            raise ValueError(f"panel {identifier} plot_type is unsupported")
        _safe_text(panel.get("claim"), f"panel {identifier} claim", minimum=12)
        _safe_text(panel.get("allowed_conclusion"), f"panel {identifier} allowed_conclusion", minimum=12)
        _safe_text(panel.get("story_role"), f"panel {identifier} story_role", minimum=8)
        _safe_text(panel.get("source_table"), f"panel {identifier} source_table")
        if panel.get("source_table_sha256") != source_digest:
            raise ValueError(f"panel {identifier} source table digest differs from the figure contract")
        upstream_ids = panel.get("upstream_result_ids")
        if (
            not isinstance(upstream_ids, list)
            or not upstream_ids
            or len(set(upstream_ids)) != len(upstream_ids)
            or any(not isinstance(item, str) or not item.strip() for item in upstream_ids)
        ):
            raise ValueError(f"panel {identifier} must bind one or more upstream result identities")
        if panel.get("vector_required") is not True:
            raise ValueError(f"panel {identifier} must require vector delivery")
        if panel.get("legend", "outside") not in {"outside", "none"}:
            raise ValueError(f"panel {identifier} legend must be outside or none")
        if panel.get("orientation", "vertical") not in {"vertical", "horizontal"}:
            raise ValueError(f"panel {identifier} orientation must be vertical or horizontal")
        where = panel.get("where")
        if where is not None and (not isinstance(where, dict) or not where or any(not isinstance(key, str) or not key.strip() for key in where)):
            raise ValueError(f"panel {identifier} where must be a nonempty equality mapping")
        labels = panel.get("label_values")
        if labels is not None and (not isinstance(labels, list) or len(labels) > 12 or len(set(map(str, labels))) != len(labels)):
            raise ValueError(f"panel {identifier} label_values must contain at most 12 unique labels")
        value_labels = panel.get("value_labels")
        if value_labels is not None and (
            panel.get("plot_type") != "heatmap"
            or not isinstance(value_labels, list)
            or len(value_labels) != len(panel.get("value_columns") or [])
            or any(not isinstance(item, str) or not item.strip() for item in value_labels)
        ):
            raise ValueError(f"panel {identifier} value_labels must match the heatmap value columns")
        context = panel.get("statistical_context")
        if not isinstance(context, dict) or set(context) != STATISTICAL_FIELDS:
            raise ValueError(f"panel {identifier} statistical_context must declare all six reporting fields")
        for field in STATISTICAL_FIELDS:
            if field == "biological_n":
                if not isinstance(context[field], int) or context[field] < 1:
                    raise ValueError(f"panel {identifier} biological_n must be positive")
            else:
                _safe_text(context[field], f"panel {identifier} statistical_context.{field}")
    return value


def _read_data(path: Path, data_format: str) -> pd.DataFrame:
    if data_format not in {"csv", "tsv"}:
        raise ValueError("data_format must be csv or tsv")
    frame = pd.read_csv(path, sep="," if data_format == "csv" else "\t")
    if frame.empty or frame.shape[0] > 1_000_000 or frame.shape[1] > 500:
        raise ValueError("figure data must contain 1 to 1,000,000 rows and at most 500 columns")
    if frame.columns.duplicated().any() or any(not str(column).strip() for column in frame.columns):
        raise ValueError("figure data columns must be unique and nonempty")
    return frame


def _required_columns(panel: dict[str, object]) -> list[str]:
    plot_type = str(panel["plot_type"])
    columns: list[object] = []
    if plot_type in {"scatter", "line", "bar", "box", "violin"}:
        columns.extend((panel.get("x"), panel.get("y")))
    elif plot_type == "heatmap":
        columns.append(panel.get("row_label"))
        columns.extend(panel.get("value_columns") or [])
    elif plot_type == "volcano":
        columns.extend((panel.get("x"), panel.get("adjusted_p")))
        if panel.get("label_column") is not None:
            columns.append(panel.get("label_column"))
    for optional in ("group", "error"):
        if panel.get(optional) is not None:
            columns.append(panel[optional])
    columns.extend((panel.get("where") or {}).keys())
    normalized = [str(column) for column in columns if isinstance(column, str) and column.strip()]
    if len(normalized) != len(columns) or len(set(normalized)) != len(normalized):
        raise ValueError(f"panel {panel['id']} has missing or duplicate column mappings")
    return normalized


def _panel_data(frame: pd.DataFrame, panel: dict[str, object]) -> pd.DataFrame:
    columns = _required_columns(panel)
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"panel {panel['id']} references missing columns: {', '.join(missing)}")
    selected = frame
    for column, expected in (panel.get("where") or {}).items():
        if column not in selected.columns:
            raise ValueError(f"panel {panel['id']} where references missing column {column}")
        selected = selected.loc[selected[column] == expected]
    if selected.empty:
        raise ValueError(f"panel {panel['id']} where selects no rows")
    data = selected.loc[:, columns].copy()
    if data.isna().any().any():
        raise ValueError(f"panel {panel['id']} contains missing plotted values; declare and resolve them upstream")
    numeric_names: list[str] = []
    plot_type = panel["plot_type"]
    if plot_type in {"scatter", "line", "bar", "box", "violin"}:
        numeric_names.append(str(panel["y"]))
        if plot_type in {"scatter", "line"}:
            numeric_names.append(str(panel["x"]))
        if panel.get("error"):
            numeric_names.append(str(panel["error"]))
    elif plot_type == "heatmap":
        numeric_names.extend(str(item) for item in panel["value_columns"])
    elif plot_type == "volcano":
        numeric_names.extend((str(panel["x"]), str(panel["adjusted_p"])))
    for name in numeric_names:
        converted = pd.to_numeric(data[name], errors="coerce")
        if converted.isna().any() or not np.isfinite(converted.to_numpy(dtype=float)).all():
            raise ValueError(f"panel {panel['id']} column {name} must contain finite numeric values")
        data[name] = converted
    if plot_type == "volcano":
        pvalues = data[str(panel["adjusted_p"])].to_numpy(dtype=float)
        if np.any((pvalues <= 0) | (pvalues > 1)):
            raise ValueError(f"panel {panel['id']} adjusted p values must be in (0, 1]")
    data.insert(0, "source_row", selected.index.to_numpy(dtype=int))
    return data


def _orders(data: pd.DataFrame, column: str, requested: object) -> list[object]:
    observed = list(dict.fromkeys(data[column].tolist()))
    if requested is None:
        return observed
    if not isinstance(requested, list) or len(set(map(str, requested))) != len(requested):
        raise ValueError(f"{column} order must be a list of unique values")
    if set(map(str, requested)) != set(map(str, observed)):
        raise ValueError(f"{column} order must include every observed category exactly once")
    by_text = {str(item): item for item in observed}
    return [by_text[str(item)] for item in requested]


def _color_map(frame: pd.DataFrame, panels: list[dict[str, object]]) -> dict[str, str]:
    values: list[str] = []
    for panel in panels:
        group = panel.get("group")
        if group:
            for item in _panel_data(frame, panel)[str(group)].tolist():
                text = str(item)
                if text not in values:
                    values.append(text)
    if len(values) > len(PALETTE):
        raise ValueError("the validated categorical palette supports at most eight global groups")
    return {value: PALETTE[index] for index, value in enumerate(values)}


def _finish_axes(ax: plt.Axes, panel: dict[str, object]) -> None:
    ax.set_title(str(panel.get("title") or ""), loc="left", pad=3)
    ax.set_xlabel(str(panel.get("x_label") or panel.get("x") or ""))
    ax.set_ylabel(str(panel.get("y_label") or panel.get("y") or ""))
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if panel.get("x_limits") is not None:
        ax.set_xlim(panel["x_limits"])
    if panel.get("y_limits") is not None:
        ax.set_ylim(panel["y_limits"])
    for item in panel.get("reference_lines") or []:
        if not isinstance(item, dict) or set(item) != {"axis", "value"} or item["axis"] not in {"x", "y"}:
            raise ValueError(f"panel {panel['id']} has an invalid reference line")
        (ax.axvline if item["axis"] == "x" else ax.axhline)(float(item["value"]), color="#777777", linewidth=0.5, linestyle="--", zorder=0)


def _plot_panel(ax: plt.Axes, data: pd.DataFrame, panel: dict[str, object], colors: dict[str, str]) -> None:
    plot_type = str(panel["plot_type"])
    x = str(panel.get("x") or "")
    y = str(panel.get("y") or "")
    group = str(panel.get("group") or "")
    if plot_type in {"scatter", "line"}:
        groups = [(None, data)] if not group else list(data.groupby(group, sort=False, observed=True))
        for name, subset in groups:
            color = colors.get(str(name), PALETTE[0])
            if plot_type == "scatter":
                ax.scatter(subset[x], subset[y], s=8, alpha=0.75, linewidths=0, color=color, label=None if name is None else str(name))
            else:
                subset = subset.sort_values(x, kind="mergesort")
                ax.plot(subset[x], subset[y], marker="o", markersize=2.2, linewidth=0.75, color=color, label=None if name is None else str(name))
    elif plot_type == "bar":
        order = _orders(data, x, panel.get("category_order"))
        indexed = data.set_index(x, drop=False)
        if not indexed.index.is_unique:
            raise ValueError(f"panel {panel['id']} bar input must contain one precomputed row per category")
        subset = indexed.loc[order]
        error = subset[str(panel["error"])] if panel.get("error") else None
        bar_colors = [colors.get(str(item), PALETTE[0]) if group else PALETTE[0] for item in (subset[group] if group else order)]
        if panel.get("orientation", "vertical") == "horizontal":
            ax.barh(range(len(order)), subset[y], xerr=error, color=bar_colors, edgecolor="#222222", linewidth=0.5, capsize=2)
            ax.set_yticks(range(len(order)), [str(item) for item in order])
            ax.invert_yaxis()
        else:
            ax.bar(range(len(order)), subset[y], yerr=error, color=bar_colors, edgecolor="#222222", linewidth=0.5, capsize=2)
            ax.set_xticks(range(len(order)), [str(item) for item in order], rotation=60 if len(order) > 10 else 30, ha="right")
    elif plot_type in {"box", "violin"}:
        order = _orders(data, x, panel.get("category_order"))
        arrays = [data.loc[data[x] == item, y].to_numpy(dtype=float) for item in order]
        positions = np.arange(1, len(order) + 1)
        if plot_type == "box":
            result = ax.boxplot(arrays, positions=positions, widths=0.55, patch_artist=True, showfliers=False,
                                medianprops={"color": "#111111", "linewidth": 0.7},
                                whiskerprops={"linewidth": 0.5}, capprops={"linewidth": 0.5}, boxprops={"linewidth": 0.5})
            for patch, color in zip(result["boxes"], PALETTE):
                patch.set_facecolor(color)
                patch.set_alpha(0.45)
        else:
            result = ax.violinplot(arrays, positions=positions, widths=0.7, showmeans=False, showmedians=True, showextrema=True)
            for body, color in zip(result["bodies"], PALETTE):
                body.set_facecolor(color)
                body.set_edgecolor("#222222")
                body.set_linewidth(0.5)
                body.set_alpha(0.45)
        for position, values in zip(positions, arrays):
            offsets = np.linspace(-0.14, 0.14, len(values)) if len(values) > 1 else np.array([0.0])
            ax.scatter(position + offsets, values, s=6, color="#333333", alpha=0.65, linewidths=0, zorder=3)
        ax.set_xticks(positions, [str(item) for item in order], rotation=30, ha="right")
    elif plot_type == "heatmap":
        values = data[[str(item) for item in panel["value_columns"]]].to_numpy(dtype=float)
        limit = float(np.max(np.abs(values))) or 1.0
        cmap = LinearSegmentedColormap.from_list("workbench_diverging", [DIVERGING["negative"], DIVERGING["midpoint"], DIVERGING["positive"]])
        image = ax.imshow(values, aspect="auto", cmap=cmap, vmin=-limit, vmax=limit, interpolation="nearest")
        ax.set_xticks(range(values.shape[1]), [str(item) for item in (panel.get("value_labels") or panel["value_columns"])], rotation=45, ha="right")
        ax.set_yticks(range(values.shape[0]), data[str(panel["row_label"])] )
        ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
        ax.set_xlabel("")
        ax.set_ylabel("")
    elif plot_type == "volcano":
        effect = data[x].to_numpy(dtype=float)
        pvalues = data[str(panel["adjusted_p"])].to_numpy(dtype=float)
        yvalues = -np.log10(pvalues)
        effect_threshold = float(panel.get("effect_threshold", 1.0))
        p_threshold = float(panel.get("adjusted_p_threshold", 0.05))
        significant = (np.abs(effect) >= effect_threshold) & (pvalues <= p_threshold)
        point_colors = np.where(significant & (effect > 0), COLORBLIND_SAFE["vermillion"], np.where(significant, COLORBLIND_SAFE["blue"], COLORBLIND_SAFE["light_grey"]))
        ax.scatter(effect, yvalues, s=7, c=point_colors, alpha=0.75, linewidths=0)
        ax.axvline(-effect_threshold, color="#777777", linewidth=0.5, linestyle="--")
        ax.axvline(effect_threshold, color="#777777", linewidth=0.5, linestyle="--")
        ax.axhline(-math.log10(p_threshold), color="#777777", linewidth=0.5, linestyle="--")
        label_values = panel.get("label_values") or []
        if label_values:
            label_column = str(panel.get("label_column") or "")
            if not label_column:
                raise ValueError(f"panel {panel['id']} label_values require label_column")
            wanted = {str(item) for item in label_values}
            matches = data[data[label_column].astype(str).isin(wanted)]
            if set(matches[label_column].astype(str)) != wanted or len(matches) != len(wanted):
                raise ValueError(f"panel {panel['id']} label_values must each match one row")
            left = matches.loc[matches[x] < 0]
            right = matches.loc[matches[x] >= 0]
            for side, subset, text_x, align in (("left", left, 0.02, "left"), ("right", right, 0.98, "right")):
                del side
                ordered = subset.sort_values(str(panel["adjusted_p"]), kind="mergesort")
                slots = np.linspace(0.96, 0.24, max(len(ordered), 1))
                for slot, (_, row) in zip(slots, ordered.iterrows()):
                    label = "\n".join(textwrap.wrap(str(row[label_column]), width=18, break_long_words=False))
                    ax.annotate(label, (float(row[x]), -math.log10(float(row[str(panel["adjusted_p"])]))),
                                xytext=(text_x, float(slot)), textcoords=ax.transAxes, ha=align, va="top", fontsize=5,
                                color="#111111", arrowprops={"arrowstyle": "-", "linewidth": 0.4, "color": "#777777"})
        ax.set_ylabel(str(panel.get("y_label") or r"$-\log_{10}$(adjusted P)"))
    _finish_axes(ax, panel)
    if group and panel.get("legend", "outside") == "outside" and plot_type in {"scatter", "line"}:
        ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0)


def _configure_style(profile: str) -> None:
    standard = scientific_figure_standard(None, profile)["style"]
    typography = standard["typography_pt"]
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": typography["font_family"],
        "font.size": typography["axis_tick"],
        "axes.titlesize": typography["axis_title"],
        "axes.labelsize": typography["axis_title"],
        "xtick.labelsize": typography["axis_tick"],
        "ytick.labelsize": typography["axis_tick"],
        "legend.fontsize": typography["legend_text"],
        "legend.title_fontsize": typography["legend_title"],
        "axes.linewidth": standard["strokes_pt"]["axis"],
        "lines.linewidth": standard["strokes_pt"]["data"],
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "svg.hashsalt": "biomed-workbench-publication-figure-v1",
        "savefig.facecolor": "white",
    })


def _render(frame: pd.DataFrame, spec: dict[str, object], output_dir: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    _configure_style(str(spec["journal_profile"]))
    rows, columns = int(spec["layout"]["rows"]), int(spec["layout"]["columns"])
    figure, axes = plt.subplots(rows, columns, figsize=(float(spec["width_mm"]) / 25.4, float(spec["height_mm"]) / 25.4), squeeze=False, constrained_layout=True)
    figure.suptitle(str(spec["title"]), x=0.01, ha="left", fontsize=7, fontweight="bold")
    panels = list(spec["panels"])
    colors = _color_map(frame, panels)
    source_rows: list[dict[str, object]] = []
    selected_rows: list[int] = []
    for index, panel in enumerate(panels):
        ax = axes.flat[index]
        data = _panel_data(frame, panel)
        selected_rows.extend(int(item) for item in data["source_row"])
        _plot_panel(ax, data, panel, colors)
        ax.text(-0.12, 1.05, str(panel["id"]), transform=ax.transAxes, fontsize=7, fontweight="bold", va="bottom", ha="left")
        source_name = f"source-data/panel-{panel['id']}.tsv"
        data.to_csv(output_dir / source_name, sep="\t", index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        source_rows.append({
            "panel_id": panel["id"], "plot_type": panel["plot_type"], "claim": panel["claim"],
            "allowed_conclusion": panel["allowed_conclusion"], "story_role": panel["story_role"],
            "upstream_result_ids": panel["upstream_result_ids"],
            "row_count": int(data.shape[0]), "column_count": int(data.shape[1]),
            "source_data": source_name, "source_data_sha256": _sha256_file(output_dir / source_name),
            "statistical_context": panel.get("statistical_context"),
        })
    for index in range(len(panels), rows * columns):
        axes.flat[index].set_visible(False)
    figure.canvas.draw()
    label_overlap_pairs = 0
    overlap_by_panel: dict[str, int] = {}
    renderer = figure.canvas.get_renderer()
    for index in range(len(panels)):
        texts = [item for item in axes.flat[index].texts if item.get_visible() and item.get_text().strip() and item.get_text() != str(panels[index]["id"])]
        boxes = [Text.get_window_extent(item, renderer=renderer).expanded(1.01, 1.05) for item in texts]
        overlap = int(sum(bool(boxes[left].overlaps(boxes[right])) for left in range(len(boxes)) for right in range(left + 1, len(boxes))))
        overlap_by_panel[str(panels[index]["id"])] = overlap
        label_overlap_pairs += overlap
    if label_overlap_pairs:
        raise ValueError(f"rendered panel annotations contain {label_overlap_pairs} overlapping label pairs: {overlap_by_panel}")
    signatures = [
        (row["plot_type"], row["source_data_sha256"], row["allowed_conclusion"])
        for row in source_rows
    ]
    if len(set(signatures)) != len(signatures):
        raise ValueError("figure contains an exact repeated panel contract")
    pdf = output_dir / "figure.pdf"
    svg = output_dir / "figure.svg"
    png = output_dir / "figure.png"
    figure.savefig(pdf, format="pdf", metadata={"Creator": "Biomed Workbench", "CreationDate": None, "ModDate": None})
    figure.savefig(svg, format="svg", metadata={"Creator": "Biomed Workbench", "Date": None})
    figure.savefig(png, format="png", dpi=int(spec["dpi"]), metadata={"Software": "Biomed Workbench"})
    plt.close(figure)
    covered = set(selected_rows)
    if covered != set(range(frame.shape[0])):
        raise ValueError("one or more registered input rows are not assigned to any panel")
    counts = pd.Series(selected_rows).value_counts()
    return source_rows, {
        "registered_row_count": int(frame.shape[0]),
        "covered_row_count": len(covered),
        "coverage_fraction": 1.0,
        "maximum_panel_reuse": int(counts.max()),
        "label_overlap_pairs": label_overlap_pairs,
    }


def _reload_validate(output_dir: Path, spec: dict[str, object], source_rows: list[dict[str, object]]) -> dict[str, object]:
    expected_width_pt = float(spec["width_mm"]) / 25.4 * 72
    expected_height_pt = float(spec["height_mm"]) / 25.4 * 72
    pdf = fitz.open(output_dir / "figure.pdf")
    try:
        if pdf.page_count != 1:
            raise ValueError("rendered PDF must contain exactly one page")
        rect = pdf[0].rect
        text = pdf[0].get_text("text")
        fonts = pdf[0].get_fonts(full=True)
    finally:
        pdf.close()
    if abs(rect.width - expected_width_pt) > 0.75 or abs(rect.height - expected_height_pt) > 0.75:
        raise ValueError("rendered PDF dimensions differ from the final-size contract")
    required_text = [str(spec["title"]), *(str(panel["id"]) for panel in spec["panels"])]
    if any(item not in text for item in required_text):
        raise ValueError("rendered PDF is missing required editable text")
    root = ElementTree.parse(output_dir / "figure.svg").getroot()
    svg_text_count = sum(1 for node in root.iter() if node.tag.endswith("text"))
    if svg_text_count < len(required_text):
        raise ValueError("rendered SVG is missing editable text elements")
    with Image.open(output_dir / "figure.png") as image:
        expected_pixels = (round(float(spec["width_mm"]) / 25.4 * int(spec["dpi"])), round(float(spec["height_mm"]) / 25.4 * int(spec["dpi"])))
        if any(abs(actual - expected) > 1 for actual, expected in zip(image.size, expected_pixels)):
            raise ValueError("rendered PNG dimensions or dpi are inconsistent")
        png_mode, png_size = image.mode, list(image.size)
    for row in source_rows:
        source = pd.read_csv(output_dir / str(row["source_data"]), sep="\t")
        if source.shape[0] != row["row_count"] or source["source_row"].nunique() != row["row_count"]:
            raise ValueError(f"panel {row['panel_id']} source-data reload lost or duplicated rows")
    return {
        "pdf": {"page_count": 1, "width_pt": round(rect.width, 4), "height_pt": round(rect.height, 4), "editable_text_found": True, "font_records": len(fonts)},
        "svg": {"parseable": True, "editable_text_elements": svg_text_count},
        "png": {"mode": png_mode, "pixel_dimensions": png_size, "dpi": int(spec["dpi"])},
        "source_data": {"panel_count": len(source_rows), "all_panels_reloaded_without_row_loss": True},
    }


def _canonical_zip(source_dir: Path, target: Path) -> None:
    entries = [path for path in source_dir.rglob("*") if path.is_file()]
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(entries, key=lambda item: item.relative_to(source_dir).as_posix()):
            info = zipfile.ZipInfo(path.relative_to(source_dir).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def render_package(data_path: Path, spec_path: Path, package_path: Path, report_path: Path, data_format: str) -> dict[str, object]:
    spec = _read_spec(spec_path)
    if spec["source_table_sha256"] != _sha256_file(data_path):
        raise ValueError("figure source table differs from the locked source_table_sha256")
    frame = _read_data(data_path, data_format)
    package_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="biomed-publication-figure-") as temp:
        output_dir = Path(temp)
        (output_dir / "source-data").mkdir()
        (output_dir / "figure-specification.json").write_bytes(_canonical_json(spec))
        figure_contract_digest = _sha256_file(output_dir / "figure-specification.json")
        source_rows, selection_report = _render(frame, spec, output_dir)
        reload_report = _reload_validate(output_dir, spec, source_rows)
        files = []
        for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
            files.append({"path": path.relative_to(output_dir).as_posix(), "byte_count": path.stat().st_size, "sha256": _sha256_file(path)})
        manifest = {
            "schema_version": 1,
            "module": {"id": MODULE_ID, "version": MODULE_VERSION},
            "style_version": STYLE_VERSION,
            "figure_contract": {
                "digest": figure_contract_digest,
                "figure_id": spec["figure_id"],
                "delivery_class": spec["delivery_class"],
                "result_status": spec["result_status"],
                "project_lock_digest": spec["project_lock_digest"],
                "renderer": spec["renderer"],
            },
            "input": {"data_sha256": _sha256_file(data_path), "specification_sha256": _sha256_file(spec_path), "row_count": int(frame.shape[0]), "column_count": int(frame.shape[1])},
            "panels": source_rows,
            "input_selection": selection_report,
            "files": files,
        }
        (output_dir / "manifest.json").write_bytes(_canonical_json(manifest))
        _canonical_zip(output_dir, package_path)
    report = {
        "schema_version": 1,
        "module": {"id": MODULE_ID, "version": MODULE_VERSION},
        "status": "passed",
        "ready": True,
        "scope": "rendering-and-delivery-validation",
        "scientific_result_interpretation": "not-performed",
        "style_version": STYLE_VERSION,
        "figure_contract": {
            "digest": figure_contract_digest,
            "figure_id": spec["figure_id"],
            "delivery_class": spec["delivery_class"],
            "result_status": spec["result_status"],
            "project_lock_digest": spec["project_lock_digest"],
            "renderer": spec["renderer"],
            "reference_dois": spec["reference_dois"],
            "caption": spec["caption"],
            "story_position": spec["story_position"],
        },
        "journal_profile": spec["journal_profile"],
        "input": {"data_sha256": _sha256_file(data_path), "specification_sha256": _sha256_file(spec_path), "row_count": int(frame.shape[0]), "column_count": int(frame.shape[1])},
        "panels": source_rows,
        "input_selection": selection_report,
        "reload_validation": reload_report,
        "package": {"sha256": _sha256_file(package_path), "byte_count": package_path.stat().st_size},
        "runtime": {"python": platform.python_version(), "matplotlib": matplotlib.__version__, "pandas": pd.__version__, "numpy": np.__version__, "pillow": Image.__version__, "pymupdf": fitz.VersionBind},
        "quality_gates": {
            "explicit-scientific-mapping": "pass",
            "source-data-row-integrity": "pass",
            "final-size-vector-raster-reload": "pass",
            "negative-result-preservation": "not-signal-gated",
            "panel-contract-completeness": "pass",
            "renderer-and-source-lock": "pass",
        },
        "limitations": [
            "This report validates rendering, source-data binding, final dimensions, and container readability; it does not validate upstream analysis or biological interpretation.",
            "Visual review of the actual rendered package remains required for label collisions, clipping, perceptual hierarchy, and project-specific scientific adequacy.",
        ],
    }
    report_path.write_bytes(_canonical_json(report))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--data-format", required=True, choices=("csv", "tsv"))
    args = parser.parse_args(argv)
    try:
        render_package(args.data, args.spec, args.package, args.report, args.data_format)
    except Exception as exc:
        print(f"publication figure rendering failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
