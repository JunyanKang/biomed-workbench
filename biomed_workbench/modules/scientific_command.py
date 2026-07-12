"""Bounded, shell-free execution for version-gated scientific commands."""

from __future__ import annotations

import hashlib
import importlib.util
import math
import os
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import zipfile
from typing import Any, Callable, Mapping

from ..kernel.artifact_store import ArtifactPayload, ProjectArtifactStore
from ..kernel.identity import digest_value, freeze_mapping, thaw, validate_identifier


_EXECUTABLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
_PLACEHOLDER_RE = re.compile(r"^\{(input|output|parameter):([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\}$")
_PARAMETER_TEMPLATE_RE = re.compile(r"\{parameter:([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\}")
_OUTPUT_DIRECTORY_PLACEHOLDER = "{output-directory}"
_IMPLEMENTATION_PLACEHOLDER = "{implementation}"
_IMPLEMENTATION_MODULE_RE = re.compile(r"^biomed_workbench\.implementations\.[a-z_][a-z0-9_]*$")


class ScientificCommandError(RuntimeError):
    """A path- and secret-free failure from scientific command execution."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"scientific command failed: {code}")


def _filename(value: str, location: str) -> str:
    if not isinstance(value, str) or not _FILENAME_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"{location} must be one safe runtime filename")
    return value


@dataclass(frozen=True)
class CommandInput:
    name: str
    port: str
    role: str
    filename: str
    materialization: str = "file"
    member: str | None = None
    sidecar_for: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_identifier(self.name, "command input name"))
        object.__setattr__(self, "port", validate_identifier(self.port, "command input port"))
        object.__setattr__(self, "role", validate_identifier(self.role, "command input role"))
        object.__setattr__(self, "filename", _filename(self.filename, "command input filename"))
        if self.materialization not in {"file", "zip-directory"}:
            raise ValueError("command input materialization is unsupported")
        if self.member is not None:
            if self.materialization != "zip-directory":
                raise ValueError("command input members require zip-directory materialization")
            member = Path(self.member)
            if member.is_absolute() or ".." in member.parts or len(member.parts) != 1:
                raise ValueError("command input member must be one safe archive-root filename")
            object.__setattr__(self, "member", _filename(self.member, "command input member"))
        if self.sidecar_for is not None:
            object.__setattr__(self, "sidecar_for", validate_identifier(self.sidecar_for, "command input sidecar target"))
            if self.materialization != "file" or self.member is not None:
                raise ValueError("command input sidecars must be ordinary files")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CommandInput":
        allowed = {"name", "port", "role", "filename", "materialization", "member", "sidecar_for"}
        if not {"name", "port", "role", "filename"} <= set(payload) or set(payload) - allowed:
            raise ValueError("command input fields are incomplete or unsupported")
        values = dict(payload)
        values.setdefault("materialization", "file")
        values.setdefault("member", None)
        values.setdefault("sidecar_for", None)
        return cls(**values)


@dataclass(frozen=True)
class CommandOutput:
    name: str
    port: str
    role: str
    filename: str
    media_type: str
    capture: str = "file"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_identifier(self.name, "command output name"))
        object.__setattr__(self, "port", validate_identifier(self.port, "command output port"))
        object.__setattr__(self, "role", validate_identifier(self.role, "command output role"))
        object.__setattr__(self, "filename", _filename(self.filename, "command output filename"))
        if self.capture not in {"file", "derived", "stdout", "stderr"}:
            raise ValueError("command output capture is unsupported")
        if self.capture in {"stdout", "stderr"} and not (self.media_type.startswith("text/") or self.media_type in {"application/json", "application/xml"}):
            raise ValueError("captured command streams require a text media type")
        ArtifactPayload(
            role=self.role,
            object_key=f"sha256/{'0' * 2}/{'0' * 64}/payload",
            media_type=self.media_type,
            byte_size=0,
            sha256="0" * 64,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CommandOutput":
        allowed = {"name", "port", "role", "filename", "media_type", "capture"}
        if not {"name", "port", "role", "filename", "media_type"} <= set(payload) or set(payload) - allowed:
            raise ValueError("command output fields are incomplete or unsupported")
        values = dict(payload)
        values.setdefault("capture", "file")
        return cls(**values)


@dataclass(frozen=True)
class ScientificCommand:
    tool_name: str
    executable: str
    arguments: tuple[str, ...]
    inputs: tuple[CommandInput, ...]
    outputs: tuple[CommandOutput, ...]
    parameter_names: tuple[str, ...]
    timeout_seconds: int
    max_output_bytes: int
    max_payload_bytes: int
    working_directory_input: str | None = None
    path_mode: str = "absolute"
    implementation_module: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_name", validate_identifier(self.tool_name, "command tool name"))
        if not isinstance(self.executable, str) or not _EXECUTABLE_RE.fullmatch(self.executable):
            raise ValueError("command executable must be a path-free executable identity")
        inputs = tuple(self.inputs)
        outputs = tuple(self.outputs)
        parameter_names = tuple(validate_identifier(value, "command parameter name") for value in self.parameter_names)
        if not inputs or not outputs or not self.arguments:
            raise ValueError("scientific command requires inputs, outputs, and arguments")
        for values, location in ((inputs, "inputs"), (outputs, "outputs")):
            if len({item.name for item in values}) != len(values):
                raise ValueError(f"command {location} contain duplicate names")
            if len({item.filename for item in values}) != len(values):
                raise ValueError(f"command {location} contain duplicate filenames")
            if len({(item.port, item.role) for item in values}) != len(values):
                raise ValueError(f"command {location} contain duplicate port-role bindings")
        if len(set(parameter_names)) != len(parameter_names):
            raise ValueError("command parameter names contain duplicates")
        input_by_name = {item.name: item for item in inputs}
        for item in inputs:
            if item.sidecar_for is None:
                continue
            target = input_by_name.get(item.sidecar_for)
            if target is None or target.sidecar_for is not None or item.name == target.name:
                raise ValueError("command input sidecar must reference one primary input")
            if not item.filename.startswith(target.filename + "."):
                raise ValueError("command input sidecar filename must extend its primary input filename")
        captures = [item.capture for item in outputs if item.capture in {"stdout", "stderr"}]
        if len(set(captures)) != len(captures):
            raise ValueError("command output streams may each be captured once")
        if self.working_directory_input is not None:
            matches = [item for item in inputs if item.name == self.working_directory_input]
            if len(matches) != 1 or matches[0].materialization != "zip-directory":
                raise ValueError("command working directory must name one zip-directory input")
        if self.path_mode not in {"absolute", "workdir-relative"}:
            raise ValueError("command path mode is unsupported")
        if self.implementation_module is not None:
            if not _IMPLEMENTATION_MODULE_RE.fullmatch(self.implementation_module) or self.executable not in {"python", "python3"}:
                raise ValueError("command implementation module requires a path-free Python module and interpreter")
            if not self.arguments or self.arguments[0] != _IMPLEMENTATION_PLACEHOLDER or self.arguments.count(_IMPLEMENTATION_PLACEHOLDER) != 1:
                raise ValueError("command implementation module must be the first and only implementation placeholder")
        elif _IMPLEMENTATION_PLACEHOLDER in self.arguments:
            raise ValueError("command implementation placeholder requires a declared module")
        references = {"input": set(), "output": set(), "parameter": set()}
        output_directory_referenced = False
        arguments = []
        for argument in self.arguments:
            if not isinstance(argument, str) or not argument or "\x00" in argument:
                raise ValueError("command arguments must be nonempty strings without NUL bytes")
            match = _PLACEHOLDER_RE.fullmatch(argument)
            if argument == _OUTPUT_DIRECTORY_PLACEHOLDER:
                output_directory_referenced = True
            elif argument == _IMPLEMENTATION_PLACEHOLDER:
                pass
            elif match:
                references[match.group(1)].add(match.group(2))
            elif "{" in argument or "}" in argument:
                parameter_references = _PARAMETER_TEMPLATE_RE.findall(argument)
                remainder = _PARAMETER_TEMPLATE_RE.sub("", argument)
                if not parameter_references or "{" in remainder or "}" in remainder:
                    raise ValueError("only scalar parameters may appear inside fixed command argument templates")
                references["parameter"].update(parameter_references)
            arguments.append(argument)
        expected = {
            "input": {item.name for item in inputs if item.sidecar_for is None},
            "output": {item.name for item in outputs if item.capture == "file"},
            "parameter": set(parameter_names),
        }
        output_binding_valid = references["output"] == expected["output"] and not output_directory_referenced
        output_directory_valid = not references["output"] and output_directory_referenced
        stream_only_valid = not expected["output"] and not references["output"] and not output_directory_referenced
        if references["input"] != expected["input"] or references["parameter"] != expected["parameter"] or not (output_binding_valid or output_directory_valid or stream_only_valid):
            raise ValueError("command argument placeholders differ from declared bindings")
        for value, location in (
            (self.timeout_seconds, "timeout"),
            (self.max_output_bytes, "output limit"),
            (self.max_payload_bytes, "payload limit"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"command {location} must be a positive integer")
        object.__setattr__(self, "arguments", tuple(arguments))
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "parameter_names", parameter_names)

    def to_dict(self) -> dict[str, object]:
        input_rows = []
        for item in self.inputs:
            row = {"name": item.name, "port": item.port, "role": item.role, "filename": item.filename}
            if item.materialization != "file":
                row["materialization"] = item.materialization
            if item.member is not None:
                row["member"] = item.member
            if item.sidecar_for is not None:
                row["sidecar_for"] = item.sidecar_for
            input_rows.append(row)
        payload = {
            "tool_name": self.tool_name,
            "executable": self.executable,
            "arguments": list(self.arguments),
            "inputs": input_rows,
            "outputs": [],
            "parameter_names": list(self.parameter_names),
            "timeout_seconds": self.timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
            "max_payload_bytes": self.max_payload_bytes,
        }
        for item in self.outputs:
            row = {"name": item.name, "port": item.port, "role": item.role, "filename": item.filename, "media_type": item.media_type}
            if item.capture != "file":
                row["capture"] = item.capture
            payload["outputs"].append(row)
        if self.working_directory_input is not None:
            payload["working_directory_input"] = self.working_directory_input
        if self.path_mode != "absolute":
            payload["path_mode"] = self.path_mode
        if self.implementation_module is not None:
            payload["implementation_module"] = self.implementation_module
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ScientificCommand":
        expected = {
            "tool_name",
            "executable",
            "arguments",
            "inputs",
            "outputs",
            "parameter_names",
            "timeout_seconds",
            "max_output_bytes",
            "max_payload_bytes",
        }
        optional = {"working_directory_input", "path_mode", "implementation_module"}
        if not isinstance(payload, Mapping) or not expected <= set(payload) or set(payload) - expected - optional:
            raise ValueError("scientific command fields are incomplete or unsupported")
        values = dict(payload)
        if (
            not isinstance(values["inputs"], list)
            or not isinstance(values["outputs"], list)
            or any(not isinstance(item, Mapping) for item in (*values["inputs"], *values["outputs"]))
        ):
            raise ValueError("scientific command inputs and outputs must be lists")
        if not isinstance(values["arguments"], list) or not isinstance(values["parameter_names"], list):
            raise ValueError("scientific command arguments and parameter names must be lists")
        values["inputs"] = tuple(CommandInput.from_dict(item) for item in values["inputs"])
        values["outputs"] = tuple(CommandOutput.from_dict(item) for item in values["outputs"])
        values["arguments"] = tuple(values["arguments"])
        values["parameter_names"] = tuple(values["parameter_names"])
        values.setdefault("working_directory_input", None)
        values.setdefault("path_mode", "absolute")
        values.setdefault("implementation_module", None)
        return cls(**values)


@dataclass(frozen=True)
class ScientificCommandResult:
    stdout: str
    stderr: str
    output_payloads: tuple[ArtifactPayload, ...]
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, object]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output_payloads": [payload.to_dict() for payload in self.output_payloads],
            "provenance": thaw(self.provenance),
        }


def _parameter(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if (
        isinstance(value, str)
        and value
        and not value.startswith("-")
        and not any(marker in value for marker in ("/", "\\", "file://", "\x00"))
        and not any(character in value for character in ("\r", "\n", "\t"))
    ):
        return value
    raise ScientificCommandError("INVALID_PARAMETER")


def _kill(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.kill()
        except ProcessLookupError:
            return


def _bounded_process(
    argv: tuple[str, ...],
    *,
    executable: Path | None = None,
    cwd: Path,
    environment: dict[str, str],
    timeout: int,
    output_limit: int,
    payload_root: Path,
    payload_limit: int,
) -> tuple[str, str]:
    try:
        process = subprocess.Popen(
            argv,
            executable=str(executable) if executable is not None else None,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
    except OSError as exc:
        raise ScientificCommandError("PROCESS_START_FAILED") from exc

    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    lock = threading.Lock()
    overflow = threading.Event()

    def read_stream(name: str, stream) -> None:
        while chunk := stream.read(65536):
            with lock:
                total = len(buffers["stdout"]) + len(buffers["stderr"])
                remaining = output_limit - total
                if remaining <= 0 or len(chunk) > remaining:
                    if remaining > 0:
                        buffers[name].extend(chunk[:remaining])
                    overflow.set()
                    return
                buffers[name].extend(chunk)

    threads = (
        threading.Thread(target=read_stream, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=read_stream, args=("stderr", process.stderr), daemon=True),
    )
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    failure_code = None
    while process.poll() is None:
        if overflow.is_set():
            failure_code = "OUTPUT_LIMIT_EXCEEDED"
            _kill(process)
            break
        if time.monotonic() >= deadline:
            failure_code = "PROCESS_TIMEOUT"
            _kill(process)
            break
        try:
            payload_bytes = sum(path.lstat().st_size for path in payload_root.rglob("*") if path.is_file() and not path.is_symlink())
        except OSError:
            failure_code = "INVALID_OUTPUT"
            _kill(process)
            break
        if payload_bytes > payload_limit:
            failure_code = "PAYLOAD_LIMIT_EXCEEDED"
            _kill(process)
            break
        time.sleep(0.01)
    process.wait()
    for thread in threads:
        thread.join(timeout=1)
    process.stdout.close()
    process.stderr.close()
    if failure_code:
        raise ScientificCommandError(failure_code)
    if overflow.is_set():
        raise ScientificCommandError("OUTPUT_LIMIT_EXCEEDED")
    if process.returncode != 0:
        raise ScientificCommandError("PROCESS_FAILED")
    return buffers["stdout"].decode("utf-8", errors="replace"), buffers["stderr"].decode("utf-8", errors="replace")


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_zip_directory(archive_path: Path, target: Path) -> str:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if not members or len(members) > 5000 or sum(item.file_size for item in members) > 200_000_000:
                raise ScientificCommandError("INVALID_INPUT_ARCHIVE")
            target.mkdir()
            for item in members:
                relative = Path(*Path(item.filename).parts)
                mode = item.external_attr >> 16
                if "\\" in item.filename or relative.is_absolute() or ".." in relative.parts or item.flag_bits & 0x1 or (mode & 0o170000) == 0o120000:
                    raise ScientificCommandError("INVALID_INPUT_ARCHIVE")
                destination = target / relative
                if item.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                destination.chmod(0o444)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, ScientificCommandError):
            raise
        raise ScientificCommandError("INVALID_INPUT_ARCHIVE") from exc
    return _digest_tree(target)


def _digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise ScientificCommandError("INVALID_INPUT_ARCHIVE")
        digest.update(("d" if path.is_dir() else "f").encode())
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(str(path.stat().st_size).encode())
            digest.update(_digest_file(path).encode())
    return digest.hexdigest()


def execute_scientific_command(
    command: ScientificCommand,
    *,
    store: ProjectArtifactStore,
    input_payloads: Mapping[str, ArtifactPayload],
    parameters: Mapping[str, Any],
    tool_versions: Mapping[str, str],
    dependency_versions: Mapping[str, str],
    compatibility_row_id: str,
    executable_resolver: Callable[[str], str | os.PathLike[str] | None] | None = None,
    implementation_resolver: Callable[[str], str | os.PathLike[str] | None] | None = None,
) -> ScientificCommandResult:
    if command.tool_name not in tool_versions or not _TOKEN_RE.fullmatch(str(tool_versions[command.tool_name])):
        raise ScientificCommandError("UNVERIFIED_TOOL_VERSION")
    if not isinstance(compatibility_row_id, str) or not _TOKEN_RE.fullmatch(compatibility_row_id):
        raise ScientificCommandError("INVALID_COMPATIBILITY_ROW")
    if set(input_payloads) != {item.name for item in command.inputs} or any(not isinstance(item, ArtifactPayload) for item in input_payloads.values()):
        raise ScientificCommandError("INVALID_INPUT_BINDING")
    if any(input_payloads[binding.name].role != binding.role for binding in command.inputs):
        raise ScientificCommandError("INVALID_INPUT_BINDING")
    if set(parameters) != set(command.parameter_names):
        raise ScientificCommandError("INVALID_PARAMETER")
    normalized_parameters = {name: _parameter(parameters[name]) for name in command.parameter_names}
    versions = {str(name): str(version) for name, version in tool_versions.items()}
    dependencies = {str(name): str(version) for name, version in dependency_versions.items()}
    if any(not _TOKEN_RE.fullmatch(name) or not _TOKEN_RE.fullmatch(version) for name, version in (*versions.items(), *dependencies.items())):
        raise ScientificCommandError("UNVERIFIED_DEPENDENCY_VERSION")

    resolve_executable = executable_resolver or shutil.which
    executable = resolve_executable(command.executable)
    if executable is None:
        raise ScientificCommandError("MISSING_EXECUTABLE")
    try:
        executable_path = Path(executable).resolve(strict=True)
    except OSError as exc:
        raise ScientificCommandError("MISSING_EXECUTABLE") from exc
    if not executable_path.is_file() or not os.access(executable_path, os.X_OK):
        raise ScientificCommandError("INVALID_EXECUTABLE")
    executable_sha256 = _digest_file(executable_path)
    implementation_path = None
    implementation_sha256 = None
    if command.implementation_module is not None:
        if implementation_resolver is not None:
            implementation = implementation_resolver(command.implementation_module)
        else:
            try:
                specification = importlib.util.find_spec(command.implementation_module)
            except (ImportError, AttributeError, ValueError):
                specification = None
            implementation = specification.origin if specification is not None else None
        if implementation is None:
            raise ScientificCommandError("MISSING_IMPLEMENTATION")
        unresolved_implementation = Path(implementation)
        if unresolved_implementation.is_symlink():
            raise ScientificCommandError("INVALID_IMPLEMENTATION")
        try:
            implementation_path = unresolved_implementation.resolve(strict=True)
        except OSError as exc:
            raise ScientificCommandError("MISSING_IMPLEMENTATION") from exc
        if implementation_resolver is None:
            implementation_root = Path(__file__).resolve().parents[1] / "implementations"
            try:
                implementation_path.relative_to(implementation_root.resolve(strict=True))
            except (OSError, ValueError) as exc:
                raise ScientificCommandError("INVALID_IMPLEMENTATION") from exc
        if not implementation_path.is_file() or implementation_path.suffix != ".py":
            raise ScientificCommandError("INVALID_IMPLEMENTATION")
        implementation_sha256 = _digest_file(implementation_path)

    runs_root = store.root / ".runs"
    runs_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="command-", dir=runs_root) as temporary:
        workdir = Path(temporary)
        input_root = workdir / "inputs"
        output_root = workdir / "outputs"
        home_root = workdir / "home"
        temp_root = workdir / "tmp"
        for directory in (input_root, output_root, home_root, temp_root):
            directory.mkdir()
        runtime_implementation = None
        if implementation_path is not None:
            runtime_implementation = input_root / "implementation.py"
            shutil.copyfile(implementation_path, runtime_implementation)
            runtime_implementation.chmod(0o444)
        runtime_inputs = {}
        runtime_input_roots = {}
        materialized_inputs = {}
        input_tree_digests = {}
        for binding in command.inputs:
            payload = input_payloads[binding.name]
            if binding.materialization == "file":
                target = input_root / binding.filename
                store.materialize(payload, target)
                target.chmod(0o444)
                runtime_inputs[binding.name] = target
                runtime_input_roots[binding.name] = None
                materialized_inputs[binding.name] = target
            else:
                archive_path = input_root / f"{binding.filename}.zip"
                store.materialize(payload, archive_path)
                archive_path.chmod(0o444)
                target = input_root / binding.filename
                input_tree_digests[binding.name] = _extract_zip_directory(archive_path, target)
                runtime_input_roots[binding.name] = target
                runtime_inputs[binding.name] = target / binding.member if binding.member else target
                if binding.member and (not runtime_inputs[binding.name].is_file() or runtime_inputs[binding.name].is_symlink()):
                    raise ScientificCommandError("INVALID_INPUT_ARCHIVE")
                materialized_inputs[binding.name] = archive_path
        runtime_outputs = {binding.name: output_root / binding.filename for binding in command.outputs}
        execution_cwd = runtime_input_roots[command.working_directory_input] if command.working_directory_input else workdir

        def runtime_argument(path: Path) -> str:
            if command.path_mode == "workdir-relative":
                return os.path.relpath(path, execution_cwd)
            return str(path)

        argv = [command.executable if command.path_mode == "workdir-relative" else str(executable_path)]
        for argument in command.arguments:
            match = _PLACEHOLDER_RE.fullmatch(argument)
            if argument == _OUTPUT_DIRECTORY_PLACEHOLDER:
                argv.append(runtime_argument(output_root))
            elif argument == _IMPLEMENTATION_PLACEHOLDER:
                argv.append(runtime_argument(runtime_implementation))
            elif not match:
                argv.append(_PARAMETER_TEMPLATE_RE.sub(lambda item: normalized_parameters[item.group(1)], argument))
            elif match.group(1) == "input":
                argv.append(runtime_argument(runtime_inputs[match.group(2)]))
            elif match.group(1) == "output":
                argv.append(runtime_argument(runtime_outputs[match.group(2)]))
            else:
                argv.append(normalized_parameters[match.group(2)])
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home_root),
            "TMPDIR": str(temp_root),
            "LANG": "C",
            "LC_ALL": "C",
        }
        if os.name == "nt" and "SYSTEMROOT" in os.environ:
            environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        stdout, stderr = _bounded_process(
            tuple(argv),
            executable=executable_path if command.path_mode == "workdir-relative" else None,
            cwd=execution_cwd,
            environment=environment,
            timeout=command.timeout_seconds,
            output_limit=command.max_output_bytes,
            payload_root=output_root,
            payload_limit=command.max_payload_bytes,
        )
        captured_streams = {"stdout": stdout, "stderr": stderr}
        for binding in command.outputs:
            if binding.capture in {"stdout", "stderr"}:
                try:
                    runtime_outputs[binding.name].write_text(captured_streams[binding.capture], encoding="utf-8")
                except OSError as exc:
                    raise ScientificCommandError("INVALID_OUTPUT") from exc
        if _digest_file(executable_path) != executable_sha256:
            raise ScientificCommandError("EXECUTABLE_DRIFT")
        if implementation_path is not None and (
            _digest_file(implementation_path) != implementation_sha256 or _digest_file(runtime_implementation) != implementation_sha256
        ):
            raise ScientificCommandError("IMPLEMENTATION_DRIFT")
        for binding in command.inputs:
            if _digest_file(materialized_inputs[binding.name]) != input_payloads[binding.name].sha256:
                raise ScientificCommandError("INPUT_MUTATION")
            if binding.materialization == "zip-directory" and _digest_tree(runtime_input_roots[binding.name]) != input_tree_digests[binding.name]:
                raise ScientificCommandError("INPUT_MUTATION")
        declared_paths = {binding.filename for binding in command.outputs}
        observed_paths = {path.name for path in output_root.iterdir()}
        if observed_paths - declared_paths:
            raise ScientificCommandError("UNDECLARED_OUTPUT")
        if declared_paths - observed_paths:
            raise ScientificCommandError("MISSING_OUTPUT")
        output_payloads = []
        total_payload_bytes = 0
        for binding in command.outputs:
            path = runtime_outputs[binding.name]
            try:
                file_stat = path.lstat()
            except OSError as exc:
                raise ScientificCommandError("MISSING_OUTPUT") from exc
            if path.is_symlink() or not path.is_file():
                raise ScientificCommandError("INVALID_OUTPUT")
            total_payload_bytes += file_stat.st_size
            if total_payload_bytes > command.max_payload_bytes:
                raise ScientificCommandError("PAYLOAD_LIMIT_EXCEEDED")
            output_payloads.append(store.import_file(path, role=binding.role, media_type=binding.media_type))

    provenance = {
        "command_contract_digest": digest_value(command.to_dict()),
        "executable_sha256": executable_sha256,
        "executable_argv0": command.executable,
        "compatibility_row_id": compatibility_row_id,
        "tools": versions,
        "dependencies": dependencies,
        "parameters": normalized_parameters,
        "inputs": {
            name: {"role": payload.role, "sha256": payload.sha256, "byte_size": payload.byte_size}
            for name, payload in sorted(input_payloads.items())
        },
        "outputs": [payload.to_dict() for payload in output_payloads],
    }
    if command.implementation_module is not None:
        provenance["implementation"] = {"module": command.implementation_module, "sha256": implementation_sha256}
    return ScientificCommandResult(stdout, stderr, tuple(output_payloads), provenance)
