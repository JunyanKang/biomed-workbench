"""Allowlisted, repository-external credentials for scientific data services."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Mapping


ALLOWED_CREDENTIALS = frozenset({"NCBI_API_KEY"})
_STORE_FILENAME = "credentials.json"
_CONFIG_HOME_OVERRIDE = "BIOMED_WORKBENCH_CONFIG_HOME"


def credential_store_path() -> Path:
    """Return the per-user credential-store path without creating it."""

    override = os.environ.get(_CONFIG_HOME_OVERRIDE, "").strip()
    if override:
        return Path(override).expanduser().resolve() / _STORE_FILENAME
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "biomed-workbench"
    elif os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        root = root / "biomed-workbench"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        root = root / "biomed-workbench"
    return root / _STORE_FILENAME


def _validate_name(name: str) -> None:
    if name not in ALLOWED_CREDENTIALS:
        raise ValueError(f"credential is not allowlisted: {name}")


def _read_store() -> dict[str, str]:
    path = credential_store_path()
    if not path.exists():
        return {}
    if path.is_symlink():
        raise PermissionError(f"credential store must not be a symbolic link: {path}")
    if os.name != "nt":
        permissions = stat.S_IMODE(path.stat().st_mode)
        if permissions & 0o077:
            raise PermissionError(
                f"credential store permissions must be 0600 or stricter: {path}"
            )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("credential store must contain a JSON object")
    values: dict[str, str] = {}
    for name, value in payload.items():
        _validate_name(str(name))
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"credential store contains an invalid value for {name}")
        values[str(name)] = value.strip()
    return values


def _write_store(values: Mapping[str, str]) -> None:
    path = credential_store_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".credentials-",
        suffix=".json",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        if os.name != "nt":
            os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(sorted(values.items())), handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def optional_credential(name: str) -> str | None:
    _validate_name(name)
    value = os.environ.get(name, "").strip()
    if value:
        return value
    return _read_store().get(name)


def credential_status() -> dict[str, bool]:
    return {name: optional_credential(name) is not None for name in sorted(ALLOWED_CREDENTIALS)}


def credential_sources() -> dict[str, str]:
    """Return configuration sources without exposing credential values."""

    stored = _read_store()
    return {
        name: (
            "environment"
            if os.environ.get(name, "").strip()
            else "local-user-store"
            if name in stored
            else "not-configured"
        )
        for name in sorted(ALLOWED_CREDENTIALS)
    }


def configure_credential(name: str, value: str) -> None:
    """Persist one allowlisted credential in the private per-user store."""

    _validate_name(name)
    normalized = value.strip()
    if not normalized:
        raise ValueError("credential value must not be empty")
    values = _read_store()
    values[name] = normalized
    _write_store(values)


def remove_credential(name: str) -> bool:
    """Remove a credential from the local store and report whether it existed."""

    _validate_name(name)
    values = _read_store()
    removed = values.pop(name, None) is not None
    if not removed:
        return False
    if values:
        _write_store(values)
    else:
        credential_store_path().unlink(missing_ok=True)
    return True
