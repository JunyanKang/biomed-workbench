#!/usr/bin/env python3
"""Execute CellRank, moscot, Slingshot, Monocle3, and tradeSeq on one bifurcation fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.modules.index import BUILTIN_ROOT
from biomed_workbench.modules.registry import ModuleRegistry


FATE_ID = "single-cell-fate-mapping"
TOPOLOGY_ID = "single-cell-trajectory-topology"
FATE_ROOT = BUILTIN_ROOT / FATE_ID
TOPOLOGY_ROOT = BUILTIN_ROOT / TOPOLOGY_ID
FATE_TEMPLATE = FATE_ROOT / "templates" / "run_cellrank_fate.py"
TOPOLOGY_TEMPLATE = TOPOLOGY_ROOT / "templates" / "run_slingshot_monocle_tradeseq.R"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], *, timeout: int = 1200) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(f"trajectory command failed ({completed.returncode}): {' '.join(command[:3])}\nstderr:\n{completed.stderr[-6000:]}\nstdout:\n{completed.stdout[-3000:]}")
    return completed


def fixture_code(work: Path) -> str:
    return f"""
import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

rng = np.random.default_rng(42)
rows, velocities, metadata, coordinates = [], [], [], []
for time, number in ((0, 60), (1, 80), (2, 100)):
    for index in range(number):
        terminal = 'none' if time < 2 else ('A' if index < 50 else 'B')
        branch = 0 if terminal == 'none' else (1 if terminal == 'A' else -1)
        pseudotime = time / 2 + rng.normal(0, 0.03)
        rate = np.full(80, 1.5)
        rate[0:5] += 4 * max(pseudotime, 0)
        if terminal == 'A': rate[10:20] += 8
        if terminal == 'B': rate[20:30] += 8
        rows.append(rng.poisson(np.maximum(rate, 0.1)).astype(np.int32))
        velocity = np.zeros(80, dtype=np.float64)
        velocity[0:5] = 4
        if terminal == 'A': velocity[10:20] = 8
        elif terminal == 'B': velocity[20:30] = 8
        else: velocity[10:30] = 4
        velocities.append(velocity)
        metadata.append({{'sample': f'T{{time}}_S{{index % 2 + 1}}', 'time': time, 'pseudotime': pseudotime, 'terminal': terminal, 'cluster': ('Root' if time == 0 else ('Mid' if time == 1 else terminal))}})
        coordinates.append((pseudotime + rng.normal(0, 0.02), branch * max(pseudotime - 0.5, 0) * 1.6 + rng.normal(0, 0.03)))
