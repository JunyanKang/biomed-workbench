"""Codex-callable read-only runtime discovery."""

from __future__ import annotations

from dataclasses import asdict

from biomed_workbench.services.environments import runtime_status


def status() -> dict[str, object]:
    return {name: asdict(state) for name, state in runtime_status().items()}
