"""Read-only discovery of optional scientific compute backends."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .model_backends import backend_catalog


@dataclass(frozen=True)
class RuntimeState:
    available: bool
    executable: str | None = None
    version: str | None = None
    details: dict[str, object] = field(default_factory=dict)


Which = Callable[[str], str | None]
Probe = Callable[[Sequence[str], float], tuple[int, str, str]]


def _default_probe(command: Sequence[str], timeout: float) -> tuple[int, str, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", type(exc).__name__
    return result.returncode, result.stdout[:4000], result.stderr[:4000]


def _version_state(
    candidates: tuple[str, ...],
    version_args: tuple[str, ...],
    *,
    which: Which,
    probe: Probe,
) -> RuntimeState:
    for name in candidates:
        executable = which(name)
        if not executable:
            continue
        code, stdout, stderr = probe([name, *version_args], 5.0)
        version = (stdout or stderr).strip().splitlines()[0][:300] if (stdout or stderr).strip() else None
        return RuntimeState(available=True, executable=executable, version=version, details={"probe_ok": code == 0})
    return RuntimeState(available=False)


def runtime_status(*, which: Which = shutil.which, probe: Probe = _default_probe) -> dict[str, RuntimeState]:
    python = _version_state(("python3", "python"), ("--version",), which=which, probe=probe)
    r_runtime = _version_state(("Rscript",), ("--version",), which=which, probe=probe)

    container = RuntimeState(available=False)
    for command in ("docker", "podman"):
        executable = which(command)
        if executable:
            code, stdout, stderr = probe([command, "version", "--format", "{{.Client.Version}}"], 5.0)
            version = (stdout or stderr).strip().splitlines()[0][:300] if (stdout or stderr).strip() else None
            container = RuntimeState(code == 0, executable, version, {"engine": command})
            break

    gpu = RuntimeState(available=False)
    for command, arguments, family in (
        ("nvidia-smi", ("--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"), "cuda"),
        ("rocm-smi", ("--showproductname",), "rocm"),
    ):
        executable = which(command)
        if executable:
            code, stdout, stderr = probe([command, *arguments], 5.0)
            details = {"family": family, "devices": [line.strip() for line in stdout.splitlines() if line.strip()][:16]}
            gpu = RuntimeState(code == 0, executable, (stderr.strip() or None), details)
            break

    slurm = _version_state(("sbatch",), ("--version",), which=which, probe=probe)

    local_commands = tuple(backend.id for backend in backend_catalog().values() if which(backend.executable))
    local_model = RuntimeState(
        available=bool(local_commands),
        details={"commands": list(local_commands), "mode": "local_scientific_compute"},
    )
    return {
        "python": python,
        "r": r_runtime,
        "container": container,
        "gpu": gpu,
        "slurm": slurm,
        "local_model": local_model,
    }
