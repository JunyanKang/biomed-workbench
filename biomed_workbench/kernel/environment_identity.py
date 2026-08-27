"""Versioned analysis-environment identities and repeat-execution drift gates."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

from .identity import digest_value


ANALYSIS_ENVIRONMENT_PROTOCOL_VERSION = "1.0.0"
ANALYSIS_ENVIRONMENT_IDENTITY_FIELDS = frozenset({
    "protocol_version", "manager", "name", "location", "location_digest", "interpreter",
    "interpreter_digest", "interpreter_version", "platform", "lock_files",
    "package_inventory_digest", "package_count", "container_image_digest", "content_digest",
    "tool_versions", "dependency_versions", "identity_digest",
})
_MANAGERS = frozenset({"conda", "mamba", "micromamba", "venv", "renv", "container", "system", "remote"})
_LOCK_NAMES = frozenset({
    "conda-lock.yml", "conda-lock.yaml", "environment.yml", "environment.yaml",
    "pyproject.toml", "poetry.lock", "uv.lock", "requirements.txt", "requirements-ci.txt",
    "renv.lock", "Dockerfile", "Singularity", "Apptainer.def",
})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _manager() -> tuple[str, str, str]:
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        executable = os.environ.get("MAMBA_EXE") or os.environ.get("CONDA_EXE", "")
        manager = "micromamba" if "micromamba" in executable else "mamba" if "mamba" in executable else "conda"
        return manager, os.environ.get("CONDA_DEFAULT_ENV", Path(conda_prefix).name), conda_prefix
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        return "venv", Path(virtual_env).name, virtual_env
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return "venv", Path(sys.prefix).name, sys.prefix
    return "system", "system-python", sys.prefix


def _package_inventory(manager: str, location: str) -> tuple[list[dict[str, str]], str]:
    records: list[dict[str, str]] = []
    conda_meta = Path(location) / "conda-meta"
    if manager in {"conda", "mamba", "micromamba"} and conda_meta.is_dir():
        for path in sorted(conda_meta.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            records.append({
                "ecosystem": "conda",
                "name": str(value.get("name", path.stem)),
                "version": str(value.get("version", "unknown")),
                "build": str(value.get("build", "unknown")),
                "channel": str(value.get("channel", "unknown")),
            })
    for distribution in importlib.metadata.distributions():
        name = str(distribution.metadata.get("Name") or "unknown").lower()
        records.append({"ecosystem": "python", "name": name, "version": str(distribution.version)})
    records.sort(key=lambda item: (item["ecosystem"], item["name"], item["version"]))
    return records, digest_value(records)


def _lock_files(project_root: str | Path | None) -> list[dict[str, str]]:
    if project_root is None:
        return []
    root = Path(project_root).expanduser().resolve(strict=False)
    if not root.is_dir():
        return []
    values = []
    for path in sorted(item for item in root.iterdir() if item.is_file() and item.name in _LOCK_NAMES):
        values.append({"path": path.name, "sha256": _sha256(path)})
    return values


def create_analysis_environment_identity(
    *,
    manager: str,
    name: str,
    location: str,
    location_digest: str,
    interpreter: str,
    interpreter_digest: str,
    interpreter_version: str,
    platform_name: str,
    lock_files: list[dict[str, str]],
    package_inventory_digest: str,
    package_count: int,
    container_image_digest: str | None,
    tool_versions: Mapping[str, str],
    dependency_versions: Mapping[str, str],
) -> dict[str, Any]:
    """Create a validated identity from explicit local, container, HPC, or remote observations."""
    content_basis = {
        "protocol_version": ANALYSIS_ENVIRONMENT_PROTOCOL_VERSION,
        "manager": manager,
        "interpreter_version": interpreter_version,
        "platform": platform_name,
        "lock_files": lock_files,
        "package_inventory_digest": package_inventory_digest,
        "package_count": package_count,
        "container_image_digest": container_image_digest,
        "tool_versions": dict(sorted(tool_versions.items())),
        "dependency_versions": dict(sorted(dependency_versions.items())),
    }
    identity_basis = {
        **content_basis,
        "name": name,
        "location": location,
        "location_digest": location_digest,
        "interpreter": interpreter,
        "interpreter_digest": interpreter_digest,
    }
    return validate_analysis_environment({
        **identity_basis,
        "content_digest": digest_value(content_basis),
        "identity_digest": digest_value(identity_basis),
    })


def capture_analysis_environment(
    *,
    project_root: str | Path | None = None,
    container_image_digest: str | None = None,
    tool_versions: Mapping[str, str] | None = None,
    dependency_versions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Capture one secret-free, content-addressed identity for the active runtime."""
    manager, name, location = _manager()
    packages, package_digest = _package_inventory(manager, location)
    locks = _lock_files(project_root)
    resolved_location = str(Path(location).expanduser().resolve(strict=False))
    resolved_interpreter = str(Path(sys.executable).resolve(strict=False))
    return create_analysis_environment_identity(
        manager=manager,
        name=name,
        location=f"{manager}://{name}",
        location_digest=_text_digest(resolved_location),
        interpreter=Path(sys.executable).name,
        interpreter_digest=_text_digest(resolved_interpreter),
        interpreter_version=platform.python_version(),
        platform_name=f"{platform.system().lower()}-{platform.machine().lower()}",
        lock_files=locks,
        package_inventory_digest=package_digest,
        package_count=len(packages),
        container_image_digest=container_image_digest,
        tool_versions=tool_versions or {},
        dependency_versions=dependency_versions or {},
    )


