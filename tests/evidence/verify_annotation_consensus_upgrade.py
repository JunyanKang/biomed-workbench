#!/usr/bin/env python3
"""Upgrade preserved atlas-backend evidence with observed five-backend consensus execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


MODULE_ID = "single-cell-atlas-annotation"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
CONSENSUS_TEMPLATE = MODULE_ROOT / "templates" / "reconcile_annotation_consensus.py"
UNCHANGED_TEMPLATES = {
    "celltypist": MODULE_ROOT / "templates" / "annotate_celltypist.py",
    "azimuth": MODULE_ROOT / "templates" / "annotate_azimuth.R",
    "popv": MODULE_ROOT / "templates" / "annotate_popv.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str]) -> None:
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=300
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"annotation consensus failed ({completed.returncode})\n"
            f"stderr:\n{completed.stderr[-6000:]}\nstdout:\n{completed.stdout[-3000:]}"
        )


def verify(base_report_path: Path, scientific_python: Path) -> dict[str, object]:
    base = json.loads(base_report_path.read_text(encoding="utf-8"))
    if (
        base.get("passed") is not True
        or base.get("module_id") != MODULE_ID
        or base.get("module_version") != "1.0.0"
    ):
        raise RuntimeError("base report is not the passing atlas annotation 1.0.0 evidence")
    for key, template in UNCHANGED_TEMPLATES.items():
        if base["templates"][key]["sha256"] != sha256(template):
            raise RuntimeError(f"preserved {key} execution evidence is stale")

    python = scientific_python.expanduser().absolute()
    if not python.exists() or not os.access(python, os.X_OK):
        raise RuntimeError("scientific Python must be executable")
    with tempfile.TemporaryDirectory(prefix="biomed-annotation-consensus-") as temporary:
        work = Path(temporary)
        genes = [f"Gene{index:02d}" for index in range(20)]
        cells = [f"cell-{index:02d}" for index in range(12)]
        counts = sparse.csr_matrix(np.arange(240, dtype=np.int32).reshape(12, 20) % 7)
        query = ad.AnnData(counts, obs=pd.DataFrame(index=cells), var=pd.DataFrame(index=genes))
        query.layers["counts"] = counts.copy()
        query_path = work / "query.h5ad"
        query.write_h5ad(query_path)
        query_digest = sha256(query_path)

        backends = ("celltypist", "azimuth", "popv", "singler", "scanvi")
        labels = {
            "celltypist": ["TypeA"] * 4 + ["TypeB"] * 4 + ["TypeC", "TypeA", "TypeB", "TypeC"],
            "azimuth": ["TypeA"] * 4 + ["TypeB"] * 4 + ["TypeC", "TypeB", "TypeA", "TypeC"],
            "popv": ["TypeA"] * 4 + ["TypeB"] * 4 + ["TypeC", "TypeA", "TypeB", "TypeC"],
            "singler": ["TypeA"] * 4 + ["TypeB"] * 4 + ["TypeC", "TypeB", "TypeA", "TypeC"],
            "scanvi": ["TypeA"] * 4 + ["TypeB"] * 4 + ["TypeC", "TypeA", "TypeA", "TypeC"],
        }
        confidence = {
            backend: [0.94] * 8 + [0.92, 0.9, 0.9, 0.42]
            for backend in backends
        }
        statuses = {
            backend: ["mapped"] * 10 + (["mapped", "rejected"] if backend != "singler" else ["unmapped", "rejected"])
            for backend in backends
        }
        label_map = {
            "TypeA": {"label": "TypeA", "ontology_id": "CL:0000001"},
            "TypeB": {"label": "TypeB", "ontology_id": "CL:0000002"},
            "TypeC": {"label": "TypeC", "ontology_id": "CL:0000003"},
        }
        methods = []
        for backend in backends:
            path = work / f"{backend}.tsv"
            pd.DataFrame({
                "cell_id": cells,
                "label": labels[backend],
                "confidence": confidence[backend],
                "status": statuses[backend],
            }).to_csv(path, sep="\t", index=False)
            methods.append({
                "backend": backend,
                "path": str(path),
                "source_kind": "tsv",
                "cell_id_column": "cell_id",
                "label_column": "label",
                "confidence_column": "confidence",
                "status_column": "status",
                "accepted_statuses": ["mapped"],
                "label_map": label_map,
                "weight": 1.0,
            })
        manifest_path = work / "manifest.json"
        manifest_path.write_text(json.dumps({"schema_version": 1, "methods": methods}), encoding="utf-8")
        consensus, evidence, report_path = work / "consensus.tsv", work / "evidence.tsv", work / "report.json"
        environment = {
            **os.environ,
            "PATH": str(python.parent) + os.pathsep + os.environ.get("PATH", ""),
            "PYTHONHASHSEED": "0",
        }
        run([
            str(python), str(CONSENSUS_TEMPLATE),
            "--query-h5ad", str(query_path),
            "--evidence-manifest", str(manifest_path),
            "--output-consensus", str(consensus),
            "--output-evidence", str(evidence),
            "--report", str(report_path),
            "--minimum-methods", "3",
            "--minimum-agreement", "0.6",
            "--minimum-weighted-support", "0.6",
            "--minimum-confidence", "0.5",
        ], environment)
        consensus_report = json.loads(report_path.read_text(encoding="utf-8"))
        consensus_table = pd.read_csv(consensus, sep="\t", keep_default_na=False)
        if sha256(query_path) != query_digest:
            raise RuntimeError("consensus execution modified the query object")
        if (
            len(consensus_table) != 12
            or consensus_report["results"]["accepted"] != 10
            or consensus_report["results"]["unknown"] != 2
            or set(consensus_report["manifest"]["backends"]) != set(backends)
            or not all(consensus_report["quality"].values())
        ):
            raise RuntimeError("five-backend consensus failed acceptance, unknown-retention, or quality gates")

        upgraded = dict(base)
        upgraded["module_version"] = "1.1.0"
        upgraded["compatibility_row_id"] = "agent-protocol-1-celltypist-171-popv-061-azimuth-051-consensus"
        upgraded["registry_digest"] = ModuleRegistry.discover(BUILTIN_ROOT).digest
        upgraded["templates"] = {
            **base["templates"],
            "consensus": {"name": CONSENSUS_TEMPLATE.name, "sha256": sha256(CONSENSUS_TEMPLATE)},
        }
        upgraded["execution"] = {
            **base["execution"],
            "consensus_completed": True,
        }
        upgraded["scientific_summary"] = {
            **base["scientific_summary"],
            "cross_backend_consensus_executed": True,
            "consensus_conflicts_retained_as_unknown": True,
            "consensus_ontology_ids_required": True,
        }
        upgraded["consensus_verification"] = {
            "backends": list(backends),
            "cells": 12,
            "accepted": 10,
            "unknown": 2,
            "evidence_rows": 60,
            "query_sha256": query_digest,
            "analysis_report_sha256": sha256(report_path),
            "consensus_sha256": sha256(consensus),
            "evidence_sha256": sha256(evidence),
            "source_query_immutable": True,
            "outputs_reloaded": True,
            "base_backend_evidence_preserved_by_template_hash": True,
        }
        return upgraded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-report", type=Path, required=True)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.base_report, args.scientific_python)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "consensus": report["consensus_verification"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
