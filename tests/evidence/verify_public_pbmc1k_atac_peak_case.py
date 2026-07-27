#!/usr/bin/env python3
"""Validate barcode-accounted MACS3 peak calling on public 10x PBMC ATAC data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

import h5py

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402

MODULE_ID = "single-cell-atac-regulatory"
ROW_ID = "agent-protocol-1-macs3-304-signac-116-chromvar-124-motifmatchr-124"
MODULE_ROOT = BUILTIN_ROOT / MODULE_ID
MANIFEST = MODULE_ROOT / "module.json"
TEMPLATE = MODULE_ROOT / "templates" / "call_macs3_fragments.py"
SOURCES = {
    "fragments": {
        "filename": "atac_pbmc_1k_nextgem_fragments.tsv.gz",
        "url": (
            "https://cf.10xgenomics.com/samples/cell-atac/1.1.0/"
            "atac_pbmc_1k_nextgem/atac_pbmc_1k_nextgem_fragments.tsv.gz"
        ),
        "sha256": "391176fa39181a96822ade86468d58a8e058f52751866048669d77a988c38bb7",
    },
    "peak_matrix": {
        "filename": "atac_pbmc_1k_nextgem_filtered_peak_bc_matrix.h5",
        "url": (
            "https://cf.10xgenomics.com/samples/cell-atac/1.1.0/"
            "atac_pbmc_1k_nextgem/"
            "atac_pbmc_1k_nextgem_filtered_peak_bc_matrix.h5"
        ),
        "sha256": "40a1a361760c8072143d1e3678a5ef807a1a15bcd240fdbea08be857a19ec380",
    },
}
N_CELLS = 300
SEED = 20260723


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def acquire_sources(work: Path, source_dir: Path | None) -> dict[str, Path]:
    paths = {}
    for key, source in SOURCES.items():
        if source_dir is None:
            path = work / source["filename"]
            urllib.request.urlretrieve(source["url"], path)
        else:
            directory = source_dir.expanduser().resolve(strict=True)
            path = directory / source["filename"]
            if not path.is_file():
                aliases = {
                    "fragments": "atac_pbmc_1k_fragments.tsv.gz",
                    "peak_matrix": "atac_pbmc_1k_filtered_peak_bc_matrix.h5",
                }
                path = directory / aliases[key]
            path = path.resolve(strict=True)
        if sha256(path) != source["sha256"]:
            raise RuntimeError(f"public PBMC1k ATAC digest mismatch: {key}")
        paths[key] = path
    return paths


def stable_barcodes(matrix_path: Path) -> list[str]:
    with h5py.File(matrix_path, "r") as handle:
        values = handle["matrix"]["barcodes"][:]
        shape = tuple(int(value) for value in handle["matrix"]["shape"][:])
    barcodes = [
        value.decode() if isinstance(value, bytes) else str(value)
        for value in values
    ]
    if len(barcodes) != 1195 or shape[1] != len(barcodes):
        raise RuntimeError("public PBMC1k peak matrix differs from contract")
    return sorted(
        barcodes,
        key=lambda barcode: hashlib.sha256(
            f"{SEED}:{barcode}".encode()
        ).hexdigest(),
    )[:N_CELLS]


def verify(
    source_dir: Path | None,
    scientific_python: Path,
    macs3: Path,
) -> dict[str, object]:
    python = scientific_python.expanduser().absolute()
    macs3_executable = macs3.expanduser().absolute()
    if (
        not python.is_file()
        or not os.access(python, os.X_OK)
        or not macs3_executable.is_file()
        or not os.access(macs3_executable, os.X_OK)
    ):
        raise RuntimeError("scientific Python and MACS3 must be executable")
    with tempfile.TemporaryDirectory(prefix="biomed-public-pbmc1k-atac-") as temporary:
        work = Path(temporary)
        paths = acquire_sources(work, source_dir)
        source_digests_before = {
            name: sha256(path) for name, path in paths.items()
        }
        barcodes = stable_barcodes(paths["peak_matrix"])
        allowlist = work / "barcodes.txt"
        allowlist.write_text("\n".join(barcodes) + "\n", encoding="utf-8")
        report_path = work / "macs3.json"
        environment = dict(os.environ)
        environment.update(
            {
                "PATH": str(macs3_executable.parent)
                + os.pathsep
                + str(python.parent)
                + os.pathsep
                + os.environ.get("PATH", ""),
                "PYTHONHASHSEED": "0",
            }
        )
        completed = subprocess.run(
            [
                str(python),
                str(TEMPLATE),
                "--fragments",
                str(paths["fragments"]),
                "--barcode-allowlist",
                str(allowlist),
                "--output-dir",
                str(work / "peaks"),
                "--name",
                "pbmc1k",
                "--genome-size",
                "hs",
                "--qvalue",
                "0.01",
                "--macs3",
                str(macs3_executable),
                "--report",
                str(report_path),
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
                "public PBMC1k MACS3 failed:\n"
                + completed.stdout[-2000:]
                + "\n"
                + completed.stderr[-6000:]
            )
        analysis = json.loads(report_path.read_text(encoding="utf-8"))
        source_digests_after = {
            name: sha256(path) for name, path in paths.items()
        }
        accounting = analysis["accounting"]
        peaks = analysis["outputs"]["narrow_peak"]["rows"]
        quality_gates = {
            "official_source_identity": "pass"
            if source_digests_before == source_digests_after
            and source_digests_before
            == {name: source["sha256"] for name, source in SOURCES.items()}
            else "fail",
            "label_blind_filtered_cell_selection": "pass",
            "all_selected_barcodes_observed": "pass"
            if accounting["allowlist_barcodes"] == N_CELLS
            and accounting["selected_barcodes"] == N_CELLS
            and not accounting["allowlist_barcodes_absent_from_fragments"]
            else "fail",
            "fragment_accounting_reconciled": "pass"
            if accounting["selected_records"] > 0
            and accounting["selected_fragment_count"] > 0
            and accounting["total_records"]
            == accounting["selected_records"] + accounting["excluded_records"]
            else "fail",
            "macs3_peaks_summits_and_reload": "pass"
            if analysis["passed"]
            and analysis["source_fragments_immutable"]
            and analysis["outputs_reloaded"]
            and peaks > 100
            and analysis["outputs"]["summits"]["rows"] > 100
            else "fail",
        }
        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        report = {
            "schema_version": 1,
            "case_id": "pbmc1k-atac-macs3-v1",
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
                "dataset": "10x PBMC 1k single-cell ATAC Next GEM v1.1",
                "files": SOURCES,
                "validation": {
                    "filtered_cells": 1195,
                    "selected_cells": N_CELLS,
                    "selection": (
                        "stable barcode hash without peak or cell labels"
                    ),
                },
            },
            "parameters": analysis["parameters"],
            "runtime": {
                "MACS3": analysis["tool_version"],
            },
            "execution": {
                "accounting": accounting,
                "outputs": analysis["outputs"],
                "source_artifacts_immutable": source_digests_before
                == source_digests_after,
                "outputs_reloaded": True,
            },
            "quality_gates": quality_gates,
            "scientific_boundaries": [
                "This public case validates real 10x fragment parsing, barcode accounting, FRAG-mode MACS3 peak calling, summit output, and reload.",
                "The public PBMC1k dataset is ATAC-only; sequence-backed motif matching, chromVAR deviations, and paired-RNA LinkPeaks remain covered by the complete executable fixture rather than being fabricated from absent RNA.",
                "Aggregate peaks depend on the selected cells, genome build, genome-size model, and MACS3 parameters and are not donor-level differential accessibility.",
                "Peak-to-gene correlation and motif evidence do not establish direct binding or causal regulation.",
            ],
        }
        if not report["passed"]:
            raise RuntimeError(
                "public PBMC1k ATAC gates failed: "
                + json.dumps(quality_gates, sort_keys=True)
            )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--scientific-python", type=Path, required=True)
    parser.add_argument("--macs3", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "public-case-pbmc1k-atac-macs3.json",
    )
    args = parser.parse_args()
    report = verify(args.source_dir, args.scientific_python, args.macs3)
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
                "peaks": report["execution"]["outputs"]["narrow_peak"]["rows"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
