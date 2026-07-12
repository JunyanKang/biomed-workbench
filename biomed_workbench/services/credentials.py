"""Central allowlist for optional scientific data credentials."""

from __future__ import annotations

import os


ALLOWED_CREDENTIALS = frozenset({"NCBI_API_KEY"})


def optional_credential(name: str) -> str | None:
    if name not in ALLOWED_CREDENTIALS:
        raise ValueError(f"credential is not allowlisted: {name}")
    value = os.environ.get(name, "").strip()
    return value or None


def credential_status() -> dict[str, bool]:
    return {name: bool(os.environ.get(name, "").strip()) for name in sorted(ALLOWED_CREDENTIALS)}
