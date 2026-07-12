"""Source-neutral capability registry."""

from __future__ import annotations

import importlib
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .models import Capability


class CapabilityResolutionError(LookupError):
    """Raised when a capability ID or entrypoint cannot be resolved."""


_REGISTRY: dict[str, Capability] = {}


def register(capability: Capability) -> Capability:
    if capability.id in _REGISTRY:
        raise ValueError(f"duplicate capability id: {capability.id}")
    _REGISTRY[capability.id] = capability
    return capability


def resolve(capability_id: str) -> Capability:
    try:
        return _REGISTRY[capability_id]
    except KeyError:
        raise CapabilityResolutionError(f"unknown capability: {capability_id}") from None


def resolve_entrypoint(capability: Capability) -> Callable[..., object] | Path:
    if capability.kind == "workflow" and ":" not in capability.entrypoint:
        path = Path(capability.entrypoint)
        if not path.is_file():
            raise CapabilityResolutionError(f"workflow entrypoint does not exist: {capability.id}")
        return path
    module_name, separator, attribute_name = capability.entrypoint.partition(":")
    if not separator or not module_name or not attribute_name:
        raise CapabilityResolutionError(f"invalid entrypoint for {capability.id}")
    try:
        module = importlib.import_module(module_name)
        entrypoint = getattr(module, attribute_name)
    except (ImportError, AttributeError):
        raise CapabilityResolutionError(f"entrypoint cannot be resolved: {capability.id}") from None
    if not callable(entrypoint):
        raise CapabilityResolutionError(f"entrypoint is not callable: {capability.id}")
    return entrypoint


def all_capabilities() -> tuple[Capability, ...]:
    return tuple(_REGISTRY[capability_id] for capability_id in sorted(_REGISTRY))


def capability_to_dict(capability: Capability) -> dict[str, object]:
    return asdict(capability)


def _object_schema(properties: dict[str, object], required: tuple[str, ...]) -> dict[str, object]:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


_DATABASE = {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"}
_IDS = {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10000}


def _register_builtins() -> None:
    definitions = (
        Capability(
            id="ncbi-info",
            workflow="evidence",
            kind="service",
            title="Inspect NCBI Entrez databases",
            description="Return current Entrez database metadata and searchable fields.",
            entrypoint="biomed_workbench.capabilities.ncbi:info",
            input_schema=_object_schema({"database": {**_DATABASE, "nullable": True}}, ()),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-search",
            workflow="evidence",
            kind="service",
            title="Search NCBI Entrez",
            description="Search any valid Entrez database with bounded pagination and optional history state.",
            entrypoint="biomed_workbench.capabilities.ncbi:search",
            input_schema=_object_schema(
                {
                    "database": _DATABASE,
                    "term": {"type": "string", "minLength": 1},
                    "retmax": {"type": "integer", "minimum": 0, "maximum": 100000},
                    "retstart": {"type": "integer", "minimum": 0},
                    "sort": {"type": "string", "nullable": True},
                    "use_history": {"type": "boolean"},
                    "idtype": {"type": "string", "nullable": True},
                },
                ("database", "term"),
            ),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-summary",
            workflow="evidence",
            kind="service",
            title="Summarize NCBI Entrez records",
            description="Retrieve normalized document summaries for identifiers in an Entrez database.",
            entrypoint="biomed_workbench.capabilities.ncbi:summary",
            input_schema=_object_schema({"database": _DATABASE, "ids": _IDS}, ("database", "ids")),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-fetch",
            workflow="evidence",
            kind="service",
            title="Fetch NCBI Entrez records",
            description="Fetch database-native records such as XML, MEDLINE, GenBank, or FASTA.",
            entrypoint="biomed_workbench.capabilities.ncbi:fetch",
            input_schema=_object_schema(
                {
                    "database": _DATABASE,
                    "ids": _IDS,
                    "rettype": {"type": "string", "nullable": True},
                    "retmode": {"type": "string", "nullable": True},
                },
                ("database", "ids"),
            ),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-link",
            workflow="evidence",
            kind="service",
            title="Link NCBI Entrez databases",
            description="Resolve linked identifiers between Entrez databases for evidence chaining.",
            entrypoint="biomed_workbench.capabilities.ncbi:link",
            input_schema=_object_schema(
                {
                    "source_database": _DATABASE,
                    "target_database": _DATABASE,
                    "ids": _IDS,
                    "linkname": {"type": "string", "nullable": True},
                },
                ("source_database", "target_database", "ids"),
            ),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
        Capability(
            id="ncbi-search-summary",
            workflow="evidence",
            kind="service",
            title="Search and summarize NCBI Entrez",
            description="Run a bounded Entrez search and return normalized summaries in one composable action.",
            entrypoint="biomed_workbench.capabilities.ncbi:search_summary",
            input_schema=_object_schema(
                {
                    "database": _DATABASE,
                    "term": {"type": "string", "minLength": 1},
                    "retmax": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                ("database", "term"),
            ),
            requirements=(),
            access="public_api",
            mutability="read_only",
        ),
    )
    for definition in definitions:
        register(definition)


_register_builtins()
