"""Single-source plugin version loading."""

from __future__ import annotations

import json
import re
from pathlib import Path


PLUGIN_MANIFEST = Path(__file__).resolve().parents[1] / ".codex-plugin" / "plugin.json"
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def read_version(manifest: Path = PLUGIN_MANIFEST) -> str:
    try:
        version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("plugin manifest does not contain a readable version") from exc
    if not isinstance(version, str) or not _VERSION_RE.fullmatch(version):
        raise RuntimeError("plugin manifest version is invalid")
    return version


VERSION = read_version()
