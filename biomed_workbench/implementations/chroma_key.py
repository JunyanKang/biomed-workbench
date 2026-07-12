"""Strict static-raster chroma-key removal with auditable matte diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
import warnings

from PIL import Image, ImageFilter


SUPPORTED_FORMATS = {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}
SUPPORTED_MODES = {"1", "L", "LA", "P", "RGB", "RGBA"}
MAX_DIMENSION = 16_384
MAX_PIXELS = 40_000_000
_HEX_COLOR = re.compile(r"#?([0-9a-fA-F]{6})")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_color(value: str) -> tuple[int, int, int]:
    match = _HEX_COLOR.fullmatch(value.strip())
    if match is None:
        raise ValueError("key color must be one six-digit RGB hex value")
    token = match.group(1)
    return tuple(int(token[index : index + 2], 16) for index in (0, 2, 4))


def _linear_channel(value: int) -> float:
    encoded = value / 255.0
    return encoded / 12.92 if encoded <= 0.04045 else ((encoded + 0.055) / 1.055) ** 2.4


def _color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> float:
    delta = [(_linear_channel(a) - _linear_channel(b)) ** 2 for a, b in zip(left, right)]
    return 255.0 * math.sqrt(sum(delta) / 3.0)


def _smooth_alpha(distance: float, transparent: float, opaque: float) -> int:
    if distance <= transparent:
        return 0
    if distance >= opaque:
        return 255
    ratio = (distance - transparent) / (opaque - transparent)
    smooth = ratio * ratio * (3.0 - 2.0 * ratio)
    return max(0, min(255, round(255.0 * smooth)))


def _border_samples(image: Image.Image, mode: str) -> list[tuple[int, int, int]]:
    width, height = image.size
    pixels = image.load()
    samples: list[tuple[int, int, int]] = []
    if mode == "corners":
        patch = max(1, min(width, height, 16))
        boxes = (
            (0, 0, patch, patch),
            (width - patch, 0, width, patch),
            (0, height - patch, patch, height),
            (width - patch, height - patch, width, height),
        )
        coordinates = (
            (x, y)
            for left, top, right, bottom in boxes
            for y in range(top, bottom)
            for x in range(left, right)
        )
    else:
        band = max(1, min(width, height, 8))
        stride = max(1, max(width, height) // 1024)
        coordinates = iter(
            list((x, y) for x in range(0, width, stride) for y in range(band))
            + list((x, height - 1 - y) for x in range(0, width, stride) for y in range(band))
            + list((x, y) for y in range(0, height, stride) for x in range(band))
            + list((width - 1 - x, y) for y in range(0, height, stride) for x in range(band))
        )
    for x, y in coordinates:
        red, green, blue, alpha = pixels[x, y]
        if alpha >= 250:
            samples.append((red, green, blue))
    if len(samples) < 16:
        raise ValueError("too few opaque border pixels are available for automatic key selection")
    return samples


def _select_key(
    image: Image.Image,
    *,
    mode: str,
    explicit: str,
    maximum_deviation: float,
    minimum_consensus: float,
) -> tuple[tuple[int, int, int], dict[str, object]]:
    if mode == "none":
        key = _parse_color(explicit)
        return key, {"method": "explicit", "sample_count": 0, "consensus_fraction": 1.0, "p95_distance": 0.0}
    samples = _border_samples(image, mode)
    key = tuple(round(median(pixel[channel] for pixel in samples)) for channel in range(3))
    distances = sorted(_color_distance(pixel, key) for pixel in samples)
    p95 = distances[min(len(distances) - 1, math.ceil(0.95 * len(distances)) - 1)]
    consensus = sum(distance <= maximum_deviation for distance in distances) / len(distances)
    if p95 > maximum_deviation or consensus < minimum_consensus:
        raise ValueError("automatic key samples are heterogeneous; provide an explicit key or a cleaner border")
    return key, {
        "method": mode,
        "sample_count": len(samples),
        "consensus_fraction": round(consensus, 8),
        "p95_distance": round(p95, 8),
    }


def _key_channels(key: tuple[int, int, int]) -> tuple[int, ...]:
    maximum = max(key)
    minimum = min(key)
    if maximum < 128 or maximum - minimum < 48:
        return ()
    return tuple(index for index, value in enumerate(key) if value >= maximum - 16)


def _key_dominance(rgb: tuple[int, int, int], key: tuple[int, int, int]) -> float:
    channels = _key_channels(key)
    if not channels:
        return 0.0
    others = tuple(index for index in range(3) if index not in channels)
    key_strength = min(rgb[index] for index in channels)
    other_strength = max((rgb[index] for index in others), default=0)
    return float(key_strength - other_strength)


def _despill(
    rgb: tuple[int, int, int],
    key: tuple[int, int, int],
    alpha: int,
    strength: float,
) -> tuple[int, int, int]:
    channels = _key_channels(key)
    if not channels or alpha in {0, 255} or strength == 0:
        return rgb
    values = [float(value) for value in rgb]
    others = tuple(index for index in range(3) if index not in channels)
    anchor = max((values[index] for index in others), default=0.0)
    edge_weight = 1.0 - alpha / 255.0
    for index in channels:
        excess = max(0.0, values[index] - anchor)
        values[index] -= excess * strength * edge_weight
    return tuple(max(0, min(255, round(value))) for value in values)


def _alpha_counts(image: Image.Image) -> dict[str, int]:
    counts = {"transparent": 0, "partial": 0, "opaque": 0}
    for alpha in image.getchannel("A").getdata():
        if alpha == 0:
            counts["transparent"] += 1
        elif alpha == 255:
            counts["opaque"] += 1
        else:
            counts["partial"] += 1
    return counts


def _partial_spill_p95(image: Image.Image, key: tuple[int, int, int]) -> float:
    values = sorted(
        max(0.0, _key_dominance((red, green, blue), key))
        for red, green, blue, alpha in image.getdata()
        if 0 < alpha < 255
    )
    if not values:
        return 0.0
    return round(values[min(len(values) - 1, math.ceil(0.95 * len(values)) - 1)], 8)


def _load_static_image(path: Path, declared_format: str) -> tuple[Image.Image, dict[str, object]]:
    if declared_format not in SUPPORTED_FORMATS:
        raise ValueError("source format must be png, jpeg, or webp")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(path)
        detected = image.format
        frames = int(getattr(image, "n_frames", 1))
        if detected != SUPPORTED_FORMATS[declared_format]:
            image.close()
            raise ValueError("declared source format differs from the decoded file signature")
        if frames != 1 or bool(getattr(image, "is_animated", False)):
            image.close()
            raise ValueError("animated or multi-frame images are outside the validated contract")
        width, height = image.size
        if width <= 0 or height <= 0 or width > MAX_DIMENSION or height > MAX_DIMENSION or width * height > MAX_PIXELS:
            image.close()
            raise ValueError("image dimensions exceed the validated static-raster limits")
        if image.mode not in SUPPORTED_MODES:
            image.close()
            raise ValueError("source pixel mode is outside the validated 8-bit raster modes")
        if image.info.get("icc_profile"):
            image.close()
            raise ValueError("embedded ICC profiles require an explicit color-managed conversion before chroma keying")
        orientation = image.getexif().get(274, 1)
        if orientation != 1:
            image.close()
            raise ValueError("non-canonical EXIF orientation must be normalized before chroma keying")
        source_mode = image.mode
        image.load()
        rgba = image.convert("RGBA")
        image.close()
    return rgba, {"detected_format": detected, "source_mode": source_mode, "frame_count": frames, "width": width, "height": height}


def remove_chroma_key(
    source: Path,
    output: Path,
    report_path: Path,
    *,
    source_format: str,
    key_color: str,
    auto_key: str,
    transparent_threshold: float,
    opaque_threshold: float,
    auto_key_maximum_deviation: float,
    auto_key_minimum_consensus: float,
    despill_strength: float,
    edge_contract: int,
    edge_feather: float,
) -> dict[str, object]:
    if not source.is_file():
        raise ValueError("source image does not exist")
    if output.suffix.lower() != ".png":
        raise ValueError("output must use the .png suffix")
    if auto_key not in {"none", "corners", "border"}:
        raise ValueError("auto key mode must be none, corners, or border")
    if not (0 <= transparent_threshold < opaque_threshold <= 255):
        raise ValueError("matte thresholds must satisfy 0 <= transparent < opaque <= 255")
    if not (0 <= auto_key_maximum_deviation <= 255 and 0.5 <= auto_key_minimum_consensus <= 1):
        raise ValueError("automatic key consistency parameters are outside validated bounds")
    if not (0 <= despill_strength <= 1 and 0 <= edge_contract <= 8 and 0 <= edge_feather <= 8):
        raise ValueError("despill, contraction, or feather parameters are outside validated bounds")

    image, source_info = _load_static_image(source, source_format)
    key, key_diagnostics = _select_key(
        image,
        mode=auto_key,
        explicit=key_color,
        maximum_deviation=auto_key_maximum_deviation,
        minimum_consensus=auto_key_minimum_consensus,
    )
    if despill_strength > 0 and not _key_channels(key):
        raise ValueError("despill requires a sufficiently chromatic key color")

    pixels = image.load()
    width, height = image.size
    source_partial = 0
    for y in range(height):
        for x in range(width):
            red, green, blue, original_alpha = pixels[x, y]
            matte_alpha = _smooth_alpha(_color_distance((red, green, blue), key), transparent_threshold, opaque_threshold)
            alpha = round(matte_alpha * original_alpha / 255.0)
            if 0 < alpha < 255:
                source_partial += 1
            rgb = _despill((red, green, blue), key, alpha, despill_strength)
            pixels[x, y] = (*rgb, alpha)

    if edge_contract:
        alpha = image.getchannel("A")
        for _ in range(edge_contract):
            alpha = alpha.filter(ImageFilter.MinFilter(3))
        image.putalpha(alpha)
    if edge_feather:
        image.putalpha(image.getchannel("A").filter(ImageFilter.GaussianBlur(edge_feather)))

    # Canonicalize invisible pixels so hidden key colors cannot create halos or covert payloads.
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                pixels[x, y] = (0, 0, 0, 0)

    counts = _alpha_counts(image)
    if counts["transparent"] == 0:
        raise ValueError("no background became transparent; key selection or thresholds are incompatible")
    if counts["opaque"] == 0:
        raise ValueError("no opaque foreground remains; key selection or thresholds are unsafe")

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", compress_level=9, optimize=False)
    spill_p95 = _partial_spill_p95(image, key)
    total = width * height
    report = {
        "schema_version": 1,
        "quality_status": "passed",
        "scientific_use": "communication-asset-only",
        "input": {**source_info, "sha256": _sha256(source), "declared_format": source_format},
        "output": {
            "format": "PNG",
            "mode": "RGBA",
            "width": width,
            "height": height,
            "sha256": _sha256(output),
            "alpha_counts": counts,
            "alpha_fractions": {name: round(value / total, 10) for name, value in counts.items()},
            "partial_key_dominance_p95": spill_p95,
        },
        "key": {"rgb": list(key), "hex": "#" + "".join(f"{value:02x}" for value in key), **key_diagnostics},
        "parameters": {
            "source_format": source_format,
            "key_color": key_color.lower(),
            "auto_key": auto_key,
            "transparent_threshold": transparent_threshold,
            "opaque_threshold": opaque_threshold,
            "auto_key_maximum_deviation": auto_key_maximum_deviation,
            "auto_key_minimum_consensus": auto_key_minimum_consensus,
            "despill_strength": despill_strength,
            "edge_contract": edge_contract,
            "edge_feather": edge_feather,
        },
        "diagnostics": {"pre_filter_partial_pixels": source_partial},
        "limitations": [
            "The output is a derived communication asset, not primary image data or a quantitative segmentation mask.",
            "Chroma keying and despill alter edge colors and alpha and must not support intensity, morphology, localization, or colocalization measurements.",
            "Foreground colors close to the key may be removed; inspect the full-resolution output against the source before publication.",
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-format", choices=sorted(SUPPORTED_FORMATS), required=True)
    parser.add_argument("--key-color", default="#00ff00")
    parser.add_argument("--auto-key", choices=("none", "corners", "border"), default="none")
    parser.add_argument("--transparent-threshold", type=float, default=8.0)
    parser.add_argument("--opaque-threshold", type=float, default=90.0)
    parser.add_argument("--auto-key-maximum-deviation", type=float, default=18.0)
    parser.add_argument("--auto-key-minimum-consensus", type=float, default=0.9)
    parser.add_argument("--despill-strength", type=float, default=1.0)
    parser.add_argument("--edge-contract", type=int, default=0)
    parser.add_argument("--edge-feather", type=float, default=0.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    remove_chroma_key(
        args.input,
        args.output,
        args.report,
        source_format=args.source_format,
        key_color=args.key_color,
        auto_key=args.auto_key,
        transparent_threshold=args.transparent_threshold,
        opaque_threshold=args.opaque_threshold,
        auto_key_maximum_deviation=args.auto_key_maximum_deviation,
        auto_key_minimum_consensus=args.auto_key_minimum_consensus,
        despill_strength=args.despill_strength,
        edge_contract=args.edge_contract,
        edge_feather=args.edge_feather,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
