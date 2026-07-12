#!/usr/bin/env python3
"""Verify chroma-key execution through the scientific command boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore  # noqa: E402
from biomed_workbench.kernel.identity import digest_value  # noqa: E402
from biomed_workbench.modules.compatibility import detect_environment  # noqa: E402
from biomed_workbench.modules.contract import parse_manifest  # noqa: E402
from biomed_workbench.modules.scientific_command import execute_scientific_command  # noqa: E402
from biomed_workbench.quality import parse_chroma_key_outputs  # noqa: E402


MODULE_PATH = ROOT / "biomed_workbench" / "modules" / "builtin" / "image-chroma-key-remove" / "module.json"
COMMAND_PARAMETERS = {
    "source-format": "png",
    "key-color": "#00ff00",
    "auto-key": "corners",
    "transparent-threshold": 8.0,
    "opaque-threshold": 90.0,
    "auto-key-maximum-deviation": 18.0,
    "auto-key-minimum-consensus": 0.9,
    "despill-strength": 1.0,
    "edge-contract": 0,
    "edge-feather": 0.0,
}
QUALITY_PARAMETERS = {key.replace("-", "_"): value for key, value in COMMAND_PARAMETERS.items()}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_fixture(path: Path) -> None:
    image = Image.new("RGBA", (64, 64), (0, 255, 0, 255))
    pixels = image.load()
    for y in range(16, 48):
        for x in range(16, 48):
            pixels[x, y] = (224, 24, 40, 255)
    for offset in range(16, 48):
        pixels[15, offset] = (24, 228, 4, 255)
        pixels[48, offset] = (24, 228, 4, 255)
        pixels[offset, 15] = (24, 228, 4, 255)
        pixels[offset, 48] = (24, 228, 4, 255)
    pixels[32, 32] = (224, 24, 40, 128)
    image.save(path, format="PNG")


def verify(executable: Path) -> dict[str, object]:
    manifest = parse_manifest(json.loads(MODULE_PATH.read_text(encoding="utf-8")))
    original_path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join((str(executable.parent), original_path))
    try:
        environment = detect_environment(manifest)
        expected = ({"python3": "3.14.3"}, {"Pillow": "10.4.0"})
        if (environment.tools, environment.dependencies) != expected:
            raise RuntimeError("raster runtime differs from the validated chroma-key compatibility row")
        row = manifest.compatibility_matrix[0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            _make_fixture(source)
            store = ProjectArtifactStore(root / "project")
            input_payload = store.import_file(source, role="image", media_type="image/png")
            result = execute_scientific_command(
                manifest.execution.command,
                store=store,
                input_payloads={"image": input_payload},
                parameters=COMMAND_PARAMETERS,
                tool_versions=environment.tools,
                dependency_versions=environment.dependencies,
                compatibility_row_id=row.id,
                executable_resolver=lambda _name: executable,
            )
            outputs = {payload.role: payload for payload in result.output_payloads}
            summary = parse_chroma_key_outputs(
                source,
                store.resolve(outputs["image"]),
                store.resolve(outputs["report"]),
                expected_parameters=QUALITY_PARAMETERS,
            )
            provenance = result.to_dict()["provenance"]
            fixture = {
                "format": "png@3.0",
                "orientation": "top-left-raster",
                "processing_level": "generated-asset",
                "color_space": "untagged-srgb",
                "dimensions": [64, 64],
                "source_sha256": _sha256(source),
                "parameters": COMMAND_PARAMETERS,
            }
        if summary["alpha_counts"]["transparent"] == 0 or summary["alpha_counts"]["partial"] == 0 or summary["alpha_counts"]["opaque"] == 0:
            raise RuntimeError("synthetic fixture did not exercise all alpha classes")
        if summary["quantitative_interpretation_allowed"] is not False:
            raise RuntimeError("scientific-use boundary was not enforced")
        return {
            "schema_version": 1,
            "passed": True,
            "module_id": manifest.id,
            "module_version": manifest.version,
            "compatibility_row_id": row.id,
            "regression_evidence_id": row.regression_evidence_ids[0],
            "end_to_end_evidence_id": row.end_to_end_evidence_ids[0],
            "tool_versions": environment.tools,
            "dependency_versions": environment.dependencies,
            "tested_version_baseline": {
                "tools": {item.name: environment.tools[item.name] in item.tested_versions for item in manifest.tool_requirements},
                "dependencies": {item.name: environment.dependencies[item.name] in item.tested_versions for item in manifest.dependencies},
            },
            "compatibility_policy": {
                "tools": {name: list(rules) for name, rules in row.tool_versions.items()},
                "dependencies": {name: list(rules) for name, rules in row.dependency_versions.items()},
            },
            "fixture": fixture,
            "fixture_digest": digest_value(fixture),
            "implementation": provenance["implementation"],
            "execution": {
                "command_contract_digest": provenance["command_contract_digest"],
                "executable_sha256": provenance["executable_sha256"],
                "inputs": provenance["inputs"],
                "outputs": provenance["outputs"],
                "parameters": provenance["parameters"],
            },
            "scientific_summary": summary,
            "html_report_validated": False,
        }
    finally:
        os.environ["PATH"] = original_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "chroma-key-live-verification.json")
    args = parser.parse_args()
    report = verify(args.python_executable.resolve())
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "alpha_counts": report["scientific_summary"]["alpha_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
