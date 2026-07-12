from __future__ import annotations

import importlib
import os
from pathlib import Path


def source_root() -> Path | None:
    configured = os.environ.get("BIOMNI_SOURCE_ROOT")
    return Path(configured).expanduser() if configured else None


def import_function(module_file: str, function_name: str):
    module_name = module_file.replace("/", ".").removesuffix(".py")
    return getattr(importlib.import_module(module_name), function_name)
