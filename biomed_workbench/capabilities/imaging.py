"""Dependency-free image measurements for deterministic fixtures and small arrays."""

from __future__ import annotations

import math
from collections import deque
from typing import Any


def _image(values: list[list[float]], name: str = "image") -> list[list[float]]:
    if not isinstance(values, list) or not values or not isinstance(values[0], list) or not values[0]:
        raise ValueError(f"{name} must be a nonempty 2D array")
    width = len(values[0])
    normalized = []
    for row in values:
        converted = [float(value) for value in row]
        if len(converted) != width or any(not math.isfinite(value) for value in converted):
            raise ValueError(f"{name} must be rectangular with finite values")
        normalized.append(converted)
    return normalized


def _volume(values: list[list[list[float]]], name: str = "volume") -> list[list[list[float]]]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{name} must be a nonempty 3D array")
    if not all(isinstance(layer, list) and layer for layer in values):
        raise ValueError(f"{name} must be a nonempty 3D array")
    width = len(values[0][0]) if values[0] else 0
    if width == 0:
        raise ValueError(f"{name} must be a nonempty 3D array")
    height = len(values[0])
    for layer in values:
        if len(layer) != height:
            raise ValueError(f"{name} must be rectangular across slices")
        for row in layer:
            converted = [float(value) for value in row]
            if len(converted) != width or any(not math.isfinite(value) for value in converted):
                raise ValueError(f"{name} must be rectangular with finite values")
            # Keep rows in-place to match row-major 2D helpers and avoid alias risk.
            for idx, value in enumerate(converted):
                row[idx] = value
    return values


def _voxel_size(mm_per_voxel: list[float] | tuple[float, float, float] | None, name: str) -> dict[str, float]:
    if mm_per_voxel is None:
        return {"x": 1.0, "y": 1.0, "z": 1.0}
    if not isinstance(mm_per_voxel, (list, tuple)) or len(mm_per_voxel) != 3:
        raise ValueError(f"{name} must be three positive float values")
    values = [float(item) for item in mm_per_voxel]
    if any(v <= 0 or not math.isfinite(v) for v in values):
        raise ValueError(f"{name} must be three positive finite float values")
    return {"x": values[0], "y": values[1], "z": values[2]}


def image_profile(image: list[list[float]]) -> dict[str, Any]:
    values = _image(image)
    flattened = [value for row in values for value in row]
    mean = math.fsum(flattened) / len(flattened)
    variance = math.fsum((value - mean) ** 2 for value in flattened) / len(flattened)
    ordered = sorted(flattened)

    def percentile(fraction: float) -> float:
        position = fraction * (len(ordered) - 1)
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])

    return {
        "shape": [len(values), len(values[0])],
        "pixel_count": len(flattened),
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "mean": mean,
        "standard_deviation": math.sqrt(variance),
        "percentiles": {"p01": percentile(0.01), "p50": percentile(0.5), "p99": percentile(0.99)},
        "zero_fraction": sum(value == 0 for value in flattened) / len(flattened),
    }


