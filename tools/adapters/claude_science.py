from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def home() -> Path | None:
    configured = os.environ.get("CLAUDE_SCIENCE_HOME")
    return Path(configured).expanduser() if configured else None


def cli() -> str:
    configured = os.environ.get("CLAUDE_SCIENCE_CLI")
    if configured:
        return configured
    root = home()
    local = root / "bin" / "claude-science" if root else None
    if local and local.exists():
        return str(local)
    found = shutil.which("claude-science")
    if found:
        return found
    return ""


def python() -> str:
    configured = os.environ.get("CLAUDE_SCIENCE_PYTHON")
    if configured:
        return configured
    root = home()
    if root:
        return str(root / "conda" / "envs" / "python" / "bin" / "python")
    return shutil.which("python3") or "python3"


def rscript() -> str:
    configured = os.environ.get("CLAUDE_SCIENCE_RSCRIPT")
    if configured:
        return configured
    root = home()
    if root:
        return str(root / "conda" / "envs" / "r" / "bin" / "Rscript")
    return shutil.which("Rscript") or "Rscript"


def micromamba() -> str:
    configured = os.environ.get("CLAUDE_SCIENCE_MICROMAMBA")
    if configured:
        return configured
    root = home()
    if root:
        return str(root / "conda" / "bin" / "micromamba")
    return shutil.which("micromamba") or "micromamba"


def status_command() -> list[str]:
    code = (
        "import json, os, shutil; "
        "cli=os.environ.get('CLAUDE_SCIENCE_CLI') or shutil.which('claude-science'); "
        "home=os.environ.get('CLAUDE_SCIENCE_HOME'); "
        "print(json.dumps({'running': False, 'configured': bool(cli or home), "
        "'cli': bool(cli), 'home': bool(home)}, ensure_ascii=False))"
    )
    return [sys.executable, "-c", code]


def command_for_runtime(entry: dict, extra_args: list[str]) -> list[str]:
    tool_id = entry["id"]
    if tool_id == "runtime_status":
        return status_command()
    if tool_id == "runtime_open":
        if not cli():
            raise SystemExit("CLAUDE_SCIENCE_CLI or claude-science on PATH is required for runtime_open.")
        return [cli(), "open", *extra_args]
    if tool_id == "runtime_serve":
        if not cli():
            raise SystemExit("CLAUDE_SCIENCE_CLI or claude-science on PATH is required for runtime_serve.")
        return [cli(), "serve", *extra_args]
    if tool_id == "python_env":
        return [python(), *extra_args]
    if tool_id == "r_env":
        return [rscript(), *extra_args]
    if tool_id == "micromamba_env":
        return [micromamba(), *extra_args]
    raise SystemExit(f"Unknown runtime entry: {tool_id}")
