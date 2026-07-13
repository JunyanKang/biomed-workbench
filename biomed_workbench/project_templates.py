"""Executable support for module-local, Codex-adaptable project templates."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .kernel.artifact_store import ProjectArtifactStore
from .modules.compatibility import (
    ArtifactSnapshot,
    CompatibilityError,
    detect_environment,
    evaluate_compatibility,
    invoke_compatible,
)
from .modules.contract import ModuleManifest
from .modules.index import BUILTIN_ROOT
from .modules.registry import ModuleRegistry
from .modules.scientific_command import execute_scientific_command
from .runner import validate_schema_value


class ProjectTemplateError(RuntimeError):
    """A bounded failure from a project-adapted scientific template."""


def _digest_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _finite(value: object, location: str = "output") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ProjectTemplateError(f"{location} contains a nonfinite value")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _finite(item, f"{location}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _finite(item, f"{location}[{index}]")


def _artifact_snapshot(value: object) -> ArtifactSnapshot:
    if not isinstance(value, Mapping):
        raise ProjectTemplateError("every artifact snapshot must be an object")
    allowed = set(ArtifactSnapshot.__dataclass_fields__)
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ProjectTemplateError(f"artifact snapshot contains unsupported fields: {', '.join(unknown)}")
    payload = dict(value)
    for field in ("indexes", "metadata_fields", "payload_roles"):
        if field in payload:
            if not isinstance(payload[field], list):
                raise ProjectTemplateError(f"artifact snapshot {field} must be an array")
            payload[field] = tuple(payload[field])
    try:
        return ArtifactSnapshot(**payload)
    except (TypeError, ValueError) as exc:
        raise ProjectTemplateError("artifact snapshot is incomplete or invalid") from exc


def _load_manifest(module_id: str) -> tuple[ModuleRegistry, ModuleManifest]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    try:
        manifest = registry.get(module_id)
    except ValueError as exc:
        raise ProjectTemplateError(f"unknown project template module: {module_id}") from exc
    return registry, manifest


def _validate_quality_binding(manifest: ModuleManifest, quality_gate_ids: tuple[str, ...]) -> None:
    declared = {gate.id for gate in manifest.quality_gates if gate.blocks_interpretation}
    supplied = set(quality_gate_ids)
    if supplied != declared:
        missing = sorted(declared - supplied)
        extra = sorted(supplied - declared)
        detail = ", ".join((*[f"missing:{item}" for item in missing], *[f"extra:{item}" for item in extra]))
        raise ProjectTemplateError(f"template quality-gate binding differs from the manifest: {detail}")


def _request_parts(request: object) -> tuple[dict[str, Any], tuple[ArtifactSnapshot, ...]]:
    if not isinstance(request, Mapping):
        raise ProjectTemplateError("template request must be a JSON object")
    if "parameters" not in request or "artifacts" not in request:
        raise ProjectTemplateError("template request requires parameters and artifacts")
    parameters = request["parameters"]
    artifacts = request["artifacts"]
    if not isinstance(parameters, dict) or not isinstance(artifacts, list):
        raise ProjectTemplateError("parameters must be an object and artifacts must be an array")
    return dict(parameters), tuple(_artifact_snapshot(item) for item in artifacts)


def _pure_module(
    registry: ModuleRegistry,
    manifest: ModuleManifest,
    request: Mapping[str, object],
    parameters: dict[str, Any],
    artifacts: tuple[ArtifactSnapshot, ...],
) -> dict[str, object]:
    unsupported = sorted(set(request) - {"parameters", "artifacts"})
    if unsupported:
        raise ProjectTemplateError(f"non-command request contains unsupported fields: {', '.join(unsupported)}")
    validate_schema_value(manifest.input_schema, parameters, "parameters")
    environment = detect_environment(manifest)
    try:
        invocation = invoke_compatible(
            manifest,
            inputs=parameters,
            environment=environment,
            artifacts=artifacts,
            entrypoint=registry.resolve_entrypoint(manifest.id),
        )
    except CompatibilityError as exc:
        codes = ", ".join(item.code for item in exc.decision.findings)
        raise ProjectTemplateError(f"compatibility gate blocked execution: {codes}") from exc
    _finite(invocation.output)
    return {"result": invocation.output, "provenance": invocation.provenance}


def _safe_path_map(value: object, expected: set[str]) -> dict[str, Path]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ProjectTemplateError("input_files must exactly match command input bindings")
    paths = {}
    for name, raw in value.items():
        if not isinstance(raw, str):
            raise ProjectTemplateError("input file paths must be strings")
        path = Path(raw).expanduser().resolve(strict=True)
        if path.is_symlink() or not path.is_file():
            raise ProjectTemplateError(f"input file is not a stable regular file: {name}")
        paths[str(name)] = path
    return paths


def _command_module(
    manifest: ModuleManifest,
    request: Mapping[str, object],
    parameters: dict[str, Any],
    artifacts: tuple[ArtifactSnapshot, ...],
) -> dict[str, object]:
    unsupported = sorted(set(request) - {"parameters", "artifacts", "input_files", "artifact_store", "output_directory"})
    if unsupported:
        raise ProjectTemplateError(f"command request contains unsupported fields: {', '.join(unsupported)}")
    command = manifest.execution.command
    if command is None:
        raise ProjectTemplateError("command module lacks its command contract")
    validate_schema_value(manifest.input_schema, parameters, "parameters")
    environment = detect_environment(manifest)
    decision = evaluate_compatibility(manifest, environment, artifacts)
    if not decision.allowed or decision.compatibility_row_id is None:
        codes = ", ".join(item.code for item in decision.findings)
        raise ProjectTemplateError(f"compatibility gate blocked command execution: {codes}")
    input_files = _safe_path_map(request.get("input_files"), {item.name for item in command.inputs})
    store_raw = request.get("artifact_store")
    output_raw = request.get("output_directory")
    if not isinstance(store_raw, str) or not isinstance(output_raw, str):
        raise ProjectTemplateError("command request requires artifact_store and output_directory paths")
    store = ProjectArtifactStore(store_raw)
    output_directory = Path(output_raw).expanduser().resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    if output_directory.is_symlink():
        raise ProjectTemplateError("output directory must not be a symbolic link")
    input_payloads = {
        binding.name: store.import_file(input_files[binding.name], role=binding.role, media_type="application/octet-stream")
        for binding in command.inputs
    }
    result = execute_scientific_command(
        command,
        store=store,
        input_payloads=input_payloads,
        parameters=parameters,
        tool_versions=environment.tools,
        dependency_versions=environment.dependencies,
        compatibility_row_id=decision.compatibility_row_id,
    )
    outputs = {}
    for binding, payload in zip(command.outputs, result.output_payloads, strict=True):
        target = output_directory / binding.filename
        if target.exists():
            raise ProjectTemplateError(f"refusing to overwrite command output: {binding.filename}")
        store.materialize(payload, target)
        outputs[binding.name] = {"path": binding.filename, **payload.to_dict()}
    return {"result": outputs, "provenance": result.provenance}


def execute_project_template(module_id: str, quality_gate_ids: tuple[str, ...], request: object) -> dict[str, object]:
    """Execute one project-adapted module after compatibility and quality binding checks."""
    registry, manifest = _load_manifest(module_id)
    _validate_quality_binding(manifest, quality_gate_ids)
    parameters, artifacts = _request_parts(request)
    if manifest.execution.kind == "command":
        payload = _command_module(manifest, request, parameters, artifacts)
    else:
        payload = _pure_module(registry, manifest, request, parameters, artifacts)
    return {
        "schema_version": 1,
        "module_id": manifest.id,
        "module_version": manifest.version,
        "quality_gate_ids": list(quality_gate_ids),
        "request_digest": _digest_json(request),
        **payload,
    }


def write_template_result(path: str | os.PathLike[str], payload: Mapping[str, object]) -> None:
    """Write one result atomically and refuse to replace previous scientific evidence."""
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ProjectTemplateError(f"refusing to overwrite template result: {target.name}")
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=f".{target.name}.", delete=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
