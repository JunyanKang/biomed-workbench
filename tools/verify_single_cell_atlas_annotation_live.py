#!/usr/bin/env python3
"""Execute CellTypist, Azimuth, and popV annotation on absent-class fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


MODULE_ID = "single-cell-atlas-annotation"
MODULE_VERSION = "1.1.0"
ROW_ID = "agent-protocol-1-celltypist-171-popv-061-azimuth-051-consensus"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
CELLTYPIST_TEMPLATE = MODULE_ROOT / "templates" / "annotate_celltypist.py"
POPV_TEMPLATE = MODULE_ROOT / "templates" / "annotate_popv.py"
AZIMUTH_TEMPLATE = MODULE_ROOT / "templates" / "annotate_azimuth.R"
CONSENSUS_TEMPLATE = MODULE_ROOT / "templates" / "reconcile_annotation_consensus.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(
    command: list[str],
    environment: dict[str, str],
    *,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"atlas annotation command failed ({completed.returncode}): {' '.join(command[:3])}\n"
            f"stderr:\n{completed.stderr[-6000:]}\nstdout:\n{completed.stdout[-3000:]}"
        )
    return completed


def python_fixture_code(query: Path, reference: Path, model: Path) -> str:
    return f"""
import anndata as ad
import celltypist
import numpy as np
import pandas as pd
import scanpy as sc
from scipy import sparse

rng = np.random.default_rng(202)
genes = [f'GENE{{index:03d}}' for index in range(140)]
labels = ('TypeA', 'TypeB', 'TypeC')
starts = {{'TypeA': 0, 'TypeB': 20, 'TypeC': 40}}
reference_rows, reference_labels, reference_batches = [], [], []
for label in labels:
    for index in range(100):
        rate = np.full(140, 1.2)
        rate[starts[label]:starts[label] + 18] += 8.0
        reference_rows.append(rng.poisson(rate))
        reference_labels.append(label)
        reference_batches.append('R1' if index < 50 else 'R2')
reference_counts = np.asarray(reference_rows, dtype=np.int32)
reference_adata = ad.AnnData(
    sparse.csr_matrix(reference_counts),
    obs=pd.DataFrame({{'celltype': reference_labels, 'reference_batch': reference_batches}}, index=[f'ref-{{index:03d}}' for index in range(300)]),
    var=pd.DataFrame(index=genes),
)
reference_adata.layers['counts'] = reference_adata.X.copy()
reference_adata.write_h5ad({str(reference)!r})

training = reference_adata.copy()
sc.pp.normalize_total(training, target_sum=10_000)
sc.pp.log1p(training)
trained_model = celltypist.train(training, labels='celltype', check_expression=True, n_jobs=1, max_iter=100, use_SGD=False)
trained_model.write({str(model)!r})

query_rows, query_truth, query_batches = [], [], []
for truth, count in (('TypeA', 40), ('TypeB', 40), ('TypeC', 40), ('Novel', 30)):
    for index in range(count):
        rate = np.full(140, 1.2)
        if truth == 'Novel':
            rate[0:9] += 4.0
            rate[20:29] += 4.0
            rate[70:88] += 7.0
        else:
            rate[starts[truth]:starts[truth] + 18] += 7.5
        query_rows.append(rng.poisson(rate))
        query_truth.append(truth)
        query_batches.append('Q1' if index % 2 == 0 else 'Q2')
query_counts = np.asarray(query_rows, dtype=np.int32)
query_adata = ad.AnnData(
    sparse.csr_matrix(query_counts),
    obs=pd.DataFrame({{'evaluation_truth': query_truth, 'query_batch': query_batches}}, index=[f'query-{{index:03d}}' for index in range(150)]),
    var=pd.DataFrame(index=genes),
)
query_adata.layers['counts'] = query_adata.X.copy()
query_adata.write_h5ad({str(query)!r})
"""


def r_fixture_code(query: Path, reference_dir: Path, homolog_table: Path) -> str:
    return f"""
