#!/usr/bin/env python3
"""Verify the repository CI, deterministic evidence, and secret-scan contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "quality.yml"
REQUIREMENTS = ROOT / "requirements-ci.txt"
GITLEAKS_CONFIG = ROOT / ".gitleaks.toml"
EVIDENCE_ID = "github-quality-and-secret-gates-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    steps = job.get("steps")
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise RuntimeError("CI job steps are invalid")
    return steps


def verify() -> dict[str, object]:
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    if not isinstance(workflow, dict) or set(workflow.get("jobs", {})) != {"verify", "secrets"}:
        raise RuntimeError("CI workflow must expose verify and secrets jobs")
    if workflow.get("permissions") != {"contents": "read"}:
        raise RuntimeError("CI permissions must remain read-only")
    jobs = workflow["jobs"]
    verify_steps = _steps(jobs["verify"])
    secret_steps = _steps(jobs["secrets"])
    verify_script = "\n".join(str(step.get("run", "")) for step in verify_steps)
    secret_script = "\n".join(str(step.get("run", "")) for step in secret_steps)
    uses = [str(step.get("uses", "")) for step in verify_steps + secret_steps]
    required_verify = (
        "python -m unittest discover -s tests",
        "python tools/validate_workbench.py --release",
        "python tools/build_module_index.py",
        "python tools/build_format_contract_report.py",
        "python tools/build_module_migration_report.py",
        "python tools/capture_compatibility_evidence.py",
        "python tools/verify_registry_snapshot.py",
        "python tools/verify_codex_native_handoffs.py",
        "python tools/verify_local_update.py",
        "python tools/verify_ci_quality.py",
        "git diff --exit-code",
    )
    if any(marker not in verify_script for marker in required_verify):
        raise RuntimeError("CI verification or deterministic drift gate is incomplete")
    if not any(value.startswith("actions/setup-python@") for value in uses) or uses.count("actions/checkout@v4") != 2:
        raise RuntimeError("CI checkout or Python setup is incomplete")
    checkout = next(step for step in secret_steps if step.get("uses") == "actions/checkout@v4")
    if checkout.get("with", {}).get("fetch-depth") != "0":
        raise RuntimeError("secret scan must check out complete history")
    required_secret = (
        "GITLEAKS_LINUX_X64_SHA256",
        "sha256sum --check --strict",
        "gitleaks git . --config .gitleaks.toml --redact --no-banner --exit-code 1",
    )
    if any(marker not in secret_script and marker not in json.dumps(secret_steps) for marker in required_secret):
        raise RuntimeError("checksum-verified redacted secret scan is incomplete")

    requirements = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, version = line.partition("==")
        if not separator or not name or not version or name in requirements:
            raise RuntimeError("CI requirements must use unique exact tested baselines")
        requirements[name] = version
    expected = {"numpy": "2.4.4", "scipy": "1.17.1", "scikit-learn": "1.8.0", "Pillow": "12.1.1", "PyYAML": "6.0.3"}
    if requirements != expected:
        raise RuntimeError("CI requirements differ from the verified repository baseline")

    gitleaks_config = tomllib.loads(GITLEAKS_CONFIG.read_text(encoding="utf-8"))
    allowlists = gitleaks_config.get("allowlists", [])
    expected_digest_pattern = r'"output_sha256"\s*:\s*"[0-9a-f]{64}"'
    if (
        gitleaks_config.get("extend") != {"useDefault": True}
        or len(allowlists) != 1
        or allowlists[0].get("paths") != [r"^reports/.*\.json$"]
        or allowlists[0].get("regexTarget") != "line"
        or allowlists[0].get("regexes") != [expected_digest_pattern]
        or re.fullmatch(expected_digest_pattern, '"output_sha256": "' + "a" * 64 + '"') is None
        or re.fullmatch(expected_digest_pattern, '"api_key": "' + "a" * 64 + '"') is not None
    ):
        raise RuntimeError("Gitleaks allowlist must remain limited to generated report output SHA-256 fields")
    return {
        "schema_version": 1,
        "passed": True,
        "evidence_id": EVIDENCE_ID,
        "evidence_type": "github-quality-and-secret-gates",
        "workflow": {"sha256": _sha256(WORKFLOW), "jobs": ["secrets", "verify"], "read_only_permissions": True},
        "gitleaks_config": {"sha256": _sha256(GITLEAKS_CONFIG), "default_rules_extended": True, "narrow_digest_allowlist": True},
        "requirements": {"sha256": _sha256(REQUIREMENTS), "tested_baselines": requirements},
        "quality_gates": {
            "complete_unittest_suite": True,
            "release_validator": True,
            "deterministic_registry_rebuild": True,
            "generated_diff_rejected": True,
            "full_history_secret_scan": True,
            "gitleaks_release_checksum_verified": True,
            "secret_findings_redacted": True,
        },
        "excluded_claims": [
            "CI does not prove scientific source-union completeness.",
            "CI does not replace module-specific regression, compatibility, or end-to-end evidence.",
            "Repository checks do not install arbitrary remote Skills into the scientific runtime.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "ci-quality-verification.json")
    args = parser.parse_args()
    report = verify()
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"evidence_id": report["evidence_id"], "passed": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