cells = [f'cell-{{index:03d}}' for index in range(len(rows))]
genes = [f'GENE{{index:03d}}' for index in range(80)]
counts = np.asarray(rows, dtype=np.int32)
adata = ad.AnnData(sparse.csr_matrix(counts), obs=pd.DataFrame(metadata, index=cells), var=pd.DataFrame(index=genes))
adata.layers['counts'] = adata.X.copy()
adata.layers['state'] = sparse.csr_matrix(np.log1p(counts.astype(np.float64)))
adata.layers['velocity'] = sparse.csr_matrix(np.asarray(velocities))
adata.write_h5ad({str(work / 'input.h5ad')!r})
pd.DataFrame(counts.T, index=genes, columns=cells).rename_axis('gene_id').reset_index().to_csv({str(work / 'counts.tsv')!r}, sep='\\t', index=False)
obs = adata.obs.copy(); obs.insert(0, 'cell_id', cells); obs.to_csv({str(work / 'metadata.tsv')!r}, sep='\\t', index=False)
pd.DataFrame(coordinates, index=cells, columns=['dim1', 'dim2']).rename_axis('cell_id').reset_index().to_csv({str(work / 'embedding.tsv')!r}, sep='\\t', index=False)
"""


def verify(python: Path, rscript: Path, r_library: Path) -> tuple[dict[str, object], dict[str, object]]:
    python = python.expanduser().absolute()
    rscript = rscript.expanduser().absolute()
    r_library = r_library.expanduser().resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="biomed-fate-topology-") as temporary:
        work = Path(temporary)
        (work / "home").mkdir(); (work / "cache").mkdir()
        environment = {"PATH": str(python.parent) + os.pathsep + str(rscript.parent) + os.pathsep + os.environ.get("PATH", ""), "HOME": str(work / "home"), "XDG_CACHE_HOME": str(work / "cache"), "PYTHONHASHSEED": "0", "R_LIBS_USER": str(r_library), "LANG": "C", "LC_ALL": "C"}
        run([str(python), "-c", fixture_code(work)], environment)
        source_digest = sha256(work / "input.h5ad")

        reports = {}
        for mode, prefix in (("velocity", "velocity"), ("pseudotime", "pseudo"), ("real-time-optimal-transport", "ot")):
            command = [str(python), str(FATE_TEMPLATE), "--input-h5ad", str(work / "input.h5ad"), "--output-h5ad", str(work / f"{prefix}.h5ad"), "--fate-table", str(work / f"{prefix}-fate.tsv"), "--driver-table", str(work / f"{prefix}-drivers.tsv"), "--report", str(work / f"{prefix}.json"), "--raw-count-location", "layers.counts", "--sample-key", "sample", "--time-key", "time", "--pseudotime-key", "pseudotime", "--terminal-state-key", "terminal", "--terminal-states", "A,B", "--mode", mode, "--n-top-genes", "60", "--n-pcs", "15", "--n-neighbors", "15", "--ot-epsilon", "0.05", "--ot-threshold", "0.001", "--minimum-terminal-own-fate", "0.7", "--minimum-time-direction", "0.0", "--seed", "43"]
            if mode == "velocity":
                command.extend(["--state-location", "layers.state", "--velocity-location", "layers.velocity", "--connectivity-weight", "0.2"])
            run(command, environment)
            reports[prefix] = json.loads((work / f"{prefix}.json").read_text())

        root_cells = ",".join(f"cell-{index:03d}" for index in range(10))
        run([str(rscript), str(TOPOLOGY_TEMPLATE), "--counts", str(work / "counts.tsv"), "--metadata", str(work / "metadata.tsv"), "--embedding", str(work / "embedding.tsv"), "--cell-results", str(work / "trajectory-cells.tsv"), "--gene-results", str(work / "trajectory-genes.tsv"), "--cds-output", str(work / "monocle-object"), "--report", str(work / "topology.json"), "--cluster-key", "cluster", "--sample-key", "sample", "--external-time-key", "time", "--start-cluster", "Root", "--end-clusters", "A,B", "--root-cells", root_cells, "--nknots", "5", "--minimum-lineage-cells", "30", "--minimum-time-correlation", "0.6", "--seed", "44"], environment)
        topology = json.loads((work / "topology.json").read_text())
        inspect = json.loads(run([str(python), "-c", f"""
