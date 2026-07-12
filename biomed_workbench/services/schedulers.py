"""Permission-gated Slurm submission and read-only job monitoring."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from .compute import slurm_plan
from .execution import ProcessExecutor, execute_process, persist_manifest, reject_secret_arguments


_JOB_ID_RE = re.compile(r"^[0-9]+(?:_[0-9]+)?$")


def submit_slurm(
    command: list[str],
    job_name: str,
    cpus: int,
    memory_gb: int,
    time_minutes: int,
    *,
    output_directory: str,
    gpus: int = 0,
    partition: str | None = None,
    output: str = "slurm-%j.out",
    timeout_seconds: int = 30,
    permission_granted: bool = False,
    submitter: ProcessExecutor = execute_process,
) -> dict[str, Any]:
    if not permission_granted:
        raise PermissionError("Slurm submission requires explicit permission")
    reject_secret_arguments(command)
    plan = slurm_plan(command, job_name, cpus, memory_gb, time_minutes, gpus, partition, output)
    root = Path(output_directory).expanduser()
    if not root.is_absolute():
        raise ValueError("output_directory must be absolute")
    root.mkdir(parents=True, exist_ok=True)
    script_path = root / f"{job_name}-{uuid.uuid4().hex[:12]}.sbatch"
    script_path.write_text(plan["script"], encoding="utf-8")
    code, stdout, stderr = submitter(["sbatch", "--parsable", str(script_path)], float(timeout_seconds))
    raw_id = stdout.strip().split(";", 1)[0] if code == 0 else ""
    if code == 0 and not _JOB_ID_RE.fullmatch(raw_id):
        code = 65
        stderr = "scheduler returned an invalid job identifier"
    manifest = {
        "schema_version": 1,
        "operation": "slurm-submit",
        "status": "submitted" if code == 0 else "failed",
        "job_id": raw_id or None,
        "script_path": str(script_path),
        "resources": plan["resources"],
        "return_code": code,
        "scheduler_stdout": stdout,
        "scheduler_stderr": stderr,
    }
    manifest["manifest_path"] = persist_manifest(output_directory, "slurm-submit", manifest)
    return manifest


def monitor_slurm(job_id: str, *, timeout_seconds: int = 15, query: ProcessExecutor = execute_process) -> dict[str, Any]:
    if not _JOB_ID_RE.fullmatch(job_id):
        raise ValueError("job_id must be a numeric Slurm job identifier")
    code, stdout, stderr = query(["squeue", "--noheader", "--jobs", job_id, "--format=%T|%M|%N"], float(timeout_seconds))
    line = next((row for row in stdout.splitlines() if row.strip()), "")
    if code != 0:
        return {"job_id": job_id, "state": "UNKNOWN", "elapsed": None, "nodes": None, "query_error": stderr or "squeue failed"}
    if not line:
        return {"job_id": job_id, "state": "NOT_IN_QUEUE", "elapsed": None, "nodes": None, "query_error": None}
    parts = [part.strip() for part in line.split("|", 2)]
    parts.extend([None] * (3 - len(parts)))
    return {"job_id": job_id, "state": parts[0], "elapsed": parts[1], "nodes": parts[2], "query_error": None}
