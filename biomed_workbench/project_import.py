"""Read-only discovery and explicit confirmation for established research projects."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Mapping


TEXT_SUFFIXES = {".r", ".py", ".ipynb", ".sh", ".md", ".txt", ".yaml", ".yml", ".json"}
FIGURE_SUFFIXES = {".pdf", ".png", ".svg", ".tif", ".tiff", ".eps"}
DATA_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".feather", ".rds", ".h5ad", ".mtx"}
SCRIPT_SUFFIXES = {".r", ".py", ".ipynb", ".sh"}
IGNORED_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".next", "site-packages"}
AUTHORITY_NAMES = {
    "00_submission_figure_panel_registry.tsv",
    "panel_registry.tsv",
    "figure_panel_registry.tsv",
    "source_data_panel_manifest.tsv",
    "figure_contract.json",
}
_PANEL = re.compile(r"(?:fig(?:ure)?[-_ ]*\d+[-_ ]*)?(?:panel[-_ ]*)?([a-z]\d*|\d+[a-z])(?:\b|[-_])", re.I)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tokens(path: Path) -> set[str]:
    ignored = {"figure", "fig", "panel", "source", "data", "plot", "render", "final", "output"}
    return {
        token.lower()
        for token in re.split(r"[^A-Za-z0-9]+", path.stem)
        if len(token) > 1 and token.lower() not in ignored
    }


def _panel_ids(path: Path) -> tuple[str, ...]:
    return tuple(sorted({match.group(1).lower() for match in _PANEL.finditer(path.stem)}))


def _kind(path: Path) -> str | None:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix in FIGURE_SUFFIXES:
        return "figure"
    if suffix in DATA_SUFFIXES:
        return "source-data"
    if suffix in SCRIPT_SUFFIXES:
        return "renderer" if any(word in name for word in ("figure", "fig", "panel", "plot", "render")) else "analysis-script"
    if suffix in {".md", ".txt", ".docx"} and any(word in name for word in ("caption", "legend", "figure")):
        return "caption"
    return None


def _readable_mentions(path: Path, candidates: Iterable[Path]) -> set[str]:
    if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 2_000_000:
        return set()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    return {candidate.name for candidate in candidates if candidate.name in text}


def discover_existing_project(project_root: Path) -> dict[str, object]:
    """Inventory an existing directory without changing it or asserting inferred lineage."""
    root = project_root.resolve(strict=True)
    files = [
        path for path in root.rglob("*")
        if path.is_file() and not any(part in IGNORED_PARTS for part in path.relative_to(root).parts)
    ]
    typed = [(path, _kind(path)) for path in files]
    typed = [(path, kind) for path, kind in typed if kind is not None]
    inventory = []
    for path, kind in typed:
        inventory.append({
            "path": path.relative_to(root).as_posix(),
            "kind": kind,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "panel_candidates": list(_panel_ids(path)),
        })

    path_by_relative = {path.relative_to(root).as_posix(): path for path, _ in typed}
    edges: list[dict[str, object]] = []
    figures = [(path, kind) for path, kind in typed if kind == "figure"]
    others = [(path, kind) for path, kind in typed if kind != "figure"]
    for figure, _ in figures:
        figure_tokens = _tokens(figure)
        figure_panels = set(_panel_ids(figure))
        mentions = _readable_mentions(figure, (path for path, _ in others))
        for candidate, kind in others:
            candidate_tokens = _tokens(candidate)
            overlap = figure_tokens & candidate_tokens
            shared_panels = figure_panels & set(_panel_ids(candidate))
            reverse_mentions = _readable_mentions(candidate, (figure,))
            reasons: list[str] = []
            score = 0.0
            if candidate.name in mentions or figure.name in reverse_mentions:
                reasons.append("explicit filename reference")
                score += 0.65
            if shared_panels:
                reasons.append("shared panel label: " + ", ".join(sorted(shared_panels)))
                score += 0.25
            if overlap:
                reasons.append("shared filename terms: " + ", ".join(sorted(overlap)))
                score += min(0.25, 0.08 * len(overlap))
            if score < 0.25:
                continue
            figure_rel = figure.relative_to(root).as_posix()
            candidate_rel = candidate.relative_to(root).as_posix()
            edge_id = hashlib.sha256(f"{figure_rel}|{kind}|{candidate_rel}".encode()).hexdigest()[:20]
            edges.append({
                "id": f"candidate-{edge_id}",
                "figure": figure_rel,
                "relation": kind,
                "target": candidate_rel,
                "confidence": round(min(score, 0.99), 2),
                "reasons": reasons,
                "confirmed": False,
            })

    stem_groups: dict[tuple[str, str], list[str]] = {}
    for item in inventory:
        key = (str(item["kind"]), re.sub(r"[^a-z0-9]", "", Path(str(item["path"])).stem.lower()))
        stem_groups.setdefault(key, []).append(str(item["path"]))
    conflicts = [
        {"kind": kind, "normalized_name": stem, "paths": paths}
        for (kind, stem), paths in stem_groups.items() if stem and len(paths) > 1
    ]
    authorities = [
        item for item in inventory
        if Path(str(item["path"])).name.lower() in AUTHORITY_NAMES
    ]
    payload: dict[str, object] = {
        "schema_version": 1,
        "project_root": str(root),
        "read_only_scan": True,
        "inventory": sorted(inventory, key=lambda item: str(item["path"])),
        "authority_candidates": authorities,
        "candidate_relations": sorted(edges, key=lambda item: (str(item["figure"]), -float(item["confidence"]), str(item["target"]))),
        "conflicts_requiring_review": conflicts,
        "confirmation_required": True,
        "interpretation": "Candidate relations are filename- and reference-based suggestions, not established scientific lineage.",
    }
    payload["scan_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return payload


def confirm_existing_project_map(
    candidate_map: Mapping[str, object],
    decisions: Mapping[str, object],
) -> dict[str, object]:
    """Create a confirmed mapping from explicit per-edge decisions."""
    rows = candidate_map.get("candidate_relations")
    if not isinstance(rows, list) or not isinstance(candidate_map.get("scan_digest"), str):
        raise ValueError("candidate map is incomplete")
    supplied = decisions.get("relations")
    if not isinstance(supplied, Mapping):
        raise ValueError("decisions.relations must map every candidate relation id to true or false")
    ids = {str(row.get("id")) for row in rows if isinstance(row, Mapping)}
    if set(supplied) != ids or any(not isinstance(value, bool) for value in supplied.values()):
        raise ValueError("every candidate relation requires one explicit boolean decision")
    confirmed = [dict(row, confirmed=True) for row in rows if supplied[str(row["id"])] is True]
    payload: dict[str, object] = {
        "schema_version": 1,
        "project_root": candidate_map.get("project_root"),
        "source_scan_digest": candidate_map["scan_digest"],
        "confirmed_relations": confirmed,
        "rejected_candidate_ids": sorted(key for key, value in supplied.items() if value is False),
        "researcher_confirmation": str(decisions.get("researcher_confirmation", "")).strip(),
        "eligible_to_seed_project_lock": bool(confirmed) and not candidate_map.get("conflicts_requiring_review"),
    }
    if len(payload["researcher_confirmation"]) < 3:
        raise ValueError("researcher confirmation identity or note is required")
    payload["confirmation_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    return payload
