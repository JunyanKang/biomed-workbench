"""Rendered visual-regression checks for scientific figure meaning and layout."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import fitz
import numpy as np
from PIL import Image


def _page_image(path: Path) -> tuple[Image.Image, dict[str, Any]]:
    if path.suffix.lower() == ".pdf":
        document = fitz.open(path)
        if len(document) != 1:
            raise ValueError("scientific panel comparison requires one-page PDFs")
        page = document[0]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        blocks = [block for block in page.get_text("blocks") if str(block[4]).strip()]
        metadata = {
            "vector_text": [str(block[4]).strip() for block in blocks],
            "text_boxes": [[round(float(value), 2) for value in block[:4]] for block in blocks],
            "page_points": [page.rect.width, page.rect.height],
        }
        document.close()
        return image, metadata
    image = Image.open(path).convert("RGB")
    return image, {"vector_text": [], "text_boxes": [], "page_points": None}


def _content_box(array: np.ndarray) -> list[float]:
    mask = np.min(array, axis=2) < 248
    y, x = np.where(mask)
    if not len(x):
        return [0.0, 0.0, 0.0, 0.0]
    h, w = mask.shape
    return [float(x.min() / w), float(y.min() / h), float((x.max() + 1) / w), float((y.max() + 1) / h)]


def _regional_density(array: np.ndarray) -> list[float]:
    mask = np.min(array, axis=2) < 248
    rows = np.array_split(mask, 3, axis=0)
    return [round(float(cell.mean()), 4) for row in rows for cell in np.array_split(row, 3, axis=1)]


def _palette(image: Image.Image) -> list[list[int]]:
    sample = image.copy()
    sample.thumbnail((500, 500))
    quantized = sample.quantize(colors=12, method=Image.Quantize.MEDIANCUT).convert("RGB")
    colors = quantized.getcolors(maxcolors=256) or []
    return [list(rgb) for _count, rgb in sorted(colors, reverse=True)[:8]]


def compare_figure_semantics(reference_path: Path, candidate_path: Path) -> dict[str, object]:
    """Compare rendered structure; scientific meaning still requires panel-aware review."""
    reference, reference_meta = _page_image(reference_path.resolve(strict=True))
    candidate, candidate_meta = _page_image(candidate_path.resolve(strict=True))
    ref = np.asarray(reference)
    cand = np.asarray(candidate)
    ref_aspect = reference.width / reference.height
    cand_aspect = candidate.width / candidate.height
    aspect_change = abs(math.log(cand_aspect / ref_aspect))
    ref_box, cand_box = _content_box(ref), _content_box(cand)
    box_shift = max(abs(a - b) for a, b in zip(ref_box, cand_box))
    ref_density, cand_density = _regional_density(ref), _regional_density(cand)
    density_shift = max(abs(a - b) for a, b in zip(ref_density, cand_density))
    findings: list[dict[str, str]] = []
    if aspect_change > 0.08:
        findings.append({"severity": "major", "code": "ASPECT_RATIO_DRIFT", "message": "The candidate changes the panel aspect ratio enough to alter spatial interpretation."})
    if box_shift > 0.08:
        findings.append({"severity": "major", "code": "CONTENT_POSITION_DRIFT", "message": "The occupied scientific content moves or scales materially relative to the panel boundary."})
    if density_shift > 0.12:
        findings.append({"severity": "major", "code": "REGIONAL_DENSITY_DRIFT", "message": "Information density changed materially in at least one region; inspect compression, empty areas, or lost elements."})
    if reference_meta["vector_text"] and not candidate_meta["vector_text"]:
        findings.append({"severity": "major", "code": "VECTOR_TEXT_LOST", "message": "Editable/searchable PDF text present in the reference is absent from the candidate."})
    missing_labels = sorted(set(reference_meta["vector_text"]) - set(candidate_meta["vector_text"]))
    if missing_labels:
        findings.append({"severity": "major", "code": "LABEL_SET_CHANGED", "message": f"Candidate omits {len(missing_labels)} reference text block(s)."})
    return {
        "reference": str(reference_path.resolve()),
        "candidate": str(candidate_path.resolve()),
        "metrics": {
            "reference_aspect_ratio": round(ref_aspect, 5),
            "candidate_aspect_ratio": round(cand_aspect, 5),
            "normalized_content_box_shift": round(box_shift, 5),
            "maximum_regional_density_shift": round(density_shift, 5),
            "reference_palette_rgb": _palette(reference),
            "candidate_palette_rgb": _palette(candidate),
        },
        "findings": findings,
        "automated_pass": not findings,
        "manual_review_required": [
            "plot family and statistical unit are unchanged",
            "colour meanings, arrow directions, and panel correspondence are unchanged",
            "no clipping, occlusion, duplicated panel, or misleading empty region is present",
            "the caption and allowed conclusion still match the rendered candidate",
        ],
    }
