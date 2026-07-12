"""Exhaustive, privacy-aware source assimilation.

The private manifest is evidence that every file in a source snapshot was read.
Tracked reports are aggregate-only so local paths and sensitive values never
become part of the public release.
"""

from __future__ import annotations

import ast
import hashlib
import json
import mimetypes
import os
import pickletools
import re
import stat
import struct
import tarfile
import tomllib
import warnings
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


DISPOSITIONS = {
    "integrate",
    "rewrite",
    "merge",
    "provenance_only",
    "generated_runtime",
    "restricted",
    "sensitive",
    "obsolete",
}

_SENSITIVE_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    "credentials",
    "credentials.json",
    "secrets.json",
}
_PRIVATE_KEY_RE = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_KNOWN_TOKEN_RE = re.compile(
    rb"(?i)\b(?:nvapi-[A-Za-z0-9_-]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._~+/-]{24,})"
)
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?im)(?P<prefix>[\"']?[A-Za-z][A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)[\"']?\s*[:=]\s*)(?P<value>[^\s,#}]+)"
)
_GENERATED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "conda",
    "dist",
    "envs",
    "logs",
    "node_modules",
    "pkgs",
    "runtime",
    "site-packages",
    "tls",
    "venv",
}
_TEXT_SUFFIXES = {
    ".cfg",
    ".csv",
    ".ini",
    ".log",
    ".md",
    ".py",
    ".r",
    ".rst",
    ".sh",
    ".sql",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}


class IncompleteAssimilationError(RuntimeError):
    """Raised when a manifest is not an exact readable source inventory."""


@dataclass(frozen=True)
class FileRecord:
    source: str
    path: str
    kind: str
    size: int
    sha256: str
    format: str
    media_type: str
    disposition: str
    capability_cluster: str
    understanding: dict[str, Any]
    semantic: dict[str, Any]
    read_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceSummary:
    source: str
    file_count: int
    total_bytes: int
    root_digest: str
    format_counts: dict[str, int]
    disposition_counts: dict[str, int]
    capability_counts: dict[str, int]
    unreadable_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AssimilationResult:
    records: list[FileRecord]
    summary: SourceSummary


def inventory(root: Path) -> list[Path]:
    """Return every regular file and symlink below root without following links."""
    root = root.resolve()
    paths: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        base = Path(directory)
        for name in filenames:
            path = base / name
            mode = path.lstat().st_mode
            if stat.S_ISREG(mode) or stat.S_ISLNK(mode):
                paths.append(path)
        for name in list(dirnames):
            path = base / name
            if path.is_symlink():
                paths.append(path)
                dirnames.remove(name)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _is_sensitive(path: Path, data: bytes) -> bool:
    name = path.name.lower()
    if name in _SENSITIVE_NAMES:
        return True
    if path.suffix.lower() in {".key", ".p12", ".pfx"}:
        return True
    sensitive_stems = {"secret", "secrets", "token", "credentials", "password", "passwd"}
    if name in sensitive_stems:
        return True
    config_suffixes = {".cfg", ".conf", ".env", ".ini", ".json", ".toml", ".txt", ".yaml", ".yml"}
    if path.stem.lower() in sensitive_stems and path.suffix.lower() in config_suffixes:
        return True
    if path.suffix.lower() in config_suffixes and re.search(
        r"(?:^|[._-])(secret|token|credential|password|passwd|private[_-]?key)(?:$|[._-])",
        name,
    ):
        return True
    return bool(_KNOWN_TOKEN_RE.search(data) or _PRIVATE_KEY_RE.search(data))


def _sanitize_string(value: str) -> str:
    value = _CREDENTIAL_ASSIGNMENT_RE.sub(r"\g<prefix>[REDACTED]", value)
    return _KNOWN_TOKEN_RE.sub(b"[REDACTED]", value.encode("utf-8", errors="replace")).decode("utf-8")


