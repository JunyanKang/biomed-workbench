"""Independent validation of chroma-key raster outputs and matte reports."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Mapping

from PIL import Image


class ChromaKeyReportError(ValueError):
    """Raised when a matte artifact cannot support safe communication use."""


def _fail(message: str) -> None:
    raise ChromaKeyReportError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(image: Image.Image) -> dict[str, int]:
    result = {"transparent": 0, "partial": 0, "opaque": 0}
    for alpha in image.getchannel("A").getdata():
        if alpha == 0:
            result["transparent"] += 1
        elif alpha == 255:
            result["opaque"] += 1
        else:
            result["partial"] += 1
    return result


def _key_channels(key: tuple[int, int, int]) -> tuple[int, ...]:
    maximum = max(key)
    minimum = min(key)
    if maximum < 128 or maximum - minimum < 48:
        return ()
    return tuple(index for index, value in enumerate(key) if value >= maximum - 16)


def _partial_spill_p95(image: Image.Image, key: tuple[int, int, int]) -> float:
    channels = _key_channels(key)
    if not channels:
        return 0.0
    others = tuple(index for index in range(3) if index not in channels)
    values = []
    for red, green, blue, alpha in image.getdata():
        if not 0 < alpha < 255:
            continue
        rgb = (red, green, blue)
        dominance = min(rgb[index] for index in channels) - max((rgb[index] for index in others), default=0)
        values.append(max(0.0, float(dominance)))
    if not values:
        return 0.0
    values.sort()
    return round(values[min(len(values) - 1, math.ceil(0.95 * len(values)) - 1)], 8)


def parse_chroma_key_outputs(
    source: Path,
    output: Path,
    report_path: Path,
    *,
    expected_parameters: Mapping[str, object],
) -> dict[str, object]:
    """Re-open every artifact and recompute structural and matte-quality claims."""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChromaKeyReportError("matte report is unreadable") from exc
    if not isinstance(report, dict) or report.get("schema_version") != 1 or report.get("quality_status") != "passed":
        _fail("matte report schema or status is invalid")
    if report.get("scientific_use") != "communication-asset-only":
        _fail("matte report does not preserve the non-quantitative scientific-use boundary")
    if report.get("parameters") != dict(expected_parameters):
        _fail("matte report parameters differ from the declared execution")
    if report.get("input", {}).get("sha256") != _sha256(source):
        _fail("source image digest differs from the matte report")
    if report.get("output", {}).get("sha256") != _sha256(output):
        _fail("output image digest differs from the matte report")

    try:
        with Image.open(source) as source_image:
            source_image.load()
            source_size = source_image.size
        with Image.open(output) as output_image:
            output_image.load()
            detected_format = output_image.format
            output_mode = output_image.mode
            frame_count = int(getattr(output_image, "n_frames", 1))
            rgba = output_image.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise ChromaKeyReportError("source or output raster cannot be decoded") from exc
    if detected_format != "PNG" or output_mode != "RGBA" or frame_count != 1:
        _fail("output must be one static RGBA PNG")
    if rgba.size != source_size:
        _fail("output dimensions differ from the source")
    if report["output"].get("width") != rgba.width or report["output"].get("height") != rgba.height:
        _fail("reported output dimensions differ from decoded pixels")

    counts = _counts(rgba)
    if counts != report["output"].get("alpha_counts"):
        _fail("reported alpha counts differ from decoded pixels")
    if counts["transparent"] == 0 or counts["opaque"] == 0:
        _fail("matte does not preserve both transparent background and opaque foreground")
    total = rgba.width * rgba.height
    fractions = {name: round(value / total, 10) for name, value in counts.items()}
    if fractions != report["output"].get("alpha_fractions"):
        _fail("reported alpha fractions differ from decoded pixels")
    if any((red, green, blue) != (0, 0, 0) for red, green, blue, alpha in rgba.getdata() if alpha == 0):
        _fail("fully transparent pixels retain hidden color payloads")

    raw_key = report.get("key", {}).get("rgb")
    if not isinstance(raw_key, list) or len(raw_key) != 3 or any(type(value) is not int or not 0 <= value <= 255 for value in raw_key):
        _fail("reported key color is invalid")
    key = tuple(raw_key)
    spill_p95 = _partial_spill_p95(rgba, key)
    if spill_p95 != report["output"].get("partial_key_dominance_p95"):
        _fail("reported edge spill differs from decoded pixels")
    if expected_parameters.get("despill_strength", 0) and spill_p95 > 96:
        _fail("residual key-channel spill exceeds the validated edge bound")

    limitations = report.get("limitations")
    if not isinstance(limitations, list) or len(limitations) < 3 or not any("not primary image data" in item for item in limitations):
        _fail("matte report omits the scientific interpretation limitations")
    return {
        "quality_status": "passed",
        "scientific_use": "communication-asset-only",
        "source_sha256": _sha256(source),
        "output_sha256": _sha256(output),
        "dimensions": [rgba.width, rgba.height],
        "alpha_counts": counts,
        "alpha_fractions": fractions,
        "key_rgb": list(key),
        "partial_key_dominance_p95": spill_p95,
        "full_resolution_review_required": True,
        "quantitative_interpretation_allowed": False,
    }
