"""Bounded local process execution and secret-free manifest persistence."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence


ProcessExecutor = Callable[[Sequence[str], float], tuple[int, str, str]]
_STREAM_LIMIT = 64_000
_SECRET_KEY_RE = re.compile(r"(?:api[_-]?key|token|secret|password|credential)", re.IGNORECASE)
_SECRET_ARGUMENT_RE = re.compile(r"^--?(?:api[-_]?key|token|secret|password|credential)(?:=|$)", re.IGNORECASE)


def reject_secret_arguments(argv: Sequence[str]) -> None:
    if any(_SECRET_ARGUMENT_RE.match(value) for value in argv):
        raise ValueError("credentials must be supplied through an approved environment variable, not command arguments")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): ("[REDACTED]" if _SECRET_KEY_RE.search(str(key)) else _redact(item)) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def execute_process(argv: Sequence[str], timeout: float) -> tuple[int, str, str]:
    if not argv or any(not isinstance(value, str) or not value for value in argv):
        raise ValueError("process arguments must be nonempty strings")
    if not 1 <= timeout <= 604_800:
        raise ValueError("timeout must be between 1 second and 7 days")
    try:
        result = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return 127, "", f"executable not found: {argv[0]}"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return 124, stdout[-_STREAM_LIMIT:], (stderr + "\nprocess timed out").strip()[-_STREAM_LIMIT:]
    return result.returncode, result.stdout[-_STREAM_LIMIT:], result.stderr[-_STREAM_LIMIT:]


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_artifacts(root: Path, *, limit: int = 1_000) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    paths = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
    artifacts = []
    for path in paths[:limit]:
        artifacts.append({"path": str(path), "size_bytes": path.stat().st_size, "sha256": file_digest(path)})
    return artifacts


def persist_manifest(output_directory: str, prefix: str, payload: dict[str, Any]) -> str:
    root = Path(output_directory).expanduser()
    if not root.is_absolute():
        raise ValueError("output_directory must be absolute")
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{prefix}-{uuid.uuid4().hex[:12]}.json"
    path.write_text(json.dumps(_redact(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)