def _sanitize_semantic(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, list):
        return [_sanitize_semantic(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_semantic(item) for key, item in value.items()}
    return value


def _disposition(path: Path, sensitive: bool) -> str:
    if sensitive:
        return "sensitive"
    if path.name == ".DS_Store":
        return "obsolete"
    if path.name in {"auth-owner.lock", "install-id", "operon-cli.db", "operon-cli.db-shm", "operon-cli.db-wal"}:
        return "generated_runtime"
    if any(part in _GENERATED_PARTS for part in path.parts):
        return "generated_runtime"
    if path.name.lower().startswith(("license", "notice", "copying")):
        return "provenance_only"
    normalized = f"/{path.as_posix().lower()}"
    codex_rewrite_markers = (
        "/agent/",
        "/agents/",
        "/auth/",
        "/bin/claude-science",
        "/llm.py",
        "/llm-tools/",
        "/provider/",
        "/providers/",
        "managed-model-endpoints",
        "using-model-endpoint",
        "model_provider",
        "model-provider",
    )
    if any(marker in normalized for marker in codex_rewrite_markers):
        return "rewrite"
    return "merge"


_CLUSTER_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("codex_native_orchestration", ("/agent/", "/agents/", "/auth/", "/bin/claude-science", "/llm.py", "/llm-tools/", "/provider/", "/providers/", "model-endpoint", "model_provider", "model-provider")),
    ("quality_assurance", ("/test/", "/tests/", "test_", ".test.", "/e2e/", "verification", "benchmark", "/eval/")),
    ("publication", ("paper", "manuscript", "writing", "citation", "patent", "narrative", "document", "pdf", "scholar")),
    ("evidence_discovery", ("literature", "pubmed", "biorxiv", "database", "databases", "search", "dossier", "evidence")),
    ("structural_biology", ("alphafold", "openfold", "esmfold", "boltz", "chai1", "diffdock", "proteinmpnn", "ligandmpnn", "solublempnn", "structure")),
    ("molecular_design", ("chemistry", "biochemistry", "pharmacology", "molecular", "synthetic_biology", "glyco", "compound", "drug", "ligand")),
    ("omics", ("genomic", "genetic", "scvi", "scgpt", "borzoi", "evo2", "transcript", "single-cell", "single_cell", "proteomic", "metabolomic")),
    ("imaging", ("image", "imaging", "microscopy", "pathology", "figure-composer")),
    ("clinical_translation", ("clinical", "cancer", "immunology", "indication", "patient", "cohort", "trial")),
    ("wetlab_experiment", ("protocol", "wetlab", "lab_automation", "microbiology", "cell_biology", "physiology", "bioengineering")),
    ("statistics_modeling", ("statistics", "biophysics", "systems_biology", "modeling", "simulation")),
    ("visualization", ("visualization", "visualisation", "figure-style", "plot", "chart")),
    ("data_engineering", ("data-engineering", "parsing", "converter", "dataset", "storage", "workspace")),
    ("runtime_orchestration", ("runtime", "compute", "cloud", "remote", "endpoint", "environment", "setup", "install", "provider", "mcp", "tool_registry", "support_tools")),
    ("product_interface", ("frontend", "/ui/", "landing", "onboarding", "theme", "tui", "server", "command")),
)


def _capability_cluster(path: Path, disposition: str) -> str:
    if disposition == "generated_runtime":
        return "generated_runtime"
    if disposition == "sensitive":
        return "sensitive_configuration"
    if disposition in {"provenance_only", "obsolete"}:
        return "governance_provenance"
    normalized = f"/{path.as_posix().lower()}"
    for cluster, keywords in _CLUSTER_RULES:
        if any(keyword in normalized for keyword in keywords):
            return cluster
    if any(part in {".github", ".husky", "docs"} for part in path.parts):
        return "governance_provenance"
    return "scientific_assistant_core"


