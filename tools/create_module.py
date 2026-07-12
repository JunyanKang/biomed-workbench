#!/usr/bin/env python3
"""Atomically create and validate an independent scientific module package."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry, ModuleRegistryError  # noqa: E402
from tools.validate_module import validate_module  # noqa: E402


class ModuleCreationError(ValueError):
    """Raised when a request cannot become a fully validated module package."""


def _validate_request(request: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(request, dict) or set(request) != {"manifest", "tests"}:
        raise ModuleCreationError("creation request must contain exactly manifest and tests")
    if not isinstance(request["manifest"], dict) or not isinstance(request["tests"], list) or not request["tests"]:
        raise ModuleCreationError("creation request requires a manifest and at least one executable test")
    try:
        manifest = parse_manifest(request["manifest"])
    except ValueError as exc:
        raise ModuleCreationError(f"manifest contract failed: {exc}") from exc
    return dict(request["manifest"]), list(request["tests"])


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o644)


def create_module(request: dict[str, Any], registry_root: Path | str) -> Path:
    """Create a module only after package, execution, and registry validation pass."""
    manifest_payload, cases = _validate_request(request)
    module_id = str(manifest_payload["id"])
    root = Path(registry_root).expanduser().absolute()
    if root.is_symlink():
        raise ModuleCreationError("registry root must not be a symbolic link")
    root.mkdir(parents=True, exist_ok=True, mode=0o755)
    target = root / module_id
    if target.exists():
        raise ModuleCreationError(f"module already exists: {module_id}")

    temporary_parent = Path(tempfile.mkdtemp(prefix=f".{module_id}.creating-", dir=root))
    temporary_module = temporary_parent / module_id
    try:
        temporary_module.mkdir(mode=0o755)
        _write_json(temporary_module / "module.json", manifest_payload)
        _write_json(temporary_module / "tests" / "cases.json", {"schema_version": 1, "cases": cases})
        report = validate_module(temporary_module)
        if not report["valid"]:
            raise ModuleCreationError("; ".join(report["errors"]))
        try:
            ModuleRegistry.discover(root)
        except ModuleRegistryError as exc:
            raise ModuleCreationError(f"registry compatibility failed: {exc}") from exc
        os.replace(temporary_module, target)
        return target
    except ModuleCreationError:
        raise
    except Exception as exc:
        raise ModuleCreationError(f"module creation failed: {exc}") from exc
    finally:
        shutil.rmtree(temporary_parent, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, help="Complete JSON creation request")
    parser.add_argument("--registry-root", type=Path, required=True, help="Destination module registry")
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        path = create_module(request, args.registry_root)
    except (OSError, json.JSONDecodeError, ModuleCreationError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"created": path.as_posix()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
