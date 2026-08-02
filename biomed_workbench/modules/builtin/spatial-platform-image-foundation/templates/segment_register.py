#!/usr/bin/env python3
"""Segment a SpatialData image or register it from paired landmarks.

The template exposes Squidpy watershed/Cellpose segmentation and SpatialData
transform metadata. Landmark registration estimates a declared transform,
records its residual error, and writes it to a named coordinate system.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import numpy as np
from pathlib import Path


def spatial_elements(sdata) -> dict[str, list[str]]:
    """Return a stable inventory used before and after image operations."""
    return {
        "images": sorted(sdata.images),
        "labels": sorted(sdata.labels),
        "shapes": sorted(sdata.shapes),
        "tables": sorted(sdata.tables),
    }


def digest_directory(path: Path) -> str:
    value = hashlib.sha256()
    for item in sorted(entry for entry in path.rglob("*") if entry.is_file()):
        value.update(item.relative_to(path).as_posix().encode())
        value.update(b"\0")
        value.update(hashlib.sha256(item.read_bytes()).digest())
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("segment-watershed", "segment-cellpose", "register-landmarks"), required=True)
    parser.add_argument("--input-spatialdata", type=Path, required=True)
    parser.add_argument("--output-spatialdata", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--image-key", required=True)
    parser.add_argument("--channel")
    parser.add_argument("--scale-level", default="scale0")
    parser.add_argument("--layer-added", required=True)
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--min-size", type=int, default=20)
    parser.add_argument("--cellpose-model", default="nuclei")
    parser.add_argument("--diameter", type=float)
    parser.add_argument("--landmarks-tsv", type=Path)
    parser.add_argument("--transform-family", choices=("affine", "similarity", "projective"), default="affine")
    parser.add_argument("--registration-coordinate-system", default="landmark_registered")
    args = parser.parse_args()
    if args.output_spatialdata.exists() or args.report.exists():
        raise FileExistsError("refusing to overwrite output")
    from spatialdata import read_zarr
    sdata = read_zarr(args.input_spatialdata)
    before = spatial_elements(sdata)
    diagnostics = {}
    if args.mode.startswith("segment"):
        import squidpy as sq
        from spatialdata.models import Labels2DModel
        from spatialdata.transformations import get_transformation

        if args.image_key not in sdata.images:
            raise ValueError(f"image element is absent: {args.image_key}")
        image_element = sdata.images[args.image_key]
        if hasattr(image_element, "children"):
            if args.scale_level not in image_element.children:
                raise ValueError(f"image scale is absent: {args.scale_level}")
            image = image_element[args.scale_level]["image"]
        else:
            image = image_element
        channel = 0
        if args.channel is not None:
            if args.channel.isdigit():
                channel = int(args.channel)
            elif "c" in image.coords:
                names = list(map(str, image.coords["c"].values))
                if args.channel not in names:
                    raise ValueError(f"channel is absent; choose from {names}")
                channel = names.index(args.channel)
            else:
                raise ValueError("named channel requested but the image has no channel labels")
        container = sq.im.ImageContainer(image, layer="image")
        method = "watershed" if args.mode == "segment-watershed" else "cellpose"
        kwargs = {"method": method, "layer": "image", "layer_added": args.layer_added, "channel": channel, "copy": False}
        if method == "watershed":
            kwargs["thresh"] = args.threshold
            kwargs["min_size"] = args.min_size
        else:
            kwargs["model"] = args.cellpose_model
            if args.diameter is not None:
                kwargs["diameter"] = args.diameter
        sq.im.segment(container, **kwargs)
        labels = container[args.layer_added].squeeze(drop=True).astype(np.uint32)
        labels.name = args.layer_added
        transformations = get_transformation(image, get_all=True)
        sdata.labels[args.layer_added] = Labels2DModel.parse(labels, transformations=transformations)
        label_values = np.asarray(labels.data.compute() if hasattr(labels.data, "compute") else labels.data)
        label_count = int(np.unique(label_values[label_values > 0]).size)
        if label_count < 1:
            raise RuntimeError("segmentation produced no foreground objects")
        diagnostics["segmentation_parameters"] = {**kwargs, "source_image": args.image_key, "scale_level": args.scale_level, "channel_name": args.channel}
        diagnostics["segmented_objects"] = label_count
    elif args.mode == "register-landmarks":
        if args.landmarks_tsv is None:
            raise ValueError("landmark registration requires --landmarks-tsv")
        import pandas as pd
        from skimage.transform import estimate_transform
        from spatialdata.transformations import Affine, set_transformation

        if args.image_key not in sdata.images:
            raise ValueError(f"image element is absent: {args.image_key}")
        landmarks = pd.read_csv(args.landmarks_tsv, sep="\t")
        required = ["moving_x", "moving_y", "fixed_x", "fixed_y"]
        absent = [column for column in required if column not in landmarks]
        if absent:
            raise ValueError(f"landmark table is missing columns: {absent}")
        minimum = 4 if args.transform_family == "projective" else 3
        if len(landmarks) < minimum:
            raise ValueError(f"{args.transform_family} registration requires at least {minimum} paired landmarks")
        moving = landmarks[["moving_x", "moving_y"]].to_numpy(dtype=float)
        fixed = landmarks[["fixed_x", "fixed_y"]].to_numpy(dtype=float)
        if not np.isfinite(moving).all() or not np.isfinite(fixed).all():
            raise ValueError("landmark coordinates must be finite")
        transform = estimate_transform(args.transform_family, src=moving, dst=fixed)
        projected = transform(moving)
        errors = np.sqrt(np.square(projected - fixed).sum(axis=1))
        if not np.isfinite(errors).all():
            raise RuntimeError("landmark transform produced non-finite residuals")
        spatial_transform = Affine(
            transform.params,
            input_axes=("x", "y"),
            output_axes=("x", "y"),
        )
        set_transformation(
            sdata.images[args.image_key],
            spatial_transform,
            to_coordinate_system=args.registration_coordinate_system,
        )
        diagnostics["registration"] = {
            "source_image": args.image_key,
            "coordinate_system": args.registration_coordinate_system,
            "transform_family": args.transform_family,
            "landmark_pairs": int(len(landmarks)),
            "matrix": transform.params.tolist(),
            "residual_rmse": float(np.sqrt(np.mean(np.square(errors)))),
            "residual_median": float(np.median(errors)),
            "residual_maximum": float(np.max(errors)),
        }
    args.output_spatialdata.parent.mkdir(parents=True, exist_ok=True)
    sdata.write(args.output_spatialdata)
    after = spatial_elements(sdata)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    reloaded = read_zarr(args.output_spatialdata)
    if args.mode.startswith("segment") and args.layer_added not in reloaded.labels:
        raise RuntimeError("segmentation label failed SpatialData reload validation")
    if args.mode == "register-landmarks":
        from spatialdata.transformations import get_transformation

        reloaded_transformations = get_transformation(reloaded.images[args.image_key], get_all=True)
        if args.registration_coordinate_system not in reloaded_transformations:
            raise RuntimeError("landmark transformation failed SpatialData reload validation")
    report = {
        "schema_version": 1,
        "passed": True,
        "mode": args.mode,
        "before": before,
        "after": after,
        "diagnostics": diagnostics,
        "runtime": {
            "spatialdata": importlib.metadata.version("spatialdata"),
            "squidpy": importlib.metadata.version("squidpy") if args.mode.startswith("segment") else None,
        },
        "output_spatialdata_sha256": digest_directory(args.output_spatialdata),
        "output_reloaded": True,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
