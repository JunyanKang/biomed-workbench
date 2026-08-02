#!/usr/bin/env python3
"""Run an approved MSBio2 wrapper or validate and normalize existing Metascape outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_files(root: Path) -> list[dict]:
    records = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        records.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)})
    return records


def parse_mcode(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    return [{str(key).strip(): str(value).strip() for key, value in row.items()} for row in rows]


def validate_gene_lists(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("gene-list input is missing or empty")
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig", errors="strict").splitlines() if line.strip()]
    if not 1 <= len(lines) <= 100_000 or any(len(line) > 500 for line in lines):
        raise ValueError("gene-list input is outside bounded size limits")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("gene_lists", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--species", type=int, required=True)
    parser.add_argument("--msbio-wrapper", type=Path)
    parser.add_argument("--msbio-root", type=Path)
    parser.add_argument("--existing-results", type=Path)
    parser.add_argument("--option-json", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=14_400)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not 60 <= args.timeout_seconds <= 86_400:
        raise ValueError("timeout-seconds must be 60..86400")
    gene_lists = args.gene_lists.resolve(); validate_gene_lists(gene_lists)
    if args.option_json and not args.option_json.resolve().is_file():
        raise ValueError("option JSON is missing")
    if not 1 <= args.species <= 9_999_999:
        raise ValueError("species must be a positive NCBI taxonomy identifier")
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    if args.execute:
        if args.option_json:
            raise ValueError("the observed direct MSBio2 command does not document an option-file flag; do not imply that an unapplied option file changed the analysis")
        if not args.msbio_wrapper or not args.msbio_root:
            raise ValueError("execution requires an approved MSBio2 root and wrapper")
        msbio_root = args.msbio_root.resolve()
        wrapper = args.msbio_wrapper.resolve()
        data_root = msbio_root / "data"
        if not wrapper.is_file() or not data_root.is_dir():
            raise ValueError("MSBio2 root, data directory, or wrapper is missing")
        try:
            wrapper.relative_to(msbio_root)
            input_relative = gene_lists.relative_to(data_root)
            output_relative = output.relative_to(data_root)
        except ValueError as exc:
            raise ValueError("MSBio2 execution requires the wrapper, input and output inside the declared installation root") from exc
        if output == data_root or not output_relative.parts:
            raise ValueError("MSBio2 output must be a dedicated directory below the installation data directory")
        container_input = "/data/" + input_relative.as_posix()
        container_output = "/data/" + output_relative.as_posix()
        command = [str(wrapper), "-u", "-S", str(args.species), "-T", str(args.species), "-o", container_output, container_input]
        completed = subprocess.run(command, cwd=msbio_root, check=False, timeout=args.timeout_seconds)
        if completed.returncode:
            raise RuntimeError(f"MSBio2 wrapper exited with {completed.returncode}")
        results = output
    elif args.existing_results:
        results = args.existing_results.resolve()
    else:
        raise ValueError("declare --execute or provide --existing-results")
    if not results.is_dir():
        raise ValueError("Metascape result directory is missing")
    files = safe_files(results)
    names = {record["path"] for record in files}
    required_families = {
        "analysis_report": any(Path(name).name.lower() == "analysisreport.html" for name in names),
        "result_workbook": any(Path(name).name.lower() == "metascape_result.xlsx" for name in names),
        "go_network": any(name.lower().endswith(".xgmml") and "go" in name.lower() for name in names),
        "ppi_network": any(name.lower().endswith(".xgmml") and "ppi" in name.lower() for name in names),
        "cytoscape_session": any(name.lower().endswith(".cys") for name in names),
        "vector_figure": any(name.lower().endswith(".pdf") for name in names),
        "raster_figure": any(name.lower().endswith(".png") for name in names),
    }
    if not all(required_families.values()):
        missing = ", ".join(key for key, value in required_families.items() if not value)
        raise RuntimeError(f"Metascape result package is incomplete: {missing}")
    mcode_paths = [results / name for name in names if Path(name).name.lower() == "mcode.csv"]
    mcode_rows = parse_mcode(mcode_paths[0]) if mcode_paths else []
    report = {
        "schema_version": 1, "backend": "MSBio2/Metascape", "species_taxon_id": args.species,
        "executed_now": args.execute, "input": {"name": gene_lists.name, "sha256": digest(gene_lists)},
        "option_config": ({"name": args.option_json.name, "sha256": digest(args.option_json.resolve())} if args.option_json and args.option_json.resolve().is_file() else None),
        "result_file_count": len(files), "required_artifact_families": required_families,
        "mcode_record_count": len(mcode_rows), "files": files,
        "method_semantics": {
            "enrichment": "hypergeometric over-representation with multiple-testing correction and similarity-based term clustering",
            "ppi": "database-derived interaction network followed by MCODE dense-subnetwork discovery when network size is eligible",
            "cytoscape": "editable network rendering and session preservation; layout proximity is not biological distance",
        },
        "limitations": [
            "MSBio2 software, images, license files, and private project data are not redistributed by Biomed Workbench.",
            "Enrichment and PPI modules are hypothesis-generating and depend on identifier mapping, background, database release, and list construction.",
        ],
    }
    target = output / "metascape_msbio_manifest.json"; target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(target), "files": len(files), "mcode_records": len(mcode_rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
