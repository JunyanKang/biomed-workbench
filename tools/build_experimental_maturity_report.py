#!/usr/bin/env python3
"""Build the evidence matrix for experimental scientific modules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def build() -> dict[str, object]:
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    experimental = [module for module in registry.all() if module.maturity == "experimental"]
    templates = {
        item["module_id"]: item
        for item in load_json(ROOT / "reports" / "bioinformatics-template-coverage.json")["records"]
    }
    compatibility_records: dict[str, list[dict[str, object]]] = {}
    for item in load_json(ROOT / "reports" / "compatibility-execution-evidence.json")["records"]:
        compatibility_records.setdefault(str(item["module_id"]), []).append(item)

    live_reports: dict[str, list[str]] = {}
    for path in sorted((ROOT / "reports").glob("*-live-verification.json")):
        payload = load_json(path)
        module_id = payload.get("module_id")
        if module_id and payload.get("passed") is True:
            live_reports.setdefault(str(module_id), []).append(path.name)

    public_cases: dict[str, list[str]] = {}
    for path in sorted((ROOT / "reports").glob("public-case-*.json")):
        payload = load_json(path)
        module_id = payload.get("module", {}).get("id")
        if (
            module_id
            and payload.get("passed") is True
            and payload.get("case_type") == "public-data-end-to-end"
        ):
            public_cases.setdefault(str(module_id), []).append(str(payload["case_id"]))

    records = []
    for module in experimental:
        template = templates.get(module.id, {})
        compatibility = compatibility_records.get(module.id, [])
        live = live_reports.get(module.id, [])
        public = public_cases.get(module.id, [])
        contract = True
        compatibility_passed = bool(compatibility) and all(
            row.get("regression", {}).get("passed") is True
            and row.get("end_to_end", {}).get("passed") is True
            for row in compatibility
        )
        template_passed = template.get("passed") is True and template.get("template_count", 0) >= 1
        representative_execution = bool(live)
        public_data_acceptance = bool(public)
        missing = []
        if not template_passed:
            missing.append("passing_code_template")
        if not compatibility_passed:
            missing.append("compatibility_regression_and_end_to_end")
        if not representative_execution:
            missing.append("representative_live_execution")
        if not public_data_acceptance:
            missing.append("stable_public_dataset_acceptance")
        records.append(
            {
                "module_id": module.id,
                "module_version": module.version,
                "maturity": module.maturity,
                "domains": list(module.domains),
                "evidence": {
                    "contract": contract,
                    "passing_code_template": template_passed,
                    "compatibility": compatibility_passed,
                    "representative_execution": representative_execution,
                    "live_public_data": public_data_acceptance,
                    "project_validation": False,
                },
                "template_files": template.get("template_files", []),
                "compatibility_row_ids": sorted(str(row["row_id"]) for row in compatibility),
                "representative_execution_reports": live,
                "public_case_ids": public,
                "missing_evidence": missing,
                "claim_boundary": (
                    "Public-data acceptance is source-, design-, parameter-, runtime-, and gate-specific."
                    if public_data_acceptance
                    else "Deterministic or representative fixtures do not establish performance on biological public data."
                ),
            }
        )

    foundational_passed = all(
        item["evidence"]["contract"]
        and item["evidence"]["passing_code_template"]
        and item["evidence"]["compatibility"]
        and item["evidence"]["representative_execution"]
        for item in records
    )
    public_count = sum(item["evidence"]["live_public_data"] for item in records)
    return {
        "schema_version": 1,
        "passed": foundational_passed,
        "registry_digest": registry.digest,
        "experimental_module_count": len(records),
        "contract_passed": sum(item["evidence"]["contract"] for item in records),
        "template_passed": sum(item["evidence"]["passing_code_template"] for item in records),
        "compatibility_passed": sum(item["evidence"]["compatibility"] for item in records),
        "representative_execution_passed": sum(
            item["evidence"]["representative_execution"] for item in records
        ),
        "public_data_accepted": public_count,
        "public_data_gap_count": len(records) - public_count,
        "all_public_data_accepted": public_count == len(records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "experimental-module-maturity.json",
    )
    args = parser.parse_args()
    report = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "passed",
        "experimental_module_count",
        "representative_execution_passed",
        "public_data_accepted",
        "public_data_gap_count",
    )}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