import json, pandas as pd
d = pd.read_csv({str(work / 'trajectory-genes.tsv')!r}, sep='\\t')
branch = {{f'GENE{{i:03d}}' for i in range(10, 30)}}
association = set(d.sort_values('association__pvalue').head(20).gene_id)
end = set(d.sort_values('differential_end__pvalue').head(20).gene_id)
print(json.dumps({{'association_branch_hits': len(branch & association), 'differential_end_branch_hits': len(branch & end), 'all_four_test_prefixes': all(any(c.startswith(p) for c in d.columns) for p in ('association__','pattern__','start_vs_end__','differential_end__'))}}))
"""], environment).stdout)
        if sha256(work / "input.h5ad") != source_digest or any(report["quality_status"] != "passed" for report in reports.values()) or topology["quality_status"] != "passed":
            raise RuntimeError("fate or topology fixture failed quality or source preservation")
        if reports["ot"]["model"]["transport_pairs"] != 2 or inspect["association_branch_hits"] < 18 or inspect["differential_end_branch_hits"] < 18 or not inspect["all_four_test_prefixes"]:
            raise RuntimeError("optimal transport or planted tradeSeq programs were not recovered")

        registry = ModuleRegistry.discover(BUILTIN_ROOT)
        fate = {"schema_version": 2, "passed": True, "module_id": FATE_ID, "module_version": "1.1.0", "compatibility_row_id": "agent-protocol-2-cellrank-232-moscot-051-velocity", "registry_digest": registry.digest, "templates": {"cellrank": {"name": FATE_TEMPLATE.name, "sha256": sha256(FATE_TEMPLATE)}}, "tool_versions": {"CellRank": reports["pseudo"]["versions"]["cellrank"], "moscot": reports["ot"]["versions"]["moscot"]}, "dependency_versions": {key: reports["ot"]["versions"][key] for key in ("python", "scanpy", "anndata", "numpy", "pandas", "scipy", "jax", "ott-jax")}, "fixture": {"sha256": source_digest, "cells": 240, "genes": 80, "samples": 6, "time_points": 3, "terminal_states": 2}, "execution": {"velocity_kernel_completed": True, "connectivity_sensitivity_completed": True, "pseudotime_kernel_completed": True, "optimal_transport_completed": True, "gpcca_completed": True, "outputs_reloaded": True}, "backend_summaries": {"velocity": reports["velocity"]["results"], "pseudotime": reports["pseudo"]["results"], "optimal_transport": reports["ot"]["results"]}, "scientific_summary": {"velocity_pseudotime_and_optimal_transport_kernels_executed": True, "velocity_connectivity_weight_recorded": reports["velocity"]["model"]["connectivity_weight"] == 0.2, "two_transport_pairs_solved": True, "gpcca_fate_probabilities_sum_to_one": True, "declared_terminal_states_recovered": True, "lineage_drivers_retained": True, "experimental_time_direction_checked": True, "source_counts_and_identifiers_preserved": True, "outputs_reloaded": True, "no_environment_or_compute_infrastructure_managed": True}}
        topo_versions = topology["versions"]
        topo = {"schema_version": 1, "passed": True, "module_id": TOPOLOGY_ID, "module_version": "1.1.0", "compatibility_row_id": "agent-protocol-1-slingshot-210-monocle3-1426-tradeseq-116", "registry_digest": registry.digest, "templates": {"trajectory": {"name": TOPOLOGY_TEMPLATE.name, "sha256": sha256(TOPOLOGY_TEMPLATE)}}, "tool_versions": {key: topo_versions[key] for key in ("slingshot", "monocle3", "tradeSeq")}, "dependency_versions": {"r": topo_versions["R"], **{key: topo_versions[key] for key in ("SingleCellExperiment", "Matrix", "BiocParallel", "jsonlite", "digest")}}, "fixture": {"counts_sha256": topology["input"]["counts_sha256"], "cells": 240, "genes": 80, "samples": 6, "lineages": 2}, "execution": {"slingshot_completed": True, "monocle3_completed": True, "tradeseq_completed": True, "outputs_reloaded": True}, "results": {**topology["results"], **inspect}, "scientific_summary": {"two_declared_lineages_recovered": True, "slingshot_and_monocle3_direction_validated": True, "method_concordance_checked": True, "tradeseq_association_pattern_start_end_and_diff_end_completed": True, "planted_branch_programs_recovered": True, "lineage_weights_and_unassigned_cells_preserved": True, "source_counts_and_identifiers_preserved": True, "outputs_reloaded": True, "no_environment_or_compute_infrastructure_managed": True}}
        return fate, topo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-python", type=Path, required=True); parser.add_argument("--rscript", type=Path, required=True); parser.add_argument("--r-library", type=Path, required=True)
    parser.add_argument("--fate-output", type=Path, required=True); parser.add_argument("--topology-output", type=Path, required=True)
    args = parser.parse_args(); fate, topology = verify(args.scientific_python, args.rscript, args.r_library)
    for path, report in ((args.fate_output, fate), (args.topology_output, topology)):
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"fate": fate["passed"], "topology": topology["passed"], "tool_versions": {**fate["tool_versions"], **topology["tool_versions"]}}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
