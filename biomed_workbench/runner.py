"""Validated execution for source-neutral scientific capabilities."""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .catalog import resolve, resolve_entrypoint
from .models import Capability, ExecutionResult


class InputValidationError(ValueError):
    """Raised before invocation when structured input violates the contract."""


class MutationPermissionError(PermissionError):
    """Raised when a capability can mutate state without explicit permission."""


class CapabilityExecutionError(RuntimeError):
    """A secret-free capability failure."""


def _type_matches(expected: str, value: Any) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _validate(schema: dict[str, Any], value: Any, location: str) -> None:
    if value is None and schema.get("nullable"):
        return
    expected = schema.get("type")
    if expected and not _type_matches(str(expected), value):
        raise InputValidationError(f"{location} must be {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise InputValidationError(f"{location} is not an allowed value")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", ())
        missing = sorted(key for key in required if key not in value)
        if missing:
            raise InputValidationError(f"{location} is missing required fields: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise InputValidationError(f"{location} has unsupported fields: {', '.join(extra)}")
        for key, item in value.items():
            if key in properties:
                _validate(properties[key], item, f"{location}.{key}")
    elif isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise InputValidationError(f"{location} has too few items")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise InputValidationError(f"{location} has too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate(item_schema, item, f"{location}[{index}]")
    elif isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise InputValidationError(f"{location} is too short")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise InputValidationError(f"{location} is too long")
        if schema.get("pattern") and not re.fullmatch(str(schema["pattern"]), value):
            raise InputValidationError(f"{location} has an invalid format")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise InputValidationError(f"{location} is below the minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise InputValidationError(f"{location} exceeds the maximum")


def validate_inputs(capability: Capability, inputs: dict[str, Any]) -> None:
    if not isinstance(inputs, dict):
        raise InputValidationError("input must be a JSON object")
    _validate(capability.input_schema, inputs, "input")


def validate_schema_value(schema: dict[str, Any], value: Any, location: str = "value") -> None:
    """Validate a value against the bounded schema subset used by modules."""
    _validate(schema, value, location)


def run(capability_id: str, inputs: dict[str, Any], *, allow_mutation: bool = False) -> ExecutionResult:
    capability = resolve(capability_id)
    validate_inputs(capability, inputs)
    if capability.mutability != "read_only" and capability.access != "agent_generated" and not allow_mutation:
        raise MutationPermissionError(f"{capability_id} requires explicit mutation permission")
    entrypoint = resolve_entrypoint(capability)
    if isinstance(entrypoint, Path):
        output: dict[str, Any] = {
            "result_kind": "execution_handoff",
            "execution_state": "prepared-not-run",
            "workflow_path": entrypoint.as_posix(),
        }
        status = "prepared"
    else:
        try:
            raw_output = entrypoint(**inputs)
        except Exception as exc:
            raise CapabilityExecutionError(f"{capability_id} failed with {type(exc).__name__}") from None
        if isinstance(raw_output, dict):
            output = raw_output
        elif is_dataclass(raw_output) and not isinstance(raw_output, type):
            output = asdict(raw_output)
        else:
            output = {"result": raw_output}
        status = (
            "awaiting_observed_execution"
            if output.get("result_kind") == "execution_handoff"
            and output.get("execution_state") == "prepared-not-run"
            else "completed"
        )
    return ExecutionResult(capability_id=capability_id, status=status, output=output)
