"""Permission-gated local container execution."""

from __future__ import annotations

from typing import Any

from .compute import container_plan
from .execution import ProcessExecutor, execute_process, persist_manifest, reject_secret_arguments


def run_container(
    image: str,
    command: list[str],
    *,
    output_directory: str | None = None,
    mounts: list[dict[str, str]] | None = None,
    gpu: bool = False,
    engine: str = "docker",
    workdir: str | None = None,
    timeout_seconds: int = 3600,
    permission_granted: bool = False,
    executor: ProcessExecutor = execute_process,
) -> dict[str, Any]:
    if not permission_granted:
        raise PermissionError("container execution requires explicit permission")
    reject_secret_arguments(command)
    plan = container_plan(image, command, mounts=mounts, gpu=gpu, engine=engine, workdir=workdir)
    code, stdout, stderr = executor(plan["argv"], float(timeout_seconds))
    manifest = {
        "schema_version": 1,
        "operation": "container-run",
        "status": "completed" if code == 0 else "failed",
        "engine": engine,
        "image": image,
        "command": list(command),
        "gpu_requested": gpu,
        "mounts": plan["mounts"],
        "return_code": code,
        "stdout": stdout,
        "stderr": stderr,
    }
    if output_directory is not None:
        manifest["manifest_path"] = persist_manifest(output_directory, "container-run", manifest)
    return manifest