def _runtime_group(path: Path) -> str | None:
    parts = path.parts
    for marker in ("pkgs", "site-packages", "node_modules", "envs"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return f"{marker}:{parts[index + 1]}"
    for marker in (".git", "artifacts", "build", "conda", "dist", "logs", "runtime"):
        if marker in parts:
            return marker
    return None


def _understanding(path: Path, file_format: str, disposition: str, semantic: dict[str, Any]) -> dict[str, Any]:
    lowered = path.as_posix().lower()
    if disposition == "generated_runtime":
        role = "generated_runtime_artifact"
    elif disposition == "sensitive":
        role = "redacted_configuration"
    elif "/test" in lowered or ".test." in lowered:
        role = "verification"
    elif path.name.lower() == "skill.md":
        role = "assistant_workflow"
    elif path.suffix.lower() in {".py", ".r", ".js", ".ts", ".tsx", ".sh"}:
        role = "executable_logic"
    elif file_format in {"markdown", "pdf", "text"}:
        role = "guidance_or_reference"
    elif file_format in {"json", "yaml", "toml", "notebook", "pickle"}:
        role = "structured_scientific_asset"
    else:
        role = "binary_or_visual_asset"
    result: dict[str, Any] = {"role": role}
    runtime_group = _runtime_group(path)
    if runtime_group:
        result["runtime_group"] = runtime_group
    for source_key, target_key in (
        ("public_symbols", "public_symbol_count"),
        ("imports", "dependency_count"),
        ("headings", "section_count"),
        ("cell_count", "notebook_cell_count"),
        ("member_count", "archive_member_count"),
    ):
        value = semantic.get(source_key)
        if isinstance(value, list):
            result[target_key] = len(value)
        elif isinstance(value, int):
            result[target_key] = value
    return result


def _decode_text(data: bytes) -> str | None:
    if b"\x00" in data[:8192]:
        return None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _python_semantics(text: str) -> dict[str, Any]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text)
    except SyntaxError as exc:
        return {"parse_error": f"line {exc.lineno}: {exc.msg}"}
    symbols: list[str] = []
    imports: set[str] = set()
    side_effect_calls: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                symbols.append(node.name)
        elif isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value.func
            if isinstance(call, ast.Name):
                side_effect_calls.append(call.id)
            elif isinstance(call, ast.Attribute):
                side_effect_calls.append(call.attr)
    return {
        "module_doc": (ast.get_docstring(tree) or "")[:500],
        "public_symbols": symbols,
        "imports": sorted(imports),
        "top_level_calls": side_effect_calls,
    }


def _markdown_semantics(text: str) -> dict[str, Any]:
    headings = []
    fences = Counter()
    for line in text.splitlines():
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level <= 6 and len(line) > level and line[level] == " ":
                headings.append({"level": level, "text": line[level + 1 :].strip()[:300]})
        match = re.match(r"^```\s*([\w+-]*)", line)
        if match:
            fences[match.group(1) or "plain"] += 1
    return {"headings": headings, "code_fences": dict(sorted(fences.items()))}


def _structured_semantics(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"root_type": "object", "keys": sorted(map(str, value.keys()))[:500], "length": len(value)}
    if isinstance(value, list):
        return {"root_type": "array", "length": len(value)}
    return {"root_type": type(value).__name__}


def _notebook_semantics(value: Any) -> dict[str, Any]:
    base = _structured_semantics(value)
    if isinstance(value, dict) and isinstance(value.get("cells"), list):
        types = Counter(str(cell.get("cell_type", "unknown")) for cell in value["cells"] if isinstance(cell, dict))
        base.update({"cell_count": len(value["cells"]), "cell_types": dict(sorted(types.items()))})
    return base


def _archive_semantics(path: Path, suffix: str) -> dict[str, Any]:
    try:
        if suffix in {".zip", ".whl", ".jar"}:
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                return {"member_count": len(members), "members": [m.filename[:500] for m in members[:100]]}
        with tarfile.open(path, mode="r:*") as archive:
            members = archive.getmembers()
            return {"member_count": len(members), "members": [m.name[:500] for m in members[:100]]}
    except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError) as exc:
        return {"parse_error": type(exc).__name__}


