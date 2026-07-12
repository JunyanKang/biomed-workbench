"""License-gated registry for independently runnable scientific models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ModelBackend:
    id: str
    tasks: tuple[str, ...]
    executable: str
    code_license: str
    weight_license: str
    license_url: str
    cpu_supported: bool
    gpu_supported: bool


_BACKENDS = {
    "boltz": ModelBackend(
        "boltz", ("structure_prediction", "complex_prediction", "affinity_prediction"), "boltz",
        "MIT", "MIT", "https://github.com/jwohlwend/boltz", True, True,
    ),
    "diffdock": ModelBackend(
        "diffdock", ("molecular_docking",), "diffdock", "MIT", "MIT",
        "https://github.com/gcorso/DiffDock", True, True,
    ),
    "foldseek": ModelBackend(
        "foldseek", ("structure_search",), "foldseek", "GPL-3.0", "not_applicable",
        "https://github.com/steineggerlab/foldseek", True, True,
    ),
    "mmseqs": ModelBackend(
        "mmseqs", ("sequence_search", "msa_search"), "mmseqs", "GPL-3.0", "not_applicable",
        "https://github.com/soedinglab/MMseqs2", True, True,
    ),
    "proteinmpnn": ModelBackend(
        "proteinmpnn", ("inverse_folding", "sequence_design"), "protein_mpnn_run.py", "MIT", "MIT",
        "https://github.com/dauparas/ProteinMPNN", True, True,
    ),
}


def backend_catalog() -> dict[str, ModelBackend]:
    return dict(_BACKENDS)


def select_backend(task: str, *, available: Iterable[str]) -> dict[str, Any]:
    candidates = [backend for backend in _BACKENDS.values() if task in backend.tasks]
    available_ids = set(available)
    selected = next((backend for backend in candidates if backend.id in available_ids), None)
    return {
        "task": task,
        "status": "ready" if selected else "unavailable",
        "backend": selected.id if selected else None,
        "candidates": [backend.id for backend in candidates],
        "network_fallback": False,
        "reason": None if selected else "No registered local backend for this task is currently available.",
    }


def _required(inputs: dict[str, Any], *names: str) -> list[str]:
    values = []
    for name in names:
        value = inputs.get(name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"local model input requires {name}")
        values.append(value)
    return values


def build_model_command(backend: str, inputs: dict[str, Any]) -> list[str]:
    if backend not in _BACKENDS:
        raise ValueError(f"unsupported local scientific model backend: {backend}")
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be an object")
    allowed = {
        "boltz": {"input", "output"},
        "foldseek": {"query", "database", "output", "temporary"},
        "mmseqs": {"query", "database", "output", "temporary"},
        "proteinmpnn": {"structure", "output", "sequences"},
        "diffdock": {"protein", "ligand", "output"},
    }[backend]
    extra = sorted(set(inputs) - allowed)
    if extra:
        raise ValueError(f"unsupported {backend} inputs: {', '.join(extra)}")
    if backend == "boltz":
        source, output = _required(inputs, "input", "output")
        return ["boltz", "predict", source, "--out_dir", output]
    if backend in {"foldseek", "mmseqs"}:
        query, database, output = _required(inputs, "query", "database", "output")
        temporary = str(inputs.get("temporary", f"{output}.tmp"))
        return [backend, "easy-search", query, database, output, temporary]
    if backend == "proteinmpnn":
        structure, output = _required(inputs, "structure", "output")
        sequences = int(inputs.get("sequences", 8))
        if not 1 <= sequences <= 10_000:
            raise ValueError("sequences must be 1..10000")
        return ["protein_mpnn_run.py", "--pdb_path", structure, "--out_folder", output, "--num_seq_per_target", str(sequences)]
    protein, ligand, output = _required(inputs, "protein", "ligand", "output")
    return ["diffdock", "--protein_path", protein, "--ligand", ligand, "--out_dir", output]
