#!/usr/bin/env python3
"""Validate a no-edit bulk-assay request and emit an execution-locked run contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MODULE_ID = 'bulk-r-loop-mapping'
ASSAYS = ('drip-seq', 'dripc-seq', 'sdrip-seq', 'qdrip-seq', 'r-chip', 'mapr', 'cuttag')
WORKFLOWS = {'drip-seq': 'S9.6 DRIP-seq protocol with restriction-fragment-aware broad signal policy', 'dripc-seq': 'S9.6 DRIPc-seq protocol with RNA-moiety strand-aware signal policy', 'sdrip-seq': 'sonication-based strand-specific S9.6 DRIP protocol', 'qdrip-seq': 'quantitative strand-specific DRIP with declared synthetic internal standards', 'r-chip': 'catalytically inactive RNase H1 R-ChIP protocol', 'mapr': 'dRNH1-MNase MapR protocol', 'cuttag': 'CUT&Tag with the exact S9.6 or dRNH1-derived hybrid sensor declared'}
REQUIRED_PARAMETERS = ('assay', 'R-loop sensor or antibody', 'fragmentation or in situ cleavage model', 'sequenced moiety and strandedness', 'RNase H specificity-control design', 'matched background control', 'synthetic internal-reference identity and addition stage', 'reference and blacklist', 'broad or narrow signal model', 'replicate-consensus rule', 'cross-method comparison policy')
FIGURES = ('read and mapping QC', 'strand accounting', 'internal-reference recovery where applicable', 'RNase H sensitivity', 'replicate correlation', 'signal width and genomic annotation', 'TSS and TTS metaprofiles', 'sense and antisense heatmaps', 'method-overlap and discordance', 'gene-body and intergenic distributions', 'genome tracks', 'orthogonal validation linkage')


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.request.is_file():
        raise FileNotFoundError(args.request)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {args.output_dir}")
    request = json.loads(args.request.read_text(encoding="utf-8"))
    if request.get("module_id") != MODULE_ID:
        raise ValueError("request module_id does not match this packaged workflow")
    assay = str(request.get("assay", "")).strip().lower()
    if assay not in ASSAYS:
        raise ValueError(f"unsupported assay for {MODULE_ID}: {assay}")
    parameters = request.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("request.parameters must be an object")
    missing = [field for field in REQUIRED_PARAMETERS if field not in parameters or parameters[field] in (None, "", [])]
    if missing:
        raise ValueError("missing required assay parameters: " + ", ".join(missing))
    inputs = request.get("input_files")
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("request.input_files must be a nonempty list")
    input_rows = []
    for value in inputs:
        path = Path(value).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        input_rows.append({"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size})
    args.output_dir.mkdir(parents=True, exist_ok=False)
    contract = {
        "schema_version": 1,
        "module_id": MODULE_ID,
        "assay": assay,
        "official_workflow": WORKFLOWS[assay],
        "request_sha256": digest(args.request),
        "inputs": input_rows,
        "parameters": parameters,
        "required_figure_inventory": FIGURES,
        "execution_state": "admitted-not-run",
        "next_gate": "Resolve and record the exact installed workflow/tool version, then execute without editing this template; reload every declared result before evidence admission.",
    }
    output = args.output_dir / "run_contract.json"
    output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"module_id": MODULE_ID, "assay": assay, "contract": str(output), "executed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