def _pickle_semantics(data: bytes) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    globals_seen: set[str] = set()
    try:
        for opcode, argument, _position in pickletools.genops(data):
            counts[opcode.name] += 1
            if opcode.name in {"GLOBAL", "STACK_GLOBAL"} and isinstance(argument, str):
                globals_seen.add(argument.replace("\n", "."))
    except (ValueError, EOFError) as exc:
        return {"parse_error": type(exc).__name__, "opcode_counts": dict(sorted(counts.items()))}
    return {"opcode_counts": dict(sorted(counts.items())), "globals": sorted(globals_seen)[:500]}


def _image_semantics(data: bytes) -> dict[str, Any]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return {"width": width, "height": height}
    if data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return {"width": width, "height": height}
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in range(0xC0, 0xC4):
                height, width = struct.unpack(">HH", data[index + 5 : index + 9])
                return {"width": width, "height": height}
            if index + 4 > len(data):
                break
            segment_length = struct.unpack(">H", data[index + 2 : index + 4])[0]
            index += max(segment_length + 2, 2)
    return {}


def _text_semantics(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    return {
        "line_count": len(lines),
        "nonempty_line_count": sum(bool(line.strip()) for line in lines),
        "preview": "\n".join(line[:300] for line in lines[:20])[:2000],
    }


def _classify(path: Path, data: bytes, text_value: str | None, truncated: bool) -> tuple[str, str, dict[str, Any]]:
    suffix = path.suffix.lower()
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if suffix == ".py" and text_value is not None:
        return "python", "text/x-python", _python_semantics(text_value)
    if suffix == ".ipynb" and text_value is not None:
        try:
            return "notebook", "application/x-ipynb+json", _notebook_semantics(json.loads(text_value))
        except json.JSONDecodeError as exc:
            return "notebook", "application/x-ipynb+json", {"parse_error": f"line {exc.lineno}"}
    if suffix == ".json" and text_value is not None:
        try:
            return "json", "application/json", _structured_semantics(json.loads(text_value))
        except json.JSONDecodeError as exc:
            return "json", "application/json", {"parse_error": f"line {exc.lineno}"}
    if suffix == ".toml" and text_value is not None:
        try:
            return "toml", "application/toml", _structured_semantics(tomllib.loads(text_value))
        except tomllib.TOMLDecodeError as exc:
            return "toml", "application/toml", {"parse_error": str(exc)[:300]}
    if suffix in {".yaml", ".yml"} and text_value is not None:
        keys = sorted(set(re.findall(r"(?m)^([A-Za-z0-9_.-]+):", text_value)))
        return "yaml", "application/yaml", {"top_level_keys": keys[:500], "line_count": len(text_value.splitlines())}
    if suffix in {".md", ".markdown", ".rst"} and text_value is not None:
        return "markdown", media_type, _markdown_semantics(text_value)
    if suffix in {".pkl", ".pickle"}:
        return "pickle", "application/x-python-pickle", _pickle_semantics(data)
    if suffix in {".zip", ".whl", ".jar", ".tar", ".tgz", ".gz", ".bz2", ".xz"}:
        return "archive", media_type, _archive_semantics(path, suffix)
    if suffix in {".png", ".jpg", ".jpeg", ".gif"}:
        return "image", media_type, _image_semantics(data)
    if suffix == ".pdf" or data.startswith(b"%PDF-"):
        return "pdf", "application/pdf", {"page_markers": data.count(b"/Type /Page"), "has_metadata": b"/Info" in data}
    if data.startswith(b"\x7fELF"):
        return "executable", "application/x-executable", {"container": "ELF", "class_bits": 64 if data[4:5] == b"\x02" else 32}
    if data[:4] in {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe"}:
        return "executable", "application/x-mach-binary", {"container": "Mach-O"}
    if text_value is not None and (suffix in _TEXT_SUFFIXES or len(data) < 2_000_000):
        semantic = _text_semantics(text_value)
        semantic["sample_truncated"] = truncated
        return "text", media_type if media_type.startswith("text/") else "text/plain", semantic
    return "binary", media_type, {"magic_hex": data[:16].hex()}


def _stream_file(path: Path, sample_limit: int = 8 * 1024 * 1024) -> tuple[bytes, int, str, bool]:
    """Read every byte while retaining only a bounded semantic sample."""
    digest = hashlib.sha256()
    sample = bytearray()
    sensitive = False
    carry = b""
    total = 0
    inspect_content = True
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            total += len(chunk)
            digest.update(chunk)
            if len(sample) < sample_limit:
                sample.extend(chunk[: sample_limit - len(sample)])
            if total == len(chunk):
                prefix = chunk[:8192]
                try:
                    prefix.decode("utf-8")
                except UnicodeDecodeError:
                    inspect_content = False
                else:
                    inspect_content = b"\x00" not in prefix
            if inspect_content:
                inspection = carry + chunk
                if _KNOWN_TOKEN_RE.search(inspection) or _PRIVATE_KEY_RE.search(inspection):
                    sensitive = True
                carry = inspection[-512:]
    return bytes(sample), total, digest.hexdigest(), sensitive


def read_record(path: Path, root: Path, source: str) -> FileRecord:
    """Read one source object and return a bounded semantic record."""
    root = root.resolve()
    path = path.parent.resolve() / path.name
    relative = path.relative_to(root).as_posix()
    before = path.lstat()
    if path.is_symlink():
        target = os.readlink(path)
        data = os.fsencode(target)
        kind = "symlink"
        file_format = "symlink"
        media_type = "inode/symlink"
        sensitive = _is_sensitive(path, data)
        semantic = {} if sensitive else {"target": target}
        size = len(data)
        sha256 = hashlib.sha256(data).hexdigest()
    else:
        data, size, sha256, content_sensitive = _stream_file(path)
        kind = "file"
        sensitive = _is_sensitive(path, data) or content_sensitive
        text_value = None if sensitive else _decode_text(data)
        file_format, media_type, semantic = _classify(path, data, text_value, size > len(data))
        if sensitive:
            semantic = {"redacted": True, "detected_by": "name_or_content_policy"}
        else:
            semantic = _sanitize_semantic(semantic)
    after = path.lstat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise IncompleteAssimilationError(f"source changed while reading: {relative}")
    return FileRecord(
        source=source,
        path=relative,
        kind=kind,
        size=size,
        sha256=sha256,
        format=file_format,
        media_type=media_type,
        disposition=(disposition := _disposition(Path(relative), sensitive)),
        capability_cluster=_capability_cluster(Path(relative), disposition),
        understanding=_understanding(Path(relative), file_format, disposition, semantic),
        semantic=semantic,
    )


def _root_digest(records: Iterable[FileRecord]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: (item.source, item.path)):
        digest.update(
            json.dumps(
                {
                    "source": record.source,
                    "path": record.path,
                    "kind": record.kind,
                    "size": record.size,
                    "sha256": record.sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def summarize(source: str, records: list[FileRecord]) -> SourceSummary:
    return SourceSummary(
        source=source,
        file_count=len(records),
        total_bytes=sum(record.size for record in records),
        root_digest=_root_digest(records),
        format_counts=dict(sorted(Counter(record.format for record in records).items())),
        disposition_counts=dict(sorted(Counter(record.disposition for record in records).items())),
        capability_counts=dict(sorted(Counter(record.capability_cluster for record in records).items())),
        unreadable_count=sum(record.read_error is not None for record in records),
    )


def verify_complete(root: Path, records: Iterable[FileRecord], source: str) -> None:
    records = list(records)
    live = {path.relative_to(root.resolve()).as_posix() for path in inventory(root)}
    recorded = [record.path for record in records if record.source == source]
    duplicates = sorted(path for path, count in Counter(recorded).items() if count > 1)
    missing = sorted(live - set(recorded))
    extra = sorted(set(recorded) - live)
    unreadable = sorted(record.path for record in records if record.source == source and record.read_error)
    invalid = sorted(record.path for record in records if record.source == source and record.disposition not in DISPOSITIONS)
    if missing or extra or duplicates or unreadable or invalid:
        details = {
            "missing": missing[:20],
            "extra": extra[:20],
            "duplicates": duplicates[:20],
            "unreadable": unreadable[:20],
            "invalid_disposition": invalid[:20],
        }
        raise IncompleteAssimilationError(json.dumps(details, sort_keys=True))


def assimilate_source(root: Path, source: str) -> AssimilationResult:
    root = root.resolve()
    records: list[FileRecord] = []
    for path in inventory(root):
        try:
            records.append(read_record(path, root, source))
        except (OSError, IncompleteAssimilationError) as exc:
            relative = path.relative_to(root).as_posix()
            records.append(
                FileRecord(
                    source=source,
                    path=relative,
                    kind="symlink" if path.is_symlink() else "file",
                    size=path.lstat().st_size,
                    sha256="",
                    format="unreadable",
                    media_type="application/octet-stream",
                    disposition="restricted",
                    capability_cluster="governance_provenance",
                    understanding={"role": "unreadable_source_object"},
                    semantic={},
                    read_error=f"{type(exc).__name__}: {exc}",
                )
            )
    verify_complete(root, records, source)
    return AssimilationResult(records=records, summary=summarize(source, records))


def public_summary(results: Iterable[AssimilationResult]) -> dict[str, Any]:
    """Return a tracked-safe summary containing aliases and aggregates only."""
    summaries = [result.summary.to_dict() for result in results]
    return {"schema_version": 1, "sources": sorted(summaries, key=lambda item: item["source"])}


def write_private_manifest(
    destination: Path,
    roots: dict[str, Path],
    results: Iterable[AssimilationResult],
) -> None:
    """Write local-only evidence, including roots needed for live verification."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    normalized_roots = {alias: str(path.resolve()) for alias, path in sorted(roots.items())}
    with destination.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "manifest", "schema_version": 1, "roots": normalized_roots}, sort_keys=True) + "\n")
        for result in sorted(results, key=lambda item: item.summary.source):
            for record in sorted(result.records, key=lambda item: item.path):
                handle.write(json.dumps({"type": "file", **record.to_dict()}, sort_keys=True) + "\n")


def load_private_manifest(path: Path) -> tuple[dict[str, Path], list[FileRecord]]:
    roots: dict[str, Path] = {}
    records: list[FileRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            value = json.loads(line)
            if line_number == 1 and value.get("type") == "manifest":
                roots = {alias: Path(root) for alias, root in value.get("roots", {}).items()}
                continue
            if value.pop("type", None) != "file":
                raise IncompleteAssimilationError(f"invalid manifest record at line {line_number}")
            records.append(FileRecord(**value))
    if not roots:
        raise IncompleteAssimilationError("manifest contains no source roots")
    return roots, records


def verify_manifest(path: Path) -> list[SourceSummary]:
    roots, records = load_private_manifest(path)
    summaries: list[SourceSummary] = []
    aliases_in_records = {record.source for record in records}
    if aliases_in_records != set(roots):
        raise IncompleteAssimilationError("manifest source aliases do not match root aliases")
    for alias, root in sorted(roots.items()):
        source_records = [record for record in records if record.source == alias]
        verify_complete(root, source_records, alias)
        current = assimilate_source(root, alias)
        recorded_summary = summarize(alias, source_records)
        if current.summary.root_digest != recorded_summary.root_digest:
            raise IncompleteAssimilationError(f"source content changed after manifest creation: {alias}")
        summaries.append(recorded_summary)
    return summaries
