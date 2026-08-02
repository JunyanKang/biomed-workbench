"""Pinned RIPSeeker adapter for HMM-based RIP-seq enrichment regions."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RIPSEEKER_VERSION = "1.28.0"
RIPSEEKER_COMMIT = "e3eb1377fc9cd28851a7b301fc410848f7b1347f"
RIPSEEKER_SOURCE = "https://git.bioconductor.org/packages/RIPSeeker"


class RIPSeekerExecutionError(ValueError):
    """Raised when a RIPSeeker input, run, or output violates the contract."""


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _bam_paths(value: object, label: str) -> list[Path]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) for item in value):
        raise RIPSeekerExecutionError(f"{label} must be a nonempty array of indexed BAM paths")
    paths: list[Path] = []
    for item in value:
        path = Path(item).expanduser()
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".bam":
            raise RIPSeekerExecutionError(f"{label} contains an invalid BAM: {path}")
        path = path.resolve()
        indexes = (Path(str(path) + ".bai"), path.with_suffix(".bai"))
        if not any(index.is_file() and not index.is_symlink() for index in indexes):
            raise RIPSeekerExecutionError(f"indexed BAM required; missing .bai for {path}")
        paths.append(path)
    return paths


def execute_ripseeker(
    request: dict[str, Any],
    *,
    output_dir: Path,
    report_path: Path,
    rscript: str = "Rscript",
    container_image: str | None = None,
    container_platform: str = "linux/amd64",
    timeout_seconds: int = 172800,
) -> dict[str, Any]:
    if request.get("schema_version") != 1 or request.get("module_id") != "bulk-rbp-rna-binding":
        raise RIPSeekerExecutionError("request must target bulk-rbp-rna-binding schema version 1")
    if str(request.get("assay", "")).lower() != "rip-seq":
        raise RIPSeekerExecutionError("this executor accepts only assay=rip-seq")
    rip_bams = _bam_paths(request.get("rip_bams"), "rip_bams")
    control_bams = _bam_paths(request.get("control_bams"), "control_bams")
    parameters = request.get("parameters", {})
    if not isinstance(parameters, dict):
        raise RIPSeekerExecutionError("request.parameters must be an object")
    allowed = {
        "bin_size", "min_bin_size", "max_bin_size", "strand_type", "paired", "genome_build",
        "reverse_complement", "unique_hit", "assign_multihits", "rerun_disambiguated_multihits",
        "multicore", "padj_method", "log_odd_cutoff", "pvalue_cutoff", "adjusted_pvalue_cutoff",
        "empirical_fdr_cutoff",
        "seed",
    }
    unknown = set(parameters) - allowed
    if unknown:
        raise RIPSeekerExecutionError("unknown RIPSeeker parameters: " + ", ".join(sorted(unknown)))
    values = {
        "bin_size": parameters.get("bin_size"),
        "min_bin_size": int(parameters.get("min_bin_size", 200)),
        "max_bin_size": int(parameters.get("max_bin_size", 1200)),
        "strand_type": parameters.get("strand_type"),
        "paired": bool(parameters.get("paired", False)),
        "genome_build": str(parameters.get("genome_build", "unknown")).strip(),
        "reverse_complement": bool(parameters.get("reverse_complement", False)),
        "unique_hit": bool(parameters.get("unique_hit", True)),
        "assign_multihits": bool(parameters.get("assign_multihits", True)),
        "rerun_disambiguated_multihits": bool(parameters.get("rerun_disambiguated_multihits", True)),
        "multicore": bool(parameters.get("multicore", True)),
        "padj_method": str(parameters.get("padj_method", "BH")),
        "log_odd_cutoff": float(parameters.get("log_odd_cutoff", 0)),
        "pvalue_cutoff": float(parameters.get("pvalue_cutoff", 1)),
        "adjusted_pvalue_cutoff": float(parameters.get("adjusted_pvalue_cutoff", 1)),
        "empirical_fdr_cutoff": float(parameters.get("empirical_fdr_cutoff", 1)),
        "seed": int(parameters.get("seed", 20260802)),
    }
    if values["bin_size"] is not None:
        values["bin_size"] = int(values["bin_size"])
    if values["strand_type"] not in {None, "+", "-", "*"}:
        raise RIPSeekerExecutionError("strand_type must be omitted, +, -, or *")
    if values["min_bin_size"] < 1 or values["max_bin_size"] < values["min_bin_size"]:
        raise RIPSeekerExecutionError("automatic bin-size range is invalid")
    if values["bin_size"] is not None and values["bin_size"] < 1:
        raise RIPSeekerExecutionError("bin_size must be positive")
    if any(not 0 <= values[name] <= 1 for name in ("pvalue_cutoff", "adjusted_pvalue_cutoff", "empirical_fdr_cutoff")):
        raise RIPSeekerExecutionError("RIPSeeker probability cutoffs must be in [0,1]")
    if not 0 <= values["seed"] <= 2147483647:
        raise RIPSeekerExecutionError("seed must be an integer in [0, 2147483647]")
    if output_dir.exists() or report_path.exists():
        raise RIPSeekerExecutionError("output directory and report path must not already exist")
    executable = None
    docker = None
    image_identity = None
    if container_image is None:
        executable = shutil.which(rscript) if "/" not in rscript else str(Path(rscript).expanduser().resolve())
        if not executable or not Path(executable).is_file():
            raise RIPSeekerExecutionError(f"Rscript executable not found: {rscript}")
    else:
        if not isinstance(container_image, str) or not container_image.strip():
            raise RIPSeekerExecutionError("container_image must be a nonempty immutable image reference")
        docker = shutil.which("docker")
        if not docker:
            raise RIPSeekerExecutionError("Docker is required for the isolated RIPSeeker runtime")
        inspected = subprocess.run(
            [docker, "image", "inspect", container_image, "--format", "{{json .RepoDigests}}"],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if inspected.returncode != 0:
            raise RIPSeekerExecutionError(f"RIPSeeker container is unavailable: {container_image}")
        digests = json.loads(inspected.stdout.strip() or "[]")
        image_identity = digests[0] if digests else container_image
    helper = Path(__file__).resolve().parents[1] / "modules" / "builtin" / "bulk-rbp-rna-binding" / "templates" / "run_ripseeker.R"
    if not helper.is_file():
        raise RIPSeekerExecutionError("packaged RIPSeeker R adapter is missing")
    output_dir.mkdir(parents=True)
    links = output_dir / "localized_bams"; links.mkdir()
    input_records: list[dict[str, Any]] = []
    for group, paths in (("RIP", rip_bams), ("CONTROL", control_bams)):
        for index, source in enumerate(paths, 1):
            target = links / f"{group}_{index:03d}.bam"
            try:
                target.hardlink_to(source)
            except OSError:
                shutil.copy2(source, target)
            source_index = Path(str(source) + ".bai")
            if not source_index.is_file():
                source_index = source.with_suffix(".bai")
            target_index = Path(str(target) + ".bai")
            try:
                target_index.hardlink_to(source_index.resolve())
            except OSError:
                shutil.copy2(source_index.resolve(), target_index)
            input_records.append({
                "group": group.lower(),
                "path": str(source),
                "bytes": source.stat().st_size,
                "sha256": sha256(source),
                "index": {
                    "path": str(source_index.resolve()),
                    "bytes": source_index.resolve().stat().st_size,
                    "sha256": sha256(source_index.resolve()),
                },
            })
    provenance = output_dir / "provenance"; provenance.mkdir()
    config = provenance / "parameters.json"
    config.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    packaged_helper = provenance / "run_ripseeker.R"
    shutil.copy2(helper, packaged_helper)
    results = output_dir / "results"
    if container_image is None:
        argv = [str(executable), str(packaged_helper), str(links), str(config), str(results), RIPSEEKER_VERSION]
    else:
        argv = [
            str(docker), "run", "--rm", "--platform", container_platform,
            "--mount", f"type=bind,src={output_dir.resolve()},dst=/job",
            container_image, "Rscript", "/job/provenance/run_ripseeker.R",
            "/job/localized_bams", "/job/provenance/parameters.json", "/job/results", RIPSEEKER_VERSION,
        ]
    completed = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=timeout_seconds)
    log = provenance / "ripseeker.log"
    log.write_text("$ " + " ".join(json.dumps(value) for value in argv) + "\n\nSTDOUT\n" + completed.stdout + "\nSTDERR\n" + completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RIPSeekerExecutionError(f"RIPSeeker failed with exit code {completed.returncode}; see {log}")
    version = results / "RIPSeeker_version.txt"
    validation_path = results / "RIPSeeker_validation.json"
    result_rds = results / "RIPSeeker_result.rds"
    regions = list(results.glob("RIPregions.*"))
    models = list(results.glob("*.RData"))
    if (
        not version.is_file()
        or version.read_text().strip() != RIPSEEKER_VERSION
        or not validation_path.is_file()
        or not result_rds.is_file()
        or not regions
        or not models
    ):
        raise RIPSeekerExecutionError("RIPSeeker completed without version, region, model, RDS, and reload-validation outputs")
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RIPSeekerExecutionError("RIPSeeker reload validation is unreadable") from error
    if (
        validation.get("ripseeker_version") != RIPSEEKER_VERSION
        or validation.get("reload_passed") is not True
        or int(validation.get("total_region_rows", 0)) < 1
        or not validation.get("model_files")
    ):
        raise RIPSeekerExecutionError("RIPSeeker reload validation did not pass")
    output_records = {
        "regions": [{"path": str(path.relative_to(output_dir)), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in regions if path.stat().st_size > 0],
        "models": [{"path": str(path.relative_to(output_dir)), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in models if path.stat().st_size > 0],
        "result_rds": {"path": str(result_rds.relative_to(output_dir)), "bytes": result_rds.stat().st_size, "sha256": sha256(result_rds)},
        "reload_validation": {"path": str(validation_path.relative_to(output_dir)), "bytes": validation_path.stat().st_size, "sha256": sha256(validation_path)},
    }
    if not output_records["regions"] or not output_records["models"]:
        raise RIPSeekerExecutionError("RIPSeeker required outputs are empty")
    implementation = Path(__file__).resolve()
    runtime_dir = implementation.parents[1] / "runtime_compat" / "ripseeker"
    dockerfile = runtime_dir / "Dockerfile"
    compatibility_patch = runtime_dir / "bioconductor-3.11-namespace.patch"
    report = {
        "schema_version": 1, "module_id": "bulk-rbp-rna-binding", "assay": "rip-seq", "passed": True,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "workflow": {
            "name": "RIPSeeker", "version": RIPSEEKER_VERSION, "commit": RIPSEEKER_COMMIT,
            "source": RIPSEEKER_SOURCE, "bioconductor_release": "3.11",
            "package_status": "last-supported-release-before-removal-in-3.12",
            "runtime": "container" if container_image else "local-r", "container_identity": image_identity,
            "container_platform": container_platform if container_image else None,
            "cran_mirror": "https://mirrors.tuna.tsinghua.edu.cn/CRAN/" if container_image else None,
            "bioconductor_mirror": "https://mirrors.tuna.tsinghua.edu.cn/bioconductor" if container_image else None,
            "container_build": {
                "dockerfile": {"path": str(dockerfile.relative_to(implementation.parents[2])), "sha256": sha256(dockerfile)},
                "compatibility_patch": {"path": str(compatibility_patch.relative_to(implementation.parents[2])), "sha256": sha256(compatibility_patch)},
            } if container_image else None,
        },
        "implementation": {"path": str(implementation.relative_to(implementation.parents[2])), "sha256": sha256(implementation)},
        "inputs": input_records, "parameters": values, "outputs": output_records,
        "validation": validation,
        "provenance": {"parameters_sha256": sha256(config), "helper_sha256": sha256(packaged_helper), "log_sha256": sha256(log)},
        "interpretation_scope": "RIPSeeker identifies protein-associated RNA enrichment regions. The result represents RIP-seq enrichment at regional resolution and is intended for replicate-aware follow-up and orthogonal binding validation.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