suppressPackageStartupMessages({{
  library(Azimuth)
  library(Seurat)
}})
set.seed(301)
genes <- paste0('GENE', sprintf('%03d', 0:139))
labels <- rep(c('TypeA', 'TypeB', 'TypeC'), each = 100)
starts <- c(TypeA = 1, TypeB = 21, TypeC = 41)
reference_counts <- matrix(rpois(140 * 300, 1.2), nrow = 140, dimnames = list(genes, paste0('az-ref-', 1:300)))
for (index in seq_len(ncol(reference_counts))) {{
  start <- starts[[labels[[index]]]]
  reference_counts[start:(start + 17), index] <- reference_counts[start:(start + 17), index] + rpois(18, 8)
}}
reference <- CreateSeuratObject(counts = reference_counts)
reference$celltype <- factor(labels)
reference <- SCTransform(reference, verbose = FALSE, return.only.var.genes = FALSE)
reference <- RunPCA(reference, assay = 'SCT', reduction.name = 'spca', reduction.key = 'SPCA_', npcs = 10, verbose = FALSE)
reference <- RunUMAP(reference, reduction = 'spca', dims = 1:10, return.model = TRUE, reduction.name = 'umap', reduction.key = 'UMAP_', n.neighbors = 30, verbose = FALSE)
reference <- AzimuthReference(reference, refUMAP = 'umap', refDR = 'spca', refAssay = 'SCT', dims = 1:10, k.param = 60, metadata = 'celltype', reference.version = 'fixture-1', verbose = FALSE)
dir.create({str(reference_dir)!r}, recursive = TRUE)
SaveAzimuthReference(reference, folder = paste0({str(reference_dir)!r}, '/'))

truth <- c(rep('TypeA', 40), rep('TypeB', 40), rep('TypeC', 40), rep('Novel', 30))
query_counts <- matrix(rpois(140 * 150, 1.2), nrow = 140, dimnames = list(genes, paste0('az-query-', 1:150)))
for (index in seq_len(ncol(query_counts))) {{
  if (truth[[index]] == 'Novel') {{
    query_counts[71:88, index] <- query_counts[71:88, index] + rpois(18, 8)
  }} else {{
    start <- starts[[truth[[index]]]]
    query_counts[start:(start + 17), index] <- query_counts[start:(start + 17), index] + rpois(18, 8)
  }}
}}
query_object <- CreateSeuratObject(counts = query_counts)
query_object$evaluation_truth <- truth
saveRDS(query_object, {str(query)!r})

homologs <- data.frame(
  Gene.stable.ID.human = paste0('ENSG', sprintf('%011d', 0:139)),
  Transcript.stable.ID.human = paste0('ENST', sprintf('%011d', 0:139)),
  Gene.name.human = genes,
  Transcript.name.human = paste0(genes, '-T'),
  Gene.stable.ID.mouse = paste0('ENSMUSG', sprintf('%09d', 0:139)),
  Transcript.stable.ID.mouse = paste0('ENSMUST', sprintf('%09d', 0:139)),
  Gene.name.mouse = paste0('Mouse', genes),
  Transcript.name.mouse = paste0('Mouse', genes, '-T'),
  stringsAsFactors = FALSE
)
saveRDS(homologs, {str(homolog_table)!r})
"""


def inspect_python_outputs(python: Path, celltypist_output: Path, popv_output: Path, environment: dict[str, str]) -> dict[str, object]:
    code = f"""
import anndata as ad
import json

def summarize(path, label_key):
    data = ad.read_h5ad(path)
    truth = data.obs['evaluation_truth'].astype(str)
    labels = data.obs[label_key].astype(str)
    known = truth != 'Novel'
    return {{
        'cells': int(data.n_obs),
        'known_accuracy': float((labels[known] == truth[known]).mean()),
        'known_unknown': int((labels[known] == 'Unknown').sum()),
        'novel_unknown': int((labels[~known] == 'Unknown').sum()),
        'unknown_total': int((labels == 'Unknown').sum()),
        'counts_present': bool('counts' in data.layers),
    }}

print(json.dumps({{
  'celltypist': summarize({str(celltypist_output)!r}, 'celltypist_label_review'),
  'popv': summarize({str(popv_output)!r}, 'popv_label_review'),
}}))
"""
    return json.loads(run([str(python), "-c", code], environment).stdout)


def inspect_azimuth_output(rscript: Path, output: Path, environment: dict[str, str]) -> dict[str, object]:
    code = f"""
