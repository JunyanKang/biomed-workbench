"""Bounded, shell-free execution for version-gated scientific commands."""

from __future__ import annotations

import hashlib
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
from typing import Any, Callable, Mapping

from ..kernel.artifact_store import ArtifactPayload, ProjectArtifactStore
from ..kernel.identity import digest_value, freeze_mapping, thaw, validate_identifier


_EXECUTABLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
_PLACEHOLDER_RE = re.compile(r"^\{(input|output|parameter):([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\}$")


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_identifier(self.name, "command input name"))
        object.__setattr__(self, "port", validate_identifier(self.port, "command input port"))
        object.__setattr__(self, "role", validate_identifier(self.role, "command input role"))
        object.__setattr__(self, "filename", _filename(self.filename, "command input filename"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CommandInput":
        if set(payload) != {"name", "port", "role", "filename"}:
            raise ValueError("command input fields are incomplete or unsupported")
        return cls(**dict(payload))


@dataclass(frozen=True)
class CommandOutput:
    name: str
    port: str
    role: str
    filename: str
    media_type: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_identifier(self.name, "command output name"))
        object.__setattr__(self, "port", validate_identifier(self.port, "command output port"))
        object.__setattr__(self, "role", validate_identifier(self.role, "command output role"))
        object.__setattr__(self, "filename", _filename(self.filename, "command output filename"))
        ArtifactPayload(
            role=self.role,
            object_key=f"sha256/{'0' * 2}/{'0' * 64}/payload",
            media_type=self.media_type,
            byte_size=0,
            sha256="0" * 64,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CommandOutput":
        if set(payload) != {"name", "port", "role", "filename", "media_type"}:
            raise ValueError("command output fields are incomplete or unsupported")
        return cls(**dict(payload))


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
        references = {"input": set(), "output": set(), "parameter": set()}
        arguments = []
        for argument in self.arguments:
            if not isinstance(argument, str) or not argument or "\x00" in argument:
                raise ValueError("command arguments must be nonempty strings without NUL bytes")
            match = _PLACEHOLDER_RE.fullmatch(argument)
            if match:
                references[match.group(1)].add(match.group(2))
            elif "{" in argument or "}" in argument:
                raise ValueError("command placeholders must occupy a complete argument")
            arguments.append(argument)
        expected = {
            "input": {item.name for item in inputs},
            "output": {item.name for item in outputs},
            "parameter": set(parameter_names),
        }
        if references != expected:
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
        return {
            "tool_name": self.tool_name,
            "executable": self.executable,
            "arguments": list(self.arguments),
            "inputs": [{"name": item.name, "port": item.port, "role": item.role, "filename": item.filename} for item in self.inputs],
            "outputs": [
                {"name": item.name, "port": item.port, "role": item.role, "filename": item.filename, "media_type": item.media_type}
                for item in self.outputs
            ],
            "parameter_names": list(self.parameter_names),
            "timeout_seconds": self.timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
            "max_payload_bytes": self.max_payload_bytes,
        }

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
        if not isinstance(payload, Mapping) or set(payload) != expected:
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
    if isinstance(value, str) and value and not value.startswith("-") and not any(marker in value for marker in ("/", "\\", "file://", "\x00")):
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
        pass


def _bounded_process(
    argv: tuple[str, ...],
    *,
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
        runtime_inputs = {}
        for binding in command.inputs:
            payload = input_payloads[binding.name]
            target = input_root / binding.filename
            store.materialize(payload, target)
            target.chmod(0o444)
            runtime_inputs[binding.name] = target
        runtime_outputs = {binding.name: output_root / binding.filename for binding in command.outputs}
        argv = [str(executable_path)]
        for argument in command.arguments:
            match = _PLACEHOLDER_RE.fullmatch(argument)
            if not match:
                argv.append(argument)
            elif match.group(1) == "input":
                argv.append(str(runtime_inputs[match.group(2)]))
            elif match.group(1) == "output":
                argv.append(str(runtime_outputs[match.group(2)]))
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
            cwd=workdir,
            environment=environment,
            timeout=command.timeout_seconds,
            output_limit=command.max_output_bytes,
            payload_root=output_root,
            payload_limit=command.max_payload_bytes,
        )
        if _digest_file(executable_path) != executable_sha256:
            raise ScientificCommandError("EXECUTABLE_DRIFT")
        for binding in command.inputs:
            if _digest_file(runtime_inputs[binding.name]) != input_payloads[binding.name].sha256:
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
    return ScientificCommandResult(stdout, stderr, tuple(output_payloads), provenance)
