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
    r"NVI" r"DIA_" r"API_" r"KEY|N" r"GC_" r"API_" r"KEY|(?:doc" r"ker|sl" r"urm|sbatch|srun)\b",
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


def _python_tree(text: str) -> tuple[ast.AST | None, list[str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return None, [f"Python syntax is invalid at line {exc.lineno}"]
    return tree, []


def _python_structure_errors(text: str) -> list[str]:
    tree, errors = _python_tree(text)
    if tree is None:
        return errors
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if len(functions) < 2:
        return ["Python template must define at least two inspectable functions"]
    if any(isinstance(node, ast.Pass) for node in ast.walk(tree)):
        return ["Python template contains an empty pass statement"]
    return []


def _implementation_imports(tree: ast.AST) -> tuple[str, ...]:
    return tuple(sorted({
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and isinstance(node.module, str)
        and node.module.startswith("biomed_workbench.implementations.")
    }))


def _repository_root(path: Path) -> Path | None:
    for parent in path.parents:
        if (parent / "biomed_workbench" / "implementations").is_dir():
            return parent
    return None


def _implementation_errors(path: Path, module_name: str) -> list[str]:
    root = _repository_root(path)
    if root is None:
        return ["cannot resolve the product-owned implementation package"]
    implementation = root.joinpath(*module_name.split(".")).with_suffix(".py")
    if not implementation.is_file():
        return [f"delegated implementation is missing: {module_name}"]
    try:
        text = implementation.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"delegated implementation is unreadable: {exc}"]
    tree, errors = _python_tree(text)
    if tree is None:
        return [f"delegated implementation {module_name}: {error}" for error in errors]
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if len(text.encode("utf-8")) < 1800 or len(functions) < 2:
        errors.append("delegated implementation is not a substantive inspectable implementation")
    lowered = text.lower()
    if not any(marker in lowered for marker in ("version", "revision", "commit", "source")):
        errors.append("delegated implementation lacks tool/version provenance")
    if not any(marker in lowered for marker in ("raise ", "error(", "valid", "quality", "check", "finite")):
        errors.append("delegated implementation lacks input or scientific validation")
    if not any(marker in lowered for marker in ("write_text", "write_bytes", "json.dump", "to_csv", "savetxt")):
        errors.append("delegated implementation lacks inspectable output serialization")
    if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "eval" for node in ast.walk(tree)):
        errors.append("delegated implementation uses eval")
    return [f"delegated implementation {module_name}: {error}" for error in errors]


def _python_adapter_errors(path: Path, text: str, tree: ast.AST) -> list[str]:
    errors: list[str] = []
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not any(node.name == "main" for node in functions):
        errors.append("Python execution adapter must define main")
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if not any(name.startswith("execute_") for name in calls):
        errors.append("Python execution adapter does not call its imported implementation")
    if "ArgumentParser" not in text or "parse_args" not in text:
        errors.append("Python execution adapter lacks a parameterized command-line interface")
    if "sys.path.insert" not in text:
        errors.append("Python execution adapter cannot resolve the product package from its source path")
    if "read_text" not in text or "json.loads" not in text:
        errors.append("Python execution adapter does not load a structured request")
    if any(isinstance(node, ast.Pass) for node in ast.walk(tree)):
        errors.append("Python execution adapter contains an empty pass statement")
    for module_name in _implementation_imports(tree):
        errors.extend(_implementation_errors(path, module_name))
    return errors


def _python_runtime_support_errors(text: str) -> list[str]:
    tree, errors = _python_tree(text)
    if tree is None:
        return errors
    if not ast.get_docstring(tree):
        errors.append("runtime support file lacks a version- and scope-specific docstring")
    if "multiprocessing.set_start_method(\"fork\")" not in text:
        errors.append("runtime support file does not apply the declared compatibility action")
    if "except RuntimeError" not in text:
        errors.append("runtime support file does not safely handle an already-selected start method")
    return errors


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
    if _PLACEHOLDER_RE.search(text):
        errors.append("template contains a placeholder marker")
    if _FORBIDDEN_RE.search(text):
        errors.append("template manages excluded infrastructure, dependencies, or unsafe shell execution")
    if path.name.endswith("sitecustomize.py"):
        errors.extend(_python_runtime_support_errors(text))
        return errors
    tree = None
    implementation_imports: tuple[str, ...] = ()
    if path.suffix == ".py":
        tree, syntax_errors = _python_tree(text)
        errors.extend(syntax_errors)
        if tree is not None:
            implementation_imports = _implementation_imports(tree)
    nonblank = [line for line in text.splitlines() if line.strip()]
    if implementation_imports and tree is not None and (
        len(text.encode("utf-8")) < 1800 or len(nonblank) < 45
    ):
        errors.extend(_python_adapter_errors(path, text, tree))
        return errors
    is_r_execution_adapter = (
        path.suffix == ".R"
        and "commandArgs(" in text
        and "::" in text
        and (len(text.encode("utf-8")) < 1800 or len(nonblank) < 45)
    )
    if is_r_execution_adapter:
        if "packageVersion(" not in text or "stop(" not in text:
            errors.append("R execution adapter lacks package-version or input failure gates")
        if not any(marker in text for marker in ("saveRDS(", "writeLines(", "write.table(", "write.csv(")):
            errors.append("R execution adapter lacks output serialization")
        errors.extend(_r_structure_errors(text))
        return errors
    if len(text.encode("utf-8")) < 1800 or len(nonblank) < 45:
        errors.append("template is too small to be a substantive analysis reference")
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
        manual = sorted(item.path for item in manifest.code_templates if item.requires_adaptation)
        if manual:
            errors.append(
                "released code templates require manual source adaptation: "
                + ", ".join(manual)
            )
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
