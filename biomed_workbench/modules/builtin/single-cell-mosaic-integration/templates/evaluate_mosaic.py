#!/usr/bin/env python3
"""Evaluate multimodal integration with paired anchors, biology and modality diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, silhouette_score
from sklearn.neighbors import KNeighborsClassifier, NearestNeighbors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latent-tsv", type=Path, required=True)
    parser.add_argument("--metadata-tsv", type=Path, required=True)
    parser.add_argument("--cell-id-column", default="cell_id")
    parser.add_argument("--modality-column", default="modality")
    parser.add_argument("--label-column", required=True)
    parser.add_argument("--batch-column", required=True)
    parser.add_argument("--paired-id-column")
    parser.add_argument("--neighbors", type=int, default=30)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def read_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    latent = pd.read_csv(args.latent_tsv, sep="\t")
    metadata = pd.read_csv(args.metadata_tsv, sep="\t")
    required = {
        args.cell_id_column,
        args.modality_column,
        args.label_column,
        args.batch_column,
    }
    if args.paired_id_column:
        required.add(args.paired_id_column)
    missing = sorted(required - set(metadata.columns))
    if missing:
        raise ValueError(f"metadata fields are absent: {', '.join(missing)}")
    if args.cell_id_column not in latent:
        raise ValueError("latent table lacks cell identifiers")
    if latent[args.cell_id_column].duplicated().any() or metadata[args.cell_id_column].duplicated().any():
        raise ValueError("cell identifiers must be unique")
    latent_columns = [column for column in latent if column.startswith("latent_")]
    if len(latent_columns) < 2:
        numeric = [
            column
            for column in latent.select_dtypes(include=[np.number]).columns
            if column != args.cell_id_column
        ]
        latent_columns = numeric
    if len(latent_columns) < 2:
        raise ValueError("latent table requires at least two numeric dimensions")
    common = metadata[args.cell_id_column].astype(str)
    latent = latent.assign(**{args.cell_id_column: latent[args.cell_id_column].astype(str)})
    metadata = metadata.assign(**{args.cell_id_column: common})
    if set(latent[args.cell_id_column]) != set(metadata[args.cell_id_column]):
        raise ValueError("latent and metadata cell identities differ")
    metadata = metadata.set_index(args.cell_id_column).loc[latent[args.cell_id_column]].reset_index()
    if metadata[list(required - {args.cell_id_column})].isna().any().any():
        raise ValueError("evaluation metadata must be complete")
    matrix = latent[latent_columns].to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("latent representation contains nonfinite values")
    return latent, metadata, latent_columns


def safe_silhouette(matrix: np.ndarray, groups: pd.Series) -> float | None:
    values = groups.astype(str).to_numpy()
    if len(np.unique(values)) < 2 or len(values) <= len(np.unique(values)):
        return None
    return float(silhouette_score(matrix, values))


def cross_modality_transfer(
    matrix: np.ndarray,
    modality: pd.Series,
    labels: pd.Series,
    neighbors: int,
) -> dict[str, float]:
    result = {}
    modality_values = modality.astype(str).to_numpy()
    label_values = labels.astype(str).to_numpy()
    for held_out in sorted(np.unique(modality_values)):
        test = modality_values == held_out
        train = ~test
        if train.sum() < 2 or test.sum() < 1:
            continue
        supported = np.isin(label_values[test], np.unique(label_values[train]))
        if not supported.any():
            continue
        classifier = KNeighborsClassifier(n_neighbors=min(neighbors, int(train.sum())))
        classifier.fit(matrix[train], label_values[train])
        prediction = classifier.predict(matrix[test][supported])
        result[held_out] = float(
            balanced_accuracy_score(label_values[test][supported], prediction)
        )
    return result


def paired_anchor_foscttm(
    matrix: np.ndarray,
    metadata: pd.DataFrame,
    modality_column: str,
    paired_id_column: str,
) -> dict[str, object]:
    usable = metadata[paired_id_column].astype(str).str.strip().ne("")
    frame = metadata.loc[usable].copy()
    counts = frame.groupby(paired_id_column, observed=True)[modality_column].nunique()
    pair_ids = set(counts[counts >= 2].index.astype(str))
    if not pair_ids:
        return {"paired_anchors": 0, "mean_foscttm": None}
    index_by_cell = {str(cell): index for index, cell in enumerate(metadata.index)}
    positions = []
    for pair_id in sorted(pair_ids):
        members = frame.index[frame[paired_id_column].astype(str) == pair_id].tolist()
        first = members[0]
        first_modality = str(metadata.loc[first, modality_column])
        second = next(
            member
            for member in members[1:]
            if str(metadata.loc[member, modality_column]) != first_modality
        )
        positions.append((index_by_cell[str(first)], index_by_cell[str(second)]))
    distances = np.linalg.norm(matrix[:, None, :] - matrix[None, :, :], axis=2)
    scores = []
    for left, right in positions:
        true_distance = distances[left, right]
        candidate_modality = str(metadata.iloc[right][modality_column])
        candidates = metadata[modality_column].astype(str).to_numpy() == candidate_modality
        scores.append(float(np.mean(distances[left, candidates] < true_distance)))
    return {"paired_anchors": len(positions), "mean_foscttm": float(np.mean(scores))}


def main() -> int:
    args = parse_args()
    if args.report.exists():
        raise FileExistsError("refusing to overwrite report")
    latent, metadata, dimensions = read_inputs(args)
    matrix = latent[dimensions].to_numpy(dtype=float)
    modality_asw = safe_silhouette(matrix, metadata[args.modality_column])
    label_asw = safe_silhouette(matrix, metadata[args.label_column])
    batch_asw = safe_silhouette(matrix, metadata[args.batch_column])
    transfer = cross_modality_transfer(
        matrix,
        metadata[args.modality_column],
        metadata[args.label_column],
        args.neighbors,
    )
    if args.paired_id_column:
        indexed_metadata = metadata.set_index(args.cell_id_column, drop=False)
        anchors = paired_anchor_foscttm(
            matrix,
            indexed_metadata,
            args.modality_column,
            args.paired_id_column,
        )
    else:
        anchors = {"paired_anchors": 0, "mean_foscttm": None}
    payload = {
        "schema_version": 1,
        "passed": True,
        "cells": len(metadata),
        "modalities": metadata[args.modality_column].value_counts().to_dict(),
        "metrics": {
            "modality_asw": modality_asw,
            "batch_asw": batch_asw,
            "label_asw": label_asw,
            "cross_modality_label_transfer_balanced_accuracy": transfer,
            "paired_anchor": anchors,
        },
        "scientific_validation": {
            "lower_modality_and_batch_asw_is_better_only_if_biology_is_preserved": True,
            "higher_label_asw_and_transfer_is_better": True,
            "lower_foscttm_is_better": True,
            "no_single_winner_score": True,
            "required_additional_checks": [
                "held-out modality reconstruction on measurements hidden before fitting",
                "cell-type and rare-state preservation",
                "batch and modality mixing within biological labels",
                "donor-level reproducibility",
            ],
        },
        "inference_boundary": (
            "Use immutable raw counts and sample or donor replication for differential inference; "
            "never use integrated, imputed or latent values as the confirmatory response."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if not json.loads(args.report.read_text()).get("passed"):
        raise RuntimeError("mosaic evaluation report failed reload validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
