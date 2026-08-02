"""No-edit exomePeak2 1.14.3 adapter for MeRIP/m6A enrichment analysis."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXOMEPEAK2_VERSION = "1.14.3"
EXOMEPEAK2_COMMIT = "8d265ea9c590c6e8e5bb10bee891467c40604d6f"
EXOMEPEAK2_SOURCE = "https://git.bioconductor.org/packages/exomePeak2"


class ExomePeak2ExecutionError(ValueError):
    """Raised when exomePeak2 inputs, execution, or outputs violate the contract."""


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ExomePeak2ExecutionError(f"{label} must be a local file path")
    path = Path(value).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ExomePeak2ExecutionError(f"{label} must be a readable non-symlink file: {path}")
    return path.resolve()


def _bam_list(request: dict[str, Any], name: str, *, required: bool) -> list[Path]:
    values = request.get(name)
    if values is None and not required:
        return []
    if not isinstance(values, list) or (required and not values) or any(not isinstance(value, str) for value in values):
        raise ExomePeak2ExecutionError(f"{name} must be {'a nonempty' if required else 'an'} array of BAM paths")
    paths = [_file(value, name) for value in values]
    for path in paths:
        if path.suffix.lower() != ".bam":
            raise ExomePeak2ExecutionError(f"{name} requires BAM files: {path}")
        candidates = (Path(str(path) + ".bai"), path.with_suffix(".bai"))
        if not any(candidate.is_file() and not candidate.is_symlink() for candidate in candidates):
            raise ExomePeak2ExecutionError(f"indexed BAM required; missing .bai for {path}")
    return paths


def execute_exomepeak2(
    request: dict[str, Any],
    *,
    output_dir: Path,
    report_path: Path,
    rscript: str = "Rscript",
    timeout_seconds: int = 172800,
) -> dict[str, Any]:
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-rna-modification-enrichment":
        raise ExomePeak2ExecutionError("request must target bulk-rna-modification-enrichment schema version 1")
    assay = str(request.get("assay", "")).lower()
    if assay not in {"merip-seq", "m6a-seq"}:
        raise ExomePeak2ExecutionError("exomePeak2 executor accepts merip-seq or m6a-seq")
    control_ip = _bam_list(request, "control_ip_bams", required=True)
    control_input = _bam_list(request, "control_input_bams", required=True)
    treated_ip = _bam_list(request, "treated_ip_bams", required=False)
    treated_input = _bam_list(request, "treated_input_bams", required=False)
    if len(control_ip) != len(control_input):
        raise ExomePeak2ExecutionError("control IP and input BAM counts must match")
    if bool(treated_ip) != bool(treated_input) or (treated_ip and len(treated_ip) != len(treated_input)):
        raise ExomePeak2ExecutionError("treated IP and input BAM arrays must both be present and matched")
    gff = _file(request.get("gff"), "gff")
    parameters = request.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ExomePeak2ExecutionError("request.parameters must be an object")
    allowed = {
        "genome", "strandness", "fragment_length", "bin_size", "step_size", "test_method",
        "p_cutoff", "diff_p_cutoff", "parallel", "plot_gc", "mode", "motif_based",
        "motif_sequence", "absolute_diff",
    }
    unknown = set(parameters) - allowed
    if unknown:
        raise ExomePeak2ExecutionError("unknown exomePeak2 parameters: " + ", ".join(sorted(unknown)))
    values = {
        "genome": str(parameters.get("genome", "")).strip(),
        "strandness": str(parameters.get("strandness", "unstrand")),
        "fragment_length": int(parameters.get("fragment_length", 100)),
        "bin_size": int(parameters.get("bin_size", 25)),
        "step_size": int(parameters.get("step_size", 25)),
        "test_method": str(parameters.get("test_method", "Poisson")),
        "p_cutoff": float(parameters.get("p_cutoff", 1e-10)),
        "diff_p_cutoff": float(parameters.get("diff_p_cutoff", 0.01)),
        "parallel": int(parameters.get("parallel", 1)),
        "plot_gc": bool(parameters.get("plot_gc", True)),
        "mode": str(parameters.get("mode", "exon")),
        "motif_based": bool(parameters.get("motif_based", False)),
        "motif_sequence": str(parameters.get("motif_sequence", "DRACH")).upper(),
        "absolute_diff": bool(parameters.get("absolute_diff", False)),
    }
    if values["strandness"] not in {"unstrand", "1st_strand", "2nd_strand"}:
        raise ExomePeak2ExecutionError("strandness is outside the official enum")
    if values["test_method"] not in {"Poisson", "DESeq2"} or values["mode"] not in {"exon", "full_transcript", "whole_genome"}:
        raise ExomePeak2ExecutionError("test_method or mode is outside the official enum")
    if min(values["fragment_length"], values["bin_size"], values["step_size"], values["parallel"]) < 1:
        raise ExomePeak2ExecutionError("fragment_length, bin_size, step_size, and parallel must be positive")
    if not 0 < values["p_cutoff"] <= 1 or not 0 < values["diff_p_cutoff"] <= 1:
        raise ExomePeak2ExecutionError("p-value cutoffs must be in (0,1]")
    if values["motif_based"] and (not values["genome"] or not re.fullmatch(r"[ACGTRYSWKMBDHVN]+", values["motif_sequence"])):
        raise ExomePeak2ExecutionError("motif analysis requires a genome and a valid IUPAC motif")
    if not treated_ip and values["absolute_diff"]:
        raise ExomePeak2ExecutionError("absolute_diff applies only to a two-condition differential analysis")
    if output_dir.exists() or report_path.exists():
        raise ExomePeak2ExecutionError("output directory and report path must not already exist")
    executable = shutil.which(rscript) if "/" not in rscript else str(_file(rscript, "Rscript executable"))
    if not executable:
        raise ExomePeak2ExecutionError(f"Rscript executable not found: {rscript}")
    helper = Path(__file__).resolve().parents[1] / "modules" / "builtin" / "bulk-rna-modification-enrichment" / "templates" / "run_exomepeak2.R"
    helper = _file(str(helper), "packaged exomePeak2 R adapter")
    output_dir.mkdir(parents=True)
    provenance = output_dir / "provenance"
    provenance.mkdir()
    manifest = provenance / "bam_manifest.tsv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("group", "path", "sha256"))
        for group, paths in (
            ("control_ip", control_ip), ("control_input", control_input),
            ("treated_ip", treated_ip), ("treated_input", treated_input),
        ):
            for path in paths:
                writer.writerow((group, str(path), sha256(path)))
    config = provenance / "parameters.json"
    config.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result_root = output_dir / "results"
    argv = [
        executable, str(helper), str(manifest), str(gff), str(config), str(result_root), EXOMEPEAK2_VERSION,
    ]
    completed = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout_seconds)
    log = provenance / "exomepeak2.log"
    log.write_text(
        "$ " + " ".join(json.dumps(value) for value in argv) + "\n\nSTDOUT\n" + completed.stdout
        + "\nSTDERR\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise ExomePeak2ExecutionError(f"exomePeak2 failed with exit code {completed.returncode}; see {log}")
    version_file = result_root / "exomePeak2_version.txt"
    if not version_file.is_file() or version_file.read_text(encoding="utf-8").strip() != EXOMEPEAK2_VERSION:
        raise ExomePeak2ExecutionError("exomePeak2 version evidence is missing or mismatched")
    result_files = [path for path in result_root.rglob("*") if path.is_file() and path != version_file]
    groups = {
        "bed": [path for path in result_files if path.suffix.lower() in {".bed", ".bed12"}],
        "tables": [path for path in result_files if path.suffix.lower() in {".csv", ".tsv", ".txt"}],
        "r_objects": [path for path in result_files if path.suffix.lower() in {".rds", ".rda", ".rdata"}],
        "figures": [path for path in result_files if path.suffix.lower() in {".pdf", ".png", ".svg"}],
    }
    if not groups["bed"] or not groups["tables"] or not groups["r_objects"]:
        raise ExomePeak2ExecutionError("exomePeak2 completed without BED, tabular, and R-object outputs")
    records = {
        name: [
            {"path": str(path.relative_to(output_dir)), "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in sorted(paths) if path.stat().st_size > 0
        ]
        for name, paths in groups.items()
    }
    if not records["bed"] or not records["tables"] or not records["r_objects"]:
        raise ExomePeak2ExecutionError("one or more required exomePeak2 output groups are empty")
    implementation = Path(__file__).resolve()
    report = {
        "schema_version": 1, "module_id": "bulk-rna-modification-enrichment", "assay": assay,
        "passed": True, "executed_at": datetime.now(timezone.utc).isoformat(),
        "workflow": {
            "name": "exomePeak2", "version": EXOMEPEAK2_VERSION, "bioconductor_release": "3.18",
            "commit": EXOMEPEAK2_COMMIT, "source": EXOMEPEAK2_SOURCE,
        },
        "implementation": {"path": str(implementation.relative_to(implementation.parents[2])), "sha256": sha256(implementation)},
        "inputs": {
            "bam_manifest": {"path": str(manifest), "sha256": sha256(manifest)},
            "gff": {"path": str(gff), "bytes": gff.stat().st_size, "sha256": sha256(gff)},
        },
        "parameters": values, "outputs": records,
        "provenance": {"parameters": {"path": str(config), "sha256": sha256(config)}, "log": {"path": str(log), "sha256": sha256(log)}},
        "interpretation_scope": (
            "MeRIP/m6A-seq enrichment is regional, antibody-dependent evidence. exomePeak2 peaks do not identify "
            "a modified nucleotide or stoichiometry without orthogonal base-resolution validation."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
