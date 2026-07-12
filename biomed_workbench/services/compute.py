"""Side-effect-free plans for containers, SLURM, and local scientific models."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any


_IMAGE_RE = re.compile(r"^[A-Za-z0-9._/-]+(?::[A-Za-z0-9._-]+|@sha256:[0-9a-f]{64})$")
_JOB_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _strings(values: list[str], name: str) -> list[str]:
    if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f"{name} must be a nonempty list of strings")
    return list(values)


def container_plan(
    image: str,
    command: list[str],
    mounts: list[dict[str, str]] | None = None,
    gpu: bool = False,
    engine: str = "docker",
    workdir: str | None = None,
) -> dict[str, Any]:
    if engine not in {"docker", "podman"}:
        raise ValueError("engine must be docker or podman")
    if not _IMAGE_RE.fullmatch(image):
        raise ValueError("image must include a valid tag or sha256 digest")
    command = _strings(command, "command")
    argv = [engine, "run", "--rm"]
    normalized_mounts = []
    for mount in mounts or []:
        host = str(mount.get("host", ""))
        container = str(mount.get("container", ""))
        mode = str(mount.get("mode", "ro"))
        if not Path(host).is_absolute() or not container.startswith("/") or mode not in {"ro", "rw"}:
            raise ValueError("mounts require absolute host/container paths and mode ro or rw")
        specification = f"{host}:{container}:{mode}"
        argv.extend(["--volume", specification])
        normalized_mounts.append({"host": host, "container": container, "mode": mode})
    if gpu:
        if engine != "docker":
            raise ValueError("generic GPU planning currently requires the Docker --gpus contract")
        argv.extend(["--gpus", "all"])
    if workdir is not None:
        if not workdir.startswith("/"):
            raise ValueError("container workdir must be absolute")
        argv.extend(["--workdir", workdir])
    argv.extend([image, *command])
    return {
        "engine": engine,
        "image": image,
        "argv": argv,
        "mounts": normalized_mounts,
        "gpu_requested": gpu,
        "executes": False,
        "requires_explicit_run_permission": True,
    }


def slurm_plan(
    command: list[str],
    job_name: str,
    cpus: int,
    memory_gb: int,
    time_minutes: int,
    gpus: int = 0,
    partition: str | None = None,
    output: str = "slurm-%j.out",
) -> dict[str, Any]:
    command = _strings(command, "command")
    if not _JOB_RE.fullmatch(job_name):
        raise ValueError("job_name contains unsupported characters")
    if not 1 <= cpus <= 4096 or not 1 <= memory_gb <= 1_048_576 or not 1 <= time_minutes <= 525_600 or not 0 <= gpus <= 128:
        raise ValueError("SLURM resources exceed supported planning bounds")
    if partition is not None and not _JOB_RE.fullmatch(partition):
        raise ValueError("partition contains unsupported characters")
    if not output or "\n" in output or "\r" in output:
        raise ValueError("output path is invalid")
    hours, minutes = divmod(time_minutes, 60)
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --cpus-per-task={cpus}",
        f"#SBATCH --mem={memory_gb}G",
        f"#SBATCH --time={hours:02d}:{minutes:02d}:00",
        f"#SBATCH --output={output}",
    ]
    if gpus:
        lines.append(f"#SBATCH --gres=gpu:{gpus}")
    if partition:
        lines.append(f"#SBATCH --partition={partition}")
    lines.extend(["", " ".join(shlex.quote(value) for value in command)])
    return {
        "script": "\n".join(lines) + "\n",
        "resources": {"cpus": cpus, "memory_gb": memory_gb, "time_minutes": time_minutes, "gpus": gpus, "partition": partition},
        "submits": False,
        "requires_explicit_submit_permission": True,
    }


def _required(inputs: dict[str, Any], *names: str) -> list[str]:
    values = []
    for name in names:
        value = inputs.get(name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"local model input requires {name}")
        values.append(value)
    return values


def local_model_plan(backend: str, inputs: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be an object")
    if backend == "boltz":
        source, output = _required(inputs, "input", "output")
        argv = ["boltz", "predict", source, "--out_dir", output]
    elif backend == "foldseek":
        query, database, output = _required(inputs, "query", "database", "output")
        temporary = str(inputs.get("temporary", f"{output}.tmp"))
        argv = ["foldseek", "easy-search", query, database, output, temporary]
    elif backend == "mmseqs":
        query, database, output = _required(inputs, "query", "database", "output")
        temporary = str(inputs.get("temporary", f"{output}.tmp"))
        argv = ["mmseqs", "easy-search", query, database, output, temporary]
    elif backend == "proteinmpnn":
        structure, output = _required(inputs, "structure", "output")
        sequences = int(inputs.get("sequences", 8))
        if not 1 <= sequences <= 10_000:
            raise ValueError("sequences must be 1..10000")
        argv = ["protein_mpnn_run.py", "--pdb_path", structure, "--out_folder", output, "--num_seq_per_target", str(sequences)]
    elif backend == "diffdock":
        protein, ligand, output = _required(inputs, "protein", "ligand", "output")
        argv = ["diffdock", "--protein_path", protein, "--ligand", ligand, "--out_dir", output]
    else:
        raise ValueError(f"unsupported local scientific model backend: {backend}")
    return {
        "backend": backend,
        "argv": argv,
        "executable": argv[0],
        "execution_mode": "local_scientific_compute",
        "executes": False,
        "requires_explicit_run_permission": True,
        "manifest_fields": ["backend_version", "input_hashes", "parameters", "output_hashes", "validation"],
    }
