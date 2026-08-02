#!/usr/bin/env python3
"""Prepare, execute, and review official AlphaFold 3 complex predictions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from biomed_workbench.implementations.alphafold3_local import execute_alphafold3_local
from biomed_workbench.implementations.alphafold3_server import parse_alphafold_server_archive


AF3_RELEASE = "3.0.3"
AF3_INPUT_VERSION = 4
FIGURE_STYLE_VERSION = "biomed-workbench-structure-v2"
R_FIGURE_TEMPLATE = Path(__file__).with_name("render_alphafold3_publication_figures.R")
OFFICIAL_DB_RELEASE = "alphafold-databases-v3.0"
OFFICIAL_DB_FILES = (
    "mgy_clusters_2022_05.fa",
    "bfd-first_non_consensus_sequences.fasta",
    "uniref90_2022_05.fa",
    "uniprot_all_2021_04.fa",
    "pdb_seqres_2022_09_28.fasta",
    "rnacentral_active_seq_id_90_cov_80_linclust.fasta",
    "nt_rna_2023_02_23_clust_seq_id_90_cov_80_rep_seq.fasta",
    "rfam_14_9_clust_seq_id_90_cov_80_rep_seq.fasta",
)
OFFICIAL_SOURCES = {
    "release": "https://github.com/google-deepmind/alphafold3/releases/tag/v3.0.3",
    "installation": "https://github.com/google-deepmind/alphafold3/blob/v3.0.3/docs/installation.md",
    "input": "https://github.com/google-deepmind/alphafold3/blob/v3.0.3/docs/input.md",
    "output": "https://github.com/google-deepmind/alphafold3/blob/v3.0.3/docs/output.md",
    "performance": "https://github.com/google-deepmind/alphafold3/blob/v3.0.3/docs/performance.md",
    "server": "https://alphafoldserver.com/",
    "server_faq": "https://alphafoldserver.com/faq",
    "server_output_terms": "https://alphafoldserver.com/output-terms",
    "server_privacy": "https://alphafoldserver.com/privacy",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clean_sequence(value: str, alphabet: str) -> str:
    sequence = re.sub(r"\s+", "", value).upper()
    if not sequence or len(sequence) > 10_000 or re.fullmatch(f"[{alphabet}]+", sequence) is None:
        raise ValueError("entity sequence is empty, too long, or outside the official alphabet")
    return sequence


def _stage_asset(value: object, request_dir: Path, asset_dir: Path, allowed_suffixes: Sequence[str]) -> tuple[str, dict]:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("external AlphaFold 3 asset path must be a nonempty string")
    source = Path(value).expanduser()
    if not source.is_absolute():
        source = request_dir / source
    source = source.resolve()
    suffixes = "".join(source.suffixes[-2:]).lower()
    if not source.is_file() or not any(suffixes.endswith(suffix) for suffix in allowed_suffixes):
        raise ValueError(f"external AlphaFold 3 asset is missing or has an unsupported format: {value}")
    asset_dir.mkdir(parents=True, exist_ok=True)
    prefix = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
    target = asset_dir / f"{prefix}-{source.name}"
    if not target.exists() or digest(target) != digest(source):
        shutil.copy2(source, target)
    record = {
        "source_name": source.name,
        "staged_path": f"assets/{target.name}",
        "sha256": digest(target),
        "bytes": target.stat().st_size,
    }
    return record["staged_path"], record


def _validate_modifications(kind: str, modifications: object, sequence_length: int) -> list[dict]:
    if not isinstance(modifications, list):
        raise ValueError("modifications must be an array")
    code_key, position_key = ("ptmType", "ptmPosition") if kind == "protein" else ("modificationType", "basePosition")
    normalized = []
    for modification in modifications:
        if not isinstance(modification, dict) or set(modification) != {code_key, position_key}:
            raise ValueError(f"{kind} modification must contain only {code_key} and {position_key}")
        code, position = modification[code_key], modification[position_key]
        if not isinstance(code, str) or re.fullmatch(r"[A-Za-z0-9-]{1,20}", code) is None:
            raise ValueError("modification code is invalid")
        if not isinstance(position, int) or not 1 <= position <= sequence_length:
            raise ValueError("modification position is outside the declared sequence")
        normalized.append({code_key: code, position_key: position})
    return normalized


def _validate_templates(templates: object, request_dir: Path, asset_dir: Path, assets: list[dict]) -> list[dict]:
    if not isinstance(templates, list):
        raise ValueError("templates must be an array")
    normalized = []
    for template in templates:
        allowed = {"mmcif", "mmcifPath", "queryIndices", "templateIndices"}
        if not isinstance(template, dict) or set(template) - allowed:
            raise ValueError("protein template contains unsupported fields")
        if ("mmcif" in template) == ("mmcifPath" in template):
            raise ValueError("protein template requires exactly one of mmcif or mmcifPath")
        query, target = template.get("queryIndices"), template.get("templateIndices")
        if not isinstance(query, list) or not isinstance(target, list) or not query or len(query) != len(target):
            raise ValueError("template queryIndices and templateIndices must be equal nonempty arrays")
        if any(not isinstance(value, int) or value < 0 for value in (*query, *target)):
            raise ValueError("template indices must be nonnegative integers")
        clean = {"queryIndices": query, "templateIndices": target}
        if "mmcif" in template:
            if not isinstance(template["mmcif"], str) or "data_" not in template["mmcif"][:200]:
                raise ValueError("inline template mmcif is invalid")
            clean["mmcif"] = template["mmcif"]
        else:
            staged, record = _stage_asset(template["mmcifPath"], request_dir, asset_dir, (".cif", ".mmcif", ".cif.gz", ".cif.xz", ".cif.zst"))
            clean["mmcifPath"] = staged
            assets.append(record)
        normalized.append(clean)
    return normalized


def prepare(request: dict, *, request_dir: Path | None = None, asset_dir: Path | None = None) -> tuple[dict, list[dict]]:
    request_dir = (request_dir or Path.cwd()).resolve()
    asset_dir = (asset_dir or request_dir / "assets").resolve()
    allowed = {"name", "model_seeds", "entities", "description", "bonded_atom_pairs", "user_ccd", "user_ccd_path"}
    if not isinstance(request, dict) or set(request) - allowed:
        raise ValueError("request must be a closed AlphaFold 3 preparation object")
    name = str(request.get("name", ""))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}", name):
        raise ValueError("name must be a short printable job name")
    seeds = request.get("model_seeds", [1])
    if not isinstance(seeds, list) or not 1 <= len(seeds) <= 20 or any(not isinstance(seed, int) or not 0 <= seed < 2**31 for seed in seeds):
        raise ValueError("model_seeds must contain 1..20 nonnegative integers")
    entities = request.get("entities")
    if not isinstance(entities, list) or not 1 <= len(entities) <= 64:
        raise ValueError("entities must contain 1..64 biomolecular entities")
    seen_ids: set[str] = set()
    normalized, assets = [], []
    for item in entities:
        if not isinstance(item, dict) or len(item) != 1:
            raise ValueError("each entity must declare exactly one official entity type")
        kind, value = next(iter(item.items()))
        if kind not in {"protein", "rna", "dna", "ligand"} or not isinstance(value, dict):
            raise ValueError("entity type must be protein, rna, dna, or ligand")
        common = {"id", "description"}
        polymer = {"sequence", "modifications"}
        extra = {
            "protein": {"unpairedMsa", "unpairedMsaPath", "pairedMsa", "pairedMsaPath", "templates"},
            "rna": {"unpairedMsa", "unpairedMsaPath"},
            "dna": set(),
            "ligand": {"ccdCodes", "smiles"},
        }[kind]
        allowed_fields = common | (polymer if kind != "ligand" else set()) | extra
        if set(value) - allowed_fields:
            raise ValueError(f"{kind} entity contains unsupported AlphaFold 3 fields")
        entity_id = value.get("id")
        ids = entity_id if isinstance(entity_id, list) else [entity_id]
        if not ids or any(not isinstance(entity, str) or re.fullmatch(r"[A-Z]+", entity) is None for entity in ids):
            raise ValueError("every entity requires one or more uppercase alphabetic chain IDs")
        if seen_ids.intersection(ids):
            raise ValueError("chain IDs must be unique across entities")
        seen_ids.update(ids)
        clean: dict[str, object] = {"id": entity_id}
        if kind in {"protein", "rna", "dna"}:
            alphabet = "ACDEFGHIKLMNPQRSTVWY" if kind == "protein" else "ACGU" if kind == "rna" else "ACGT"
            sequence = clean_sequence(str(value.get("sequence", "")), alphabet)
            clean["sequence"] = sequence
            if value.get("modifications") is not None:
                clean["modifications"] = _validate_modifications(kind, value["modifications"], len(sequence))
            for inline_key, path_key in (("unpairedMsa", "unpairedMsaPath"), ("pairedMsa", "pairedMsaPath")):
                if inline_key not in allowed_fields:
                    continue
                if value.get(inline_key) is not None and value.get(path_key) is not None:
                    raise ValueError(f"{inline_key} and {path_key} are mutually exclusive")
                if value.get(inline_key) is not None:
                    if not isinstance(value[inline_key], str) or len(value[inline_key]) > 100_000_000:
                        raise ValueError(f"{inline_key} must be bounded A3M text")
                    clean[inline_key] = value[inline_key]
                elif value.get(path_key) is not None:
                    staged, record = _stage_asset(value[path_key], request_dir, asset_dir, (".a3m", ".a3m.gz", ".a3m.xz", ".a3m.zst"))
                    clean[path_key] = staged
                    assets.append(record)
            if kind == "protein" and value.get("templates") is not None:
                clean["templates"] = _validate_templates(value["templates"], request_dir, asset_dir, assets)
        else:
            ccd, smiles = value.get("ccdCodes"), value.get("smiles")
            if (ccd is None) == (smiles is None):
                raise ValueError("ligand must declare exactly one of ccdCodes or smiles")
            if ccd is not None:
                if not isinstance(ccd, list) or not ccd or any(not isinstance(code, str) or re.fullmatch(r"[A-Za-z0-9-]{1,20}", code) is None for code in ccd):
                    raise ValueError("ccdCodes must be a nonempty array of CCD identifiers")
                clean["ccdCodes"] = ccd
            else:
                if not isinstance(smiles, str) or not smiles.strip() or len(smiles) > 20_000:
                    raise ValueError("SMILES is invalid or too long")
                clean["smiles"] = smiles.strip()
        if value.get("description"):
            clean["description"] = str(value["description"])[:500]
        normalized.append({kind: clean})
    result: dict[str, object] = {
        "name": name,
        "modelSeeds": seeds,
        "sequences": normalized,
        "dialect": "alphafold3",
        "version": AF3_INPUT_VERSION,
    }
    if request.get("bonded_atom_pairs") is not None:
        bonds = request["bonded_atom_pairs"]
        if not isinstance(bonds, list):
            raise ValueError("bonded_atom_pairs must be an array")
        for bond in bonds:
            if not isinstance(bond, list) or len(bond) != 2:
                raise ValueError("each bond must contain two atom addresses")
            for atom in bond:
                if not isinstance(atom, list) or len(atom) != 3 or atom[0] not in seen_ids or not isinstance(atom[1], int) or atom[1] < 1 or not isinstance(atom[2], str):
                    raise ValueError("bond atom address must be [known_chain_id, residue_id, atom_name]")
        result["bondedAtomPairs"] = bonds
    if request.get("user_ccd") is not None and request.get("user_ccd_path") is not None:
        raise ValueError("user_ccd and user_ccd_path are mutually exclusive")
    if request.get("user_ccd") is not None:
        if not isinstance(request["user_ccd"], str) or "data_" not in request["user_ccd"][:200]:
            raise ValueError("user_ccd must be inline CCD mmCIF")
        result["userCCD"] = request["user_ccd"]
    elif request.get("user_ccd_path") is not None:
        staged, record = _stage_asset(request["user_ccd_path"], request_dir, asset_dir, (".cif", ".mmcif", ".cif.gz", ".cif.xz", ".cif.zst"))
        result["userCCDPath"] = staged
        assets.append(record)
    return result, assets


def prepare_server_submission(prepared: dict) -> tuple[list[dict], list[dict]]:
    """Convert a validated local job to the official Server import dialect.

    The Server dialect is intentionally narrower.  Unsupported local-only
    features are blocked instead of being silently removed.
    """

    unsupported_top_level = {"bondedAtomPairs", "userCCD", "userCCDPath"}.intersection(prepared)
    if unsupported_top_level:
        raise ValueError(
            "AlphaFold Server import does not preserve: "
            + ", ".join(sorted(unsupported_top_level))
        )
    server_sequences: list[dict] = []
    mapping: list[dict] = []
    for index, entity in enumerate(prepared["sequences"], start=1):
        kind, value = next(iter(entity.items()))
        ids = value["id"] if isinstance(value["id"], list) else [value["id"]]
        count = len(ids)
        if kind == "protein":
            forbidden = {"unpairedMsa", "unpairedMsaPath", "pairedMsa", "pairedMsaPath"}.intersection(value)
            if forbidden:
                raise ValueError(
                    "AlphaFold Server package cannot import custom MSA fields: "
                    + ", ".join(sorted(forbidden))
                )
            contents = {
                "sequence": value["sequence"],
                "count": count,
                "useStructureTemplate": not ("templates" in value and value["templates"] == []),
            }
            if "templates" in value and value["templates"]:
                raise ValueError("AlphaFold Server package cannot preserve local inline/path templates")
            if value.get("modifications"):
                contents["modifications"] = [
                    {
                        "ptmType": f"CCD_{item['ptmType'].removeprefix('CCD_')}",
                        "ptmPosition": item["ptmPosition"],
                    }
                    for item in value["modifications"]
                ]
            server_sequences.append({"proteinChain": contents})
        elif kind in {"rna", "dna"}:
            if kind == "rna" and {"unpairedMsa", "unpairedMsaPath"}.intersection(value):
                raise ValueError("AlphaFold Server package cannot preserve a custom RNA MSA")
            contents = {"sequence": value["sequence"], "count": count}
            if value.get("modifications"):
                contents["modifications"] = [
                    {
                        "modificationType": f"CCD_{item['modificationType'].removeprefix('CCD_')}",
                        "basePosition": item["basePosition"],
                    }
                    for item in value["modifications"]
                ]
            server_sequences.append({"rnaSequence" if kind == "rna" else "dnaSequence": contents})
        else:
            if value.get("smiles"):
                raise ValueError("AlphaFold Server JSON import requires a supported CCD ligand or ion, not SMILES")
            codes = value.get("ccdCodes", [])
            if len(codes) != 1:
                raise ValueError("AlphaFold Server JSON import requires one CCD code per ligand entity")
            code = codes[0].removeprefix("CCD_")
            server_sequences.append({"ligand": {"ligand": f"CCD_{code}", "count": count}})
        mapping.append(
            {
                "source_entity_index": index,
                "source_chain_ids": ids,
                "server_sequence_index": len(server_sequences),
                "server_assigns_chain_ids": True,
            }
        )
    job = {
        "name": prepared["name"],
        "modelSeeds": prepared["modelSeeds"],
        "sequences": server_sequences,
        "dialect": "alphafoldserver",
        "version": 1,
    }
    return [job], mapping


def prepare_from_server_job(payload: object, *, job_name: str) -> dict:
    """Recover the closed local request from an official Server v1 job record."""

    jobs = payload if isinstance(payload, list) else [payload]
    matches = [job for job in jobs if isinstance(job, dict) and str(job.get("name", "")).lower() == job_name.lower()]
    if len(matches) != 1:
        raise ValueError(f"expected one AlphaFold Server job named {job_name}; found {len(matches)}")
    job = matches[0]
    if job.get("dialect") != "alphafoldserver" or job.get("version") != 1:
        raise ValueError("server-result import requires the official AlphaFold Server v1 dialect")
    next_chain = ord("A")
    entities = []
    for item in job.get("sequences", []):
        if not isinstance(item, dict) or len(item) != 1:
            raise ValueError("AlphaFold Server sequence entry is invalid")
        kind, value = next(iter(item.items()))
        if not isinstance(value, dict):
            raise ValueError("AlphaFold Server sequence value is invalid")
        count = int(value.get("count", 1))
        ids = [chr(next_chain + index) for index in range(count)]
        next_chain += count
        entity_id: str | list[str] = ids[0] if count == 1 else ids
        if kind == "proteinChain":
            clean = {"id": entity_id, "sequence": value.get("sequence", "")}
            if value.get("modifications"):
                clean["modifications"] = value["modifications"]
            entities.append({"protein": clean})
        elif kind in {"rnaSequence", "dnaSequence"}:
            clean = {"id": entity_id, "sequence": value.get("sequence", "")}
            if value.get("modifications"):
                clean["modifications"] = value["modifications"]
            entities.append({"rna" if kind == "rnaSequence" else "dna": clean})
        elif kind == "ligand":
            code = str(value.get("ligand", "")).removeprefix("CCD_")
            entities.append({"ligand": {"id": entity_id, "ccdCodes": [code]}})
        else:
            raise ValueError(f"unsupported AlphaFold Server entity type: {kind}")
    seeds = [int(seed) for seed in job.get("modelSeeds", [1])]
    return {"name": job["name"], "model_seeds": seeds, "entities": entities}


def write_server_package(
    prepared: dict,
    output: Path,
    *,
    access_state: str,
    terms_reviewed: bool,
) -> dict:
    server_jobs, mapping = prepare_server_submission(prepared)
    submission_path = output / "alphafold_server_submission.json"
    mapping_path = output / "alphafold_server_chain_mapping.tsv"
    instructions_path = output / "ALPHAFOLD_SERVER_SUBMISSION.md"
    write_json(submission_path, server_jobs)
    with mapping_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mapping[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(mapping)
    ready = access_state == "ready" and terms_reviewed
    blocker = None
    if access_state != "ready":
        blocker = f"AlphaFold Server interactive access state is {access_state}."
    elif not terms_reviewed:
        blocker = "Current AlphaFold Server terms have not been confirmed for this submission."
    instructions_path.write_text(
        "# AlphaFold Server submission package\n\n"
        "1. Open https://alphafoldserver.com/ and sign in with Google in the browser.\n"
        "2. Review the current service, output-terms, privacy, and non-commercial-use notices.\n"
        "3. Use Upload JSON to import `alphafold_server_submission.json`.\n"
        "4. Review every molecular entity, copy count, modification, seed, and template setting.\n"
        "5. Submit manually. This workbench does not automate an undocumented server API.\n"
        "6. Download the complete result archive and retain its terms notice, request JSON, "
        "models, confidence JSON, ranking table, MSA, and template files.\n\n"
        "Server outputs must not be passed to automated ligand/peptide binding or interaction "
        "prediction systems. They remain theoretical predictions and are not clinical evidence.\n"
        + (f"\nCurrent blocker: {blocker}\n" if blocker else ""),
        encoding="utf-8",
    )
    return {
        "submission_ready": ready,
        "access_state": access_state,
        "terms_reviewed": terms_reviewed,
        "manual_submission_required": True,
        "undocumented_api_used": False,
        "blocker": blocker,
        "artifacts": [
            {"path": submission_path.name, "sha256": digest(submission_path)},
            {"path": mapping_path.name, "sha256": digest(mapping_path)},
            {"path": instructions_path.name, "sha256": digest(instructions_path)},
        ],
    }


def _memory_bytes() -> int | None:
    try:
        if platform.system() == "Linux":
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages * page_size)
        completed = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=False, timeout=5)
        return int(completed.stdout.strip()) if completed.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _available_memory_bytes() -> int | None:
    try:
        if platform.system() == "Linux":
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        if platform.system() == "Darwin":
            page_size = int(subprocess.run(["sysctl", "-n", "hw.pagesize"], capture_output=True, text=True, check=True, timeout=5).stdout)
            result = subprocess.run(["vm_stat"], capture_output=True, text=True, check=True, timeout=5).stdout
            pages = {}
            for line in result.splitlines():
                match = re.match(r"([^:]+):\s+([0-9]+)\.", line)
                if match:
                    pages[match.group(1)] = int(match.group(2))
            return page_size * sum(
                pages.get(name, 0)
                for name in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable")
            )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def _nvidia_gpus() -> list[dict]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return []
    query = "name,memory.total,memory.free,compute_cap,driver_version"
    completed = subprocess.run([executable, f"--query-gpu={query}", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False, timeout=15)
    if completed.returncode:
        return []
    records = []
    for line in completed.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) == 5:
            try:
                records.append({"name": fields[0], "memory_mib": int(fields[1]), "memory_free_mib": int(fields[2]), "compute_capability": float(fields[3]), "driver_version": fields[4]})
            except ValueError:
                continue
    return records


def probe_host(
    path: Path,
    *,
    minimum_ram_gb: int = 64,
    minimum_gpu_memory_gb: int = 40,
    minimum_disk_gb: int = 750,
    minimum_cpu_threads: int = 8,
) -> dict:
    memory = _memory_bytes()
    available_memory = _available_memory_bytes()
    gpus = _nvidia_gpus()
    disk = shutil.disk_usage(path)
    cpu_threads = os.cpu_count() or 0
    try:
        load_one = float(os.getloadavg()[0])
    except (AttributeError, OSError):
        load_one = 0.0
    estimated_idle_threads = max(0.0, cpu_threads - load_one)
    reserve_factor = 2
    checks = {
        "linux": platform.system() == "Linux",
        "x86_64": platform.machine().lower() in {"x86_64", "amd64"},
        "half_available_ram_preserved": available_memory is not None and available_memory >= reserve_factor * minimum_ram_gb * 1024**3,
        "half_available_disk_preserved": disk.free >= reserve_factor * minimum_disk_gb * 1024**3,
        "half_available_cpu_preserved": estimated_idle_threads >= reserve_factor * minimum_cpu_threads,
        "nvidia_compute_capability_at_least_8": any(gpu["compute_capability"] >= 8.0 for gpu in gpus),
        "half_available_gpu_memory_preserved": any(gpu["memory_free_mib"] >= reserve_factor * minimum_gpu_memory_gb * 1024 for gpu in gpus),
    }
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "cpu_threads": cpu_threads,
        "one_minute_load": load_one,
        "estimated_idle_cpu_threads": estimated_idle_threads,
        "memory_bytes": memory,
        "available_memory_bytes": available_memory,
        "disk_free_bytes": disk.free,
        "nvidia_gpus": gpus,
        "thresholds": {
            "reserve_fraction": 0.5,
            "minimum_ram_gb_for_af3": minimum_ram_gb,
            "minimum_gpu_memory_gb_for_af3": minimum_gpu_memory_gb,
            "minimum_disk_gb_for_full_deployment": minimum_disk_gb,
            "minimum_cpu_threads_for_af3": minimum_cpu_threads,
        },
        "checks": checks,
        "recommended_local_inference_ready": all(checks.values()),
        "local_deployment_requires_explicit_user_permission": True,
        "official_note": "Official AlphaFold 3 supports Linux and NVIDIA GPUs; A100/H100 80 GB are the numerically verified reference GPUs. The workbench additionally reserves at least half of currently available resources.",
    }


def validate_resources(model_dir: Path | None, db_dir: Path | None, *, run_inference: bool, run_data_pipeline: bool) -> dict:
    report: dict[str, object] = {"model": None, "databases": None}
    if run_inference:
        if model_dir is None or not model_dir.is_dir():
            raise ValueError("inference requires an approved AlphaFold 3 model directory")
        model_files = sorted(path for path in model_dir.iterdir() if path.is_file() and re.search(r"\.bin(?:\.zst)?(?:\.\d+)?$", path.name))
        if not model_files:
            raise ValueError("model directory contains no AlphaFold 3 .bin or .bin.zst parameter file")
        report["model"] = [{"name": path.name, "bytes": path.stat().st_size} for path in model_files]
    if run_data_pipeline:
        if db_dir is None or not db_dir.is_dir():
            raise ValueError("data pipeline requires the official AlphaFold 3 database directory")
        missing = [name for name in OFFICIAL_DB_FILES if not (db_dir / name).is_file()]
        mmcif_dir = db_dir / "mmcif_files"
        if missing or not mmcif_dir.is_dir():
            raise ValueError(f"database directory is incomplete; missing: {missing + ([] if mmcif_dir.is_dir() else ['mmcif_files/'])}")
        report["databases"] = {
            "release": OFFICIAL_DB_RELEASE,
            "files": [{"name": name, "bytes": (db_dir / name).stat().st_size} for name in OFFICIAL_DB_FILES],
            "mmcif_file_count": sum(1 for path in mmcif_dir.rglob("*") if path.is_file()),
        }
    return report


def _read_bytes(path: Path) -> bytes:
    if path.suffix != ".zst":
        return path.read_bytes()
    try:
        import zstandard
    except ImportError as exc:
        raise RuntimeError("zstandard is required to read compressed AlphaFold 3 outputs") from exc
    with path.open("rb") as handle:
        return zstandard.ZstdDecompressor().stream_reader(handle).read()


def _read_json(path: Path) -> dict:
    value = json.loads(_read_bytes(path).decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"AlphaFold 3 JSON must contain an object: {path.name}")
    return value


def _one(directory: Path, pattern: str, label: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(f"AlphaFold 3 output must contain one {label}; found {len(matches)}")
    return matches[0]


def _one_confidence(directory: Path, label: str) -> Path:
    matches = [
        path
        for path in sorted(directory.glob("*_confidences.json*"))
        if "_summary_confidences." not in path.name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"AlphaFold 3 output must contain one {label}; found {len(matches)}")
    return matches[0]


def locate_job_output(output_root: Path) -> Path:
    direct = sorted(output_root.glob("*_ranking_scores.csv"))
    if len(direct) == 1:
        return output_root
    candidates = sorted({path.parent for path in output_root.rglob("*_ranking_scores.csv")})
    if len(candidates) != 1:
        raise RuntimeError(f"expected one AlphaFold 3 job output, found {len(candidates)}")
    return candidates[0]


def _validate_summary(summary: dict, label: str) -> None:
    required = {"ranking_score", "ptm", "iptm", "fraction_disordered", "has_clash"}
    if not required <= set(summary):
        raise RuntimeError(f"{label} lacks documented summary-confidence fields")
    for field in ("ranking_score", "ptm", "iptm", "fraction_disordered"):
        value = summary[field]
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise RuntimeError(f"{label} field {field} is non-finite")
    if not isinstance(summary["has_clash"], bool):
        raise RuntimeError(f"{label} has_clash must be boolean")


def _matrix(value: object, name: str) -> list[list[float]]:
    if not isinstance(value, list) or not value or any(not isinstance(row, list) for row in value):
        raise RuntimeError(f"{name} must be a nonempty matrix")
    size = len(value)
    if any(len(row) != size for row in value):
        raise RuntimeError(f"{name} must be square")
    matrix = []
    for row in value:
        clean = []
        for item in row:
            if not isinstance(item, (int, float)) or not math.isfinite(float(item)):
                raise RuntimeError(f"{name} contains non-finite values")
            clean.append(float(item))
        matrix.append(clean)
    return matrix


def parse_outputs(output_root: Path, report_dir: Path) -> dict:
    job_dir = locate_job_output(output_root.resolve())
    ranking_file = _one(job_dir, "*_ranking_scores.csv", "top-level ranking table")
    summary_file = _one(job_dir, "*_summary_confidences.json*", "top-level summary-confidence JSON")
    confidence_file = _one_confidence(job_dir, "top-level confidence JSON")
    model_file = _one(job_dir, "*_model.cif*", "top-level mmCIF model")
    terms_file = _one(job_dir, "TERMS_OF_USE.md", "output terms file")
    rows = list(csv.DictReader(ranking_file.open(encoding="utf-8")))
    if not rows or not {"seed", "sample", "ranking_score"} <= set(rows[0]):
        raise RuntimeError("AlphaFold 3 ranking table is empty or lacks seed, sample, and ranking_score")
    sample_records = []
    for sample_dir in sorted(path for path in job_dir.iterdir() if path.is_dir() and re.fullmatch(r"seed-\d+_sample-\d+", path.name)):
        match = re.fullmatch(r"seed-(\d+)_sample-(\d+)", sample_dir.name)
        sample_summary_path = _one(sample_dir, "*_summary_confidences.json*", f"summary JSON in {sample_dir.name}")
        sample_model_path = _one(sample_dir, "*_model.cif*", f"mmCIF model in {sample_dir.name}")
        sample_confidence_path = _one_confidence(sample_dir, f"confidence JSON in {sample_dir.name}")
        sample_summary = _read_json(sample_summary_path)
        _validate_summary(sample_summary, sample_dir.name)
        sample_records.append({
            "seed": int(match.group(1)),
            "sample": int(match.group(2)),
            **{key: sample_summary[key] for key in ("ranking_score", "ptm", "iptm", "fraction_disordered", "has_clash")},
            "summary_path": sample_summary_path.relative_to(job_dir).as_posix(),
            "confidence_path": sample_confidence_path.relative_to(job_dir).as_posix(),
            "model_path": sample_model_path.relative_to(job_dir).as_posix(),
            "model_sha256": digest(sample_model_path),
        })
    if len(sample_records) != len(rows):
        raise RuntimeError("ranking rows do not reconcile with seed/sample output directories")
    ranking_pairs = {(int(row["seed"]), int(row["sample"])) for row in rows}
    if ranking_pairs != {(row["seed"], row["sample"]) for row in sample_records}:
        raise RuntimeError("ranking seed/sample identities do not match output directories")
    summary, confidence = _read_json(summary_file), _read_json(confidence_file)
    _validate_summary(summary, "top-ranked prediction")
    pae = _matrix(confidence.get("pae"), "PAE")
    token_chain_ids = confidence.get("token_chain_ids")
    if not isinstance(token_chain_ids, list) or len(token_chain_ids) != len(pae) or any(not isinstance(value, str) for value in token_chain_ids):
        raise RuntimeError("token_chain_ids do not reconcile with PAE dimensions")
    atom_plddts, atom_chain_ids = confidence.get("atom_plddts"), confidence.get("atom_chain_ids")
    if not isinstance(atom_plddts, list) or not isinstance(atom_chain_ids, list) or len(atom_plddts) != len(atom_chain_ids) or not atom_plddts:
        raise RuntimeError("atom pLDDT values and chain IDs do not reconcile")
    if any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in atom_plddts):
        raise RuntimeError("atom pLDDT contains non-finite values")
    chain_ids = list(dict.fromkeys(token_chain_ids))
    chain_pair_iptm = _matrix(summary.get("chain_pair_iptm"), "chain_pair_iptm")
    chain_pair_pae_min = _matrix(summary.get("chain_pair_pae_min"), "chain_pair_pae_min")
    chain_ptm, chain_iptm = summary.get("chain_ptm"), summary.get("chain_iptm")
    if not all(isinstance(values, list) and len(values) == len(chain_ids) for values in (chain_ptm, chain_iptm)):
        raise RuntimeError("chain confidence arrays do not reconcile with chain IDs")
    if len(chain_pair_iptm) != len(chain_ids) or len(chain_pair_pae_min) != len(chain_ids):
        raise RuntimeError("chain-pair matrices do not reconcile with chain IDs")
    report_dir.mkdir(parents=True, exist_ok=True)
    ranking_tsv = report_dir / "ranking_scores.tsv"
    with ranking_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    sample_tsv = report_dir / "sample_confidence.tsv"
    with sample_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(sample_records[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(sample_records)
    by_chain: dict[str, list[float]] = defaultdict(list)
    for chain, value in zip(atom_chain_ids, atom_plddts, strict=True):
        by_chain[str(chain)].append(float(value))
    chain_records = []
    for index, chain in enumerate(chain_ids):
        values = by_chain.get(chain, [])
        chain_records.append({
            "chain_id": chain,
            "chain_ptm": float(chain_ptm[index]),
            "chain_iptm": float(chain_iptm[index]),
            "mean_atom_plddt": sum(values) / len(values) if values else float("nan"),
            "atom_count": len(values),
        })
    chain_tsv = report_dir / "chain_confidence.tsv"
    with chain_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(chain_records[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(chain_records)
    pair_records = []
    for row_index, source in enumerate(chain_ids):
        for column_index, target in enumerate(chain_ids):
            pair_records.append({"source_chain": source, "target_chain": target, "chain_pair_iptm": chain_pair_iptm[row_index][column_index], "chain_pair_pae_min": chain_pair_pae_min[row_index][column_index]})
    pair_tsv = report_dir / "chain_pair_confidence.tsv"
    with pair_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pair_records[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(pair_records)
    import numpy as np

    pae_npz = report_dir / "pae_matrix.npz"
    np.savez_compressed(pae_npz, pae=np.asarray(pae, dtype=np.float32), token_chain_ids=np.asarray(token_chain_ids, dtype=str))
    return {
        "job_directory": job_dir.as_posix(),
        "ranking_rows": len(rows),
        "sample_count": len(sample_records),
        "model_count": len(sample_records),
        "chain_ids": chain_ids,
        "summary_confidences": summary,
        "top_model": {"path": model_file.as_posix(), "sha256": digest(model_file), "compressed": model_file.suffix == ".zst"},
        "top_confidence": {"path": confidence_file.as_posix(), "sha256": digest(confidence_file)},
        "terms": {"path": terms_file.as_posix(), "sha256": digest(terms_file)},
        "source_artifacts": [{"path": path.as_posix(), "sha256": digest(path)} for path in (ranking_file, summary_file, confidence_file)],
        "tables": [{"path": path.name, "sha256": digest(path)} for path in (ranking_tsv, sample_tsv, chain_tsv, pair_tsv, pae_npz)],
        "plot_data": {
            "ranking_rows": rows,
            "sample_records": sample_records,
            "chain_records": chain_records,
            "chain_pair_iptm": chain_pair_iptm,
            "chain_pair_pae_min": chain_pair_pae_min,
            "pae": pae,
            "token_chain_ids": token_chain_ids,
            "atom_plddts_by_chain": dict(by_chain),
        },
    }


def _save_figure(fig, stem: Path) -> list[Path]:
    outputs = []
    for suffix in ("pdf", "svg", "png"):
        target = stem.with_suffix(f".{suffix}")
        fig.savefig(target, dpi=600 if suffix == "png" else None, bbox_inches="tight", facecolor="white")
        outputs.append(target)
    return outputs


def render_confidence(report: dict, report_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    data = report["plot_data"]
    summary = report["summary_confidences"]
    samples = sorted(data["sample_records"], key=lambda row: float(row["ranking_score"]), reverse=True)
    chains = data["chain_records"]
    colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
    with plt.rc_context({"font.size": 7, "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6}):
        fig, axes = plt.subplots(2, 3, figsize=(7.2, 5.0), constrained_layout=True)
        ax = axes[0, 0]
        labels = [f"{row['seed']}:{row['sample']}" for row in samples]
        bars = ax.bar(range(len(samples)), [float(row["ranking_score"]) for row in samples], color=["#B2182B" if row["has_clash"] else "#2166AC" for row in samples], width=0.72)
        ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right", fontsize=5)
        ax.set_ylabel("Ranking score")
        ax.set_title("A  Model inventory", loc="left", fontweight="bold")
        if bars:
            ax.legend(handles=[plt.Line2D([0], [0], color="#2166AC", lw=5, label="no clash"), plt.Line2D([0], [0], color="#B2182B", lw=5, label="clash")], frameon=False, fontsize=5, loc="best")
        ax = axes[0, 1]
        metric_labels = ["pTM", "ipTM", "ranking", "ordered"]
        metric_values = [float(summary["ptm"]), float(summary["iptm"]), float(summary["ranking_score"]), 1 - float(summary["fraction_disordered"])]
        ax.bar(metric_labels, metric_values, color=colors[:4], width=0.65)
        ax.axhline(0.8, color="#777777", lw=0.6, ls="--")
        ax.set_ylim(0, max(1.05, max(metric_values) * 1.08))
        ax.tick_params(axis="x", rotation=25, labelsize=5)
        ax.set_title("B  Top-model confidence", loc="left", fontweight="bold")
        ax = axes[0, 2]
        pae = np.asarray(data["pae"], dtype=float)
        image = ax.imshow(pae, cmap="magma_r", vmin=0, vmax=max(30, float(np.nanpercentile(pae, 99))), interpolation="nearest")
        boundaries = [index for index in range(1, len(data["token_chain_ids"])) if data["token_chain_ids"][index] != data["token_chain_ids"][index - 1]]
        for boundary in boundaries:
            ax.axhline(boundary - 0.5, color="white", lw=0.45)
            ax.axvline(boundary - 0.5, color="white", lw=0.45)
        ax.set_xlabel("Aligned token")
        ax.set_ylabel("Scored token")
        ax.set_title("C  Predicted aligned error", loc="left", fontweight="bold")
        fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03, label="PAE (Å)")
        ax = axes[1, 0]
        matrix = np.asarray(data["chain_pair_iptm"], dtype=float)
        image = ax.imshow(matrix, cmap="viridis", vmin=0, vmax=1)
        ax.set_xticks(range(len(report["chain_ids"])), report["chain_ids"])
        ax.set_yticks(range(len(report["chain_ids"])), report["chain_ids"])
        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                ax.text(column, row, f"{matrix[row, column]:.2f}", ha="center", va="center", fontsize=5, color="white" if matrix[row, column] < 0.55 else "black")
        ax.set_title("D  Chain-pair ipTM", loc="left", fontweight="bold")
        fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03)
        ax = axes[1, 1]
        x = np.arange(len(chains))
        ax.bar(x - 0.18, [row["chain_ptm"] for row in chains], width=0.36, color="#0072B2", label="chain pTM")
        ax.bar(x + 0.18, [row["chain_iptm"] for row in chains], width=0.36, color="#D55E00", label="chain ipTM")
        ax.set_xticks(x, [row["chain_id"] for row in chains])
        ax.set_ylim(0, 1.05)
        ax.legend(frameon=False, fontsize=5)
        ax.set_title("E  Per-chain confidence", loc="left", fontweight="bold")
        ax = axes[1, 2]
        distributions = [data["atom_plddts_by_chain"].get(row["chain_id"], []) for row in chains]
        if all(distributions):
            parts = ax.violinplot(distributions, showmeans=True, showextrema=False)
            for body, color in zip(parts["bodies"], colors, strict=False):
                body.set_facecolor(color)
                body.set_alpha(0.75)
            ax.set_xticks(range(1, len(chains) + 1), [row["chain_id"] for row in chains])
        ax.axhline(70, color="#777777", lw=0.6, ls="--")
        ax.set_ylim(0, 100)
        ax.set_ylabel("Atom pLDDT")
        ax.set_title("F  pLDDT by chain", loc="left", fontweight="bold")
        for axis in axes.ravel():
            axis.spines[["top", "right"]].set_visible(False)
        outputs = _save_figure(fig, report_dir / "alphafold3_confidence_overview")
        plt.close(fig)
    return outputs


def render_structure(report: dict, report_dir: Path) -> tuple[list[Path], Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from Bio.PDB import MMCIFParser

    model_path = Path(report["top_model"]["path"])
    parser = MMCIFParser(QUIET=True)
    structure = parser.get_structure("alphafold3", io.StringIO(_read_bytes(model_path).decode("utf-8")))
    chain_atoms: dict[str, list[tuple[str, str, int, float, float, float]]] = defaultdict(list)
    for atom in structure.get_atoms():
        residue = atom.get_parent()
        chain = residue.get_parent()
        coordinate = atom.get_coord()
        chain_atoms[str(chain.id)].append((str(atom.name), str(residue.resname), int(residue.id[1]), float(coordinate[0]), float(coordinate[1]), float(coordinate[2])))
    if not chain_atoms:
        raise RuntimeError("top AlphaFold 3 mmCIF contains no atoms")
    coordinate_table = report_dir / "structure_coordinates.tsv"
    with coordinate_table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["chain_id", "atom_name", "residue_name", "residue_number", "x", "y", "z"])
        for chain, atoms in chain_atoms.items():
            for atom in atoms:
                writer.writerow([chain, *atom])
    colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
    all_coordinates = np.asarray([[atom[3], atom[4], atom[5]] for atoms in chain_atoms.values() for atom in atoms])
    center = all_coordinates.mean(axis=0)
    radius = max(float(np.ptp(all_coordinates, axis=0).max()) / 2, 1.0)
    with plt.rc_context({"font.size": 7}):
        fig = plt.figure(figsize=(7.2, 3.4), constrained_layout=True)
        for panel, (azimuth, elevation) in enumerate(((35, 18), (125, 18))):
            ax = fig.add_subplot(1, 2, panel + 1, projection="3d")
            for index, (chain, atoms) in enumerate(sorted(chain_atoms.items())):
                trace = [atom for atom in atoms if atom[0] in {"CA", "P"}]
                if len(trace) < 2:
                    trace = atoms
                xyz = np.asarray([[atom[3], atom[4], atom[5]] for atom in trace])
                ax.plot(xyz[:, 0], xyz[:, 1], xyz[:, 2], lw=1.2, color=colors[index % len(colors)], label=f"Chain {chain}")
                ax.scatter(xyz[:, 0], xyz[:, 1], xyz[:, 2], s=2.5, color=colors[index % len(colors)], alpha=0.75)
            ax.set_xlim(center[0] - radius, center[0] + radius)
            ax.set_ylim(center[1] - radius, center[1] + radius)
            ax.set_zlim(center[2] - radius, center[2] + radius)
            ax.view_init(elev=elevation, azim=azimuth)
            ax.set_axis_off()
            ax.set_title(f"{'A' if panel == 0 else 'B'}  Complex view {panel + 1}", loc="left", fontweight="bold")
            if panel == 0:
                ax.legend(frameon=False, fontsize=6, loc="upper right")
        outputs = _save_figure(fig, report_dir / "alphafold3_structure_overview")
        plt.close(fig)
    return outputs, coordinate_table


def _downstream_handoff(report: dict, report_dir: Path, *, result_origin: str) -> Path:
    target = report_dir / "downstream_structure_handoff.json"
    eligible = ["structure-quality-assessment", "structure-chain-comparison", "structure-interactive-visualization"]
    if result_origin != "alphafold-server":
        eligible.append("protein-complex-docking")
    write_json(target, {
        "schema_version": 1,
        "source_module": "alphafold3-complex-prediction",
        "top_model": report["top_model"],
        "chain_ids": report["chain_ids"],
        "result_origin": result_origin,
        "eligible_next_modules": eligible,
        "automated_docking_allowed": result_origin != "alphafold-server",
        "required_review": (["AlphaFold Server outputs and derivatives must not be used with automated ligand or peptide binding/interaction prediction systems."] if result_origin == "alphafold-server" else ["Confirm chain identity and biological assembly before docking."]) + ["Convert and split mmCIF only with residue, ligand, bond, and chain accounting; do not silently drop unsupported records."],
    })
    return target


def render_confidence_with_r(report_dir: Path, *, job_label: str, chain_a_label: str, chain_b_label: str) -> list[Path]:
    rscript = shutil.which("Rscript")
    if not rscript:
        raise RuntimeError("Rscript is required for the selected AlphaFold 3 figure backend")
    completed = subprocess.run(
        [rscript, str(R_FIGURE_TEMPLATE), str(report_dir), job_label, chain_a_label, chain_b_label],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if completed.returncode:
        raise RuntimeError(f"AlphaFold 3 R figure renderer failed: {completed.stderr.strip()}")
    expected = [
        report_dir / f"{stem}.{suffix}"
        for stem in ("alphafold3_confidence_overview", "alphafold3_structure_overview")
        for suffix in ("pdf", "svg", "png")
    ]
    missing = [path.name for path in expected if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError(f"AlphaFold 3 R figure renderer omitted outputs: {missing}")
    return expected


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend", choices=("server-package", "prepare", "parse-existing", "parse-server-archive", "local-native", "local-container", "local-portable-container"), default="server-package")
    parser.add_argument("--parse-output", type=Path)
    parser.add_argument("--server-job-name")
    parser.add_argument("--result-origin", choices=("alphafold-server", "local-official", "external-official"))
    parser.add_argument("--render-backend", choices=("python", "r"), default="python")
    parser.add_argument("--job-label")
    parser.add_argument("--chain-a-label", default="Chain A")
    parser.add_argument("--chain-b-label", default="Chain B")
    parser.add_argument("--server-access-state", choices=("not-configured", "ready", "authentication-error", "session-expired", "access-denied", "quota-exhausted", "terms-not-accepted"), default="not-configured")
    parser.add_argument("--server-terms-reviewed", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--terms-accepted", action="store_true")
    parser.add_argument("--local-deployment-approved", action="store_true")
    parser.add_argument("--local-executable")
    parser.add_argument("--container-runtime-executable")
    parser.add_argument("--portable-runtime-executable")
    parser.add_argument("--container-image", default=f"alphafold3:{AF3_RELEASE}")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--db-dir", type=Path)
    parser.add_argument("--run-data-pipeline", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--run-inference", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--num-recycles", type=int, default=10)
    parser.add_argument("--num-diffusion-samples", type=int, default=5)
    parser.add_argument("--num-seeds", type=int)
    parser.add_argument("--save-distogram", action="store_true")
    parser.add_argument("--save-embeddings", action="store_true")
    parser.add_argument("--compress-large-output-files", action="store_true")
    parser.add_argument("--jax-compilation-cache-dir")
    parser.add_argument("--runtime-timeout-seconds", type=int, default=172800)
    parser.add_argument("--minimum-ram-gb", type=int, default=64)
    parser.add_argument("--minimum-gpu-memory-gb", type=int, default=40)
    parser.add_argument("--minimum-disk-gb", type=int, default=750)
    parser.add_argument("--minimum-cpu-threads", type=int, default=8)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not 1 <= args.num_recycles <= 100 or not 1 <= args.num_diffusion_samples <= 100:
        raise ValueError("num-recycles and num-diffusion-samples must be 1..100")
    if args.num_seeds is not None and not 1 <= args.num_seeds <= 100:
        raise ValueError("num-seeds must be 1..100")
    output = args.output.resolve()
    input_dir = output / "runtime_input"
    prediction_dir = output / "prediction"
    input_dir.mkdir(parents=True, exist_ok=True)
    prediction_dir.mkdir(parents=True, exist_ok=True)
    request_path = args.request.resolve()
    raw_request = json.loads(request_path.read_text(encoding="utf-8"))
    if args.backend == "parse-server-archive":
        if not args.server_job_name:
            raise ValueError("parse-server-archive requires --server-job-name")
        raw_request = prepare_from_server_job(raw_request, job_name=args.server_job_name)
    request, assets = prepare(raw_request, request_dir=request_path.parent, asset_dir=input_dir / "assets")
    input_path = input_dir / "alphafold3_input.json"
    write_json(input_path, request)
    host = probe_host(
        output,
        minimum_ram_gb=args.minimum_ram_gb,
        minimum_gpu_memory_gb=args.minimum_gpu_memory_gb,
        minimum_disk_gb=args.minimum_disk_gb,
        minimum_cpu_threads=args.minimum_cpu_threads,
    )
    manifest: dict[str, object] = {
        "schema_version": 2,
        "module": {"id": "alphafold3-complex-prediction", "version": "1.2.0"},
        "alphafold3_release": AF3_RELEASE,
        "official_sources": OFFICIAL_SOURCES,
        "input": {"path": input_path.relative_to(output).as_posix(), "sha256": digest(input_path), "assets": assets},
        "backend": args.backend,
        "host_preflight": host,
        "parameters": {
            "run_data_pipeline": args.run_data_pipeline,
            "run_inference": args.run_inference,
            "num_recycles": args.num_recycles,
            "num_diffusion_samples": args.num_diffusion_samples,
            "num_seeds": args.num_seeds,
            "save_distogram": args.save_distogram,
            "save_embeddings": args.save_embeddings,
            "compress_large_output_files": args.compress_large_output_files,
        },
        "execution": {"state": "prepared", "inference_performed": False, "data_pipeline_performed": False},
        "scientific_boundaries": [
            "AlphaFold 3 confidence is not experimental evidence of interaction, affinity, kinetics, function, mechanism, or clinical validity.",
            "A docking follow-up requires independently reviewed chain identity, restraints, coordinate preparation, and sampling.",
        ],
    }
    if args.backend == "server-package":
        manifest["server_submission"] = write_server_package(
            request,
            output,
            access_state=args.server_access_state,
            terms_reviewed=args.server_terms_reviewed,
        )
        manifest["execution"]["state"] = "ready-for-manual-submission" if manifest["server_submission"]["submission_ready"] else "awaiting-interactive-access"
    execution_backend = args.backend in {"local-native", "local-container", "local-portable-container"}
    if execution_backend:
        if not args.terms_accepted:
            raise ValueError("execution requires explicit acknowledgement of the current AlphaFold 3 model-parameter terms")
        manifest["resources"] = validate_resources(args.model_dir, args.db_dir, run_inference=args.run_inference, run_data_pipeline=args.run_data_pipeline)
        if not args.preflight_only and not host["recommended_local_inference_ready"]:
            raise RuntimeError("local execution host does not meet the configured Linux, NVIDIA, CPU, RAM, disk, and GPU-memory gate")
        if not args.preflight_only and not args.local_deployment_approved:
            raise RuntimeError("local execution requires explicit user permission via --local-deployment-approved")
        if not args.preflight_only:
            local_report = execute_alphafold3_local(
                {
                    "backend": args.backend,
                    "input_path": str(input_path),
                    "output_directory": str(prediction_dir),
                    "model_directory": str(args.model_dir.resolve()) if args.model_dir else None,
                    "database_directory": str(args.db_dir.resolve()) if args.db_dir else None,
                    "container_image": args.container_image,
                    "local_executable": args.local_executable,
                    "container_runtime_executable": args.container_runtime_executable,
                    "portable_runtime_executable": args.portable_runtime_executable,
                    "run_data_pipeline": args.run_data_pipeline,
                    "run_inference": args.run_inference,
                    "num_recycles": args.num_recycles,
                    "num_diffusion_samples": args.num_diffusion_samples,
                    "num_seeds": args.num_seeds,
                    "save_distogram": args.save_distogram,
                    "save_embeddings": args.save_embeddings,
                    "compress_large_output_files": args.compress_large_output_files,
                    "jax_compilation_cache_dir": args.jax_compilation_cache_dir,
                    "timeout_seconds": args.runtime_timeout_seconds,
                }
            )
            manifest["execution"].update(local_report)
    parse_root = args.parse_output.resolve() if args.parse_output else prediction_dir
    should_parse = args.parse_output is not None or args.backend == "parse-existing" or (manifest["execution"]["state"] == "completed")
    if args.backend in {"parse-existing", "parse-server-archive"} and args.parse_output is None:
        raise ValueError(f"{args.backend} requires --parse-output")
    if args.backend == "parse-server-archive" and not args.server_job_name:
        raise ValueError("parse-server-archive requires --server-job-name")
    if should_parse:
        parsed = (
            parse_alphafold_server_archive(parse_root, output, job_name=args.server_job_name)
            if args.backend == "parse-server-archive"
            else parse_outputs(parse_root, output)
        )
        result_origin = args.result_origin or ("alphafold-server" if args.backend in {"server-package", "parse-server-archive"} else "external-official" if args.backend == "parse-existing" else "local-official")
        manifest.update({key: value for key, value in parsed.items() if key != "plot_data"})
        if args.backend == "parse-server-archive":
            if args.render_backend != "r":
                raise ValueError("observed AlphaFold Server archives require --render-backend r in the current publication workflow")
            confidence_figures = render_confidence_with_r(
                output,
                job_label=args.job_label or args.server_job_name,
                chain_a_label=args.chain_a_label,
                chain_b_label=args.chain_b_label,
            )
            structure_figures = []
            coordinate_table = output / "structure_coordinates.tsv"
        else:
            confidence_figures = render_confidence(parsed, output)
            structure_figures, coordinate_table = render_structure(parsed, output)
        handoff = _downstream_handoff(parsed, output, result_origin=result_origin)
        all_figures = [*confidence_figures, *structure_figures]
        manifest["figures"] = [{"path": path.name, "sha256": digest(path)} for path in all_figures]
        manifest["replot_artifacts"] = parsed.get("replot_artifacts", [*parsed["tables"], {"path": coordinate_table.name, "sha256": digest(coordinate_table)}])
        manifest["downstream_handoff"] = {"path": handoff.name, "sha256": digest(handoff)}
        manifest["result_origin"] = result_origin
        manifest["execution"]["state"] = "server-results-imported" if result_origin == "alphafold-server" else "results-imported"
        manifest["execution"]["outputs_reloaded"] = True
        manifest["execution"]["inference_performed"] = bool(execution_backend and args.run_inference and manifest["execution"]["state"] == "completed")
        manifest["execution"]["data_pipeline_performed"] = bool(execution_backend and args.run_data_pipeline and manifest["execution"]["state"] == "completed")
    manifest_path = output / "alphafold3_manifest.json"
    write_json(manifest_path, manifest)
    print(json.dumps({"manifest": str(manifest_path), "input": str(input_path), "state": manifest["execution"]["state"], "outputs_reloaded": bool(manifest["execution"].get("outputs_reloaded"))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