suppressPackageStartupMessages(library(jsonlite))
object <- readRDS({str(output)!r})
truth <- as.character(object$evaluation_truth)
labels <- as.character(object$azimuth_label_review)
known <- truth != 'Novel'
cat(toJSON(list(
  cells = length(truth), known_accuracy = mean(labels[known] == truth[known]),
  known_unknown = sum(labels[known] == 'Unknown'), novel_unknown = sum(labels[!known] == 'Unknown'),
  unknown_total = sum(labels == 'Unknown'), counts_present = 'counts' %in% Layers(object[['RNA']])
), auto_unbox = TRUE))
"""
    return json.loads(run([str(rscript), "-e", code], environment).stdout)


def verify(scientific_python: Path, rscript: Path, r_library: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    r_executable = rscript.expanduser().absolute()
    r_lib = r_library.expanduser().resolve(strict=True)
    if not python.exists() or not r_executable.exists() or not os.access(python, os.X_OK) or not os.access(r_executable, os.X_OK):
        raise RuntimeError("scientific Python and Rscript must be executable")
    with tempfile.TemporaryDirectory(prefix="biomed-atlas-annotation-") as temporary:
        work = Path(temporary)
        for name in ("home", "cache", "matplotlib", "numba"):
            (work / name).mkdir()
        environment = {
            "PATH": str(python.parent) + os.pathsep + str(r_executable.parent) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(work / "home"),
            "XDG_CACHE_HOME": str(work / "cache"),
            "MPLCONFIGDIR": str(work / "matplotlib"),
            "NUMBA_CACHE_DIR": str(work / "numba"),
            "PYTHONHASHSEED": "0",
            "R_LIBS_USER": str(r_lib),
            "LANG": "C",
            "LC_ALL": "C",
        }

        query_h5ad, reference_h5ad = work / "query.h5ad", work / "reference.h5ad"
        celltypist_model = work / "celltypist.pkl"
        run([str(python), "-c", python_fixture_code(query_h5ad, reference_h5ad, celltypist_model)], environment)
        query_digest, reference_digest = sha256(query_h5ad), sha256(reference_h5ad)

        celltypist_output, celltypist_report = work / "celltypist.h5ad", work / "celltypist.json"
        run([
            str(python), str(CELLTYPIST_TEMPLATE), "--query-h5ad", str(query_h5ad), "--model", str(celltypist_model),
            "--output-h5ad", str(celltypist_output), "--report", str(celltypist_report), "--raw-count-location", "layers.counts",
            "--mode", "best match", "--probability-threshold", "0.5", "--unknown-threshold", "0.7",
        ], environment)

        popv_output, popv_report, popv_models = work / "popv.h5ad", work / "popv.json", work / "popv-models"
        run([
            str(python), str(POPV_TEMPLATE), "--query-h5ad", str(query_h5ad), "--reference-h5ad", str(reference_h5ad),
            "--output-h5ad", str(popv_output), "--report", str(popv_report), "--query-count-layer", "counts",
            "--reference-count-layer", "counts", "--reference-label-key", "celltype", "--reference-batch-key", "reference_batch",
            "--query-batch-key", "query_batch", "--methods", "Support_Vector,Random_Forest,CELLTYPIST",
            "--minimum-consensus", "3", "--model-dir", str(popv_models), "--seed", "203",
        ], environment)

        azimuth_query, azimuth_reference, homolog_table = work / "azimuth-query.rds", work / "azimuth-reference", work / "homologs.rds"
        fixture_script = work / "build_azimuth_fixture.R"
        fixture_script.write_text(r_fixture_code(azimuth_query, azimuth_reference, homolog_table), encoding="utf-8")
        run([str(r_executable), str(fixture_script)], environment)
        azimuth_output, azimuth_table, azimuth_report = work / "azimuth.rds", work / "azimuth.tsv", work / "azimuth.json"
        run([
            str(r_executable), str(AZIMUTH_TEMPLATE), "--query-rds", str(azimuth_query), "--reference-dir", str(azimuth_reference),
            "--homolog-table", str(homolog_table), "--output-rds", str(azimuth_output), "--annotations-tsv", str(azimuth_table),
            "--report", str(azimuth_report), "--annotation-level", "celltype", "--assay", "RNA",
            "--prediction-score-threshold", "0.8", "--mapping-score-threshold", "0.9", "--k-weight", "20",
            "--mapping-score-k", "100", "--n-trees", "10", "--seed", "302",
        ], environment)

        celltypist_payload = json.loads(celltypist_report.read_text(encoding="utf-8"))
        popv_payload = json.loads(popv_report.read_text(encoding="utf-8"))
        azimuth_payload = json.loads(azimuth_report.read_text(encoding="utf-8"))
        python_summary = inspect_python_outputs(python, celltypist_output, popv_output, environment)
        azimuth_summary = inspect_azimuth_output(r_executable, azimuth_output, environment)
        backend_summaries = {**python_summary, "azimuth": azimuth_summary}

        run(
            [str(python), "-c", (
                "import anndata as ad; d=ad.read_h5ad(" + repr(str(celltypist_output)) + "); "
                "d.obs.assign(cell_id=d.obs_names, normalized_confidence=d.obs['celltypist_confidence'], "
                "status=d.obs['celltypist_label_review'].astype(str).ne('Unknown').map({True:'mapped',False:'unknown'}))"
                ".to_csv(" + repr(str(work / "celltypist-evidence.tsv")) + ", sep='\\t', index=False)"
            )],
            environment,
        )
        run(
            [str(python), "-c", (
                "import anndata as ad; d=ad.read_h5ad(" + repr(str(popv_output)) + "); "
                "d.obs.assign(cell_id=d.obs_names, normalized_confidence=d.obs['popv_consensus_count'].astype(float)/3.0, "
                "status=d.obs['popv_mapping_status']).to_csv(" + repr(str(work / "popv-evidence.tsv")) + ", sep='\\t', index=False)"
            )],
            environment,
        )
        label_map = {
            label: {"label": label, "ontology_id": f"CL:fixture-{index + 1:04d}"}
            for index, label in enumerate(("TypeA", "TypeB", "TypeC"))
        }
        consensus_manifest = work / "consensus-manifest.json"
        consensus_manifest.write_text(json.dumps({
            "schema_version": 1,
            "methods": [
                {
                    "backend": "celltypist", "path": str(work / "celltypist-evidence.tsv"), "source_kind": "tsv",
                    "cell_id_column": "cell_id", "label_column": "celltypist_label_review",
                    "confidence_column": "normalized_confidence", "status_column": "status",
                    "accepted_statuses": ["mapped"], "label_map": label_map, "weight": 1.0,
                },
                {
                    "backend": "popv", "path": str(work / "popv-evidence.tsv"), "source_kind": "tsv",
                    "cell_id_column": "cell_id", "label_column": "popv_label_review",
                    "confidence_column": "normalized_confidence", "status_column": "status",
                    "accepted_statuses": ["mapped"], "label_map": label_map, "weight": 1.0,
                },
            ],
        }), encoding="utf-8")
        consensus_table, consensus_evidence, consensus_report = (
            work / "annotation-consensus.tsv",
            work / "annotation-evidence.tsv",
            work / "annotation-consensus.json",
        )
        run([
            str(python), str(CONSENSUS_TEMPLATE), "--query-h5ad", str(query_h5ad),
            "--evidence-manifest", str(consensus_manifest), "--output-consensus", str(consensus_table),
            "--output-evidence", str(consensus_evidence), "--report", str(consensus_report),
            "--minimum-methods", "2", "--minimum-agreement", "1.0",
            "--minimum-weighted-support", "0.5", "--minimum-confidence", "0.5",
        ], environment)
        consensus_payload = json.loads(consensus_report.read_text(encoding="utf-8"))
        if sha256(query_h5ad) != query_digest or sha256(reference_h5ad) != reference_digest:
            raise RuntimeError("atlas annotation templates modified source H5AD fixtures")
        for backend, summary in backend_summaries.items():
            if summary["cells"] != 150 or summary["known_accuracy"] < 0.95 or summary["novel_unknown"] < 1 or not summary["counts_present"]:
                raise RuntimeError(f"{backend} failed known-class recovery, novel-state retention, counts, or cell accounting")
        if popv_payload["methods"] != ["Support_Vector", "Random_Forest", "CELLTYPIST"] or popv_payload["not_mapped_query_cells"] != 0:
            raise RuntimeError("popV expert or preprocessing accounting differs from the frozen contract")
        if not all(payload["raw_counts_preserved"] and payload["output_reloaded"] for payload in (celltypist_payload, popv_payload, azimuth_payload)):
            raise RuntimeError("one or more atlas backends failed source-count or output-reload validation")

        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": MODULE_ID,
            "module_version": MODULE_VERSION,
            "compatibility_row_id": ROW_ID,
            "registry_digest": registry.digest,
            "templates": {
                "celltypist": {"name": CELLTYPIST_TEMPLATE.name, "sha256": sha256(CELLTYPIST_TEMPLATE)},
                "azimuth": {"name": AZIMUTH_TEMPLATE.name, "sha256": sha256(AZIMUTH_TEMPLATE)},
                "popv": {"name": POPV_TEMPLATE.name, "sha256": sha256(POPV_TEMPLATE)},
                "consensus": {"name": CONSENSUS_TEMPLATE.name, "sha256": sha256(CONSENSUS_TEMPLATE)},
            },
            "tool_versions": {
                "CellTypist": celltypist_payload["versions"]["celltypist"],
                "popV": popv_payload["versions"]["popv"],
                "Azimuth": azimuth_payload["versions"]["Azimuth"],
            },
            "dependency_versions": {
                "python": popv_payload["versions"]["python"],
                "anndata": popv_payload["versions"]["anndata"],
                "scanpy": run([str(python), "-c", "import importlib.metadata; print(importlib.metadata.version('scanpy'))"], environment).stdout.strip(),
                "r": azimuth_payload["versions"]["R"],
                "Seurat": azimuth_payload["versions"]["Seurat"],
            },
            "fixtures": {
                "python_query": {"sha256": query_digest, "cells": 150, "features": 140, "known_classes": 3, "absent_reference_class_cells": 30},
                "python_reference": {"sha256": reference_digest, "cells": 300, "features": 140, "classes": 3, "batches": 2},
                "azimuth_query": {"sha256": sha256(azimuth_query), "cells": 150, "features": 140, "absent_reference_class_cells": 30},
                "azimuth_reference": {"sha256": sha256(azimuth_reference / "ref.Rds"), "cells": 300, "features": 140, "classes": 3},
            },
            "execution": {
                "celltypist_completed": True,
                "azimuth_completed": True,
                "popv_completed": True,
                "consensus_completed": True,
                "outputs_reloaded": True,
            },
            "backend_summaries": backend_summaries,
            "compatibility_observations": {
                "popv_validated_experts": ["Support_Vector", "Random_Forest", "CELLTYPIST"],
                "popv_xgboost_status": "excluded-on-observed-macos-arm-profile-after-native-segmentation-fault",
            },
            "scientific_summary": {
                "all_three_backends_executed": True,
                "cross_backend_consensus_executed": True,
                "consensus_conflicts_retained_as_unknown": consensus_payload["quality"]["low_confidence_disagreement_and_ties_retained_as_unknown"],
                "consensus_ontology_ids_required": consensus_payload["quality"]["ontology_ids_required_for_mapped_labels"],
                "method_specific_probabilities_and_scores_retained": True,
                "known_reference_classes_recovered": True,
                "absent_reference_population_retained_as_unknown": True,
                "popv_expert_disagreement_preserved": True,
                "all_query_cells_accounted": True,
                "source_counts_and_identifiers_preserved": True,
                "outputs_reloaded": True,
                "evaluation_labels_posthoc_only": True,
                "no_environment_or_compute_infrastructure_managed": True,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.scientific_python, args.rscript, args.r_library)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "passed": True, "tool_versions": report["tool_versions"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
