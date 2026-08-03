"""Repository source, credential, path, and Python-syntax release checks."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

from biomed_workbench.services.credentials import ALLOWED_CREDENTIALS


SECRET_PATTERNS = (
    re.compile(r"(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"][A-Za-z0-9_-]{16,}['\"]", re.IGNORECASE),
    re.compile(r"\b[A-Z][A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET)=[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"(?:bearer\s+)[A-Za-z0-9._-]{20,}", re.IGNORECASE),
)
LOCAL_PATH_PATTERNS = ("/Users/" + "kangjunyan", "/private/" + "var/folders/")


def _publishable_files(root: Path):
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    for relative in result.stdout.decode().split("\0"):
        path = root / relative
        if relative and path.is_file():
            yield path


def validate_source_hygiene(root: Path) -> list[str]:
    """Return deterministic findings without printing or mutating the repository."""
    errors: list[str] = []
    for path in _publishable_files(root):
        text = path.read_text(errors="ignore")
        relative = path.relative_to(root).as_posix()
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            errors.append(f"credential-like value found in {relative}")
        if any(pattern in text for pattern in LOCAL_PATH_PATTERNS):
            errors.append(f"machine-local path found in {relative}")

    credential_names: set[str] = set()
    for operational_root in (root / "biomed_workbench", root / "tools", root / "skills"):
        if not operational_root.exists():
            continue
        for path in operational_root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and not any(part.startswith(".") for part in path.parts):
                text = path.read_text(errors="ignore")
                credential_names.update(re.findall(r"\b[A-Z][A-Z0-9_]*(?:API_KEY|AUTH_TOKEN)\b", text))
    undeclared = sorted(credential_names - set(ALLOWED_CREDENTIALS))
    if undeclared:
        errors.append(f"undeclared operational credentials: {undeclared}")

    syntax_errors: list[str] = []
    for operational_root in (root / "biomed_workbench", root / "tools"):
        for path in operational_root.rglob("*.py"):
            try:
                ast.parse(path.read_text(errors="ignore"), filename=str(path))
            except SyntaxError as exc:
                syntax_errors.append(f"{path.relative_to(root)}:{exc.lineno}")
    if syntax_errors:
        errors.append(f"Python syntax errors: {syntax_errors[:10]}")
    return errors