def register_image_translation(fixed: list[list[float]], moving: list[list[float]], max_shift_pixels: int = 10, minimum_overlap_fraction: float = 0.5) -> dict[str, Any]:
    """Register equal-shape 2D images by exhaustive integer translation and overlap MSE."""
    fixed_values, moving_values = _image(fixed, "fixed"), _image(moving, "moving")
    if len(fixed_values) != len(moving_values) or len(fixed_values[0]) != len(moving_values[0]):
        raise ValueError("fixed and moving images must have identical shapes")
    if not isinstance(max_shift_pixels, int) or not 0 <= max_shift_pixels <= 200:
        raise ValueError("max_shift_pixels must be an integer from 0 through 200")
    if not isinstance(minimum_overlap_fraction, (int, float)) or not 0 < minimum_overlap_fraction <= 1:
        raise ValueError("minimum_overlap_fraction must be in (0, 1]")
    height, width, total = len(fixed_values), len(fixed_values[0]), len(fixed_values) * len(fixed_values[0])
    candidates = []
    for row_shift in range(-max_shift_pixels, max_shift_pixels + 1):
        for column_shift in range(-max_shift_pixels, max_shift_pixels + 1):
            errors = [
                (fixed_values[row][column] - moving_values[row - row_shift][column - column_shift]) ** 2
                for row in range(height) for column in range(width)
                if 0 <= row - row_shift < height and 0 <= column - column_shift < width
            ]
            if len(errors) / total >= minimum_overlap_fraction:
                candidates.append((math.fsum(errors) / len(errors), len(errors) / total, row_shift, column_shift))
    if not candidates:
        raise ValueError("no translation candidate satisfies minimum_overlap_fraction")
    candidates.sort(key=lambda item: (item[0], -item[1], abs(item[2]) + abs(item[3])))
    best, second = candidates[0], candidates[1] if len(candidates) > 1 else None
    return {"shape": [height, width], "transform": {"type": "integer_translation", "fixed_to_moving_row_shift": best[2], "fixed_to_moving_column_shift": best[3]}, "overlap_fraction": round(best[1], 8), "mean_squared_error": best[0], "second_best_mean_squared_error": second[0] if second else None, "registration_margin": second[0] / best[0] if second and best[0] > 0 else None, "evaluated_candidate_count": len(candidates), "limitations": ["This is exhaustive integer translation only; it does not estimate rotation, scale, affine or deformable registration.", "Registration quality requires acquisition-aware visual review, masking where appropriate, and independent assessment of biological correspondence."]}


def segment_components(
    image: list[list[float]],
    threshold: float,
    connectivity: int = 8,
    minimum_area: int = 1,
    polarity: str = "high",
) -> dict[str, Any]:
    values = _image(image)
    if connectivity not in {4, 8} or minimum_area < 1 or polarity not in {"high", "low"}:
        raise ValueError("invalid connectivity, minimum_area, or polarity")
    height, width = len(values), len(values[0])
    foreground = [
        [value >= threshold if polarity == "high" else value <= threshold for value in row]
        for row in values
    ]
    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if connectivity == 8:
        neighbors += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    visited: set[tuple[int, int]] = set()
    raw_components = []
    for row in range(height):
        for column in range(width):
            if not foreground[row][column] or (row, column) in visited:
                continue
            queue = deque([(row, column)])
            visited.add((row, column))
            pixels = []
            while queue:
                current = queue.popleft()
                pixels.append(current)
                for delta_row, delta_column in neighbors:
                    candidate = (current[0] + delta_row, current[1] + delta_column)
                    if 0 <= candidate[0] < height and 0 <= candidate[1] < width and foreground[candidate[0]][candidate[1]] and candidate not in visited:
                        visited.add(candidate)
                        queue.append(candidate)
            if len(pixels) >= minimum_area:
                raw_components.append(sorted(pixels))
    raw_components.sort(key=lambda pixels: (pixels[0][0], pixels[0][1]))
    components = []
    labels = [[0 for _column in range(width)] for _row in range(height)]
    for label, pixels in enumerate(raw_components, start=1):
        pixel_set = set(pixels)
        for row, column in pixels:
            labels[row][column] = label
        perimeter = 0
        for row, column in pixels:
            perimeter += sum((row + dr, column + dc) not in pixel_set for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)])
        area = len(pixels)
        centroid_row = math.fsum(row + 1 for row, _column in pixels) / area
        centroid_column = math.fsum(column + 1 for _row, column in pixels) / area
        covariance_row = math.fsum(((row + 1) - centroid_row) ** 2 for row, _column in pixels) / area
        covariance_column = math.fsum(((column + 1) - centroid_column) ** 2 for _row, column in pixels) / area
        covariance_cross = math.fsum(
            ((row + 1) - centroid_row) * ((column + 1) - centroid_column) for row, column in pixels
        ) / area
        trace = covariance_row + covariance_column
        discriminant = max(0.0, (covariance_column - covariance_row) ** 2 + 4.0 * covariance_cross**2)
        major_variance = max(0.0, (trace + math.sqrt(discriminant)) / 2.0)
        minor_variance = max(0.0, (trace - math.sqrt(discriminant)) / 2.0)
        # The axes are second-moment descriptors, not fitted physical cell dimensions.
        major_axis = 4.0 * math.sqrt(major_variance)
        minor_axis = 4.0 * math.sqrt(minor_variance)
        orientation = math.degrees(0.5 * math.atan2(2.0 * covariance_cross, covariance_column - covariance_row)) if major_variance > 0 else None
        components.append(
            {
                "label": label,
                "area": area,
                "centroid": {"row": centroid_row, "column": centroid_column},
                "bounding_box": {
                    "min_row": min(row for row, _column in pixels) + 1,
                    "min_column": min(column for _row, column in pixels) + 1,
                    "max_row": max(row for row, _column in pixels) + 1,
                    "max_column": max(column for _row, column in pixels) + 1,
                },
                "perimeter": perimeter,
                "circularity": 4.0 * math.pi * area / perimeter**2 if perimeter else None,
                "major_axis_second_moment_pixels": major_axis,
                "minor_axis_second_moment_pixels": minor_axis,
                "axis_aspect_ratio": major_axis / minor_axis if minor_axis > 0 else None,
                "eccentricity_second_moment": math.sqrt(1.0 - minor_variance / major_variance) if major_variance > 0 else None,
                "orientation_degrees_from_column_axis": orientation,
                "mean_intensity": math.fsum(values[row][column] for row, column in pixels) / area,
            }
        )
    return {"shape": [height, width], "threshold": threshold, "polarity": polarity, "connectivity": connectivity, "component_count": len(components), "components": components, "labels": labels, "coordinate_system": "one-based pixel centers"}


