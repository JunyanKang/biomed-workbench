"""Module-bound semantic admission for externally produced scientific outputs.

Container reload proves that bytes can be read.  This module separately binds
those bytes to a module, output port, declared result schema, primary-payload
digest, structured quality metrics, and (where available) method-specific
scientific invariants.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree


_METADATA_FIELDS = {
    "schema_version",
    "module_id",
    "module_version",
    "port",
    "result_schema_id",
    "primary_payload_sha256",
    "analysis_mode",
    "input_accounting",
    "result_accounting",
    "limitations",
    "empty_result_reason",
    "handoff_request_digest",
    "compatibility_contract_digest",
    "input_artifacts",
}
_TABULAR_MEDIA = {"text/tab-separated-values": "\t", "text/csv": ","}
_FIGURE_MEDIA = {"application/pdf", "image/svg+xml", "image/tiff"}
_PLACEHOLDER_COLUMNS = {"foo", "bar", "x", "y", "column1", "column2", "unnamed"}


_PROFILE_BY_ARTIFACT_TYPE = {
    "functional_enrichment_evidence": "functional-enrichment-v2",
    "bulk_chromatin_accessibility_evidence": "bulk-assay-summary-v1",
    "bulk_dna_methylation_evidence": "bulk-assay-summary-v1",
    "bulk_nascent_transcription_evidence": "bulk-assay-summary-v1",
    "bulk_r_loop_mapping_evidence": "bulk-assay-summary-v1",
    "bulk_rbp_rna_binding_evidence": "bulk-assay-summary-v1",
    "bulk_ribosome_profiling_evidence": "bulk-assay-summary-v1",
    "bulk_rna_modification_enrichment_evidence": "bulk-assay-summary-v1",
    "bulk_three_dimensional_genome_evidence": "bulk-assay-summary-v1",
    "deqms_proteomics_inference": "statistical-results-v1",
    "donor_aware_differential_result": "statistical-results-v1",
    "gwas_fine_mapping_evidence": "statistical-results-v1",
    "held_out_genomic_prediction_evidence": "statistical-results-v1",
    "single_cell_statistical_evidence": "statistical-results-v1",
    "wgcna_coexpression_network_evidence": "statistical-results-v1",
    "assembly_alignment_evidence": "genomic-records-v1",
    "bulk_chromatin_peak_evidence": "genomic-records-v1",
    "genomic_intervals": "genomic-records-v1",
    "comparative_sequence_evidence": "sequence-phylogeny-v1",
    "reloaded_coalescent_simulation_evidence": "sequence-phylogeny-v1",
    "pseudobulk_count_matrix": "count-matrix-v1",
    "single_cell_analysis_object": "single-cell-object-v1",
    "single_cell_annotated_object": "single-cell-object-v1",
    "single_cell_decontaminated_counts": "single-cell-object-v1",
    "single_cell_doublet_annotated_object": "single-cell-object-v1",
    "single_cell_generative_model": "model-bundle-v1",
    "single_cell_integrated_object": "single-cell-object-v1",
    "single_cell_mosaic_integration_evidence": "single-cell-object-v1",
    "single_cell_multimodal_evidence": "single-cell-object-v1",
    "single_cell_reference_mapping_evidence": "single-cell-object-v1",
    "single_cell_regulatory_velocity_object": "single-cell-object-v1",
    "single_cell_trajectory_object": "single-cell-object-v1",
    "cross_species_integration_evidence": "single-cell-results-v1",
    "integration_benchmark_evidence": "single-cell-results-v1",
    "single_cell_annotation_validation": "single-cell-results-v1",
    "single_cell_atac_regulatory_evidence": "single-cell-results-v1",
    "single_cell_cluster_model": "single-cell-results-v1",
    "single_cell_communication_evidence": "single-cell-results-v1",
    "single_cell_communication_validation": "single-cell-results-v1",
    "single_cell_doublet_evidence": "single-cell-results-v1",
    "single_cell_droplet_evidence": "single-cell-results-v1",
    "single_cell_fate_evidence": "single-cell-results-v1",
    "single_cell_integration_benchmark": "single-cell-results-v1",
    "single_cell_integration_decision": "single-cell-results-v1",
    "single_cell_marker_evidence": "single-cell-results-v1",
    "single_cell_model_validation": "single-cell-results-v1",
    "single_cell_qc_report": "single-cell-results-v1",
    "single_cell_regulatory_network_evidence": "single-cell-results-v1",
    "single_cell_regulatory_velocity_validation": "single-cell-results-v1",
    "single_cell_statistical_validation": "single-cell-results-v1",
    "single_cell_trajectory_evidence": "single-cell-results-v1",
    "single_cell_trajectory_validation": "single-cell-results-v1",
    "donor_aware_inference_report": "single-cell-results-v1",
    "pseudobulk_sample_manifest": "single-cell-results-v1",
    "multislice_spatial_evidence": "spatial-results-v1",
    "platform_qc_evidence": "spatial-results-v1",
    "spatial_inference_evidence": "spatial-results-v1",
    "spatial_single_cell_analysis_evidence": "spatial-results-v1",
    "structure_coordinates": "structure-coordinate-v1",
    "secondary_structure_report": "structure-analysis-v1",
    "structure_comparison_report": "structure-analysis-v1",
    "structure_quality_report": "structure-analysis-v1",
    "structure_prediction_bundle": "model-bundle-v1",
    "complex_docking_bundle": "analysis-archive-v1",
    "enrichment_network_bundle": "analysis-archive-v1",
    "docking_batch_manifest": "statistical-results-v1",
    "docking_inference_config": "configuration-v1",
    "network_figure_bundle": "figure-package-v1",
    "structure_figure_bundle": "figure-package-v1",
    "trajectory_spatial_figure_package": "figure-package-v1",
    "secondary_structure_diagram": "svg-figure-v1",
    "interactive_structure_view": "interactive-html-v1",
    "analysis_provenance": "scientific-report-v1",
    "docking_preparation_report": "scientific-report-v1",
    "docking_review_report": "scientific-report-v1",
    "secondary_structure_diagram_manifest": "scientific-report-v1",
    "substructure_filter_report": "scientific-report-v1",
    "visualization_manifest": "scientific-report-v1",
}


def semantic_profile_for(artifact_type: str) -> str:
    """Return an explicitly registered scientific family; unknown types fail closed."""
    try:
        return _PROFILE_BY_ARTIFACT_TYPE[artifact_type]
    except KeyError as exc:
        raise ValueError(f"no scientific semantic profile is registered for artifact type: {artifact_type}") from exc


def registered_semantic_profiles() -> tuple[str, ...]:
    return tuple(sorted(set(_PROFILE_BY_ARTIFACT_TYPE.values())))


_MEDIA_TYPES_BY_PROFILE = {
    "functional-enrichment-v2": frozenset({"application/json", *_TABULAR_MEDIA, *_FIGURE_MEDIA}),
    "bulk-assay-summary-v1": frozenset({"application/json"}),
    "statistical-results-v1": frozenset({"application/json", *_TABULAR_MEDIA, *_FIGURE_MEDIA}),
    "genomic-records-v1": frozenset({"application/json", "text/tab-separated-values", *_FIGURE_MEDIA}),
    "sequence-phylogeny-v1": frozenset({
        "application/json", "application/octet-stream", "text/tab-separated-values",
        "text/x-fasta", "text/x-newick", "text/x-vcf",
    }),
    "count-matrix-v1": frozenset({"text/plain", "text/tab-separated-values"}),
    "single-cell-object-v1": frozenset({
        "application/json", "application/octet-stream", "application/x-hdf5",
        "application/zip", "text/plain", "text/tab-separated-values",
    }),
    "single-cell-results-v1": frozenset({
        "application/json", "application/octet-stream", "application/x-hdf5",
        "application/zip", "text/plain", "text/tab-separated-values",
    }),
    "spatial-results-v1": frozenset({
        "application/json", "application/octet-stream", "application/x-hdf5",
        "application/zip", "text/plain", "text/tab-separated-values",
    }),
    "structure-coordinate-v1": frozenset({"chemical/x-mmcif", "chemical/x-pdb"}),
    "structure-analysis-v1": frozenset({"application/json", "text/tab-separated-values"}),
    "analysis-archive-v1": frozenset({"application/zip"}),
    "figure-package-v1": frozenset({"application/json", "application/zip", *_FIGURE_MEDIA}),
    "scientific-report-v1": frozenset({"application/json", "text/tab-separated-values"}),
    "configuration-v1": frozenset({"application/yaml"}),
    "interactive-html-v1": frozenset({"text/html"}),
    "svg-figure-v1": frozenset({"image/svg+xml"}),
    "model-bundle-v1": frozenset({"application/x-hdf5", "application/zip"}),
}


def semantic_profile_supports_media_type(profile: str, media_type: str) -> bool:
    """Return whether a profile has an explicit dispatch branch for this media type."""
    return media_type in _MEDIA_TYPES_BY_PROFILE.get(profile, ())


def _semantic_metadata(payloads: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], Mapping[str, Any]]:
    matches = [item for item in payloads if item.get("role") == "semantic-metadata"]
    if len(matches) != 1 or matches[0].get("media_type") != "application/json":
        raise ValueError("observed output requires one JSON semantic-metadata payload")
    path = Path(str(matches[0].get("path", "")))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("semantic metadata cannot be reloaded as JSON") from exc
    if not isinstance(value, dict) or set(value) != _METADATA_FIELDS:
        raise ValueError("semantic metadata fields are incomplete or unsupported")
    return value, matches[0]


def _primary(payloads: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    matches = [item for item in payloads if item.get("role") == "primary"]
    if len(matches) != 1:
        raise ValueError("semantic validation requires one primary payload")
    return matches[0]


def _validate_accounting(metadata: Mapping[str, Any], record_count: int) -> None:
    for field in ("input_accounting", "result_accounting"):
        value = metadata[field]
        if not isinstance(value, dict) or not value:
            raise ValueError(f"semantic metadata {field} must be a nonempty object")
        if any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(observed, (int, float))
            or isinstance(observed, bool)
            or not math.isfinite(float(observed))
            or observed < 0
            for key, observed in value.items()
        ):
            raise ValueError(f"semantic metadata {field} contains invalid counts or measures")
    if metadata["result_accounting"].get("reported_records") != record_count:
        raise ValueError("semantic result accounting differs from the declared record count")
    reason = metadata["empty_result_reason"]
    if record_count == 0:
        if not isinstance(reason, str) or len(reason.strip()) < 12:
            raise ValueError("empty scientific results require a reason and input accounting")
    elif reason is not None:
        raise ValueError("nonempty scientific results cannot declare an empty-result reason")


def _read_table(primary: Mapping[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    delimiter = _TABULAR_MEDIA.get(str(primary.get("media_type")))
    if delimiter is None:
        raise ValueError("the semantic profile requires a tabular primary payload")
    path = Path(str(primary.get("path", "")))
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader((line for line in handle if not line.startswith("#")), delimiter=delimiter)
        columns = list(reader.fieldnames or ())
        raw_rows = list(reader)
    normalized = [item.strip().lower() for item in columns]
    if len(columns) < 2 or len(set(normalized)) != len(normalized):
        raise ValueError("scientific result table requires unique semantic columns")
    if set(normalized) <= _PLACEHOLDER_COLUMNS or any(not item for item in normalized):
        raise ValueError("scientific result table uses placeholder or empty column names")
    rows = [
        {
            normalized[index]: "" if row.get(column) is None else str(row[column])
            for index, column in enumerate(columns)
        }
        for row in raw_rows
    ]
    return normalized, rows


def _json_records(primary: Mapping[str, Any], record_count: int) -> dict[str, Any]:
    path = Path(str(primary.get("path", "")))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("scientific JSON primary cannot be reloaded") from exc
    required = {"schema_version", "analysis_mode", "records", "summary"}
    if not isinstance(value, dict) or not required <= set(value):
        raise ValueError("scientific JSON primary requires schema_version, analysis_mode, records, and summary")
    if value["schema_version"] != 1 or value["analysis_mode"] in {"not-run", "planned", "dry-run", "unknown"}:
        raise ValueError("scientific JSON primary does not describe an observed analysis")
    if not isinstance(value["summary"], str) or len(value["summary"].strip()) < 8:
        raise ValueError("scientific JSON primary requires a substantive summary")
    if not isinstance(value["records"], list) or len(value["records"]) != record_count:
        raise ValueError("scientific JSON records differ from declared result accounting")
    if any(not isinstance(item, dict) or not item for item in value["records"]):
        raise ValueError("scientific JSON records must be nonempty objects")
    return value


def _validate_table(primary: Mapping[str, Any], record_count: int, *, numeric: bool = False) -> None:
    columns, rows = _read_table(primary)
    if len(rows) != record_count:
        raise ValueError("scientific result table differs from declared result accounting")
    if record_count and any(all(not str(value).strip() for value in row.values()) for row in rows):
        raise ValueError("scientific result table contains an empty record")
    if numeric and record_count:
        numeric_columns = 0
        for column in columns:
            values = [row[column] for row in rows if row[column].strip()]
            try:
                parsed = [float(value) for value in values]
            except ValueError:
                continue
            if parsed and all(math.isfinite(value) for value in parsed):
                numeric_columns += 1
        if numeric_columns == 0:
            raise ValueError("statistical result table requires at least one finite numeric column")


def _validate_json_or_table(primary: Mapping[str, Any], record_count: int, *, numeric: bool = False) -> None:
    media_type = str(primary.get("media_type"))
    if media_type == "application/json":
        _json_records(primary, record_count)
    elif media_type in _TABULAR_MEDIA:
        _validate_table(primary, record_count, numeric=numeric)
    else:
        raise ValueError("semantic profile requires a JSON or tabular primary payload")


def _validate_matrix_market(primary: Mapping[str, Any], record_count: int) -> None:
    path = Path(str(primary.get("path", "")))
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or not lines[0].startswith("%%MatrixMarket matrix coordinate"):
        raise ValueError("count matrix requires a MatrixMarket coordinate header")
    body = [line for line in lines[1:] if not line.startswith("%")]
    if not body or len(body[0].split()) != 3:
        raise ValueError("count matrix dimensions are missing")
    rows, columns, entries = (int(value) for value in body[0].split())
    if rows <= 0 or columns <= 0 or entries != len(body) - 1 or entries != record_count:
        raise ValueError("count matrix dimensions or nonzero accounting are inconsistent")
    for line in body[1:]:
        row, column, value = line.split()
        if not (1 <= int(row) <= rows and 1 <= int(column) <= columns) or float(value) < 0:
            raise ValueError("count matrix contains an invalid coordinate or negative value")


def _validate_hdf5(primary: Mapping[str, Any], record_count: int, *, single_cell: bool) -> None:
    path = Path(str(primary.get("path", "")))
    if path.read_bytes()[:8] != b"\x89HDF\r\n\x1a\n":
        raise ValueError("HDF5 primary has an invalid file signature")
    try:
        import h5py
    except ImportError as exc:  # pragma: no cover - release runtime includes h5py
        raise ValueError("HDF5 semantic validation requires h5py") from exc
    with h5py.File(path, "r") as handle:
        if not list(handle.keys()):
            raise ValueError("HDF5 primary contains no scientific objects")
        if single_cell:
            if not {"obs", "var"} <= set(handle.keys()):
                raise ValueError("single-cell HDF5 primary requires obs and var")
            obs = handle["obs"]
            index_key = obs.attrs.get("_index", "_index")
            if isinstance(index_key, bytes):
                index_key = index_key.decode("utf-8")
            observed = len(obs[index_key]) if index_key in obs else len(next(iter(obs.values()), ()))
            var = handle["var"]
            var_index_key = var.attrs.get("_index", "_index")
            if isinstance(var_index_key, bytes):
                var_index_key = var_index_key.decode("utf-8")
            features = len(var[var_index_key]) if var_index_key in var else len(next(iter(var.values()), ()))
            if observed <= 0 or features <= 0 or observed != record_count:
                raise ValueError("single-cell HDF5 observations differ from result accounting")


def _archive_manifest(primary: Mapping[str, Any], record_count: int) -> tuple[set[str], dict[str, Any]]:
    path = Path(str(primary.get("path", "")))
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError("analysis bundle is not a readable ZIP archive") from exc
    with archive:
        names = {item.filename for item in archive.infolist() if not item.is_dir()}
        if not names or any(name.startswith("/") or ".." in Path(name).parts for name in names):
            raise ValueError("analysis bundle contains no files or unsafe member paths")
        manifests = sorted(name for name in names if Path(name).name == "manifest.json")
        if len(manifests) != 1:
            raise ValueError("analysis bundle requires exactly one manifest.json")
        try:
            manifest = json.loads(archive.read(manifests[0]).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("analysis bundle manifest is invalid") from exc
        required = {"schema_version", "artifact_family", "record_count", "members"}
        if not isinstance(manifest, dict) or set(manifest) != required or manifest["schema_version"] != 1:
            raise ValueError("analysis bundle manifest fields are incomplete or unsupported")
        members = names - set(manifests)
        if manifest["record_count"] != record_count or set(manifest["members"]) != members:
            raise ValueError("analysis bundle manifest does not reconcile its members")
        return members, manifest


def _validate_structure_coordinates(primary: Mapping[str, Any], record_count: int) -> None:
    text = Path(str(primary.get("path", ""))).read_text(encoding="utf-8")
    media_type = str(primary.get("media_type"))
    if media_type == "chemical/x-pdb":
        atoms = [line for line in text.splitlines() if line.startswith(("ATOM  ", "HETATM"))]
    elif media_type == "chemical/x-mmcif":
        atoms = [line for line in text.splitlines() if line.startswith(("ATOM ", "HETATM "))]
    else:
        raise ValueError("structure coordinate profile requires PDB or mmCIF")
    if not atoms or len(atoms) != record_count:
        raise ValueError("structure atom accounting is empty or inconsistent")


def _validate_figure(primary: Mapping[str, Any], record_count: int) -> None:
    media_type = str(primary.get("media_type"))
    path = Path(str(primary.get("path", "")))
    if media_type == "application/zip":
        members, _ = _archive_manifest(primary, record_count)
        if not any(Path(name).suffix.lower() in {".pdf", ".svg", ".tif", ".tiff", ".png"} for name in members):
            raise ValueError("figure bundle contains no publication figure")
        return
    data = path.read_bytes()
    if media_type == "application/pdf":
        try:
            import fitz

            with fitz.open(path) as document:
                if document.page_count <= 0:
                    raise ValueError("figure PDF contains no rendered pages")
                document.load_page(0).get_pixmap(matrix=fitz.Matrix(0.1, 0.1), alpha=False)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise ValueError("figure PDF cannot be parsed and rendered") from exc
    elif media_type == "image/tiff":
        try:
            from PIL import Image

            with Image.open(path) as image:
                if image.n_frames <= 0 or image.width <= 0 or image.height <= 0:
                    raise ValueError("figure TIFF contains no image frame")
                image.seek(0)
                image.load()
        except (ImportError, OSError, ValueError) as exc:
            raise ValueError("figure TIFF cannot be decoded") from exc
    elif media_type == "image/svg+xml":
        try:
            root = ElementTree.fromstring(data)
        except ElementTree.ParseError as exc:
            raise ValueError("figure SVG is invalid") from exc
        if not root.tag.endswith("svg") or len(list(root.iter())) < 2:
            raise ValueError("figure SVG contains no graphical elements")
    elif media_type not in {"application/pdf", "image/tiff", "image/svg+xml"}:
        raise ValueError("figure profile received an unsupported media type")
    if record_count != 1:
        raise ValueError("single figure payload must declare one record")


def _validate_html(primary: Mapping[str, Any], record_count: int) -> None:
    text = Path(str(primary.get("path", ""))).read_text(encoding="utf-8").lower()
    if "<html" not in text or "</html>" not in text or len(re.sub(r"<[^>]+>", "", text).strip()) < 8:
        raise ValueError("interactive HTML is empty or malformed")
    if record_count != 1:
        raise ValueError("interactive HTML must declare one rendered document")


def _validate_configuration(primary: Mapping[str, Any], record_count: int) -> None:
    text = Path(str(primary.get("path", ""))).read_text(encoding="utf-8")
    pairs = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#") and ":" in line]
    if len(pairs) < 2 or any(token in text.upper() for token in ("TODO", "REPLACE_ME", "/PATH/TO/")):
        raise ValueError("configuration is empty, placeholder-bound, or not parameterized")
    if record_count != len(pairs):
        raise ValueError("configuration entry count differs from result accounting")


def _validate_genomic(primary: Mapping[str, Any], record_count: int) -> None:
    media_type = str(primary.get("media_type"))
    if media_type == "application/json":
        _json_records(primary, record_count)
        return
    path = Path(str(primary.get("path", "")))
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith(("#", "track", "browser"))]
    if len(lines) != record_count:
        raise ValueError("genomic records differ from result accounting")
    if media_type == "text/tab-separated-values":
        for line in lines:
            fields = line.split("\t")
            try:
                if len(fields) >= 12:
                    query_length, query_start, query_end = map(int, fields[1:4])
                    target_length, target_start, target_end = map(int, fields[6:9])
                    matches, block_length, mapping_quality = map(int, fields[9:12])
                    valid = (
                        fields[4] in {"+", "-"}
                        and 0 <= query_start < query_end <= query_length
                        and 0 <= target_start < target_end <= target_length
                        and 0 <= matches <= block_length
                        and 0 <= mapping_quality <= 255
                    )
                else:
                    valid = len(fields) >= 3 and bool(fields[0]) and 0 <= int(fields[1]) < int(fields[2])
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("genomic interval or pairwise-alignment coordinates are invalid")
    elif media_type == "text/x-vcf":
        if not any(line.startswith("#CHROM") for line in path.read_text(encoding="utf-8").splitlines()):
            raise ValueError("VCF header is missing")
    else:
        raise ValueError("genomic record profile received an unsupported media type")


def _validate_sequence(
    primary: Mapping[str, Any], payloads: Sequence[Mapping[str, Any]], record_count: int
) -> None:
    media_type = str(primary.get("media_type"))
    text = Path(str(primary.get("path", ""))).read_text(encoding="utf-8")
    if media_type == "text/x-fasta":
        observed = sum(line.startswith(">") for line in text.splitlines())
    elif media_type == "text/x-newick":
        observed = 1 if text.strip().endswith(";") and "(" in text else 0
    elif media_type == "text/tab-separated-values":
        _columns, rows = _read_table(primary)
        observed = len(rows)
    elif media_type in {"application/json", "text/x-vcf"}:
        if media_type == "application/json":
            _json_records(primary, record_count)
            return
        observed = len([line for line in text.splitlines() if line and not line.startswith("#")])
    elif media_type == "application/octet-stream":
        data = Path(str(primary.get("path", ""))).read_bytes()
        inventories = [
            item for item in payloads
            if item.get("role") == "source-data" and item.get("media_type") == "application/json"
        ]
        if len(data) < 32 or len(inventories) != 1:
            raise ValueError("opaque tree-sequence output requires binary content and one JSON inventory")
        _json_records(inventories[0], record_count)
        observed = record_count
    else:
        raise ValueError("sequence profile received an unsupported media type")
    if observed <= 0 or observed != record_count:
        raise ValueError("sequence or tree records are empty or inconsistent")


def _validate_single_cell(primary: Mapping[str, Any], payloads: Sequence[Mapping[str, Any]], record_count: int) -> None:
    media_type = str(primary.get("media_type"))
    if media_type == "application/x-hdf5":
        _validate_hdf5(primary, record_count, single_cell=True)
    elif media_type == "text/plain":
        _validate_matrix_market(primary, record_count)
    elif media_type == "application/zip":
        _archive_manifest(primary, record_count)
    elif media_type == "application/octet-stream":
        data = Path(str(primary.get("path", ""))).read_bytes()
        if len(data) < 32 or not data.startswith((b"X\n", b"RDX", b"BZh", b"\x1f\x8b")):
            raise ValueError("R or model object has no recognized serialization signature")
        inventories = [item for item in payloads if item.get("role") == "source-data" and item.get("media_type") == "application/json"]
        if len(inventories) != 1:
            raise ValueError("opaque single-cell objects require one JSON source-data inventory")
        _json_records(inventories[0], record_count)
    else:
        _validate_json_or_table(primary, record_count, numeric=False)


def _validate_model(primary: Mapping[str, Any], record_count: int) -> None:
    media_type = str(primary.get("media_type"))
    if media_type == "application/zip":
        members, manifest = _archive_manifest(primary, record_count)
        if not any(Path(name).suffix.lower() in {".cif", ".pdb", ".pt", ".ckpt", ".json", ".h5"} for name in members):
            raise ValueError("model bundle contains no structure or model artifact")
        if "model" not in str(manifest["artifact_family"]).lower() and "prediction" not in str(manifest["artifact_family"]).lower():
            raise ValueError("model bundle manifest has the wrong artifact family")
    elif media_type == "application/x-hdf5":
        _validate_hdf5(primary, record_count, single_cell=False)
    else:
        raise ValueError("model bundle requires ZIP or HDF5")


def _validate_json_functional_enrichment(
    metadata: Mapping[str, Any], primary: Mapping[str, Any], record_count: int
) -> None:
    value = _json_records(primary, record_count)
    mode = metadata["analysis_mode"]
    required = {
        "ora": {
            "term_id", "term_name", "p_value", "adjusted_p_value", "gene_ratio",
            "background_ratio", "gene_set_size", "overlap_genes",
        },
        "gsea": {
            "term_id", "term_name", "enrichment_score", "normalized_enrichment_score",
            "p_value", "adjusted_p_value", "gene_set_size", "leading_edge",
        },
    }.get(mode)
    if required is None or any(not required <= set(row) for row in value["records"]):
        raise ValueError("functional enrichment JSON omits method-specific scientific fields")
    _validate_functional_enrichment_rows(metadata, value["records"], record_count)


def _ratio(value: str, field: str) -> tuple[int, int]:
    try:
        numerator_text, denominator_text = value.split("/", 1)
        numerator, denominator = int(numerator_text), int(denominator_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"functional enrichment {field} must use numerator/denominator") from exc
    if denominator <= 0 or numerator < 0 or numerator > denominator:
        raise ValueError(f"functional enrichment {field} is outside its valid range")
    return numerator, denominator


def _probability(value: str, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"functional enrichment {field} must be numeric") from exc
    if not math.isfinite(result) or result < 0 or result > 1:
        raise ValueError(f"functional enrichment {field} must lie in [0, 1]")
    return result


def _validate_functional_enrichment(
    metadata: Mapping[str, Any],
    primary: Mapping[str, Any],
    record_count: int,
) -> None:
    mode = metadata["analysis_mode"]
    if mode not in {"ora", "gsea"}:
        raise ValueError("functional enrichment analysis_mode must be ora or gsea")
    if str(primary.get("media_type")) in _FIGURE_MEDIA:
        _validate_figure(primary, record_count)
        return
    if str(primary.get("media_type")) == "application/json":
        _validate_json_functional_enrichment(metadata, primary, record_count)
        return
    if record_count == 0:
        return
    columns, rows = _read_table(primary)
    required = {
        "ora": {
            "term_id", "term_name", "p_value", "adjusted_p_value", "gene_ratio",
            "background_ratio", "gene_set_size", "overlap_genes",
        },
        "gsea": {
            "term_id", "term_name", "enrichment_score", "normalized_enrichment_score",
            "p_value", "adjusted_p_value", "gene_set_size", "leading_edge",
        },
    }[mode]
    if not required <= set(columns):
        raise ValueError(f"functional enrichment {mode} table omits required scientific columns")
    if len(rows) != record_count:
        raise ValueError("functional enrichment rows differ from result accounting")
    _validate_functional_enrichment_rows(metadata, rows, record_count)


def _validate_functional_enrichment_rows(
    metadata: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], record_count: int
) -> None:
    mode = metadata["analysis_mode"]
    if len(rows) != record_count:
        raise ValueError("functional enrichment rows differ from result accounting")
    for row in rows:
        raw_p = _probability(str(row["p_value"]), "p_value")
        adjusted_p = _probability(str(row["adjusted_p_value"]), "adjusted_p_value")
        if adjusted_p + 1e-15 < raw_p:
            raise ValueError("functional enrichment adjusted P value is smaller than its raw P value")
        try:
            size = int(row["gene_set_size"])
        except (TypeError, ValueError) as exc:
            raise ValueError("functional enrichment gene_set_size must be an integer") from exc
        if size <= 0:
            raise ValueError("functional enrichment gene_set_size must be positive")
        if mode == "ora":
            overlap, tested_denominator = _ratio(str(row["gene_ratio"]), "gene_ratio")
            background_size, background_denominator = _ratio(str(row["background_ratio"]), "background_ratio")
            if (
                tested_denominator != metadata["input_accounting"].get("tested_entities")
                or background_denominator != metadata["input_accounting"].get("background_entities")
                or background_size != size
                or overlap > size
                or not str(row["overlap_genes"]).strip()
            ):
                raise ValueError("functional enrichment overlap is inconsistent with the gene-set size")
        else:
            for field in ("enrichment_score", "normalized_enrichment_score"):
                try:
                    score = float(row[field])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"functional enrichment {field} must be numeric") from exc
                if not math.isfinite(score):
                    raise ValueError(f"functional enrichment {field} must be finite")
            if not str(row["leading_edge"]).strip():
                raise ValueError("GSEA results require a nonempty leading edge")


def _profile_functional(metadata, primary, payloads, record_count):
    _validate_functional_enrichment(metadata, primary, record_count)


def _profile_bulk(metadata, primary, payloads, record_count):
    value = _json_records(primary, record_count)
    if record_count and any(
        not {"sample_id", "metric", "value", "unit"} <= set(row)
        for row in value["records"]
    ):
        raise ValueError("bulk assay records require sample_id, metric, value, and unit")


def _profile_statistical(metadata, primary, payloads, record_count):
    if primary.get("media_type") in _FIGURE_MEDIA:
        _validate_figure(primary, record_count)
    else:
        _validate_json_or_table(primary, record_count, numeric=True)


def _profile_genomic(metadata, primary, payloads, record_count):
    if primary.get("media_type") in _FIGURE_MEDIA:
        _validate_figure(primary, record_count)
    else:
        _validate_genomic(primary, record_count)


def _profile_sequence(metadata, primary, payloads, record_count):
    _validate_sequence(primary, payloads, record_count)


def _profile_count_matrix(metadata, primary, payloads, record_count):
    if primary.get("media_type") == "text/plain":
        _validate_matrix_market(primary, record_count)
    else:
        _validate_table(primary, record_count, numeric=True)


def _profile_single_cell_object(metadata, primary, payloads, record_count):
    _validate_single_cell(primary, payloads, record_count)


def _profile_single_cell_results(metadata, primary, payloads, record_count):
    if primary.get("media_type") in {
        "application/x-hdf5", "application/octet-stream", "application/zip", "text/plain"
    }:
        _validate_single_cell(primary, payloads, record_count)
    else:
        _validate_json_or_table(primary, record_count, numeric=False)


def _profile_spatial(metadata, primary, payloads, record_count):
    _profile_single_cell_results(metadata, primary, payloads, record_count)


def _profile_structure_coordinate(metadata, primary, payloads, record_count):
    _validate_structure_coordinates(primary, record_count)


def _profile_structure_analysis(metadata, primary, payloads, record_count):
    _validate_json_or_table(primary, record_count, numeric=False)


def _profile_archive(metadata, primary, payloads, record_count):
    members, _ = _archive_manifest(primary, record_count)
    if not any(
        Path(name).suffix.lower() in {".json", ".tsv", ".csv", ".pdb", ".cif", ".mmcif"}
        for name in members
    ):
        raise ValueError("analysis archive contains no inspectable scientific result")


def _profile_figure(metadata, primary, payloads, record_count):
    if primary.get("media_type") == "application/json":
        _json_records(primary, record_count)
    else:
        _validate_figure(primary, record_count)


def _profile_report(metadata, primary, payloads, record_count):
    _validate_json_or_table(primary, record_count, numeric=False)


def _profile_configuration(metadata, primary, payloads, record_count):
    _validate_configuration(primary, record_count)


def _profile_html(metadata, primary, payloads, record_count):
    _validate_html(primary, record_count)


def _profile_model(metadata, primary, payloads, record_count):
    _validate_model(primary, record_count)


_PROFILE_VALIDATORS = {
    "functional-enrichment-v2": _profile_functional,
    "bulk-assay-summary-v1": _profile_bulk,
    "statistical-results-v1": _profile_statistical,
    "genomic-records-v1": _profile_genomic,
    "sequence-phylogeny-v1": _profile_sequence,
    "count-matrix-v1": _profile_count_matrix,
    "single-cell-object-v1": _profile_single_cell_object,
    "single-cell-results-v1": _profile_single_cell_results,
    "spatial-results-v1": _profile_spatial,
    "structure-coordinate-v1": _profile_structure_coordinate,
    "structure-analysis-v1": _profile_structure_analysis,
    "analysis-archive-v1": _profile_archive,
    "figure-package-v1": _profile_figure,
    "scientific-report-v1": _profile_report,
    "configuration-v1": _profile_configuration,
    "interactive-html-v1": _profile_html,
    "svg-figure-v1": _profile_figure,
    "model-bundle-v1": _profile_model,
}


def semantic_profile_is_implemented(profile: str) -> bool:
    return profile in _PROFILE_VALIDATORS


def validate_observed_output_semantics(
    *,
    content: Mapping[str, Any],
    payloads: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
    profile: str,
) -> dict[str, object]:
    """Validate module identity, accounting, primary bytes, and profile semantics."""
    metadata, _ = _semantic_metadata(payloads)
    primary = _primary(payloads)
    expected_identity = {
        "schema_version": 1,
        "module_id": context.get("module_id"),
        "module_version": context.get("module_version"),
        "port": context.get("port"),
        "result_schema_id": f"{context.get('module_id')}:{context.get('port')}:{profile}",
    }
    if any(metadata.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("semantic metadata identity differs from the frozen module output contract")
    expected_bindings = {
        "handoff_request_digest": context.get("handoff_request_digest"),
        "compatibility_contract_digest": context.get("compatibility_contract_digest"),
        "input_artifacts": context.get("input_artifacts"),
    }
    if any(metadata.get(key) != value for key, value in expected_bindings.items()):
        raise ValueError("semantic metadata is not bound to the exact handoff inputs and compatibility contract")
    primary_path = Path(str(primary.get("path", "")))
    if hashlib.sha256(primary_path.read_bytes()).hexdigest() != metadata["primary_payload_sha256"]:
        raise ValueError("semantic metadata is not bound to the imported primary payload")
    if not isinstance(metadata["limitations"], list) or any(
        not isinstance(item, str) or len(item.strip()) < 4 for item in metadata["limitations"]
    ):
        raise ValueError("semantic metadata limitations must be an explicit string array")
    record_count = int(content.get("record_count", -1))
    _validate_accounting(metadata, record_count)
    validator = _PROFILE_VALIDATORS.get(profile)
    if validator is None:
        raise ValueError(f"observed output semantic profile has no registered implementation: {profile}")
    if not semantic_profile_supports_media_type(profile, str(primary.get("media_type"))):
        raise ValueError(f"semantic profile has no media-specific implementation: {profile}")
    validator(metadata, primary, payloads, record_count)
    return {
        "family_admission_status": "passed",
        "profile": profile,
        "family_admission": True,
        "evidence_payload_digests": {
            str(item["role"]): str(item["sha256"])
            for item in payloads
        },
    }


def evaluate_structured_gate(
    *,
    payloads: Sequence[Mapping[str, Any]],
    gate_id: str,
    evaluator_type: str,
    evidence_payload_role: str,
    metric_key: str,
    metric_type: str,
    operator: str,
    threshold: object,
    semantic_result: Mapping[str, object],
) -> dict[str, object]:
    """Evaluate one gate without promoting family admission into scientific proof."""
    if set(semantic_result) != {
        "family_admission_status", "profile", "family_admission", "evidence_payload_digests"
    } or semantic_result.get("family_admission_status") != "passed":
        raise ValueError("packaged semantic result is incomplete or unsuccessful")
    by_role = {str(item["role"]): item for item in payloads}
    evidence = by_role.get(evidence_payload_role)
    if evidence is None:
        return {
            "status": "not_evaluable",
            "observed_metric": json.dumps(None),
            "threshold": json.dumps({"operator": operator, "value": threshold}, sort_keys=True, separators=(",", ":")),
            "evidence_payload_sha256": None,
            "reason": f"declared evidence payload role is absent: {evidence_payload_role}",
            "evaluator_type": evaluator_type,
        }
    expected_digest = semantic_result["evidence_payload_digests"].get(evidence_payload_role)  # type: ignore[union-attr]
    if expected_digest != evidence.get("sha256"):
        raise ValueError("gate evidence payload differs from the family-admitted payload")
    if evaluator_type in {"provenance-design", "claim-boundary", "payload-derived", "tool-native"}:
        return {
            "status": "requires_review",
            "observed_metric": json.dumps("pending-independent-scientific-review"),
            "threshold": json.dumps({"operator": operator, "value": threshold}, sort_keys=True, separators=(",", ":")),
            "evidence_payload_sha256": evidence["sha256"],
            "reason": (
                f"{gate_id} requires gate-specific design, tool-native, or claim review; "
                "family-level file admission is not a verdict"
            ),
            "evaluator_type": evaluator_type,
        }
    if evaluator_type != "system-provenance" or metric_key != "family_admission":
        raise ValueError(f"gate evaluator contract is unsupported: {gate_id}")
    observed = semantic_result[metric_key]
    expected = {
        "boolean": bool,
        "integer": int,
        "number": (int, float),
        "string": str,
    }[metric_type]
    if not isinstance(observed, expected) or (metric_type in {"integer", "number"} and isinstance(observed, bool)):
        raise ValueError(f"semantic quality metric has the wrong type: {metric_key}")
    if metric_type == "number" and not math.isfinite(float(observed)):
        raise ValueError(f"semantic quality metric is non-finite: {metric_key}")
    comparisons = {
        "equals": lambda: observed == threshold,
        "not-equals": lambda: observed != threshold,
        "greater-than": lambda: observed > threshold,
        "greater-or-equal": lambda: observed >= threshold,
        "less-than": lambda: observed < threshold,
        "less-or-equal": lambda: observed <= threshold,
    }
    passed = bool(comparisons[operator]())
    return {
        "status": "passed" if passed else "failed",
        "observed_metric": json.dumps(observed, sort_keys=True, separators=(",", ":")),
        "threshold": json.dumps(
            {"operator": operator, "value": threshold}, sort_keys=True, separators=(",", ":")
        ),
        "evidence_payload_sha256": evidence["sha256"],
        "reason": "system provenance and family admission were recomputed by the packaged ingest path",
        "evaluator_type": evaluator_type,
    }
