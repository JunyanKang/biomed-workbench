#!/usr/bin/env python3
"""Export a versioned trajectory/spatial figure profile for the R renderer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.visualization import scientific_figure_standard


SUPPORTED_ANALYSES = {
    "trajectory-topology",
    "trajectory-velocity",
    "fate-mapping",
    "regulatory-velocity",
    "spatial-platform-qc",
    "spatial-core-analysis",
    "spatial-deconvolution",
    "spatial-domain-benchmark",
    "spatial-communication",
    "spatial-image-analysis",
    "spatial-multislice",
}
SUPPORTED_JOURNALS = {"nature", "science", "cell", "screen"}


def validate_inputs(analysis_type: str, journal_profile: str, output: Path) -> None:
    """Validate input selections and the non-overwrite output policy."""
    if analysis_type not in SUPPORTED_ANALYSES:
        raise ValueError(f"unsupported trajectory or spatial analysis type: {analysis_type}")
    if journal_profile not in SUPPORTED_JOURNALS:
        raise ValueError(f"unsupported journal profile: {journal_profile}")
    if output.exists():
        raise FileExistsError(output)
    if output.suffix.lower() != ".json":
        raise ValueError("figure contract output must be JSON")


def validate_contract(contract: dict[str, object]) -> None:
    """Validate the exported profile before serialization."""
    required = contract.get("required_plots")
    style = contract.get("style")
    if not isinstance(required, list) or not required or len(required) != len(set(required)):
        raise ValueError("analysis figure profile requires unique mandatory plots")
    if not isinstance(style, dict) or not str(style.get("version", "")).strip():
        raise ValueError("figure contract lacks style version provenance")
    if not style.get("export") or not style.get("typography_pt"):
        raise ValueError("figure contract lacks export or typography quality tokens")
    typography = style["typography_pt"]
    strokes = style.get("strokes_pt", {})
    export = style["export"]
    if typography.get("minimum") < 5 or typography.get("maximum") > 7:
        raise ValueError("final-size typography is outside the registered 5-7 pt contract")
    if strokes.get("minimum", 0) < 0.5:
        raise ValueError("registered minimum stroke is below 0.5 pt")
    if not {"pdf", "svg"} <= set(export.get("primary", [])):
        raise ValueError("editable vector PDF and SVG outputs are required")
    if export.get("raster_dpi", 0) < 600:
        raise ValueError("publication raster export must be at least 600 dpi")
    if contract.get("analysis_type") not in SUPPORTED_ANALYSES:
        raise ValueError("serialized contract changed analysis identity")
    if contract.get("journal_profile") not in SUPPORTED_JOURNALS:
        raise ValueError("serialized contract changed journal identity")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-type", required=True)
    parser.add_argument("--journal-profile", default="nature")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate_inputs(args.analysis_type, args.journal_profile, args.output)
    contract = scientific_figure_standard(args.analysis_type, args.journal_profile)
    validate_contract(contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    reloaded = json.loads(args.output.read_text())
    validate_contract(reloaded)
    if reloaded["required_plots"] != contract["required_plots"]:
        raise RuntimeError("figure profile changed during output reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
