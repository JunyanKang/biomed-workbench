from __future__ import annotations

import os
from pathlib import Path


def source_root() -> Path | None:
    configured = os.environ.get("OPENSCIENCE_SOURCE_ROOT")
    return Path(configured).expanduser() if configured else None


def connector_path(relative_path: str) -> Path | None:
    root = source_root()
    return root / relative_path if root else None
