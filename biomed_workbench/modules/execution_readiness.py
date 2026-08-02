"""Machine-enforced readiness checks for packaged scientific analyses."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .contract import ModuleManifest
from .template_quality import referenced_template_paths


READINESS_LEVELS = (
    "validated",
    "executable",
    "scaffolded",
    "manual-adaptation",
    "invalid",
)
_PLACEHOLDER = re.compile(
    r"\b(?:TODO|FIXME|NotImplementedError|YOUR[_ -]|REPLACE[_ -]?ME|EDIT HERE)\b|/path/to/",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExecutionReadiness:
    module_id: str
    level: str
    released: bool
    contract_ready: bool
    executor_ready: bool
    public_data_validated: bool
    template_paths: tuple[str, ...]
    assay_readiness: tuple[dict[str, object], ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "level": self.level,
            "released": self.released,
            "contract_ready": self.contract_ready,
            "executor_ready": self.executor_ready,
            "public_data_validated": self.public_data_validated,
            "template_paths": list(self.template_paths),
            "assay_readiness": list(self.assay_readiness),
            "reasons": list(self.reasons),
        }


def _parameterized_cli(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if _PLACEHOLDER.search(text):
        return False
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return False
        has_parser = "argparse" in text and any(
            isinstance(node, ast.Call)
            and (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"parse_args", "parse_known_args"}
            )
            for node in ast.walk(tree)
        )
        has_main = "if __name__" in text
        return has_parser and has_main
    if path.suffix == ".R":
        # Both optparse and validated positional Rscript interfaces are complete
        # CLIs.  Project variation enters through commandArgs, never source edits.
        return "commandArgs(" in text or "parse_args(" in text or "parse_args_into_list(" in text
    return False


def _is_contract_only(path: Path) -> bool:
    """Return whether a parameterized adapter only admits a run without executing it."""
    text = path.read_text(encoding="utf-8")
    return (
        '"execution_state": "admitted-not-run"' in text
        or '"executed": False' in text
        or "planned_output_is_not_evidence" in text and "subprocess" not in text
    )


def _is_runtime_support(path: Path, manifest: ModuleManifest) -> bool:
    relative = str(path.relative_to(path.parents[1]))
    purposes = {
        item.path: item.purpose.lower()
        for item in manifest.code_templates
    }
    purpose = purposes.get(relative, "")
    return path.name.endswith("sitecustomize.py") and "compatibility" in purpose


def assess_execution_readiness(
    module_path: Path,
    manifest: ModuleManifest,
    *,
    public_data_validated: bool = False,
    public_data_validated_assays: frozenset[str] = frozenset(),
) -> ExecutionReadiness:
    paths = referenced_template_paths(manifest)
    if manifest.access != "agent_generated":
        return ExecutionReadiness(
            manifest.id,
            "validated" if public_data_validated else "executable",
            True,
            True,
            True,
            public_data_validated,
            paths,
            (),
            ("The registered Python, service, or scientific-command entrypoint is the execution surface; templates are reproducible examples only.",),
        )
    reasons: list[str] = []
    if manifest.agent_protocol is None:
        reasons.append("Agent-orchestrated analysis lacks a packaged execution protocol.")
    if not paths:
        reasons.append("Agent-orchestrated analysis has no packaged adapter.")
    if any(item.requires_adaptation for item in manifest.code_templates):
        reasons.append("At least one adapter declares manual source adaptation.")
    parameterized_paths: list[Path] = []
    for relative in paths:
        path = module_path / relative
        if not path.is_file():
            reasons.append(f"Packaged adapter is missing: {relative}.")
        elif _is_runtime_support(path, manifest):
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                reasons.append(f"Packaged runtime support file does not parse: {relative}.")
        elif not _parameterized_cli(path):
            reasons.append(f"Packaged adapter lacks a complete parameterized CLI: {relative}.")
        else:
            parameterized_paths.append(path)
    official_sources = [
        item.version_source
        for item in (*manifest.tool_requirements, *manifest.dependencies)
        if item.required or manifest.access == "agent_generated"
    ]
    if not official_sources or any(not source.startswith(("https://", "http://")) for source in official_sources):
        reasons.append("Required tool or runtime contracts lack official version/API sources.")
    contract_ready = not reasons and bool(parameterized_paths)
    executor_ready = contract_ready and any(not _is_contract_only(path) for path in parameterized_paths)
    structural_failure = bool(reasons)
    assay_readiness: list[dict[str, object]] = []
    coverage_path = module_path / "execution_coverage.json"
    if coverage_path.is_file():
        try:
            coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            properties = manifest.input_schema.get("properties", {})
            assay_schema = properties.get("assay", {}) if isinstance(properties, dict) else {}
            declared_assays = tuple(assay_schema.get("enum", ())) if isinstance(assay_schema, dict) else ()
            rows = coverage.get("assays", []) if isinstance(coverage, dict) else []
            if coverage.get("schema_version") != 1 or coverage.get("module_id") != manifest.id:
                raise ValueError("identity or schema mismatch")
            if not isinstance(rows, list) or {row.get("assay") for row in rows if isinstance(row, dict)} != set(declared_assays):
                raise ValueError("coverage does not exactly match the declared assay enum")
            registered_templates = {item.path for item in manifest.code_templates}
            for row in rows:
                assay = str(row["assay"])
                adapter = row.get("executor_path")
                assay_contract = row.get("contract_ready") is True
                cross_module_id = row.get("executor_module_id")
                cross_paths = row.get("executor_paths")
                if cross_module_id is not None or cross_paths is not None:
                    target = module_path.parent / str(cross_module_id)
                    target_manifest = json.loads((target / "module.json").read_text(encoding="utf-8"))
                    target_templates = {
                        item.get("path") for item in target_manifest.get("code_templates", [])
                        if isinstance(item, dict)
                    }
                    valid_cross_paths = isinstance(cross_paths, list) and bool(cross_paths) and all(
                        isinstance(relative, str)
                        and relative in target_templates
                        and (target / relative).is_file()
                        and _parameterized_cli(target / relative)
                        and not _is_contract_only(target / relative)
                        for relative in cross_paths
                    )
                    assay_executor = bool(assay_contract and isinstance(cross_module_id, str) and valid_cross_paths)
                else:
                    adapter_path = module_path / adapter if isinstance(adapter, str) else None
                    assay_executor = bool(
                        assay_contract
                        and isinstance(adapter, str)
                        and adapter in registered_templates
                        and adapter_path is not None
                        and adapter_path.is_file()
                        and _parameterized_cli(adapter_path)
                        and not _is_contract_only(adapter_path)
                    )
                assay_validated = assay_executor and (
                    assay in public_data_validated_assays
                    or (public_data_validated and len(declared_assays) == 1)
                )
                assay_level = "validated" if assay_validated else "executable" if assay_executor else "scaffolded"
                assay_readiness.append({
                    "assay": assay,
                    "level": assay_level,
                    "contract_ready": assay_contract,
                    "executor_ready": assay_executor,
                    "public_data_validated": assay_validated,
                    "executor_path": adapter,
                    "executor_module_id": cross_module_id,
                    "executor_paths": cross_paths,
                })
            contract_ready = contract_ready and all(row["contract_ready"] for row in assay_readiness)
            executor_ready = contract_ready and all(row["executor_ready"] for row in assay_readiness)
            public_data_validated = executor_ready and all(row["public_data_validated"] for row in assay_readiness)
            missing = [str(row["assay"]) for row in assay_readiness if not row["executor_ready"]]
            if missing:
                reasons.append("Declared assays without a complete executor: " + ", ".join(missing) + ".")
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            reasons.append(f"Assay execution coverage is invalid: {exc}.")
            structural_failure = True
            contract_ready = False
            executor_ready = False
    if structural_failure:
        level = (
            "manual-adaptation"
            if any("adaptation" in reason or "parameterized CLI" in reason for reason in reasons)
            else "invalid"
        )
    elif not executor_ready:
        level = "scaffolded"
        reasons.append(
            "The packaged adapter freezes an execution contract but does not invoke and reload an external scientific workflow."
        )
    elif public_data_validated:
        level = "validated"
    else:
        level = "executable"
    return ExecutionReadiness(
        manifest.id,
        level,
        executor_ready,
        contract_ready,
        executor_ready,
        public_data_validated and executor_ready,
        paths,
        tuple(assay_readiness),
        tuple(reasons),
    )
