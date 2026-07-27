"""Strict read-only extraction of enhancer-promoter contact candidates from .cool HDF5."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import h5py
import numpy as np


class CoolContactError(ValueError):
    """Raised when a .cool contact or regulatory-element contract is invalid."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def regulatory_elements(path: Path) -> list[dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise CoolContactError("regulatory-elements BED must be a stable non-symlink file")
    rows = []
    identifiers = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip() or raw.startswith(("#", "track", "browser")):
                continue
            fields = raw.rstrip("\n").split("\t")
            if len(fields) < 5:
                raise CoolContactError("regulatory-elements BED requires chrom, start, end, id, and explicit element_type columns")
            chrom, start_text, end_text, identifier, element_type = fields[:5]
            try:
                start, end = int(start_text), int(end_text)
            except ValueError as exc:
                raise CoolContactError(f"regulatory element line {line_number} has noninteger coordinates") from exc
            if not chrom or start < 0 or end <= start or not identifier or identifier in identifiers or element_type not in {"enhancer", "promoter"}:
                raise CoolContactError(f"regulatory element line {line_number} has invalid coordinates, id, or element_type")
            rows.append({"chrom": chrom, "start": start, "end": end, "id": identifier, "element_type": element_type, "midpoint": (start + end) // 2})
            identifiers.add(identifier)
    if not rows or not any(row["element_type"] == "enhancer" for row in rows) or not any(row["element_type"] == "promoter" for row in rows):
        raise CoolContactError("regulatory elements must contain at least one explicit enhancer and promoter")
    return rows


def _dataset(handle: h5py.File, name: str) -> np.ndarray:
    if name not in handle:
        raise CoolContactError(f".cool file lacks required dataset: {name}")
    return np.asarray(handle[name])


def cool_contact_candidates(cool_path: Path, elements_path: Path, *, max_candidates: int = 10000) -> dict[str, Any]:
    """Return all bounded same-chromosome enhancer-promoter contact candidates.

    The function reports raw count and observed-over-distance-median only. It
    deliberately performs no loop calling, p-value calculation, TAD detection,
    or biological assignment.
    """
    if cool_path.is_symlink() or not cool_path.is_file() or max_candidates < 1 or max_candidates > 100000:
        raise CoolContactError(".cool input must be a stable file and max_candidates must be 1..100000")
    elements = regulatory_elements(elements_path)
    cool_digest = sha256(cool_path)
    element_digest = sha256(elements_path)
    with h5py.File(cool_path, "r") as handle:
        format_name = decode(handle.attrs.get("format", ""))
        if format_name.lower() != "hdf5::cooler":
            raise CoolContactError("input does not declare the HDF5::Cooler format")
        chrom_names = [decode(item) for item in _dataset(handle, "chroms/name")]
        chrom_lengths = _dataset(handle, "chroms/length").astype(np.int64)
        bin_chrom = _dataset(handle, "bins/chrom").astype(np.int64)
        bin_start = _dataset(handle, "bins/start").astype(np.int64)
        bin_end = _dataset(handle, "bins/end").astype(np.int64)
        pixel_bin1 = _dataset(handle, "pixels/bin1_id").astype(np.int64)
        pixel_bin2 = _dataset(handle, "pixels/bin2_id").astype(np.int64)
        pixel_count = _dataset(handle, "pixels/count").astype(float)
        declared_bin_size = int(handle.attrs["bin-size"]) if "bin-size" in handle.attrs else None
    if not (len(chrom_names) == len(chrom_lengths) and len(bin_chrom) == len(bin_start) == len(bin_end)):
        raise CoolContactError(".cool chromosome or bin arrays are structurally inconsistent")
    if not (len(pixel_bin1) == len(pixel_bin2) == len(pixel_count)) or np.any(pixel_bin1 < 0) or np.any(pixel_bin2 < pixel_bin1) or np.any(pixel_bin2 >= len(bin_chrom)) or np.any(~np.isfinite(pixel_count)) or np.any(pixel_count < 0):
        raise CoolContactError(".cool pixel arrays are structurally invalid")
    bins_by_chrom: dict[str, list[tuple[int, int, int]]] = {name: [] for name in chrom_names}
    for index, (chrom_index, start, end) in enumerate(zip(bin_chrom, bin_start, bin_end)):
        if chrom_index < 0 or chrom_index >= len(chrom_names) or start < 0 or end <= start:
            raise CoolContactError(".cool bins contain invalid chromosome or coordinates")
        bins_by_chrom[chrom_names[chrom_index]].append((int(start), int(end), index))
    element_bins = []
    for row in elements:
        matches = [identifier for start, end, identifier in bins_by_chrom.get(row["chrom"], []) if start <= row["midpoint"] < end]
        if len(matches) != 1:
            raise CoolContactError(f"regulatory element {row['id']} does not map to exactly one .cool bin")
        element_bins.append({**row, "bin_id": matches[0]})
    diagonal_counts: dict[tuple[int, int], list[float]] = {}
    contacts: dict[tuple[int, int], float] = {}
    for first, second, count in zip(pixel_bin1, pixel_bin2, pixel_count):
        first_chrom = int(bin_chrom[first])
        second_chrom = int(bin_chrom[second])
        if first_chrom != second_chrom:
            continue
        distance = abs(int(first) - int(second))
        diagonal_counts.setdefault((first_chrom, distance), []).append(float(count))
        contacts[(int(first), int(second))] = float(count)
    expected = {key: float(np.median(values)) for key, values in diagonal_counts.items() if values}
    candidates = []
    for enhancer in (row for row in element_bins if row["element_type"] == "enhancer"):
        for promoter in (row for row in element_bins if row["element_type"] == "promoter" and row["chrom"] == enhancer["chrom"]):
            first, second = sorted((enhancer["bin_id"], promoter["bin_id"]))
            distance_bins = second - first
            if distance_bins == 0:
                continue
            observed = contacts.get((first, second), 0.0)
            baseline = expected.get((int(bin_chrom[first]), distance_bins))
            candidates.append({"chrom": enhancer["chrom"], "enhancer_id": enhancer["id"], "enhancer_bin_id": enhancer["bin_id"], "promoter_id": promoter["id"], "promoter_bin_id": promoter["bin_id"], "distance_bp": abs(enhancer["midpoint"] - promoter["midpoint"]), "distance_bins": distance_bins, "observed_count": observed, "distance_median_count": baseline, "observed_over_distance_median": observed / baseline if baseline and baseline > 0 else None})
    candidates.sort(key=lambda row: (-(row["observed_over_distance_median"] or 0), -row["observed_count"], row["enhancer_id"], row["promoter_id"]))
    return {"cool": {"sha256": cool_digest, "format": "HDF5::Cooler", "chromosome_count": len(chrom_names), "bin_count": len(bin_chrom), "pixel_count": len(pixel_bin1), "bin_size": declared_bin_size}, "regulatory_elements": {"sha256": element_digest, "count": len(element_bins), "enhancer_count": sum(row["element_type"] == "enhancer" for row in element_bins), "promoter_count": sum(row["element_type"] == "promoter" for row in element_bins)}, "candidate_count": len(candidates), "returned_candidate_count": min(len(candidates), max_candidates), "truncated": len(candidates) > max_candidates, "candidates": candidates[:max_candidates], "limitations": ["Candidates provide raw contact and distance-stratified descriptive evidence only; they are not loop calls or statistically significant interactions.", "This extraction does not balance matrices, call TADs, control for copy number or coverage, perform replicate concordance, or establish enhancer-promoter regulation."]}
