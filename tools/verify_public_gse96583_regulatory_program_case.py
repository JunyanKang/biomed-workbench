#!/usr/bin/env python3
"""Validate GRNBoost2 coexpression programs on public paired GSE96583 PBMCs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from tools.verify_public_gse96583_donor_case import (  # noqa: E402
    EXPECTED_DONORS,
    SOURCES,
    acquire_sources,
    extract_members,
    read_condition,
    unique_gene_names,
)

MODULE_ID = "single-cell-regulatory-network"
ROW_ID = "agent-protocol-1-pyscenic-0121-scenicplus-10a2"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "run_grnboost2_programs.py"
SEED = 96583
MAX_CELLS_PER_SAMPLE = 30
N_FEATURES = 800
DECLARED_TFS = (
    "ATF3",
    "BATF",
    "BCL11B",
    "BCL6",
    "CEBPB",
    "CEBPD",
    "EOMES",
    "ETS1",
    "FOS",
    "FOSB",
    "GATA3",
    "IKZF1",
    "IRF1",
    "IRF7",
    "JUN",
    "JUND",
    "KLF2",
    "KLF6",
    "LEF1",
    "NFKB1",
    "PAX5",
    "PRDM1",
    "RELA",
    "RUNX1",
    "RUNX3",
    "SPI1",
    "STAT1",
    "STAT2",
    "STAT3",
    "TBX21",
    "TCF7",
)
IFN_TFS = {"IRF1", "IRF7", "STAT1", "STAT2"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_sample_indices(obs: pd.DataFrame) -> np.ndarray:
    selected = []
    samples = obs["biological_sample"].astype(str).to_numpy()
    for sample in sorted(set(samples)):
        candidates = np.flatnonzero(samples == sample)
        ranked = sorted(
            candidates,
            key=lambda index: hashlib.sha256(
                f"{SEED}:{obs.index[index]}".encode()
            ).hexdigest(),
        )
        selected.extend(ranked[:MAX_CELLS_PER_SAMPLE])
    return np.asarray(sorted(selected), dtype=int)


def run_template(
    scientific_python: Path,
    expression: Path,
    tf_list: Path,
    work: Path,
    environment: dict[str, str],
) -> None:
    completed = subprocess.run(
        [
            str(scientific_python),
            str(TEMPLATE),
            "--expression-tsv",
            str(expression),
            "--tf-list",
            str(tf_list),
            "--adjacencies-output",
            str(work / "adjacencies.tsv"),
            "--programs-output",
            str(work / "programs.json"),
            "--auc-output",
            str(work / "program-auc.tsv"),
            "--report",
            str(work / "template-report.json"),
            "--seed",
            str(SEED),
            "--min-targets",
            "5",
            "--rho-threshold",
            "0.03",
            "--aucell-threshold",
            "0.05",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "public GSE96583 regulatory program execution failed:\n"
            + completed.stdout[-2000:]
            + "\n"
            + completed.stderr[-5000:]
        )


def verify(source_dir: Path | None, scientific_python: Path) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError("pySCENIC scientific Python must be executable")
    with tempfile.TemporaryDirectory(
        prefix="biomed-public-gse96583-regulatory-"
    ) as temporary:
        work = Path(temporary)
        paths = acquire_sources(
            work,
            source_dir.expanduser().resolve(strict=True) if source_dir else None,
        )
        source_digests_before = {
            name: sha256(path) for name, path in paths.items()
        }
        members = extract_members(paths["archive"], work / "raw")
        metadata = pd.read_csv(paths["metadata"], sep="\t", index_col=0)
        genes = pd.read_csv(paths["genes"], sep="\t", header=None)
        matrices, observations = [], []
        for condition in ("ctrl", "stim"):
            matrix, obs, _ = read_condition(
                members[f"{condition}_matrix"],
                members[f"{condition}_barcodes"],
                metadata,
                condition,
            )
            matrices.append(matrix)
            observations.append(obs)
        counts = sparse.vstack(matrices, format="csr", dtype=np.int64)
        obs = pd.concat(observations)
        selected_cells = stable_sample_indices(obs)
        counts = counts[selected_cells]
        obs = obs.iloc[selected_cells].copy()
        if (
            obs["biological_sample"].nunique() != 16
            or set(obs["donor"].astype(str)) != EXPECTED_DONORS
            or len(obs) != 16 * MAX_CELLS_PER_SAMPLE
        ):
            raise RuntimeError("public regulatory sampling lost paired design")

        gene_names = np.asarray(unique_gene_names(genes), dtype=object)
        name_to_index = {name: index for index, name in enumerate(gene_names)}
        tf_names = [name for name in DECLARED_TFS if name in name_to_index]
        if len(tf_names) < 20 or not IFN_TFS.issubset(tf_names):
            raise RuntimeError("public source lacks the declared TF control set")
        detected = np.asarray((counts > 0).sum(axis=0)).ravel()
        totals = np.asarray(counts.sum(axis=0)).ravel()
        ranked = np.lexsort((np.arange(counts.shape[1]), -totals, -detected))
        selected_features = list(ranked[:N_FEATURES])
        selected_features.extend(name_to_index[name] for name in tf_names)
        selected_features = np.asarray(sorted(set(selected_features)), dtype=int)
        counts = counts[:, selected_features].tocsr()
        library = np.asarray(counts.sum(axis=1)).ravel()
        if (library <= 0).any():
            raise RuntimeError("selected public cells contain empty libraries")
        expression = counts.multiply(1e4 / library[:, None]).tocsr()
        expression.data = np.log1p(expression.data)
        expression_path = work / "expression.tsv"
        pd.DataFrame(
            expression.toarray(),
            index=obs.index,
            columns=gene_names[selected_features],
        ).to_csv(expression_path, sep="\t")
        tf_path = work / "transcription-factors.txt"
        tf_path.write_text("\n".join(tf_names) + "\n", encoding="utf-8")

        environment = dict(os.environ)
        environment.update(
            {
                "PATH": str(python.parent)
                + os.pathsep
                + os.environ.get("PATH", ""),
                "PYTHONHASHSEED": "0",
                "LANG": "C",
                "LC_ALL": "C",
            }
        )
        run_template(python, expression_path, tf_path, work, environment)
        template_report = json.loads(
            (work / "template-report.json").read_text(encoding="utf-8")
        )
        programs = json.loads(
            (work / "programs.json").read_text(encoding="utf-8")
        )
        auc = pd.read_csv(work / "program-auc.tsv", sep="\t", index_col=0)
        auc = auc.loc[obs.index]
        evaluation = obs[
            ["donor", "condition", "biological_sample", "cell_type"]
        ].copy()
        evaluation = evaluation.join(auc)
        program_tfs = {
            column: next(
                record["transcription_factor"]
                for record in programs
                if record["name"] == column
            )
            for column in auc.columns
        }
        paired_effects = {}
        for column, tf in program_tfs.items():
            sample_medians = evaluation.groupby(
                ["donor", "condition"], observed=True
            )[column].median()
            donor_deltas = {
                donor: float(
                    sample_medians.loc[(donor, "stim")]
                    - sample_medians.loc[(donor, "ctrl")]
                )
                for donor in sorted(EXPECTED_DONORS)
            }
            paired_effects[tf] = {
                "median_stim_minus_ctrl": float(np.median(list(donor_deltas.values()))),
                "positive_donors": int(
                    sum(value > 0 for value in donor_deltas.values())
                ),
                "donor_deltas": donor_deltas,
            }
        ifn_evidence = {
            tf: effect
            for tf, effect in paired_effects.items()
            if tf in IFN_TFS
            and effect["median_stim_minus_ctrl"] > 0
            and effect["positive_donors"] >= 5
        }
        source_digests_after = {
            name: sha256(path) for name, path in paths.items()
        }
        quality_gates = {
            "official_source_identity": "pass"
            if source_digests_before == source_digests_after
            else "fail",
            "label_blind_balanced_cell_and_feature_selection": "pass",
            "grnboost2_programs_and_aucell_reloaded": "pass"
            if template_report["passed"]
            and template_report["scientific_checks"]["outputs_reloaded"]
            and auc.shape[0] == len(obs)
            else "fail",
            "motif_pruning_boundary_preserved": "pass"
            if template_report["scientific_checks"][
                "programs_not_labeled_as_motif_pruned_regulons"
            ]
            and all(
                record["evidence_class"]
                == "coexpression-program-not-motif-pruned-regulon"
                for record in programs
            )
            else "fail",
            "external_paired_condition_control": "pass"
            if ifn_evidence
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "gse96583-regulatory-program-v1",
            "case_type": "public-data-end-to-end",
            "passed": set(quality_gates.values()) == {"pass"},
            "module": {
                "id": MODULE_ID,
                "version": registry.get(MODULE_ID).version,
                "compatibility_row_id": ROW_ID,
                "manifest_sha256": sha256(MANIFEST),
                "template_sha256": sha256(TEMPLATE),
                "registry_digest": registry.digest,
            },
            "source": {
                "accession": "GSE96583",
                "files": {
                    name: {
                        "filename": SOURCES[name]["filename"],
                        "sha256": source_digests_before[name],
                    }
                    for name in sorted(SOURCES)
                },
                "validation": {
                    "selected_cells": len(obs),
                    "genes": len(selected_features),
                    "transcription_factors": len(tf_names),
                    "donors": obs["donor"].nunique(),
                    "biological_samples": obs["biological_sample"].nunique(),
                    "selection": (
                        "stable cell hash within biological sample and "
                        "detected-cell/total-count gene ranking without labels"
                    ),
                },
            },
            "parameters": template_report["parameters"],
            "runtime": template_report["versions"],
            "execution": {
                **template_report["results"],
                "paired_condition_effects": paired_effects,
                "independent_ifn_control_programs": ifn_evidence,
                "source_artifacts_immutable": source_digests_before
                == source_digests_after,
                "outputs_reloaded": True,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "GRNBoost2 and AUCell execute without condition or cell-type labels; paired treatment labels are used only after fitting for external evaluation.",
                "The public case reports TF coexpression programs and does not call them motif-pruned regulons because no species-matched cisTarget ranking database is supplied.",
                "The complete executable fixture separately validates cisTarget motif pruning, regulon construction, AUCell, and SCENIC+ gene and region activity.",
                "A positive paired interferon-program control supports recovery of known treatment structure but does not establish direct TF binding or causal regulation.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "public regulatory-network gates failed: "
                + json.dumps(quality_gates, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--pyscenic-python", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-gse96583-regulatory-program.json",
    )
    args = parser.parse_args()
    report = verify(args.source_dir, args.pyscenic_python)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "case_id": report["case_id"],
                "passed": report["passed"],
                "programs": report["execution"]["scored_programs"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