def colocalization(
    channel_a: list[list[float]],
    channel_b: list[list[float]],
    threshold_a: float = 0,
    threshold_b: float = 0,
) -> dict[str, Any]:
    a = _image(channel_a, "channel_a")
    b = _image(channel_b, "channel_b")
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        raise ValueError("channels must have identical shape")
    flat_a = [value for row in a for value in row]
    flat_b = [value for row in b for value in row]
    mean_a = math.fsum(flat_a) / len(flat_a)
    mean_b = math.fsum(flat_b) / len(flat_b)
    covariance = math.fsum((left - mean_a) * (right - mean_b) for left, right in zip(flat_a, flat_b))
    denominator = math.sqrt(math.fsum((value - mean_a) ** 2 for value in flat_a) * math.fsum((value - mean_b) ** 2 for value in flat_b))
    pearson = covariance / denominator if denominator else None
    denominator_a = math.fsum(value for value in flat_a if value > threshold_a)
    denominator_b = math.fsum(value for value in flat_b if value > threshold_b)
    coloc_a = math.fsum(left for left, right in zip(flat_a, flat_b) if left > threshold_a and right > threshold_b)
    coloc_b = math.fsum(right for left, right in zip(flat_a, flat_b) if left > threshold_a and right > threshold_b)
    return {
        "shape": [len(a), len(a[0])],
        "pearson_r": pearson,
        "manders_m1": coloc_a / denominator_a if denominator_a else None,
        "manders_m2": coloc_b / denominator_b if denominator_b else None,
        "threshold_a": threshold_a,
        "threshold_b": threshold_b,
        "method": "Pearson intensity correlation and thresholded Manders overlap coefficients",
    }


