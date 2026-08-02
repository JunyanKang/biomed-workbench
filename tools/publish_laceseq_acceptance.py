#!/usr/bin/env python3
"""Publish path-neutral evidence from an observed public LACE-seq run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.laceseq import UPSTREAM_COMMIT, UPSTREAM_REPOSITORY  # noqa: E402
from biomed_workbench.implementations.laceseq_fastq import METHOD_DOI  # noqa: E402
from biomed_workbench.modules.evidence_scope import module_evidence_scope  # noqa: E402
from biomed_workbench.modules.index import BUILTIN_ROOT  # noqa: E402
from biomed_workbench.modules.registry import ModuleRegistry  # noqa: E402


MODULE_ID = "bulk-rbp-rna-binding"
FASTQ_IMPLEMENTATION = "biomed_workbench/implementations/laceseq_fastq.py"
CLUSTER_IMPLEMENTATION = "biomed_workbench/implementations/laceseq.py"
PUBLIC_INPUTS = {
    "experiment": {"accession": "SRR10173391", "sha256": "1b45b9993fc4ea2d525a5d9d1b3d002f465472d4df7a829c811f6430afb43cac"},
    "control": {"accession": "SRR10173407", "sha256": "9539b3e2d11b24c1f23433146288baa0728be4a31a4dbd49ca76592334377d60"},
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def _artifact(item: object, *, require_rows: bool = False) -> dict[str, Any]:
    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
        raise ValueError("artifact record is incomplete")
    path = Path(item["path"])
    if not path.is_file() or path.stat().st_size != item.get("bytes") or _sha256(path) != item.get("sha256"):
        raise ValueError(f"artifact no longer matches its execution record: {path}")
    published = {"name": path.name, "bytes": item["bytes"], "sha256": item["sha256"]}
    for field in ("records", "rows"):
        if field in item:
            published[field] = item[field]
    if require_rows and int(published.get("rows", 0)) < 1:
        raise ValueError(f"nonempty row output required: {path}")
    return published


def _input_evidence(raw: dict[str, Any], subset_reports: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    inputs = raw.get("inputs")
    if not isinstance(inputs, dict):
        raise ValueError("LACE-seq inputs are missing")
    published: list[dict[str, Any]] = []
    for group, expected in PUBLIC_INPUTS.items():
        item = inputs.get(group)
        subset = subset_reports.get(group)
        if (
            not isinstance(item, dict)
            or item.get("reads") != 100000
            or item.get("sha256") != expected["sha256"]
            or not isinstance(subset, dict)
            or subset.get("passed") is not True
            or subset.get("accession") != expected["accession"]
            or subset.get("selection") != {"kind": "first_n_reads", "reads": 100000}
            or subset.get("output", {}).get("sha256") != item.get("sha256")
            or subset.get("output", {}).get("bytes") != item.get("bytes")
        ):
            raise ValueError(f"public LACE-seq {group} input or prefix evidence is stale")
        source = subset.get("source")
        if not isinstance(source, dict) or len(str(source.get("full_object_md5", ""))) != 32:
            raise ValueError(f"public LACE-seq {group} source metadata is incomplete")
        published.append({
            "group": group,
            "accession": expected["accession"],
            "url": f"https://www.ncbi.nlm.nih.gov/sra/{expected['accession']}",
            "selection": subset["selection"],
            "source_fastq": {
                "url": source.get("resolved_url"),
                "bytes": source.get("full_object_bytes"),
                "md5": source.get("full_object_md5"),
            },
            "subset_fastq": {"name": Path(item["path"]).name, "bytes": item["bytes"], "sha256": item["sha256"]},
        })
    return published


def _reference_evidence(raw: dict[str, Any]) -> dict[str, Any]:
    references = raw.get("references")
    if not isinstance(references, dict):
        raise ValueError("reference evidence is missing")
    published: dict[str, Any] = {}
    for kind in ("rrna", "genome"):
        item = references.get(kind)
        if not isinstance(item, dict) or not isinstance(item.get("index_prefix"), str):
            raise ValueError(f"{kind} reference evidence is incomplete")
        fasta = _artifact(item.get("fasta"))
        prefix = Path(item["index_prefix"])
        index_parts = item.get("index_parts")
        if not isinstance(index_parts, dict) or len(index_parts) != 6:
            raise ValueError(f"{kind} Bowtie index evidence is incomplete")
        clean_parts: dict[str, dict[str, Any]] = {}
        for name, record in index_parts.items():
            path = prefix.parent / name
            if (
                not isinstance(record, dict)
                or not path.is_file()
                or path.stat().st_size != record.get("bytes")
                or _sha256(path) != record.get("sha256")
            ):
                raise ValueError(f"{kind} Bowtie index part is stale: {name}")
            clean_parts[name] = {"bytes": record["bytes"], "sha256": record["sha256"]}
        published[kind] = {
            **{key: item[key] for key in item if key not in {"fasta", "index_prefix", "index_parts"}},
            "fasta": fasta,
            "bowtie_index_parts": clean_parts,
        }
    return published


def build_reports(
    raw: dict[str, Any],
    experiment_subset: dict[str, Any],
    control_subset: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    implementation = raw.get("implementation")
    method = raw.get("method")
    runtime = raw.get("runtime")
    software = raw.get("software")
    cluster_stage = raw.get("cluster_stage")
    if (
        raw.get("schema_version") != 1
        or raw.get("module_id") != MODULE_ID
        or raw.get("assay") != "lace-seq"
        or raw.get("passed") is not True
        or not isinstance(implementation, dict)
        or implementation.get("path") != FASTQ_IMPLEMENTATION
        or implementation.get("sha256") != _sha256(ROOT / FASTQ_IMPLEMENTATION)
        or not isinstance(method, dict)
        or method.get("doi") != METHOD_DOI
        or method.get("upstream_repository") != UPSTREAM_REPOSITORY
        or method.get("upstream_commit") != UPSTREAM_COMMIT
        or software != {"cutadapt": "1.15", "bowtie": "/usr/local/bin/bowtie-align-s version 1.2.3"}
        or not isinstance(runtime, dict)
        or runtime.get("mode") != "containers"
        or runtime.get("platform") != "linux/amd64"
        or "@sha256:" not in str(runtime.get("cutadapt_image", ""))
        or runtime.get("cutadapt_image") != runtime.get("bowtie_image")
        or not isinstance(cluster_stage, dict)
        or cluster_stage.get("implementation", {}).get("path") != CLUSTER_IMPLEMENTATION
        or cluster_stage.get("implementation", {}).get("sha256") != _sha256(ROOT / CLUSTER_IMPLEMENTATION)
        or cluster_stage.get("method", {}).get("upstream_commit") != UPSTREAM_COMMIT
    ):
        raise ValueError("raw report is not a passing current LACE-seq public execution")
    dockerfile = runtime.get("dockerfile")
    if not isinstance(dockerfile, dict) or not isinstance(dockerfile.get("path"), str):
        raise ValueError("LACE-seq Dockerfile provenance is missing")
    dockerfile_path = ROOT / dockerfile["path"]
    if not dockerfile_path.is_file() or _sha256(dockerfile_path) != dockerfile.get("sha256"):
        raise ValueError("LACE-seq Dockerfile provenance is stale")
    inputs = _input_evidence(raw, {"experiment": experiment_subset, "control": control_subset})
    references = _reference_evidence(raw)
    preprocessing = raw.get("preprocessing")
    preprocessing_outputs = raw.get("preprocessing_outputs")
    if not isinstance(preprocessing, dict) or not isinstance(preprocessing_outputs, dict):
        raise ValueError("LACE-seq preprocessing evidence is incomplete")
    clean_preprocessing_outputs: dict[str, dict[str, Any]] = {}
    for group in ("experiment", "control"):
        metrics = preprocessing.get(group)
        records = preprocessing_outputs.get(group)
        if (
            not isinstance(metrics, dict)
            or int(metrics.get("post_trim_reads", 0)) < 1
            or int(metrics.get("non_rrna_reads", 0)) < 1
            or int(metrics.get("mapped_bed_rows", 0)) < 1
            or not isinstance(records, dict)
        ):
            raise ValueError(f"LACE-seq {group} preprocessing did not reload")
        clean_preprocessing_outputs[group] = {name: _artifact(item) for name, item in records.items()}
    output_records = raw.get("outputs")
    if not isinstance(output_records, dict):
        raise ValueError("LACE-seq cluster outputs are missing")
    outputs = {
        name: _artifact(item, require_rows=name in {"clusters_bed", "clusters_tsv", "control_subtracted_reads"})
        for name, item in output_records.items()
    }
    clusters = raw.get("clusters")
    if (
        not isinstance(clusters, dict)
        or int(clusters.get("experiment_unique_reads", 0)) < 1
        or int(clusters.get("control_unique_reads", 0)) < 1
        or int(clusters.get("control_filtered_unique_reads", 0)) < 1
        or int(clusters.get("retained_clusters", 0)) < 1
    ):
        raise ValueError("LACE-seq cluster metrics are incomplete")
    gates = {
        "current_fastq_and_cluster_implementations": True,
        "official_method_doi_and_code_commit_pinned": True,
        "cutadapt_1_15_observed": True,
        "bowtie_1_2_3_observed": True,
        "container_digest_and_build_checksum_recorded": True,
        "public_ago2_and_igg_prefixes_checksum_bound": True,
        "rrna_and_genome_references_checksum_bound": True,
        "adapter_and_polya_trimming_reloaded": True,
        "rrna_filtering_reloaded": True,
        "genome_alignments_reloaded": True,
        "official_whole_read_igg_exclusion_applied": True,
        "official_coordinate_strand_deduplication_applied": True,
        "nonempty_clusters_reloaded": True,
        "input_and_output_checksums_recorded": True,
    }
    registry = ModuleRegistry.discover(BUILTIN_ROOT)
    manifest = registry.get(MODULE_ID)
    scope = module_evidence_scope(registry, [MODULE_ID]).to_dict()
    templates_root = BUILTIN_ROOT / MODULE_ID / "templates"
    templates = {path.name: _sha256(path) for path in sorted(templates_root.iterdir()) if path.is_file()}
    execution = {
        "assay": "lace-seq",
        "external_tools_executed": True,
        "outputs_reloaded": True,
        "parameters": raw.get("parameters"),
        "software": software,
        "runtime": {
            "platform": runtime["platform"],
            "image": runtime["cutadapt_image"],
            "dockerfile": {"name": dockerfile_path.name, "sha256": dockerfile["sha256"]},
        },
        "preprocessing": preprocessing,
        "preprocessing_outputs": clean_preprocessing_outputs,
        "clusters": clusters,
        "outputs": outputs,
    }
    source = {
        "method": method,
        "cluster_stage": cluster_stage,
        "public_inputs": inputs,
        "references": references,
    }
    common = {
        "schema_version": 1,
        "passed": all(gates.values()),
        "assay": "lace-seq",
        "evidence_scope": scope,
        "execution_evidence_level": "observed_scientific_workflow",
        "observed_at": raw.get("executed_at"),
        "implementation": implementation,
        "execution": execution,
        "source": source,
        "quality_gates": gates,
        "scientific_scope": (
            "This acceptance validates the complete public FASTQ-to-cluster path on the first 100,000 reads "
            "from Ago2 and matched IgG runs against mm9 chromosome X. Full-project biological inference requires "
            "complete references, complete biological replicates, and the prespecified project design."
        ),
    }
    live = {
        **common,
        "module_id": MODULE_ID,
        "module_version": manifest.version,
        "registry_digest": registry.digest,
        "templates": templates,
    }
    public = {
        **common,
        "case_id": "laceseq-srr10173391-srr10173407-first100000-mm9-chrx-v1",
        "case_type": "public-data-end-to-end",
        "module": {"id": MODULE_ID, "version": manifest.version},
    }
    return live, public


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-report", type=Path, required=True)
    parser.add_argument("--experiment-subset-report", type=Path, required=True)
    parser.add_argument("--control-subset-report", type=Path, required=True)
    parser.add_argument("--live-report", type=Path, required=True)
    parser.add_argument("--public-case", type=Path, required=True)
    args = parser.parse_args()
    live, public = build_reports(
        _load(args.raw_report),
        _load(args.experiment_subset_report),
        _load(args.control_subset_report),
    )
    for path, payload in ((args.live_report, live), (args.public_case, public)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "live_report": str(args.live_report), "public_case": str(args.public_case)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
