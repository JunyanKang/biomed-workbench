#!/usr/bin/env python3
"""Audit whether every released analysis runs without editing source templates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.execution_readiness import assess_execution_readiness  # noqa: E402
from biomed_workbench.modules.evidence_scope import (  # noqa: E402
    evidence_scope_is_current,
    report_module_ids,
)
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402
from tools.validate_module import validate_module  # noqa: E402


_CONTROLLED_RECEIPT_FIELDS = frozenset({
    "schema_version",
    "module_id",
    "module_version",
    "compatibility_row_id",
    "input_sha256",
    "output_payloads",
    "reload_checks",
})
_CONTROLLED_PAYLOAD_FIELDS = frozenset({"role", "media_type", "sha256", "byte_size"})
_CONTROLLED_RELOAD_FIELDS = frozenset({"check_id", "passed", "payload_sha256"})


def _implementation_is_current(report: dict[str, object]) -> bool:
    implementation = report.get("implementation")
    if not isinstance(implementation, dict):
        return True
    relative = implementation.get("path")
    digest = implementation.get("sha256")
    if relative is None and digest is None:
        return True
    if not isinstance(relative, str) or not isinstance(digest, str):
        return False
    path = ROOT / relative
    return (
        path.is_file()
        and len(digest) == 64
        and hashlib.sha256(path.read_bytes()).hexdigest() == digest
    )


def _controlled_fixture_report_receipts(registry: ModuleRegistry) -> dict[str, str]:
    """Read only explicit, current, execution-and-reload fixture receipts."""
    receipts: dict[str, str] = {}
    for path in sorted((ROOT / "reports").glob("*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            not isinstance(report, dict)
            or report.get("passed") is not True
            or not evidence_scope_is_current(report, registry)
            or not _implementation_is_current(report)
        ):
            continue
        receipt = report.get("controlled_fixture_receipt")
        if not isinstance(receipt, dict) or set(receipt) != _CONTROLLED_RECEIPT_FIELDS:
            continue
        module_id = receipt.get("module_id")
        try:
            manifest = registry.get(module_id) if isinstance(module_id, str) else None
        except ValueError:
            continue
        if (
            manifest is None
            or receipt.get("schema_version") != 1
            or receipt.get("module_version") != manifest.version
            or receipt.get("compatibility_row_id") not in {row.id for row in manifest.compatibility_matrix}
            or not isinstance(receipt.get("input_sha256"), str)
            or len(receipt["input_sha256"]) != 64
        ):
            continue
        execution = report.get("execution")
        payloads = receipt.get("output_payloads")
        reload_checks = receipt.get("reload_checks")
        if (
            not isinstance(execution, dict)
            or not isinstance(execution.get("input"), dict)
            or execution["input"].get("sha256") != receipt["input_sha256"]
            or not isinstance(execution.get("outputs"), list)
            or not isinstance(payloads, list)
            or not payloads
            or not isinstance(reload_checks, list)
            or not reload_checks
        ):
            continue
        expected_payloads = [
            {key: item.get(key) for key in _CONTROLLED_PAYLOAD_FIELDS}
            for item in execution["outputs"]
            if isinstance(item, dict)
        ]
        if (
            len(expected_payloads) != len(execution["outputs"])
            or any(not isinstance(item, dict) or set(item) != _CONTROLLED_PAYLOAD_FIELDS for item in payloads)
            or payloads != expected_payloads
            or any(
                not isinstance(item, dict)
                or set(item) != _CONTROLLED_RELOAD_FIELDS
                or item.get("passed") is not True
                for item in reload_checks
            )
            or {item["payload_sha256"] for item in reload_checks} != {item["sha256"] for item in payloads}
        ):
            continue
        digest = hashlib.sha256(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        existing = receipts.get(module_id)
        if existing is not None and existing != digest:
            raise ValueError(f"conflicting controlled fixture receipts for {module_id}")
        receipts[module_id] = digest
    return receipts


_PORTABLE_RECEIPT_FIELDS = (
    "case_name",
    "case_digest",
    "module_id",
    "module_version",
    "compatibility_row_id",
    "validated_projection_digest",
    "reload_method",
    "round_trip_kind",
)


def _portable_validation_identity(validation: dict[str, object]) -> str | None:
    """Bind successful execution without turning host-specific values into release metadata."""
    receipts = validation.get("controlled_fixture_receipts")
    observed_digest = validation.get("controlled_fixture_receipt_digest")
    if not isinstance(observed_digest, str) or not isinstance(receipts, list) or not receipts:
        return None
    portable: list[dict[str, object]] = []
    for receipt in receipts:
        if (
            not isinstance(receipt, dict)
            or any(field not in receipt for field in _PORTABLE_RECEIPT_FIELDS)
            or not isinstance(receipt.get("full_normalized_output_digest"), str)
            or not isinstance(receipt.get("runtime_versions"), dict)
        ):
            return None
        portable.append({field: receipt[field] for field in _PORTABLE_RECEIPT_FIELDS})
    return hashlib.sha256(
        json.dumps(portable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_run_receipt_archive(
    validations: list[dict[str, object]],
    output_directory: Path,
) -> Path:
    """Persist full host-specific fixture receipts separately from portable catalog identity."""
    observed_at = datetime.now(timezone.utc).isoformat()
    entries = [
        {
            "module_id": validation.get("module_id"),
            "module_version": validation.get("module_version"),
            "receipt_digest": validation.get("controlled_fixture_receipt_digest"),
            "receipts": validation.get("controlled_fixture_receipts"),
        }
        for validation in validations
        if validation.get("controlled_fixture_receipt_digest")
        and validation.get("controlled_fixture_receipts")
    ]
    basis = {
        "schema_version": 1,
        "observed_at": observed_at,
        "executor": {
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
        "entries": entries,
    }
    payload = {
        **basis,
        "archive_digest": hashlib.sha256(
            json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = output_directory / f"controlled-fixture-receipts-{stamp}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def build(*, receipt_archive: Path | None = None) -> dict[str, object]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    report_receipts = _controlled_fixture_report_receipts(registry)
    validated_modules: set[str] = set()
    validated_assays: dict[str, set[str]] = {}
    reports_root = ROOT / "reports"
    for path in sorted(reports_root.glob("public-case-*.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(report, dict)
            and report.get("passed") is True
            and evidence_scope_is_current(report, registry)
            and _implementation_is_current(report)
        ):
            module_ids = report_module_ids(report)
            validated_modules.update(module_ids)
            assay_values: list[str] = []
            if isinstance(report.get("assay"), str):
                assay_values.append(report["assay"])
            if isinstance(report.get("assays"), list):
                assay_values.extend(value for value in report["assays"] if isinstance(value, str))
            execution = report.get("execution")
            if isinstance(execution, dict) and isinstance(execution.get("assay"), str):
                assay_values.append(execution["assay"])
            for module_id in module_ids:
                validated_assays.setdefault(module_id, set()).update(value.lower() for value in assay_values)
    records = []
    validations: list[dict[str, object]] = []
    for manifest in registry.all():
        validation = validate_module(BUILTIN_ROOT / manifest.id, require_tests=True, execute_tests=True)
        validations.append(validation)
        validation_identity = _portable_validation_identity(validation)
        report_receipt = report_receipts.get(manifest.id)
        receipt_digest = validation_identity or report_receipt
        round_trip_kind = "process-json" if validation_identity else "artifact-payload" if report_receipt else None
        records.append(
            assess_execution_readiness(
                BUILTIN_ROOT / manifest.id,
                manifest,
                public_data_validated=manifest.id in validated_modules,
                public_data_validated_assays=frozenset(validated_assays.get(manifest.id, set())),
                controlled_fixture_portable_identity_digest=receipt_digest if isinstance(receipt_digest, str) else None,
                controlled_fixture_round_trip_kind=round_trip_kind,
            ).to_dict()
        )
    counts: dict[str, int] = {}
    for record in records:
        counts[record["level"]] = counts.get(record["level"], 0) + 1
    blocked = [record["module_id"] for record in records if not record["executor_ready"]]
    axis_counts = {
        axis: sum(record["evidence_axes"][axis] is True for record in records)
        for axis in (
            "contract_valid",
            "adapter_static_reachable",
            "fixture_declared",
            "controlled_fixture_executed_and_reloaded",
            "controlled_fixture_process_json_round_trip",
            "controlled_fixture_artifact_payload_reloaded",
            "representative_or_public_case_validated",
            "current_project_reviewed",
        )
    }
    validation_scope_counts = {
        key: sum(record[key] is True for record in records)
        for key in ("engineering_validated", "method_validated", "project_promoted")
    }
    report = {
        "schema_version": 8,
        "registry_digest": registry.digest,
        "module_count": len(records),
        "counts": counts,
        "axis_counts": axis_counts,
        "validation_scope_counts": validation_scope_counts,
        "blocked_module_ids": blocked,
        "passed": axis_counts["contract_valid"] == len(records),
        "single_maturity_count_is_authoritative": False,
        "status_model": {
            "engineering_validated": "The registered implementation executed a controlled case and independently reloaded its declared outputs.",
            "method_validated": "Engineering validation is supplemented by a current representative or public-data case for the exact registered method slice.",
            "project_promoted": "A current project result has passed observed execution, reload, scientific review and an explicit FORMAL promotion decision; release reports always leave this false.",
            "contract_valid": "The versioned module contract parses and all referenced packaged assets satisfy release rules.",
            "adapter_static_reachable": "At least one declared execution surface reaches packaged implementation code rather than only a suggestion or editable template.",
            "fixture_declared": "A controlled case is declared; declaration alone is not execution evidence.",
            "controlled_fixture_executed_and_reloaded": "A controlled fixture has exercised the registered implementation and its declared output reload path.",
            "controlled_fixture_process_json_round_trip": "The controlled case returned a complete normalized process result that was decoded and checked against its closed output contract.",
            "controlled_fixture_artifact_payload_reloaded": "The controlled case serialized one or more artifact payloads and independently reloaded their recorded byte identities.",
            "portable_receipt_identity": "The checked readiness catalog binds portable case, module, compatibility, validated projection, reload, and round-trip identity. Complete observed output and runtime digests remain in the run-specific validation receipt and are intentionally excluded from cross-host release identity.",
            "representative_or_public_case_validated": "A current dependency-scoped representative or public-data case passed its declared gates.",
            "current_project_reviewed": "The current project has observed execution, artifact reload, scientific review, and an accepted decision; generic release reports never set this axis.",
            "scaffolded": "A no-edit contract exists, but no external scientific workflow is executed.",
            "executable": "A controlled fixture executes the registered implementation and reloads declared outputs; this does not imply current-project scientific completion.",
            "validated": "Executable evidence is supplemented by a current dependency-scoped public-data acceptance case.",
        },
        "records": records,
    }
    if receipt_archive is not None:
        _write_run_receipt_archive(validations, receipt_archive)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--receipt-archive",
        type=Path,
        help="Write complete host-specific validation receipts outside deterministic release metadata.",
    )
    args = parser.parse_args()
    report = build(receipt_archive=args.receipt_archive)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