def track_points(frames: list[list[list[float]]], max_distance: float) -> dict[str, Any]:
    if not frames or not math.isfinite(float(max_distance)) or max_distance <= 0:
        raise ValueError("frames must be nonempty and max_distance positive")
    normalized_frames = []
    for frame in frames:
        points = []
        for point in frame:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("each point must be [x, y]")
            x, y = map(float, point)
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("point coordinates must be finite")
            points.append((x, y))
        normalized_frames.append(points)
    tracks: list[dict[str, Any]] = []
    active: dict[int, tuple[float, float]] = {}
    for frame_index, points in enumerate(normalized_frames):
        assignments = []
        for track_id, previous in active.items():
            for point_index, point in enumerate(points):
                distance = math.dist(previous, point)
                if distance <= max_distance:
                    assignments.append((distance, track_id, point_index))
        used_tracks, used_points = set(), set()
        next_active = {}
        for distance, track_id, point_index in sorted(assignments):
            if track_id in used_tracks or point_index in used_points:
                continue
            point = points[point_index]
            tracks[track_id]["points"].append({"frame": frame_index, "x": point[0], "y": point[1], "link_distance": distance})
            used_tracks.add(track_id)
            used_points.add(point_index)
            next_active[track_id] = point
        for point_index, point in enumerate(points):
            if point_index in used_points:
                continue
            track_id = len(tracks)
            tracks.append({"track_id": track_id + 1, "points": [{"frame": frame_index, "x": point[0], "y": point[1], "link_distance": None}]})
            next_active[track_id] = point
        active = next_active
    return {"tracks": tracks, "track_count": len(tracks), "max_distance": max_distance, "method": "frame-local greedy one-to-one nearest-neighbor linking", "limitations": ["Crossings, missed detections, motion models, and gap closing are not resolved."]}


def summarize_cell_migration_tracks(tracks: list[dict[str, Any]], pixel_size_um: float = 1.0, time_interval_min: float = 1.0, min_track_length: int = 3) -> dict[str, Any]:
    """Summarize calibrated displacement, path length, speed, and directionality."""
    if not all(isinstance(v, (int, float)) and v > 0 for v in (pixel_size_um, time_interval_min)) or not isinstance(min_track_length, int) or min_track_length < 2:
        raise ValueError("calibration values must be positive and min_track_length must be at least 2")
    rows=[]
    for track in tracks:
        points=track.get("points") if isinstance(track, dict) else None
        if not isinstance(points, list) or len(points)<min_track_length: continue
        points=sorted(points,key=lambda p:p["frame"])
        if any(not isinstance(p,dict) or not all(isinstance(p.get(k),(int,float)) for k in ("frame","x","y")) for p in points): raise ValueError("track points require numeric frame, x, and y")
        steps=[math.hypot((b["x"]-a["x"])*pixel_size_um,(b["y"]-a["y"])*pixel_size_um) for a,b in zip(points,points[1:])]
        path=math.fsum(steps); net=math.hypot((points[-1]["x"]-points[0]["x"])*pixel_size_um,(points[-1]["y"]-points[0]["y"])*pixel_size_um); duration=(points[-1]["frame"]-points[0]["frame"])*time_interval_min
        rows.append({"track_id":track.get("track_id"),"frames_tracked":len(points),"path_length_um":round(path,8),"net_displacement_um":round(net,8),"directionality":round(net/path,8) if path else 0.0,"speed_um_per_min":round(path/duration,8) if duration>0 else 0.0})
    return {"track_metrics":rows,"included_track_count":len(rows),"calibration":{"pixel_size_um":pixel_size_um,"time_interval_min":time_interval_min,"min_track_length":min_track_length},"limitations":["Metrics inherit detection and tracking errors and do not establish chemotaxis, persistence mechanism, viability, or independent field-level replication."]}


