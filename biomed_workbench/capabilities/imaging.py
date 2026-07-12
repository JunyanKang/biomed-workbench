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
        components.append(
            {
                "label": label,
                "area": area,
                "centroid": {"row": math.fsum(row + 1 for row, _column in pixels) / area, "column": math.fsum(column + 1 for _row, column in pixels) / area},
                "bounding_box": {
                    "min_row": min(row for row, _column in pixels) + 1,
                    "min_column": min(column for _row, column in pixels) + 1,
                    "max_row": max(row for row, _column in pixels) + 1,
                    "max_column": max(column for _row, column in pixels) + 1,
                },
                "perimeter": perimeter,
                "circularity": 4.0 * math.pi * area / perimeter**2 if perimeter else None,
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
