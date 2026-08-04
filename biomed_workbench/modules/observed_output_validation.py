"""Packaged reload validation for agent-produced scientific artifacts."""

from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence


_FORMAT_MEDIA_TYPES = {
    "alphafold3-output": "application/zip",
    "artifact-directory": "application/zip",
    "bed": "text/tab-separated-values",
    "broadpeak": "text/tab-separated-values",
    "cellbender-h5": "application/x-hdf5",
    "count-matrix": "text/tab-separated-values",
    "csv": "text/csv",
    "fasta": "text/x-fasta",
    "h5ad": "application/x-hdf5",
    "h5mu": "application/x-hdf5",
    "html": "text/html",
    "inline-json": "application/json",
    "json": "application/json",
    "matrix-market": "text/plain",
    "metascape-result": "application/zip",
    "mmcif": "chemical/x-mmcif",
    "mofa-hdf5": "application/x-hdf5",
    "monocle-object-directory": "application/zip",
    "narrowpeak": "text/tab-separated-values",
    "newick": "text/x-newick",
    "normalized-json": "application/json",
    "paf": "text/tab-separated-values",
    "pdb": "chemical/x-pdb",
    "pdf": "application/pdf",
    "publication-figure-set": "application/zip",
    "rds": "application/octet-stream",
    "scvi-model-directory": "application/zip",
    "seurat-rds": "application/octet-stream",
    "spatialdata-zarr": "application/zip",
    "svg": "image/svg+xml",
    "tab-separated-values": "text/tab-separated-values",
    "tabular": "text/tab-separated-values",
    "tiff": "image/tiff",
    "tskit-trees": "application/octet-stream",
    "vcf": "text/x-vcf",
    "yaml": "application/yaml",
}
_ZIP_FORMATS = {
    "alphafold3-output",
    "artifact-directory",
    "metascape-result",
    "monocle-object-directory",
    "publication-figure-set",
    "scvi-model-directory",
    "spatialdata-zarr",
}
_HDF5_FORMATS = {"cellbender-h5", "h5ad", "h5mu", "mofa-hdf5"}
_JSON_FORMATS = {"inline-json", "json", "normalized-json"}
_RDS_FORMATS = {"rds", "seurat-rds"}
_TABULAR_FORMATS = {"bed", "broadpeak", "count-matrix", "csv", "narrowpeak", "paf", "tab-separated-values", "tabular"}


def _text(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("observed text payload is not valid UTF-8") from exc
    if not value.strip():
        raise ValueError("observed text payload is empty")
    return value


def _validate_tabular(path: Path, format_name: str, record_count: int) -> None:
    delimiter = "," if format_name == "csv" else "\t"
    rows = [row for row in csv.reader(_text(path).splitlines(), delimiter=delimiter) if row and not row[0].startswith("#")]
    if not rows:
        raise ValueError("observed table contains no reloadable records")
    minimum_columns = {"bed": 3, "broadpeak": 9, "narrowpeak": 10, "paf": 12}.get(format_name, 2)
    if any(len(row) < minimum_columns for row in rows):
        raise ValueError(f"observed {format_name} payload has too few columns")
    headerless = format_name in {"bed", "broadpeak", "narrowpeak", "paf"}
    observed_records = len(rows) if headerless else len(rows) - 1
    if observed_records != record_count:
        raise ValueError("observed table record count differs from its result contract")
    if not headerless and any(len(row) != len(rows[0]) for row in rows[1:]):
        raise ValueError("observed table rows do not match the reloaded header width")


def _validate_structure(path: Path, format_name: str) -> None:
    text = _text(path)
    if format_name == "pdb" and not any(
        line.startswith(("ATOM  ", "HETATM", "HEADER", "MODEL ")) for line in text.splitlines()
    ):
        raise ValueError("observed PDB payload has no structural records")
    if format_name == "mmcif" and not text.lstrip().startswith("data_"):
        raise ValueError("observed mmCIF payload lacks a data block")


def _validate_primary(path: Path, format_name: str, record_count: int) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("observed primary payload is missing or empty")
    prefix = path.read_bytes()[:16]
    if format_name in _TABULAR_FORMATS:
        _validate_tabular(path, format_name, record_count)
    elif format_name in _JSON_FORMATS:
        try:
            json.loads(_text(path))
        except json.JSONDecodeError as exc:
            raise ValueError("observed JSON payload cannot be reloaded") from exc
    elif format_name in _ZIP_FORMATS:
        if not zipfile.is_zipfile(path):
            raise ValueError("observed bundle is not a valid ZIP container")
        with zipfile.ZipFile(path) as archive:
            if not archive.namelist() or archive.testzip() is not None:
                raise ValueError("observed ZIP container is empty or corrupt")
    elif format_name in _HDF5_FORMATS:
        if prefix[:8] != b"\x89HDF\r\n\x1a\n":
            raise ValueError("observed HDF5 payload has an invalid signature")
    elif format_name in _RDS_FORMATS:
        if not prefix.startswith((b"X\n", b"A\n", b"B\n", b"\x1f\x8b")):
            raise ValueError("observed RDS payload has an invalid serialization signature")
    elif format_name == "pdf":
        if not prefix.startswith(b"%PDF-"):
            raise ValueError("observed PDF payload has an invalid signature")
    elif format_name == "tiff":
        if not prefix.startswith((b"II*\x00", b"MM\x00*")):
            raise ValueError("observed TIFF payload has an invalid signature")
    elif format_name == "svg":
        if "<svg" not in _text(path)[:4096].lower():
            raise ValueError("observed SVG payload has no SVG root")
    elif format_name == "html":
        if "<html" not in _text(path)[:4096].lower():
            raise ValueError("observed HTML payload has no HTML root")
    elif format_name == "matrix-market":
        if not _text(path).startswith("%%MatrixMarket"):
            raise ValueError("observed Matrix Market payload has an invalid header")
    elif format_name == "fasta":
        if not _text(path).lstrip().startswith(">"):
            raise ValueError("observed FASTA payload has no sequence header")
    elif format_name == "newick":
        if not _text(path).strip().endswith(";"):
            raise ValueError("observed Newick payload has no terminating semicolon")
    elif format_name in {"pdb", "mmcif"}:
        _validate_structure(path, format_name)
    elif format_name == "vcf":
        if not _text(path).startswith("##fileformat=VCF"):
            raise ValueError("observed VCF payload has an invalid header")
    elif format_name == "yaml":
        import yaml

        if yaml.safe_load(_text(path)) is None:
            raise ValueError("observed YAML payload is empty after reload")
    elif format_name == "tskit-trees":
        if not prefix.startswith(b"\x89KAS"):
            raise ValueError("observed tree-sequence payload has an invalid kastore signature")
    else:
        raise ValueError(f"observed output format has no packaged reload validator: {format_name}")


def validate_observed_output(
    *,
    content: Mapping[str, Any],
    payloads: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
) -> bool:
    """Reload and validate the primary payload under the declared result format."""
    if not context.get("module_id") or not context.get("module_version") or not context.get("port"):
        raise ValueError("observed output validator context is incomplete")
    format_name = content.get("format")
    if format_name not in _FORMAT_MEDIA_TYPES:
        raise ValueError("observed output format is not supported by the packaged validator")
    primary = [item for item in payloads if item.get("role") == "primary"]
    if len(primary) != 1 or primary[0].get("media_type") != _FORMAT_MEDIA_TYPES[format_name]:
        raise ValueError("observed primary payload does not match the declared format media type")
    path = Path(str(primary[0].get("path", "")))
    _validate_primary(path, str(format_name), int(content.get("record_count", -1)))
    return True
