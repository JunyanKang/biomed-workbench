"""Permission-gated execution for registered local scientific models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .execution import ProcessExecutor, collect_artifacts, execute_process, persist_manifest
from .model_backends import backend_catalog, build_model_command


def _confined_output(inputs: dict[str, Any], output_directory: str) -> tuple[dict[str, Any], Path]:
    root = Path(output_directory).expanduser()
    if not root.is_absolute():
        raise ValueError("output_directory must be absolute")
    root = root.resolve()
    normalized = dict(inputs)
    raw_output = inputs.get("output")
    if not isinstance(raw_output, str) or not raw_output:
        raise ValueError("local model input requires output")
    target = Path(raw_output).expanduser()
    target = (target if target.is_absolute() else root / target).resolve()
    if not target.is_relative_to(root):
        raise ValueError("model output must remain inside output_directory")
    normalized["output"] = str(target)
    if "temporary" in normalized:
        temporary = Path(str(normalized["temporary"])).expanduser()
        temporary = (temporary if temporary.is_absolute() else root / temporary).resolve()
        if not temporary.is_relative_to(root):
            raise ValueError("model temporary path must remain inside output_directory")
        normalized["temporary"] = str(temporary)
    return normalized, target


def run_local_model(
    backend: str,
    inputs: dict[str, Any],
    output_directory: str,
    *,
    timeout_seconds: int = 86_400,
    permission_granted: bool = False,
    executor: ProcessExecutor = execute_process,
) -> dict[str, Any]:
    if not permission_granted:
        raise PermissionError("local scientific model execution requires explicit permission")
    normalized, artifact_root = _confined_output(inputs, output_directory)
    command = build_model_command(backend, normalized)
    definition = backend_catalog()[backend]
    code, stdout, stderr = executor(command, float(timeout_seconds))
    manifest = {
        "schema_version": 1,
        "operation": "local-model-run",
        "status": "completed" if code == 0 else "failed",
        "backend": backend,
        "task_contracts": list(definition.tasks),
        "license": {
            "code": definition.code_license,
            "weights": definition.weight_license,
            "url": definition.license_url,
        },
        "command": command,
        "parameters": normalized,
        "return_code": code,
        "stdout": stdout,
        "stderr": stderr,
        "artifacts": collect_artifacts(artifact_root),
    }
    manifest["manifest_path"] = persist_manifest(output_directory, "local-model-run", manifest)
    return manifest
