"""Parse observed AlphaFold Server download archives without expanding MSAs/templates."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import defaultdict
from pathlib import Path


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: bytes, label: str) -> dict | list:
    payload = json.loads(value.decode("utf-8"))
    if not isinstance(payload, (dict, list)):
        raise RuntimeError(f"{label} must contain a JSON object or array")
    return payload


def _matrix(value: object, label: str) -> list[list[float]]:
    if not isinstance(value, list) or not value or any(not isinstance(row, list) for row in value):
        raise RuntimeError(f"{label} must be a nonempty matrix")
    width = len(value[0])
    if width == 0 or any(len(row) != width for row in value):
        raise RuntimeError(f"{label} rows must have equal nonzero length")
    result: list[list[float]] = []
    for row in value:
        clean = []
        for item in row:
            if not isinstance(item, (int, float)) or not math.isfinite(float(item)):
                raise RuntimeError(f"{label} contains a non-finite value")
            clean.append(float(item))
        result.append(clean)
    return result


def _write_tsv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if not rows:
        raise RuntimeError(f"cannot write empty table: {path.name}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _structure_tables(cif_bytes: bytes, output: Path) -> tuple[Path, Path]:
    from Bio.PDB import MMCIFParser

    structure = MMCIFParser(QUIET=True).get_structure("alphafold_server", io.StringIO(cif_bytes.decode("utf-8")))
    atom_rows: list[dict] = []
    residue_plddt: dict[tuple[str, int, str], list[float]] = defaultdict(list)
    for atom in structure.get_atoms():
        residue = atom.get_parent()
        chain = residue.get_parent()
        coordinate = atom.get_coord()
        row = {
            "chain_id": str(chain.id),
            "atom_name": str(atom.name),
            "residue_name": str(residue.resname),
            "residue_number": int(residue.id[1]),
            "x": float(coordinate[0]),
            "y": float(coordinate[1]),
            "z": float(coordinate[2]),
            "plddt": float(atom.bfactor),
        }
        atom_rows.append(row)
        residue_plddt[(row["chain_id"], row["residue_number"], row["residue_name"])].append(row["plddt"])
    if not atom_rows:
        raise RuntimeError("top AlphaFold Server mmCIF contains no atoms")
    coordinate_path = output / "structure_coordinates.tsv"
    _write_tsv(coordinate_path, atom_rows)
    residue_rows = [
        {
            "chain_id": chain,
            "residue_number": residue_number,
            "residue_name": residue_name,
            "mean_plddt": sum(values) / len(values),
            "atom_count": len(values),
        }
        for (chain, residue_number, residue_name), values in sorted(residue_plddt.items())
    ]
    residue_path = output / "residue_confidence.tsv"
    _write_tsv(residue_path, residue_rows)
    return coordinate_path, residue_path


def _binned_matrix_rows(matrix: list[list[float]], chain_ids: list[str], bins: int = 120) -> list[dict]:
    import numpy as np

    values = np.asarray(matrix, dtype=np.float32)
    size = values.shape[0]
    breaks = np.linspace(0, size, min(bins, size) + 1, dtype=int)
    rows = []
    for row_bin in range(len(breaks) - 1):
        row_start, row_end = int(breaks[row_bin]), int(breaks[row_bin + 1])
        for col_bin in range(len(breaks) - 1):
            col_start, col_end = int(breaks[col_bin]), int(breaks[col_bin + 1])
            block = values[row_start:row_end, col_start:col_end]
            rows.append(
                {
                    "row_bin": row_bin + 1,
                    "column_bin": col_bin + 1,
                    "row_start_token": row_start + 1,
                    "row_end_token": row_end,
                    "column_start_token": col_start + 1,
                    "column_end_token": col_end,
                    "row_chain": chain_ids[row_start],
                    "column_chain": chain_ids[col_start],
                    "mean_pae": float(block.mean()),
                    "minimum_pae": float(block.min()),
                }
            )
    return rows


def _cross_chain_profiles(
    pae: list[list[float]],
    contact_probs: list[list[float]],
    chain_ids: list[str],
    residue_ids: list[int],
) -> tuple[list[dict], list[dict]]:
    import numpy as np

    pae_array = np.asarray(pae, dtype=np.float32)
    contact_array = np.asarray(contact_probs, dtype=np.float32)
    if pae_array.shape != contact_array.shape or pae_array.shape[0] != len(chain_ids) or len(residue_ids) != len(chain_ids):
        raise RuntimeError("token identities do not reconcile with PAE/contact matrices")
    profile_rows: list[dict] = []
    pair_candidates: list[dict] = []
    unique_chains = _unique(chain_ids)
    for source_chain in unique_chains:
        source_indices = np.flatnonzero(np.asarray(chain_ids) == source_chain)
        target_indices = np.flatnonzero(np.asarray(chain_ids) != source_chain)
        if target_indices.size == 0:
            continue
        cross_contacts = contact_array[np.ix_(source_indices, target_indices)]
        cross_pae = pae_array[np.ix_(source_indices, target_indices)]
        best_target_positions = cross_contacts.argmax(axis=1)
        for local_index, source_index in enumerate(source_indices):
            target_index = int(target_indices[int(best_target_positions[local_index])])
            profile_rows.append(
                {
                    "chain_id": source_chain,
                    "residue_number": int(residue_ids[int(source_index)]),
                    "maximum_cross_chain_contact_probability": float(cross_contacts[local_index].max()),
                    "minimum_cross_chain_pae": float(cross_pae[local_index].min()),
                    "median_cross_chain_pae": float(np.median(cross_pae[local_index])),
                    "best_partner_chain": chain_ids[target_index],
                    "best_partner_residue": int(residue_ids[target_index]),
                }
            )
    upper = np.triu(np.ones(contact_array.shape, dtype=bool), k=1)
    cross = np.not_equal.outer(np.asarray(chain_ids), np.asarray(chain_ids)) & upper
    candidate_indices = np.argwhere(cross)
    if candidate_indices.size:
        scores = contact_array[cross]
        order = np.argsort(scores)[::-1][:200]
        for rank, candidate_index in enumerate(order, start=1):
            left, right = candidate_indices[int(candidate_index)]
            pair_candidates.append(
                {
                    "rank": rank,
                    "source_chain": chain_ids[int(left)],
                    "source_residue": int(residue_ids[int(left)]),
                    "target_chain": chain_ids[int(right)],
                    "target_residue": int(residue_ids[int(right)]),
                    "contact_probability": float(contact_array[int(left), int(right)]),
                    "pae": float(pae_array[int(left), int(right)]),
                }
            )
    return profile_rows, pair_candidates


def parse_alphafold_server_archive(archive_path: Path, report_dir: Path, *, job_name: str) -> dict:
    """Parse one named job from an immutable official Server download archive."""

    archive_path = archive_path.resolve()
    if not archive_path.is_file() or not zipfile.is_zipfile(archive_path):
        raise RuntimeError("AlphaFold Server result must be a readable ZIP archive")
    report_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        members = set(archive.namelist())
        job_directories = sorted(
            {member.split("/", 1)[0] for member in members if member.endswith("_job_request.json") and "/" in member}
        )
        if job_name not in job_directories:
            raise RuntimeError(f"Server archive does not contain requested job {job_name}; available: {job_directories}")
        prefix = f"{job_name}/fold_{job_name}"
        request_member = f"{prefix}_job_request.json"
        model_members: dict[int, str] = {}
        summary_members: dict[int, str] = {}
        full_members: dict[int, str] = {}
        for member in members:
            match = re.fullmatch(re.escape(prefix) + r"_model_(\d+)\.cif", member)
            if match:
                model_members[int(match.group(1))] = member
            match = re.fullmatch(re.escape(prefix) + r"_summary_confidences_(\d+)\.json", member)
            if match:
                summary_members[int(match.group(1))] = member
            match = re.fullmatch(re.escape(prefix) + r"_full_data_(\d+)\.json", member)
            if match:
                full_members[int(match.group(1))] = member
        indices = sorted(set(model_members) & set(summary_members) & set(full_members))
        if not indices or set(indices) != set(model_members) or set(indices) != set(summary_members) or set(indices) != set(full_members):
            raise RuntimeError("Server model, summary-confidence, and full-data files do not reconcile")
        sample_records: list[dict] = []
        summaries: dict[int, dict] = {}
        for index in indices:
            summary = _json_bytes(archive.read(summary_members[index]), summary_members[index])
            if not isinstance(summary, dict):
                raise RuntimeError("Server summary-confidence JSON must contain an object")
            required = {"ranking_score", "ptm", "iptm", "fraction_disordered", "has_clash", "chain_ptm", "chain_iptm", "chain_pair_iptm", "chain_pair_pae_min"}
            if not required <= set(summary):
                raise RuntimeError(f"Server model {index} lacks documented confidence fields")
            summaries[index] = summary
            summary_chain_ids = _unique([str(value) for value in summary.get("chain_ids", [])])
            summary_pair_iptm = _matrix(summary["chain_pair_iptm"], f"chain_pair_iptm model {index}")
            summary_pair_pae = _matrix(summary["chain_pair_pae_min"], f"chain_pair_pae_min model {index}")
            if len(summary_chain_ids) != len(summary_pair_iptm) or len(summary_chain_ids) != len(summary_pair_pae):
                raise RuntimeError(f"Server model {index} chain-pair matrices do not reconcile with chain identities")
            off_diagonal_iptm = [summary_pair_iptm[row][column] for row in range(len(summary_chain_ids)) for column in range(len(summary_chain_ids)) if row != column]
            off_diagonal_pae = [summary_pair_pae[row][column] for row in range(len(summary_chain_ids)) for column in range(len(summary_chain_ids)) if row != column]
            sample_records.append(
                {
                    "model_index": index,
                    "ranking_score": float(summary["ranking_score"]),
                    "ptm": float(summary["ptm"]),
                    "iptm": float(summary["iptm"]),
                    "fraction_disordered": float(summary["fraction_disordered"]),
                    "has_clash": bool(summary["has_clash"]),
                    "maximum_interchain_pair_iptm": max(off_diagonal_iptm) if off_diagonal_iptm else float("nan"),
                    "minimum_interchain_pae": min(off_diagonal_pae) if off_diagonal_pae else float("nan"),
                    "summary_member": summary_members[index],
                    "full_data_member": full_members[index],
                    "model_member": model_members[index],
                    "model_sha256": _sha256_bytes(archive.read(model_members[index])),
                }
            )
        top_record = sorted(sample_records, key=lambda row: (-row["ranking_score"], row["model_index"]))[0]
        top_index = int(top_record["model_index"])
        summary = summaries[top_index]
        top_summary_bytes = archive.read(summary_members[top_index])
        top_full_bytes = archive.read(full_members[top_index])
        full_data = _json_bytes(top_full_bytes, full_members[top_index])
        if not isinstance(full_data, dict):
            raise RuntimeError("Server full-data JSON must contain an object")
        pae = _matrix(full_data.get("pae"), "pae")
        contact_probs = _matrix(full_data.get("contact_probs"), "contact_probs")
        token_chain_ids = full_data.get("token_chain_ids")
        token_res_ids = full_data.get("token_res_ids")
        atom_chain_ids = full_data.get("atom_chain_ids")
        atom_plddts = full_data.get("atom_plddts")
        if not isinstance(token_chain_ids, list) or any(not isinstance(item, str) for item in token_chain_ids):
            raise RuntimeError("token_chain_ids must be a string array")
        if not isinstance(token_res_ids, list) or any(not isinstance(item, int) for item in token_res_ids):
            raise RuntimeError("token_res_ids must be an integer array")
        if not isinstance(atom_chain_ids, list) or not isinstance(atom_plddts, list) or len(atom_chain_ids) != len(atom_plddts):
            raise RuntimeError("atom chain identities do not reconcile with pLDDT")
        chain_ids = _unique(token_chain_ids)
        chain_ptm = summary["chain_ptm"]
        chain_iptm = summary["chain_iptm"]
        chain_pair_iptm = _matrix(summary["chain_pair_iptm"], "chain_pair_iptm")
        chain_pair_pae_min = _matrix(summary["chain_pair_pae_min"], "chain_pair_pae_min")
        if len(chain_ptm) != len(chain_ids) or len(chain_iptm) != len(chain_ids):
            raise RuntimeError("chain confidence arrays do not reconcile with chain identities")
        by_chain: dict[str, list[float]] = defaultdict(list)
        for chain, value in zip(atom_chain_ids, atom_plddts, strict=True):
            by_chain[str(chain)].append(float(value))
        chain_records = [
            {
                "chain_id": chain,
                "chain_ptm": float(chain_ptm[index]),
                "chain_iptm": float(chain_iptm[index]),
                "mean_atom_plddt": sum(by_chain[chain]) / len(by_chain[chain]),
                "atom_count": len(by_chain[chain]),
            }
            for index, chain in enumerate(chain_ids)
        ]
        pair_records = [
            {
                "source_chain": source,
                "target_chain": target,
                "chain_pair_iptm": chain_pair_iptm[row][column],
                "chain_pair_pae_min": chain_pair_pae_min[row][column],
            }
            for row, source in enumerate(chain_ids)
            for column, target in enumerate(chain_ids)
        ]
        ranking_path = report_dir / "ranking_scores.tsv"
        sample_path = report_dir / "sample_confidence.tsv"
        chain_path = report_dir / "chain_confidence.tsv"
        pair_path = report_dir / "chain_pair_confidence.tsv"
        top_summary_path = report_dir / "top_model_summary.tsv"
        _write_tsv(ranking_path, [{key: row[key] for key in ("model_index", "ranking_score", "ptm", "iptm", "fraction_disordered", "has_clash", "maximum_interchain_pair_iptm", "minimum_interchain_pae")} for row in sample_records])
        _write_tsv(sample_path, sample_records)
        _write_tsv(chain_path, chain_records)
        _write_tsv(pair_path, pair_records)
        _write_tsv(top_summary_path, [{"metric": key, "value": float(summary[key])} for key in ("ranking_score", "ptm", "iptm", "fraction_disordered")])
        binned_path = report_dir / "pae_binned.tsv"
        _write_tsv(binned_path, _binned_matrix_rows(pae, token_chain_ids))
        profile_rows, candidate_rows = _cross_chain_profiles(pae, contact_probs, token_chain_ids, token_res_ids)
        profile_path = report_dir / "cross_chain_residue_profile.tsv"
        candidate_path = report_dir / "top_cross_chain_contacts.tsv"
        _write_tsv(profile_path, profile_rows)
        _write_tsv(candidate_path, candidate_rows)
        top_model_path = report_dir / "top_model.cif"
        top_model_bytes = archive.read(model_members[top_index])
        top_model_path.write_bytes(top_model_bytes)
        coordinate_path, residue_path = _structure_tables(top_model_bytes, report_dir)
        request_path = report_dir / "server_job_request.json"
        request_path.write_bytes(archive.read(request_member))
        terms_candidates = [member for member in ("terms_of_use.md", "TERMS_OF_USE.md") if member in members]
        if len(terms_candidates) != 1:
            raise RuntimeError("Server archive must contain exactly one terms-of-use file")
        terms_path = report_dir / "TERMS_OF_USE.md"
        terms_path.write_bytes(archive.read(terms_candidates[0]))
    table_paths = [ranking_path, sample_path, chain_path, pair_path, top_summary_path, binned_path, profile_path, candidate_path, coordinate_path, residue_path]
    return {
        "job_name": job_name,
        "job_directory": f"{archive_path.as_posix()}::{job_name}",
        "ranking_rows": len(sample_records),
        "sample_count": len(sample_records),
        "model_count": len(sample_records),
        "chain_ids": chain_ids,
        "top_model_index": top_index,
        "summary_confidences": summary,
        "top_model": {"path": top_model_path.as_posix(), "sha256": _sha256_file(top_model_path), "compressed": False},
        "top_confidence": {"archive_member": full_members[top_index], "archive_sha256": _sha256_file(archive_path)},
        "terms": {"path": terms_path.as_posix(), "sha256": _sha256_file(terms_path)},
        "source_artifacts": [
            {"path": archive_path.as_posix(), "sha256": _sha256_file(archive_path)},
            {"archive_member": request_member, "sha256": _sha256_bytes(request_path.read_bytes())},
            {"archive_member": summary_members[top_index], "sha256": _sha256_bytes(top_summary_bytes)},
            {"archive_member": full_members[top_index], "sha256": _sha256_bytes(top_full_bytes)},
        ],
        "tables": [{"path": path.name, "sha256": _sha256_file(path)} for path in table_paths],
        "replot_artifacts": [{"path": path.name, "sha256": _sha256_file(path)} for path in table_paths],
    }
