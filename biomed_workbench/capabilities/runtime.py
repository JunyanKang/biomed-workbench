"""Codex-callable managed compute capabilities."""

from __future__ import annotations

from dataclasses import asdict

from biomed_workbench.services.environments import runtime_status
from biomed_workbench.services.containers import run_container
from biomed_workbench.services.schedulers import monitor_slurm, submit_slurm
from biomed_workbench.services.model_execution import run_local_model


def status() -> dict[str, object]:
    return {name: asdict(state) for name, state in runtime_status().items()}


def container_run(
    image: str,
    command: list[str],
    output_directory: str,
    mounts: list[dict[str, str]] | None = None,
    gpu: bool = False,
    engine: str = "docker",
    workdir: str | None = None,
    timeout_seconds: int = 3600,
) -> dict[str, object]:
    return run_container(
        image,
        command,
        output_directory=output_directory,
        mounts=mounts,
        gpu=gpu,
        engine=engine,
        workdir=workdir,
        timeout_seconds=timeout_seconds,
        permission_granted=True,
    )


def slurm_submit(
    command: list[str],
    job_name: str,
    cpus: int,
    memory_gb: int,
    time_minutes: int,
    output_directory: str,
    gpus: int = 0,
    partition: str | None = None,
    output: str = "slurm-%j.out",
    timeout_seconds: int = 30,
) -> dict[str, object]:
    return submit_slurm(
        command,
        job_name,
        cpus,
        memory_gb,
        time_minutes,
        output_directory=output_directory,
        gpus=gpus,
        partition=partition,
        output=output,
        timeout_seconds=timeout_seconds,
        permission_granted=True,
    )


def slurm_monitor(job_id: str, timeout_seconds: int = 15) -> dict[str, object]:
    return monitor_slurm(job_id, timeout_seconds=timeout_seconds)


def local_model_run(
    backend: str,
    inputs: dict[str, object],
    output_directory: str,
    timeout_seconds: int = 86_400,
) -> dict[str, object]:
    return run_local_model(
        backend,
        inputs,
        output_directory,
        timeout_seconds=timeout_seconds,
        permission_granted=True,
    )