def validate_analysis_environment(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize an environment identity supplied by a local or remote executor."""
    required = ANALYSIS_ENVIRONMENT_IDENTITY_FIELDS
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("analysis environment identity has incomplete or unsupported fields")
    normalized = dict(value)
    if normalized["protocol_version"] != ANALYSIS_ENVIRONMENT_PROTOCOL_VERSION:
        raise ValueError("analysis environment protocol version is unsupported")
    if normalized["manager"] not in _MANAGERS:
        raise ValueError("analysis environment manager is unsupported")
    if not all(isinstance(normalized[key], str) and normalized[key] for key in (
        "name", "location", "interpreter", "interpreter_version", "platform",
    )):
        raise ValueError("analysis environment identity requires explicit runtime coordinates")
    if not isinstance(normalized["package_count"], int) or isinstance(normalized["package_count"], bool) or normalized["package_count"] < 0:
        raise ValueError("analysis environment package count is invalid")
    for key in ("tool_versions", "dependency_versions"):
        versions = normalized[key]
        if not isinstance(versions, Mapping) or any(
            not isinstance(name, str) or not name or not isinstance(version, str) or not version
            for name, version in versions.items()
        ):
            raise ValueError(f"analysis environment {key} must be an explicit version mapping")
        normalized[key] = dict(sorted(versions.items()))
    locks = normalized["lock_files"]
    if not isinstance(locks, (list, tuple)) or any(
        not isinstance(item, Mapping) or set(item) != {"path", "sha256"}
        or not isinstance(item["path"], str) or not isinstance(item["sha256"], str) or len(item["sha256"]) != 64
        for item in locks
    ):
        raise ValueError("analysis environment lock-file identities are invalid")
    normalized["lock_files"] = [dict(item) for item in locks]
    for key in ("location_digest", "interpreter_digest", "package_inventory_digest", "content_digest", "identity_digest"):
        if not isinstance(normalized[key], str) or len(normalized[key]) != 64:
            raise ValueError(f"analysis environment {key} must be SHA-256")
    container_digest = normalized["container_image_digest"]
    if container_digest is not None and (not isinstance(container_digest, str) or len(container_digest) != 64):
        raise ValueError("analysis environment container image digest must be SHA-256 or null")
    content_basis = {
        key: normalized[key]
        for key in (
            "protocol_version", "manager", "interpreter_version", "platform", "lock_files",
            "package_inventory_digest", "package_count", "container_image_digest",
            "tool_versions", "dependency_versions",
        )
    }
    if digest_value(content_basis) != normalized["content_digest"]:
        raise ValueError("analysis environment content digest differs from its recorded content")
    identity_basis = {
        **content_basis,
        "name": normalized["name"],
        "location": normalized["location"],
        "location_digest": normalized["location_digest"],
        "interpreter": normalized["interpreter"],
        "interpreter_digest": normalized["interpreter_digest"],
    }
    if digest_value(identity_basis) != normalized["identity_digest"]:
        raise ValueError("analysis environment identity digest differs from its recorded content")
    return normalized


def bind_analysis_environment_versions(
    value: Mapping[str, Any],
    *,
    tool_versions: Mapping[str, str],
    dependency_versions: Mapping[str, str],
) -> dict[str, Any]:
    """Bind module-observed tool and dependency versions into an environment identity."""
    normalized = validate_analysis_environment(value)
    normalized["tool_versions"] = dict(sorted(tool_versions.items()))
    normalized["dependency_versions"] = dict(sorted(dependency_versions.items()))
    content_basis = {
        key: normalized[key]
        for key in (
            "protocol_version", "manager", "interpreter_version", "platform", "lock_files",
            "package_inventory_digest", "package_count", "container_image_digest",
            "tool_versions", "dependency_versions",
        )
    }
    normalized["content_digest"] = digest_value(content_basis)
    identity_basis = {
        **content_basis,
        "name": normalized["name"],
        "location": normalized["location"],
        "location_digest": normalized["location_digest"],
        "interpreter": normalized["interpreter"],
        "interpreter_digest": normalized["interpreter_digest"],
    }
    normalized["identity_digest"] = digest_value(identity_basis)
    return validate_analysis_environment(normalized)


def environment_reuse_status(current: Mapping[str, Any], prior: tuple[Mapping[str, Any], ...]) -> str:
    """Classify whether a prior runtime can be safely reused for a repeat analysis."""
    normalized = validate_analysis_environment(current)
    if not prior:
        return "first-observed"
    valid_prior = [validate_analysis_environment(value) for value in prior]
    if any(value["identity_digest"] == normalized["identity_digest"] for value in valid_prior):
        return "reused-exact"
    if any(value["content_digest"] == normalized["content_digest"] for value in valid_prior):
        return "reused-relocated"
    return "drift-blocked"


def persist_analysis_environment_record(project_root: str | Path, value: Mapping[str, Any]) -> Path:
    """Persist one immutable environment record without overwriting an existing identity."""
    normalized = validate_analysis_environment(value)
    directory = Path(project_root).expanduser().resolve(strict=True) / ".biomed-workbench" / "environments"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{normalized['content_digest']}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != normalized:
            raise ValueError("analysis-environment record conflicts with its content identity")
        return path
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path
