#!/usr/bin/env python3
"""Generate and optionally execute a bounded HADDOCK3 protein-complex workflow."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def checked_path(value: str, *, suffixes: tuple) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in suffixes:
        raise ValueError(f"required input is missing or has an unsupported format: {value}")
    return path


def read_request(path: Path) -> dict:
    request = json.loads(path.read_text(encoding="utf-8"))
    allowed = {
        "run_name", "molecules", "restraints", "reference", "mode", "ncores",
        "rigidbody_sampling", "rigidbody_select", "flexref_select", "top_models_per_cluster",
        "haddock3_executable", "prodigy_executable", "dockq_executable", "allowed_mismatches",
    }
    if not isinstance(request, dict) or set(request) - allowed:
        raise ValueError("request must be a closed JSON object")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", str(request.get("run_name", ""))):
        raise ValueError("run_name must be a filesystem-safe identifier")
    molecules = request.get("molecules")
    if not isinstance(molecules, list) or not 2 <= len(molecules) <= 8:
        raise ValueError("molecules must contain 2..8 PDB coordinate files")
    request["molecules"] = [str(checked_path(value, suffixes=(".pdb",))) for value in molecules]
    if request.get("restraints"):
        request["restraints"] = str(checked_path(request["restraints"], suffixes=(".tbl", ".txt")))
    if request.get("reference"):
        request["reference"] = str(checked_path(request["reference"], suffixes=(".pdb",)))
    mode = request.get("mode", "production")
    if mode not in {"official-test", "production"}:
        raise ValueError("mode must be official-test or production")
    defaults = {
        "official-test": (20, 5, 5, 4),
        "production": (1000, 200, 200, 4),
    }[mode]
    request["mode"] = mode
    request["ncores"] = int(request.get("ncores", 1))
    request["rigidbody_sampling"] = int(request.get("rigidbody_sampling", defaults[0]))
    request["rigidbody_select"] = int(request.get("rigidbody_select", defaults[1]))
    request["flexref_select"] = int(request.get("flexref_select", defaults[2]))
    request["top_models_per_cluster"] = int(request.get("top_models_per_cluster", defaults[3]))
    request["allowed_mismatches"] = int(request.get("allowed_mismatches", 0))
    if not 1 <= request["ncores"] <= 256:
        raise ValueError("ncores must be 1..256")
    if not 1 <= request["rigidbody_select"] <= request["rigidbody_sampling"] <= 100000:
        raise ValueError("rigidbody sampling and selection are inconsistent")
    if not 1 <= request["flexref_select"] <= request["rigidbody_select"]:
        raise ValueError("flexref_select must be within rigidbody_select")
    if not 1 <= request["top_models_per_cluster"] <= 100:
        raise ValueError("top_models_per_cluster must be 1..100")
    if not 0 <= request["allowed_mismatches"] <= 20:
        raise ValueError("allowed_mismatches must be 0..20 and scientifically justified")
    return request


def quote_cfg(path: str) -> str:
    return json.dumps(path)


def build_config(request: dict, work: Path) -> Path:
    run_dir = work / request["run_name"]
    if run_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run directory: {run_dir}")
    lines = [
        f"run_dir = {quote_cfg(str(run_dir))}",
        "molecules = [" + ", ".join(quote_cfg(value) for value in request["molecules"]) + "]",
        f"ncores = {request['ncores']}",
        "mode = \"local\"",
        "clean = true",
        "offline = true",
    ]
    if request.get("reference"):
        lines.append(f"reference_fname = {quote_cfg(request['reference'])}")
    lines.extend(["", "[topoaa]", "", "[rigidbody]", f"sampling = {request['rigidbody_sampling']}"])
    if request.get("restraints"):
        lines.append(f"ambig_fname = {quote_cfg(request['restraints'])}")
    lines.extend([
        "", "[caprieval]", "", "[seletop]", f"select = {request['rigidbody_select']}",
        "", "[flexref]", "", "[caprieval]", "", "[emref]", "", "[clustfcc]",
        "min_population = 1", "", "[seletopclusts]",
        f"top_models = {request['top_models_per_cluster']}", "", "[caprieval]", "",
    ])
    config = work / f"{request['run_name']}.cfg"
    config.write_text("\n".join(lines), encoding="utf-8")
    return config


def find_final_table(run_dir: Path) -> Path:
    candidates = sorted(run_dir.glob("*_caprieval/capri_ss.tsv"))
    if not candidates:
        raise RuntimeError("HADDOCK3 completed without a CAPRI structure table")
    return candidates[-1]


def expand_model(run_dir: Path, relative_model: str, destination: Path) -> Path:
    source = (find_final_table(run_dir).parent / relative_model).resolve()
    if source.is_file():
        shutil.copyfile(source, destination)
    elif Path(str(source) + ".gz").is_file():
        with gzip.open(Path(str(source) + ".gz"), "rb") as reader, destination.open("wb") as writer:
            shutil.copyfileobj(reader, writer)
    else:
        raise RuntimeError(f"ranked model is absent: {relative_model}")
    return destination


def run_capture(command: list[str], output: Path) -> dict:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    output.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    return {"command": [Path(command[0]).name, *command[1:]], "exit_code": completed.returncode, "output": output.name}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    request = read_request(args.request.resolve())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = build_config(request, output)
    manifest = {
        "schema_version": 1,
        "workflow": "HADDOCK3 protein-complex docking",
        "mode": request["mode"],
        "research_grade_sampling": request["mode"] == "production" and request["rigidbody_sampling"] >= 1000,
        "inputs": [{"path": Path(value).name, "sha256": digest(Path(value))} for value in request["molecules"]],
        "parameters": {key: request[key] for key in ("ncores", "rigidbody_sampling", "rigidbody_select", "flexref_select", "top_models_per_cluster")},
        "config": {"path": config.name, "sha256": digest(config)},
        "executed": False,
        "evaluations": [],
        "limitations": [
            "A docking rank or HADDOCK score is not binding affinity or experimental interaction evidence.",
            "The official-test profile validates software integration only; it is not a production sampling protocol.",
        ],
    }
    if args.execute:
        haddock = request.get("haddock3_executable", "haddock3")
        completed = subprocess.run([haddock, str(config)], cwd=output, check=False)
        if completed.returncode:
            raise RuntimeError(f"HADDOCK3 failed with exit code {completed.returncode}")
        run_dir = output / request["run_name"]
        table = find_final_table(run_dir)
        rows = list(csv.DictReader(table.open(encoding="utf-8"), delimiter="\t"))
        if not rows:
            raise RuntimeError("final CAPRI table is empty")
        top_model = expand_model(run_dir, rows[0]["model"], output / "top_model.pdb")
        manifest.update({
            "executed": True,
            "final_table": {"path": table.relative_to(output).as_posix(), "sha256": digest(table), "model_count": len(rows)},
            "top_model": {"path": top_model.name, "sha256": digest(top_model)},
        })
        if request.get("prodigy_executable"):
            manifest["evaluations"].append(run_capture([request["prodigy_executable"], str(top_model)], output / "prodigy.txt"))
        if request.get("dockq_executable") and request.get("reference"):
            command = [request["dockq_executable"], str(top_model), request["reference"], "--short"]
            if request["allowed_mismatches"]:
                command.extend(["--allowed_mismatches", str(request["allowed_mismatches"])])
            manifest["evaluations"].append(run_capture(command, output / "dockq.txt"))
        if any(record["exit_code"] for record in manifest["evaluations"]):
            raise RuntimeError("one or more declared post-docking evaluations failed")
    manifest_path = output / "docking_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    json.loads(manifest_path.read_text(encoding="utf-8"))
    print(json.dumps({"executed": manifest["executed"], "manifest": str(manifest_path), "config": str(config)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
