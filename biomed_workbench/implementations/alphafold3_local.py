"""AlphaFold 3 v3.0.3 local execution backend for an already-approved runtime.

This product-owned executor never installs software, downloads model parameters,
or downloads reference databases.  Its caller must enforce scientific terms,
host headroom, and explicit user permission before invoking it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


ALPHAFOLD3_RELEASE = "3.0.3"
ALLOWED_BACKENDS = frozenset({"local-native", "local-container", "local-portable-container"})


def _stable_file(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty path")
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be a stable regular file")
    return path


def _stable_directory(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty path")
    path = Path(value).expanduser().resolve()
    if not path.is_dir() or path.is_symlink():
        raise ValueError(f"{label} must be a stable directory")
    return path


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _bounded_integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be {minimum}..{maximum}")
    return value


def _executable(value: object, default: str, label: str) -> str:
    candidate = str(value).strip() if isinstance(value, str) and value.strip() else default
    resolved = shutil.which(candidate) if os.sep not in candidate else str(_stable_file(candidate, label))
    if not resolved:
        raise ValueError(f"{label} is unavailable")
    return resolved


def _model_flags(request: dict[str, object], input_path: str, output_dir: str, model_dir: str | None, db_dir: str | None) -> list[str]:
    flags = [
        f"--json_path={input_path}",
        f"--output_dir={output_dir}",
        f"--run_data_pipeline={'true' if request['run_data_pipeline'] else 'false'}",
        f"--run_inference={'true' if request['run_inference'] else 'false'}",
        f"--num_recycles={request['num_recycles']}",
        f"--num_diffusion_samples={request['num_diffusion_samples']}",
    ]
    if model_dir:
        flags.append(f"--model_dir={model_dir}")
    if db_dir:
        flags.append(f"--db_dir={db_dir}")
    if request["num_seeds"] is not None:
        flags.append(f"--num_seeds={request['num_seeds']}")
    for key in ("save_distogram", "save_embeddings", "compress_large_output_files"):
        if request[key]:
            flags.append(f"--{key}=true")
    if request["jax_compilation_cache_dir"]:
        flags.append(f"--jax_compilation_cache_dir={request['jax_compilation_cache_dir']}")
    return flags


def validate_local_request(request: dict[str, object]) -> dict[str, object]:
    allowed = {
        "backend",
        "input_path",
        "output_directory",
        "model_directory",
        "database_directory",
        "container_image",
        "local_executable",
        "container_runtime_executable",
        "portable_runtime_executable",
        "run_data_pipeline",
        "run_inference",
        "num_recycles",
        "num_diffusion_samples",
        "num_seeds",
        "save_distogram",
        "save_embeddings",
        "compress_large_output_files",
        "jax_compilation_cache_dir",
        "timeout_seconds",
    }
    if not isinstance(request, dict) or set(request) != allowed:
        raise ValueError("local AlphaFold 3 request is not a closed execution contract")
    backend = request["backend"]
    if backend not in ALLOWED_BACKENDS:
        raise ValueError("unsupported local AlphaFold 3 backend")
    input_path = _stable_file(request["input_path"], "AlphaFold 3 input")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("dialect") != "alphafold3" or payload.get("version") != 4:
        raise ValueError("local execution requires the official AlphaFold 3 v4 input dialect")
    output_dir = Path(str(request["output_directory"])).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise ValueError("local output directory must not be a symbolic link")
    run_data = _boolean(request["run_data_pipeline"], "run_data_pipeline")
    run_inference = _boolean(request["run_inference"], "run_inference")
    model_dir = _stable_directory(request["model_directory"], "model directory") if run_inference else None
    db_dir = _stable_directory(request["database_directory"], "database directory") if run_data else None
    normalized = dict(request)
    normalized.update(
        {
            "input_path": input_path,
            "output_directory": output_dir,
            "model_directory": model_dir,
            "database_directory": db_dir,
            "num_recycles": _bounded_integer(request["num_recycles"], "num_recycles", 1, 100),
            "num_diffusion_samples": _bounded_integer(request["num_diffusion_samples"], "num_diffusion_samples", 1, 100),
        }
    )
    if request["num_seeds"] is not None:
        normalized["num_seeds"] = _bounded_integer(request["num_seeds"], "num_seeds", 1, 100)
    for key in ("save_distogram", "save_embeddings", "compress_large_output_files"):
        normalized[key] = _boolean(request[key], key)
    normalized["timeout_seconds"] = _bounded_integer(
        request["timeout_seconds"], "timeout_seconds", 300, 604_800
    )
    return normalized


def build_local_command(request: dict[str, object]) -> tuple[list[str], dict[str, object]]:
    normalized = validate_local_request(request)
    backend = str(normalized["backend"])
    input_path = Path(normalized["input_path"])
    output_dir = Path(normalized["output_directory"])
    model_dir = Path(normalized["model_directory"]) if normalized["model_directory"] else None
    db_dir = Path(normalized["database_directory"]) if normalized["database_directory"] else None
    if backend == "local-native":
        executable = _executable(normalized["local_executable"], "run_alphafold.py", "AlphaFold 3 executable")
        command = [
            executable,
            *_model_flags(
                normalized,
                str(input_path),
                str(output_dir),
                str(model_dir) if model_dir else None,
                str(db_dir) if db_dir else None,
            ),
        ]
    elif backend == "local-container":
        runtime = _executable(normalized["container_runtime_executable"], "docker", "container runtime")
        image = str(normalized["container_image"] or "").strip()
        if not image or re.search(r"[\r\n\x00]", image):
            raise ValueError("container image identity is invalid")
        command = [
            runtime,
            "run",
            "--rm",
            "--gpus",
            "all",
            "--volume",
            f"{input_path.parent}:/root/af_input:ro",
            "--volume",
            f"{output_dir}:/root/af_output",
        ]
        if model_dir:
            command.extend(["--volume", f"{model_dir}:/root/models:ro"])
        if db_dir:
            command.extend(["--volume", f"{db_dir}:/root/public_databases:ro"])
        command.extend(
            [
                image,
                "python",
                "run_alphafold.py",
                *_model_flags(
                    normalized,
                    f"/root/af_input/{input_path.name}",
                    "/root/af_output",
                    "/root/models" if model_dir else None,
                    "/root/public_databases" if db_dir else None,
                ),
            ]
        )
    else:
        runtime = _executable(normalized["portable_runtime_executable"], "apptainer", "portable container runtime")
        image = _stable_file(normalized["container_image"], "portable container image")
        command = [
            runtime,
            "exec",
            "--nv",
            "--bind",
            f"{input_path.parent}:/root/af_input:ro",
            "--bind",
            f"{output_dir}:/root/af_output",
        ]
        if model_dir:
            command.extend(["--bind", f"{model_dir}:/root/models:ro"])
        if db_dir:
            command.extend(["--bind", f"{db_dir}:/root/public_databases:ro"])
        command.extend(
            [
                str(image),
                "python",
                "run_alphafold.py",
                *_model_flags(
                    normalized,
                    f"/root/af_input/{input_path.name}",
                    "/root/af_output",
                    "/root/models" if model_dir else None,
                    "/root/public_databases" if db_dir else None,
                ),
            ]
        )
    provenance = {
        "alphafold3_release": ALPHAFOLD3_RELEASE,
        "backend": backend,
        "input_sha256": _sha256(input_path),
        "runtime_identity": Path(command[0]).name,
        "runtime_path_recorded": False,
        "model_assets_bundled": False,
        "database_assets_bundled": False,
    }
    return command, provenance


def execute_alphafold3_local(request: dict[str, object]) -> dict[str, object]:
    command, provenance = build_local_command(request)
    output_dir = Path(str(request["output_directory"])).expanduser().resolve()
    log_path = output_dir / "alphafold3_runtime.log"
    with log_path.open("w", encoding="utf-8") as handle:
        try:
            completed = subprocess.run(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=int(request["timeout_seconds"]),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"AlphaFold 3 local execution exceeded {request['timeout_seconds']} seconds"
            ) from exc
    if completed.returncode:
        raise RuntimeError(f"AlphaFold 3 local execution failed with exit code {completed.returncode}")
    return {
        "state": "completed",
        "local_executor": provenance,
        "runtime_log": {"path": log_path.name, "sha256": _sha256(log_path)},
    }
