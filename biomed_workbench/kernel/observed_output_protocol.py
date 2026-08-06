"""Fail-closed validation for observed-output handoff protocol identities."""

from __future__ import annotations

from typing import Any, Mapping

from .identity import digest_value


SUPPORTED_OBSERVED_OUTPUT_PROTOCOL_VERSIONS = frozenset({"2.1.0"})


def validate_observed_output_protocol(protocol: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate one supported protocol and return its canonical frozen gate IDs."""
    if not isinstance(protocol, Mapping):
        raise ValueError("execution handoff protocol must be a mapping")
    version = protocol.get("observed_output_protocol_version")
    if version not in SUPPORTED_OBSERVED_OUTPUT_PROTOCOL_VERSIONS:
        raise ValueError(f"unsupported observed-output protocol version: {version!r}")
    raw_gate_ids = protocol.get("required_postflight_gate_ids")
    if not isinstance(raw_gate_ids, (list, tuple)):
        raise ValueError("observed-output protocol must freeze its required gate IDs")
    gate_ids = tuple(raw_gate_ids)
    if (
        not gate_ids
        or any(not isinstance(value, str) or not value for value in gate_ids)
        or len(set(gate_ids)) != len(gate_ids)
        or gate_ids != tuple(sorted(gate_ids))
    ):
        raise ValueError("observed-output protocol gate IDs must be nonempty, unique, and sorted")
    if protocol.get("required_postflight_gate_set_digest") != digest_value(list(gate_ids)):
        raise ValueError("observed-output protocol gate-set digest is invalid")
    return gate_ids


def validate_handoff_receipt_gate_coverage(handoff: object, receipt: object) -> tuple[str, ...]:
    """Require an observed receipt to cover the handoff's exact frozen gate set."""
    gate_ids = validate_observed_output_protocol(getattr(handoff, "protocol"))
    result_keys = set(getattr(receipt, "postflight_results"))
    digest_keys = set(getattr(receipt, "postflight_result_digests"))
    if set(gate_ids) != result_keys or set(gate_ids) != digest_keys:
        raise ValueError("observed execution does not cover the frozen handoff gate set")
    return gate_ids
