"""Quality contract for code templates packaged with bioinformatics modules."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .contract import ModuleManifest


BIOINFORMATICS_DOMAINS = frozenset({"omics", "molecular_design"})
BIOINFORMATICS_MODULE_TYPES = frozenset({"analysis", "validation", "transform", "design"})
_PLACEHOLDER_RE = re.compile(r"\b(?:TODO|FIXME|NotImplementedError)\b|\.\.\.")
_FORBIDDEN_RE = re.compile(
    r"shell\s*=\s*True|os\.system\s*\(|(?:pip|conda|mamba)\s+install|"
    r"NVID" r"IA_" r"API_" r"KEY|NGC_" r"API_" r"KEY|(?:doc" r"ker|sl" r"urm|sbatch|srun)\b",
    re.IGNORECASE,
)
_REQUIRED_CONCEPTS = {
    "input validation": ("input", "read", "load"),
    "output serialization": ("output", "write", "save"),
    "failure handling": ("raise", "stop(", "try:", "trycatch"),
    "version provenance": ("version", "sessioninfo", "packageversion"),
    "scientific validation": ("valid", "quality", "check", "finite", "threshold"),
}


def is_bioinformatics_module(manifest: ModuleManifest) -> bool:
    """Return whether the module belongs to the enforced bioinformatics surface."""
    return bool(BIOINFORMATICS_DOMAINS.intersection(manifest.domains)) and manifest.module_type in BIOINFORMATICS_MODULE_TYPES


def referenced_template_paths(manifest: ModuleManifest) -> tuple[str, ...]:
    """Return every code template referenced by either supported manifest contract."""
    paths = {item.path for item in manifest.code_templates}
    if manifest.agent_protocol is not None:
        paths.update(path for section in manifest.agent_protocol.template_sections for path in section.template_files)
    return tuple(sorted(paths))


def _python_structure_errors(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [f"Python syntax is invalid at line {exc.lineno}"]
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if len(functions) < 2:
        return ["Python template must define at least two inspectable functions"]
    if any(isinstance(node, ast.Pass) for node in ast.walk(tree)):
        return ["Python template contains an empty pass statement"]
    return []


def _r_structure_errors(text: str) -> list[str]:
    if "<- function(" not in text and "commandArgs(" not in text:
        return ["R template must expose functions or a command-line entrypoint"]
    structural = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', "", text)
    structural = "\n".join(line.split("#", 1)[0] for line in structural.splitlines())
    if structural.count("(") != structural.count(")") or structural.count("{") != structural.count("}"):
        return ["R template has unbalanced delimiters"]
    return []


def validate_code_template(path: Path) -> list[str]:
    """Apply language-neutral and parser-backed checks to one template file."""
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"template is unreadable: {exc}"]
    nonblank = [line for line in text.splitlines() if line.strip()]
    if len(text.encode("utf-8")) < 1800 or len(nonblank) < 45:
        errors.append("template is too small to be a substantive analysis reference")
    if _PLACEHOLDER_RE.search(text):
        errors.append("template contains a placeholder marker")
    if _FORBIDDEN_RE.search(text):
        errors.append("template manages excluded infrastructure, dependencies, or unsafe shell execution")
    lowered = text.lower()
    for concept, markers in _REQUIRED_CONCEPTS.items():
        if not any(marker in lowered for marker in markers):
            errors.append(f"template lacks {concept}")
    if path.suffix == ".py":
        errors.extend(_python_structure_errors(text))
    elif path.suffix == ".R":
        errors.extend(_r_structure_errors(text))
    else:
        errors.append("template language is not statically validated")
    return errors


def validate_module_templates(module_path: Path, manifest: ModuleManifest) -> list[str]:
    """Validate coverage, gate binding, and source quality for one module package."""
    errors: list[str] = []
    paths = referenced_template_paths(manifest)
    if is_bioinformatics_module(manifest) and not paths:
        return ["bioinformatics module must package at least one high-quality code template"]
    blocking_gate_ids = {gate.id for gate in manifest.quality_gates if gate.blocks_interpretation}
    if manifest.code_templates:
        covered = {gate_id for item in manifest.code_templates for gate_id in item.quality_gate_ids}
        missing = sorted(blocking_gate_ids - covered)
        if missing:
            errors.append(f"code templates do not bind blocking quality gates: {', '.join(missing)}")
    for relative in paths:
        path = module_path / relative
        if not path.is_file():
            errors.append(f"referenced code template is missing: {relative}")
            continue
        errors.extend(f"{relative}: {error}" for error in validate_code_template(path))
    return errors