def medical_volume_summary(
    volume: list[list[list[float]]],
    mm_per_voxel: list[float] | tuple[float, float, float] | None = None,
    required_voxel_order: str = "z-y-x",
) -> dict[str, Any]:
    """Summarize declared 3D medical-image tensors without assuming any external file parser."""
    volume_values = _volume(volume, "volume")
    if required_voxel_order not in {"z-y-x", "z-y-x-mm", "xyz"}:
        raise ValueError("required_voxel_order must be one of z-y-x, z-y-x-mm, xyz")
    scale = _voxel_size(mm_per_voxel, "mm_per_voxel")
    depth, height, width = len(volume_values), len(volume_values[0]), len(volume_values[0][0])
    flat = [value for layer in volume_values for row in layer for value in row]
    mean = math.fsum(flat) / len(flat)
    variance = math.fsum((value - mean) ** 2 for value in flat) / len(flat)
    ordered = sorted(flat)
    voxel_count = len(flat)
    nonzero_count = sum(value != 0 for value in flat)
    nonnegative = all(value >= 0 for value in flat)
    in_range_count = sum(0 <= value <= 10_000 for value in flat)
    return {
        "shape": [depth, height, width],
        "voxel_geometry": {"shape": [depth, height, width], "voxel_count": voxel_count, "mm_per_voxel": scale, "required_order": required_voxel_order},
        "intensity": {
            "minimum": ordered[0],
            "maximum": ordered[-1],
            "mean": mean,
            "standard_deviation": math.sqrt(variance),
            "median": ordered[len(ordered) // 2],
            "p05": ordered[max(0, math.floor(0.05 * (len(ordered) - 1)))],
            "p95": ordered[max(0, math.floor(0.95 * (len(ordered) - 1)))],
            "mean_by_slice": [
                {
                    "slice": index,
                    "mean_intensity": math.fsum(value for row in layer for value in row) / (height * width),
                    "nonzero_fraction": sum(value != 0 for row in layer for value in row) / (height * width),
                }
                for index, layer in enumerate(volume_values)
            ],
            "quality_flags": [
                "Nonlinear intensity transforms are not performed",
                "No motion correction or registration is applied",
                "Values retain declared geometry and scale only"
            ],
            "nonzero_fraction": nonzero_count / voxel_count,
            "physical_volume_mm3": voxel_count * scale["x"] * scale["y"] * scale["z"],
            "mean_is_positive": mean > 0,
            "nonnegative_all": nonnegative,
            "in_range_0_10000_count": in_range_count,
            "outside_0_10000_count": voxel_count - in_range_count,
            "outside_range_fraction": (voxel_count - in_range_count) / voxel_count,
        },
        "limitations": [
            "No resampling, orientation normalization, NIfTI/DICOM parsing, or bias-field correction is performed.",
            "This is a tensor-level quality check; clinical interpretation requires sequence context and acquisition metadata."
        ],
    }


def medical_metadata_audit(
    metadata: dict[str, Any],
    declare_modality: str | None = None,
    minimum_required_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Validate declared imaging metadata and flag likely privacy risks for a minimal workflow."""
    if not isinstance(metadata, dict) or not metadata:
        raise ValueError("metadata must be a nonempty object")
    requested_fields = minimum_required_fields or [
        "Modality",
        "PatientID",
        "PatientName",
        "StudyDate",
        "SeriesDescription",
        "PixelSpacing",
        "SliceThickness",
    ]
    if not isinstance(requested_fields, list) or any(not isinstance(name, str) or not name.strip() for name in requested_fields):
        raise ValueError("minimum_required_fields must be a nonempty list of field names")
    normalized_keys = {str(key).lower(): value for key, value in metadata.items()}
    detected_pii_patterns = ("patientname", "patient_id", "patientid", "name", "id", "phone", "address", "dob", "social")
    has_potential_pii_key = any(pattern in normalized_key for pattern in detected_pii_patterns for normalized_key in normalized_keys)
    missing_fields = sorted({field.lower() for field in requested_fields if field.lower() not in normalized_keys})
    provided_fields = [field for field in requested_fields if field.lower() in normalized_keys]
    quality_gates = [
        "Raw image metadata is an input descriptor, not analyzed as biological evidence.",
        "Any retained PHI-relevant fields must be pseudonymized before sharing.",
        "Spatial, contrast-agent, and sequence metadata are declared before any interpretation."
    ]
    modality = declare_modality or normalized_keys.get("modality")
    return {
        "metadata_fields": sorted(metadata.keys()),
        "required_fields": {
            "declared": sorted(set(requested_fields)),
            "present": sorted(provided_fields),
            "missing": sorted(missing_fields),
        },
        "declared_modality": str(modality) if modality is not None else None,
        "pii_risk": {
            "has_potential_pii_key": has_potential_pii_key,
            "risk_level": "high" if has_potential_pii_key or "patientid" in normalized_keys or "patientname" in normalized_keys else "low",
            "sensitive_fields": [
                key
                for key, value in normalized_keys.items()
                if any(pattern in key for pattern in detected_pii_patterns)
                or str(value).lower() in {"unknown", "xx", "匿名"}
            ],
        },
        "privacy_gates": quality_gates,
        "release_ready": False,
        "limitations": [
            "This audit is a declared-metadata pass; full privacy governance depends on project policy and local IRB controls.",
            "No de-identification service is executed and no on-file DICOM parser is called.",
        ],
    }


_ILLUSTRATION_TYPES = {
    "conceptual-mechanism",
    "graphical-abstract",
    "experimental-schematic",
    "scientific-illustration",
    "editorial-cover",
    "educational-diagram",
}
_ASPECT_RATIOS = {"auto", "square", "landscape", "portrait", "wide", "tall"}


def _bounded_text(value: str, name: str, *, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{name} must be nonempty and at most {maximum} characters")
    return value.strip()


def _bounded_strings(values: list[str] | None, name: str, *, maximum_items: int = 20, maximum_length: int = 300) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > maximum_items:
        raise ValueError(f"{name} must contain at most {maximum_items} strings")
    normalized = [_bounded_text(value, f"{name} item", maximum=maximum_length) for value in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{name} must not contain duplicate values")
    return normalized


def scientific_illustration_generation(
    subject: str,
    intended_claim: str,
    illustration_type: str,
    *,
    mode: str = "generate",
    audience: str = "scientific",
    composition: str = "clear hierarchy with uncluttered negative space",
    style: str = "scientifically precise editorial illustration",
    background: str = "clean neutral background",
    aspect_ratio: str = "auto",
    labels: list[str] | None = None,
    palette: list[str] | None = None,
    visual_semantics: list[str] | None = None,
    protected_elements: list[str] | None = None,
    constraints: list[str] | None = None,
    avoid: list[str] | None = None,
    reference_image_count: int = 0,
    disclosure_context: str = "internal-draft",
) -> dict[str, Any]:
    """Prepare a bounded Codex-native image-generation handoff for scientific communication."""

    subject = _bounded_text(subject, "subject")
    intended_claim = _bounded_text(intended_claim, "intended_claim")
    audience = _bounded_text(audience, "audience", maximum=200)
    composition = _bounded_text(composition, "composition", maximum=500)
    style = _bounded_text(style, "style", maximum=300)
    background = _bounded_text(background, "background", maximum=300)
    if illustration_type not in _ILLUSTRATION_TYPES:
        raise ValueError("illustration_type is unsupported")
    if mode not in {"generate", "edit"}:
        raise ValueError("mode must be generate or edit")
    if aspect_ratio not in _ASPECT_RATIOS:
        raise ValueError("aspect_ratio is unsupported")
    if disclosure_context not in {"internal-draft", "manuscript", "presentation", "public-communication"}:
        raise ValueError("disclosure_context is unsupported")
    if not isinstance(reference_image_count, int) or isinstance(reference_image_count, bool) or not 0 <= reference_image_count <= 5:
        raise ValueError("reference_image_count must be an integer from 0 through 5")
    if mode == "edit" and reference_image_count == 0:
        raise ValueError("edit mode requires at least one visible reference image")
    normalized_labels = _bounded_strings(labels, "labels", maximum_length=80)
    normalized_palette = _bounded_strings(palette, "palette", maximum_items=12, maximum_length=80)
    normalized_semantics = _bounded_strings(visual_semantics, "visual_semantics", maximum_length=200)
    normalized_protected = _bounded_strings(protected_elements, "protected_elements", maximum_length=200)
    normalized_constraints = _bounded_strings(constraints, "constraints")
    normalized_avoid = _bounded_strings(avoid, "avoid")
    integrity_constraint = (
        "Scientific integrity: create a clearly conceptual generated illustration, not measured data. "
        "Do not fabricate microscopy fields, gel bands, blots, instrument readouts, quantitative plots, "
        "patient-specific findings, numerical results, or exact molecular evidence."
    )
    prompt_sections = [
        f"Use case: {illustration_type} for {audience}.",
        f"Primary subject: {subject}.",
        f"Communication claim: {intended_claim}.",
        f"Composition: {composition}.",
        f"Style: {style}.",
        f"Background: {background}.",
        f"Aspect ratio: {aspect_ratio}.",
    ]
    if normalized_labels:
        prompt_sections.append("Text labels to render verbatim: " + " | ".join(normalized_labels) + ".")
    if normalized_palette:
        prompt_sections.append("Color palette: " + " | ".join(normalized_palette) + ".")
    if normalized_semantics:
        prompt_sections.append("Visual semantics that must remain consistent: " + " | ".join(normalized_semantics) + ".")
    if normalized_protected:
        prompt_sections.append("Protected elements for reference-preserving edits: " + " | ".join(normalized_protected) + ".")
    if normalized_constraints:
        prompt_sections.append("Required constraints: " + " | ".join(normalized_constraints) + ".")
    prompt_sections.append(integrity_constraint)
    avoid_values = [
        "invented experimental evidence",
        "unlabeled ambiguity",
        "decorative elements that imply unsupported mechanism",
        *normalized_avoid,
    ]
    prompt_sections.append("Avoid: " + " | ".join(avoid_values) + ".")
    return {
        "ready": True,
        "representation_scope": "scientific-communication-only",
        "disclosure_context": disclosure_context,
        "execution_handoff": {
            "tool": "image_gen",
            "operation": mode,
            "prompt": "\n".join(prompt_sections),
            "reference_image_count": reference_image_count,
            "requires_visible_reference_images": mode == "edit" or reference_image_count > 0,
            "authentication": "codex-managed",
            "cli_fallback_allowed": False,
            "output_kind": "bitmap",
        },
        "quality_gates": [
            {"id": "generated-not-observed-data", "severity": "fatal", "check": "The image is never represented as acquired, measured, simulated, or experimentally observed evidence."},
            {"id": "scientific-accuracy-review", "severity": "major", "check": "A domain expert checks anatomy, molecular relationships, scale cues, directionality, and causal implications before publication."},
            {"id": "text-label-fidelity", "severity": "major", "check": "Every requested label is visually inspected character by character; incorrect generated text is regenerated or replaced in an editable figure workflow."},
            {"id": "reference-invariant-preservation", "severity": "major", "check": "For edits, declared objects, geometry, identity, and protected regions are compared against every visible reference image."},
            {"id": "generation-disclosure", "severity": "major", "check": "Journal, institutional, copyright, consent, and AI-image disclosure requirements are checked before external use."},
        ],
        "post_generation_validation": [
            "Inspect the generated bitmap at full resolution.",
            "Confirm all requested subjects and relationships are present and no unsupported element was introduced.",
            "Confirm text, symbols, arrows, color semantics, and panel hierarchy are correct and non-occluding.",
            "For edits, verify every protected element against the visible source image at matched scale.",
            "Record that the artifact is generated communication material and not primary research data.",
        ],
        "limitations": [
            "The handoff prepares and constrains a Codex-native image operation; the bitmap exists only after the native tool returns an observed result.",
            "Generated scientific illustrations require expert factual review and cannot substitute for plots, microscopy, diagnostic images, structural predictions, or experimental evidence.",
            "The plugin does not call a provider SDK, request a provider API key, select a hidden model, or silently fall back to a CLI client.",
        ],
    }
