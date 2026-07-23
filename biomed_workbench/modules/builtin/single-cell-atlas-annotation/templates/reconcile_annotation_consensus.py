#!/usr/bin/env python3
"""Reconcile multiple cell-annotation backends without forcing unsupported labels.

The evidence manifest is project-specific. Codex must build it only after
inspecting and freezing each backend's score semantics, label map, reference
scope, and rejection status.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd


SUPPORTED_BACKENDS = {"celltypist", "azimuth", "popv", "singler", "scanvi"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-h5ad", required=True)
    parser.add_argument("--evidence-manifest", required=True)
    parser.add_argument("--output-consensus", required=True)
    parser.add_argument("--output-evidence", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--unknown-label", default="Unknown")
    parser.add_argument("--minimum-methods", type=int, required=True)
    parser.add_argument("--minimum-agreement", type=float, required=True)
    parser.add_argument("--minimum-weighted-support", type=float, required=True)
    parser.add_argument("--minimum-confidence", type=float, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("methods"), list):
        raise ValueError("evidence manifest must use schema version 1 and declare methods")
    methods = payload["methods"]
    backends = [item.get("backend") for item in methods if isinstance(item, dict)]
    if (
        len(methods) < 2
        or len(backends) != len(methods)
        or len(set(backends)) != len(backends)
        or not set(backends) <= SUPPORTED_BACKENDS
    ):
        raise ValueError("evidence manifest requires two or more unique supported backends")
    return payload


def read_method(method: dict[str, object], query_cells: pd.Index) -> pd.DataFrame:
    backend = str(method["backend"])
    source = Path(str(method["path"])).expanduser().resolve(strict=True)
    source_kind = method.get("source_kind")
    label_column = str(method.get("label_column", ""))
    confidence_column = str(method.get("confidence_column", ""))
    status_column = str(method.get("status_column", ""))
    if not label_column or not confidence_column or not status_column:
        raise ValueError(f"{backend} must declare label, normalized confidence, and status columns")
    if source_kind == "tsv":
        cell_column = str(method.get("cell_id_column", ""))
        frame = pd.read_csv(source, sep="\t", dtype={cell_column: str})
        if not cell_column or cell_column not in frame:
            raise ValueError(f"{backend} TSV lacks its declared cell identifier")
        frame = frame.set_index(cell_column)
    elif source_kind == "h5ad_obs":
        frame = ad.read_h5ad(source, backed="r").obs.copy()
    else:
        raise ValueError(f"{backend} source_kind must be tsv or h5ad_obs")
    required = {label_column, confidence_column, status_column}
    if not required <= set(frame.columns) or not frame.index.is_unique:
        raise ValueError(f"{backend} evidence columns or cell identities are invalid")
    unexpected = frame.index.difference(query_cells)
    if len(unexpected):
        raise ValueError(f"{backend} contains cells absent from the query")

    accepted_statuses = method.get("accepted_statuses")
    label_map = method.get("label_map")
    weight = method.get("weight", 1.0)
    if (
        not isinstance(accepted_statuses, list)
        or not accepted_statuses
        or not isinstance(label_map, dict)
        or not isinstance(weight, (int, float))
        or not np.isfinite(weight)
        or weight <= 0
    ):
        raise ValueError(f"{backend} status, label-map, or weight contract is invalid")
    result = frame.reindex(query_cells)[[label_column, confidence_column, status_column]].copy()
    result.columns = ["raw_label", "normalized_confidence", "raw_status"]
    result["normalized_confidence"] = pd.to_numeric(
        result["normalized_confidence"], errors="coerce"
    )
    finite = result["normalized_confidence"].dropna()
    if ((finite < 0) | (finite > 1) | ~np.isfinite(finite)).any():
        raise ValueError(f"{backend} normalized confidence must be within zero and one")

    canonical_labels, ontology_ids, map_status = [], [], []
    for raw_label in result["raw_label"]:
        if pd.isna(raw_label):
            canonical_labels.append(None)
            ontology_ids.append(None)
            map_status.append("missing-label")
            continue
        mapping = label_map.get(str(raw_label))
        if not isinstance(mapping, dict):
            canonical_labels.append(None)
            ontology_ids.append(None)
            map_status.append("unmapped-label")
            continue
        label, ontology_id = mapping.get("label"), mapping.get("ontology_id")
        if not isinstance(label, str) or not label.strip() or not isinstance(ontology_id, str) or not ontology_id.strip():
            raise ValueError(f"{backend} label map entries require canonical label and ontology_id")
        canonical_labels.append(label.strip())
        ontology_ids.append(ontology_id.strip())
        map_status.append("mapped")
    result["canonical_label"] = canonical_labels
    result["ontology_id"] = ontology_ids
    result["label_map_status"] = map_status
    result["backend"] = backend
    result["backend_weight"] = float(weight)
    result["backend_accepted"] = result["raw_status"].astype(str).isin(map(str, accepted_statuses))
    result["source_filename"] = source.name
    result["source_sha256"] = sha256(source)
    result.index.name = "cell_id"
    return result.reset_index()


def decide_cell(
    frame: pd.DataFrame,
    *,
    unknown_label: str,
    minimum_methods: int,
    minimum_agreement: float,
    minimum_weighted_support: float,
    minimum_confidence: float,
) -> dict[str, object]:
    usable = frame.loc[
        frame["backend_accepted"]
        & frame["canonical_label"].notna()
        & frame["normalized_confidence"].notna()
        & frame["normalized_confidence"].ge(minimum_confidence)
        & frame["canonical_label"].ne(unknown_label)
    ].copy()
    if usable.empty:
        return {
            "consensus_label": unknown_label,
            "ontology_id": "",
            "status": "unknown",
            "reason": "no-usable-method-evidence",
            "usable_methods": 0,
            "agreeing_methods": 0,
            "agreement_fraction": 0.0,
            "weighted_support": 0.0,
        }
    usable["vote_weight"] = usable["backend_weight"] * usable["normalized_confidence"]
    grouped = (
        usable.groupby(["canonical_label", "ontology_id"], dropna=False)
        .agg(agreeing_methods=("backend", "nunique"), vote_weight=("vote_weight", "sum"))
        .reset_index()
        .sort_values(["agreeing_methods", "vote_weight", "canonical_label"], ascending=[False, False, True])
    )
    top = grouped.iloc[0]
    tied = (
        len(grouped) > 1
        and grouped.iloc[1]["agreeing_methods"] == top["agreeing_methods"]
        and np.isclose(grouped.iloc[1]["vote_weight"], top["vote_weight"], rtol=0, atol=1e-12)
    )
    usable_methods = int(usable["backend"].nunique())
    agreeing_methods = int(top["agreeing_methods"])
    agreement = agreeing_methods / usable_methods
    weighted_support = float(top["vote_weight"] / usable["vote_weight"].sum())
    reasons = []
    if tied:
        reasons.append("top-label-tie")
    if usable_methods < minimum_methods:
        reasons.append("insufficient-methods")
    if agreement < minimum_agreement:
        reasons.append("insufficient-agreement")
    if weighted_support < minimum_weighted_support:
        reasons.append("insufficient-weighted-support")
    if reasons:
        label, ontology_id, status = unknown_label, "", "unknown"
    else:
        label, ontology_id, status = str(top["canonical_label"]), str(top["ontology_id"]), "accepted"
    return {
        "consensus_label": label,
        "ontology_id": ontology_id,
        "status": status,
        "reason": ";".join(reasons) if reasons else "multi-method-consensus",
        "usable_methods": usable_methods,
        "agreeing_methods": agreeing_methods,
        "agreement_fraction": round(agreement, 8),
        "weighted_support": round(weighted_support, 8),
    }


def main() -> int:
    args = parse_args()
    if (
        args.minimum_methods < 2
        or not 0.5 <= args.minimum_agreement <= 1
        or not 0.5 <= args.minimum_weighted_support <= 1
        or not 0 <= args.minimum_confidence <= 1
        or not args.unknown_label.strip()
    ):
        raise ValueError("consensus thresholds or unknown label are invalid")
    query_path = Path(args.query_h5ad).resolve(strict=True)
    manifest_path = Path(args.evidence_manifest).resolve(strict=True)
    outputs = [Path(args.output_consensus), Path(args.output_evidence), Path(args.report)]
    if any(path.exists() for path in outputs):
        raise FileExistsError("refusing to overwrite an annotation consensus output")
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)

    query = ad.read_h5ad(query_path, backed="r")
    if query.n_obs < 1 or query.n_vars < 1 or not query.obs_names.is_unique:
        raise ValueError("query h5ad requires nonempty unique cell and feature identities")
    manifest = load_manifest(manifest_path)
    methods = [read_method(item, query.obs_names) for item in manifest["methods"]]
    evidence = pd.concat(methods, ignore_index=True)
    expected_rows = query.n_obs * len(methods)
    if len(evidence) != expected_rows or evidence.duplicated(["cell_id", "backend"]).any():
        raise RuntimeError("annotation method evidence failed complete cell accounting")

    decisions = []
    for cell_id, frame in evidence.groupby("cell_id", sort=False, observed=True):
        decisions.append({
            "cell_id": cell_id,
            **decide_cell(
                frame,
                unknown_label=args.unknown_label,
                minimum_methods=args.minimum_methods,
                minimum_agreement=args.minimum_agreement,
                minimum_weighted_support=args.minimum_weighted_support,
                minimum_confidence=args.minimum_confidence,
            ),
        })
    consensus = pd.DataFrame(decisions).set_index("cell_id").reindex(query.obs_names)
    consensus.index.name = "cell_id"
    consensus = consensus.reset_index()
    if len(consensus) != query.n_obs or consensus["cell_id"].duplicated().any() or consensus.isna().any().any():
        raise RuntimeError("annotation consensus failed query-cell reconciliation")
    evidence.to_csv(outputs[1], sep="\t", index=False)
    consensus.to_csv(outputs[0], sep="\t", index=False)
    reloaded_evidence = pd.read_csv(outputs[1], sep="\t")
    reloaded_consensus = pd.read_csv(outputs[0], sep="\t", keep_default_na=False)
    if len(reloaded_evidence) != expected_rows or len(reloaded_consensus) != query.n_obs:
        raise RuntimeError("annotation consensus outputs failed reload validation")

    accepted = consensus["status"].eq("accepted")
    report = {
        "schema_version": 1,
        "query": {
            "filename": query_path.name,
            "sha256": sha256(query_path),
            "cells": int(query.n_obs),
            "features": int(query.n_vars),
        },
        "manifest": {
            "filename": manifest_path.name,
            "sha256": sha256(manifest_path),
            "backends": [str(item["backend"]) for item in manifest["methods"]],
        },
        "thresholds": {
            "unknown_label": args.unknown_label,
            "minimum_methods": args.minimum_methods,
            "minimum_agreement": args.minimum_agreement,
            "minimum_weighted_support": args.minimum_weighted_support,
            "minimum_confidence": args.minimum_confidence,
        },
        "results": {
            "cells": int(len(consensus)),
            "accepted": int(accepted.sum()),
            "unknown": int((~accepted).sum()),
            "status_counts": consensus["status"].value_counts().sort_index().to_dict(),
            "reason_counts": consensus["reason"].value_counts().sort_index().to_dict(),
            "label_counts": consensus["consensus_label"].value_counts().sort_index().to_dict(),
        },
        "quality": {
            "all_query_cells_accounted": True,
            "all_backend_cell_slots_accounted": True,
            "raw_backend_evidence_retained": True,
            "ontology_ids_required_for_mapped_labels": True,
            "low_confidence_disagreement_and_ties_retained_as_unknown": True,
            "outputs_reloaded": True,
            "query_opened_read_only": True,
        },
        "outputs": {
            "consensus_filename": outputs[0].name,
            "consensus_sha256": sha256(outputs[0]),
            "evidence_filename": outputs[1].name,
            "evidence_sha256": sha256(outputs[1]),
        },
        "versions": {
            "python": platform.python_version(),
            "anndata": importlib.metadata.version("anndata"),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    }
    outputs[2].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["results"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
