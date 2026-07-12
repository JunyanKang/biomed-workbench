import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from biomed_workbench.kernel.artifact_store import ProjectArtifactStore
from biomed_workbench.modules.scientific_command import (
    CommandInput,
    CommandOutput,
    ScientificCommand,
    ScientificCommandError,
    execute_scientific_command,
)


def executable(path: Path, body: str) -> Path:
    path.write_text(f"#!/usr/bin/env python3\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def command(**overrides):
    values = {
        "tool_name": "fixture-tool",
        "executable": "fixture-tool",
        "arguments": ("--input", "{input:reads}", "--output", "{output:report}", "--label", "{parameter:label}"),
        "inputs": (CommandInput("reads", "reads", "reads", "reads.fastq"),),
        "outputs": (CommandOutput("report", "report", "report", "report.json", "application/json"),),
        "parameter_names": ("label",),
        "timeout_seconds": 5,
        "max_output_bytes": 4096,
        "max_payload_bytes": 4096,
    }
    values.update(overrides)
    return ScientificCommand(**values)


class ScientificCommandTests(unittest.TestCase):
    def test_materializes_a_digest_bound_companion_index_without_argv_exposure(self):
        indexed = command(
            inputs=(
                CommandInput("reads", "reads", "reads", "reads.fastq"),
                CommandInput("index", "reads", "index", "reads.fastq.idx", sidecar_for="reads"),
            ),
        )
        body = """
import argparse, json, pathlib
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
sidecar = pathlib.Path(args.input + '.idx')
json.dump({'index': sidecar.read_text(encoding='utf-8'), 'argv_has_index': any(value.endswith('.idx') for value in __import__('sys').argv)}, open(args.output, 'w', encoding='utf-8'))
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            source = root / "reads.fastq"
            source.write_text("ACGT\n", encoding="utf-8")
            index = root / "reads.fastq.idx"
            index.write_text("bound-index", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            source_payload = store.import_file(source, role="reads", media_type="text/plain")
            index_payload = store.import_file(index, role="index", media_type="application/octet-stream")
            result = execute_scientific_command(
                indexed,
                store=store,
                input_payloads={"reads": source_payload, "index": index_payload},
                parameters={"label": "sample-01"},
                tool_versions={"fixture-tool": "2.4.1"},
                dependency_versions={"python": "3.14.3"},
                compatibility_row_id="fixture-tool-2.4.1-json-1",
                executable_resolver=lambda _name: tool,
            )
            output = json.loads(store.resolve(result.output_payloads[0]).read_text(encoding="utf-8"))
        self.assertEqual(output, {"index": "bound-index", "argv_has_index": False})
        self.assertEqual(result.provenance["inputs"]["index"]["sha256"], index_payload.sha256)

    def test_imports_declared_derived_sidecar_without_requiring_an_argv_placeholder(self):
        sidecar = command(
            outputs=(
                CommandOutput("report", "report", "report", "report.json", "application/json"),
                CommandOutput("index", "report", "index", "report.json.csi", "application/octet-stream", "derived"),
            ),
        )
        body = """
import argparse, json, pathlib
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
json.dump({'label': args.label}, open(args.output, 'w', encoding='utf-8'))
pathlib.Path(args.output + '.csi').write_bytes(b'validated-index')
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            source = root / "reads.fastq"
            source.write_text("ACGT\n", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(source, role="reads", media_type="text/plain")
            result = execute_scientific_command(
                sidecar,
                store=store,
                input_payloads={"reads": payload},
                parameters={"label": "sample-01"},
                tool_versions={"fixture-tool": "2.4.1"},
                dependency_versions={"python": "3.14.3"},
                compatibility_row_id="fixture-tool-2.4.1-json-1",
                executable_resolver=lambda _name: tool,
            )
        self.assertEqual([payload.role for payload in result.output_payloads], ["report", "index"])

    def test_workdir_relative_path_mode_keeps_machine_paths_out_of_tool_argv(self):
        relative = command(path_mode="workdir-relative")
        body = """
import argparse, json, pathlib
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
json.dump({'input': args.input, 'output': args.output, 'input_absolute': pathlib.Path(args.input).is_absolute()}, open(args.output, 'w', encoding='utf-8'))
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            source = root / "reads.fastq"
            source.write_text("ACGT\n", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(source, role="reads", media_type="text/plain")
            result = execute_scientific_command(
                relative,
                store=store,
                input_payloads={"reads": payload},
                parameters={"label": "sample-01"},
                tool_versions={"fixture-tool": "2.4.1"},
                dependency_versions={"python": "3.14.3"},
                compatibility_row_id="fixture-tool-2.4.1-json-1",
                executable_resolver=lambda _name: tool,
            )
            output = json.loads(store.resolve(result.output_payloads[0]).read_text(encoding="utf-8"))
        self.assertEqual(output, {"input": "inputs/reads.fastq", "output": "outputs/report.json", "input_absolute": False})
        self.assertEqual(result.provenance["executable_argv0"], "fixture-tool")

    def test_renders_validated_scalar_parameters_inside_fixed_argv_templates(self):
        templated = command(
            arguments=(
                "--input", "{input:reads}", "--output", "{output:report}",
                "--read-group", "@RG\\tID:{parameter:label}\\tSM:{parameter:label}",
            ),
        )
        body = """
import argparse, json
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--read-group', required=True)
args = parser.parse_args()
json.dump({'read_group': args.read_group}, open(args.output, 'w', encoding='utf-8'))
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            source = root / "reads.fastq"
            source.write_text("ACGT\n", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(source, role="reads", media_type="text/plain")
            result = execute_scientific_command(
                templated,
                store=store,
                input_payloads={"reads": payload},
                parameters={"label": "sample-01"},
                tool_versions={"fixture-tool": "2.4.1"},
                dependency_versions={"python": "3.14.3"},
                compatibility_row_id="fixture-tool-2.4.1-json-1",
                executable_resolver=lambda _name: tool,
            )
            output = json.loads(store.resolve(result.output_payloads[0]).read_text(encoding="utf-8"))
        self.assertEqual(output["read_group"], "@RG\\tID:sample-01\\tSM:sample-01")

    def test_captures_text_stdout_as_a_declared_content_addressed_output(self):
        captured = command(
            arguments=("--input", "{input:reads}", "--label", "{parameter:label}"),
            outputs=(CommandOutput("report", "report", "report", "report.json", "application/json", "stdout"),),
        )
        body = """
import argparse, json
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
print(json.dumps({'label': args.label, 'input_is_materialized': bool(open(args.input).read())}, sort_keys=True))
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            source = root / "reads.fastq"
            source.write_text("ACGT\n", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(source, role="reads", media_type="text/plain")

            result = execute_scientific_command(
                captured,
                store=store,
                input_payloads={"reads": payload},
                parameters={"label": "treated"},
                tool_versions={"fixture-tool": "2.4.1"},
                dependency_versions={"python": "3.14.3"},
                compatibility_row_id="fixture-tool-2.4.1-json-1",
                executable_resolver=lambda _name: tool,
            )
            output = json.loads(store.resolve(result.output_payloads[0]).read_text(encoding="utf-8"))

        self.assertEqual(output, {"input_is_materialized": True, "label": "treated"})
        self.assertEqual(result.stdout, json.dumps(output, sort_keys=True) + "\n")

    def test_safely_materializes_a_read_only_zip_collection_for_aggregate_tools(self):
        body = """
import argparse, json, pathlib
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
files = sorted(path.name for path in pathlib.Path(args.input).rglob('*') if path.is_file())
json.dump({'files': files}, open(args.output, 'w', encoding='utf-8'))
"""
        aggregate = command(
            inputs=(CommandInput("reads", "reads", "reads", "qc-inputs", "zip-directory"),),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            bundle = root / "reports.zip"
            with zipfile.ZipFile(bundle, "w") as output:
                output.writestr("sample-a/fastqc_data.txt", "PASS")
                output.writestr("sample-b/fastqc_data.txt", "WARN")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(bundle, role="reads", media_type="application/zip")

            result = execute_scientific_command(
                aggregate,
                store=store,
                input_payloads={"reads": payload},
                parameters={"label": "cohort"},
                tool_versions={"fixture-tool": "2.4.1"},
                dependency_versions={"python": "3.14.3"},
                compatibility_row_id="fixture-tool-2.4.1-json-1",
                executable_resolver=lambda _name: tool,
            )

            output = json.loads(store.resolve(result.output_payloads[0]).read_text(encoding="utf-8"))
        self.assertEqual(output["files"], ["fastqc_data.txt", "fastqc_data.txt"])

    def test_archive_member_and_bounded_input_working_directory_support_reference_bundles(self):
        body = """
import argparse, json, pathlib
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
config = pathlib.Path(args.input).read_text(encoding='utf-8').strip()
reference = pathlib.Path(config).read_text(encoding='utf-8').strip()
json.dump({'reference': reference, 'cwd': pathlib.Path.cwd().name}, open(args.output, 'w', encoding='utf-8'))
"""
        reference_command = command(
            inputs=(CommandInput("reads", "reads", "reads", "reference-bundle", "zip-directory", "screen.conf"),),
            working_directory_input="reads",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            bundle = root / "reference.zip"
            with zipfile.ZipFile(bundle, "w") as output:
                output.writestr("screen.conf", "reference.txt\n")
                output.writestr("reference.txt", "validated-reference\n")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(bundle, role="reads", media_type="application/zip")

            result = execute_scientific_command(
                reference_command,
                store=store,
                input_payloads={"reads": payload},
                parameters={"label": "screen"},
                tool_versions={"fixture-tool": "2.4.1"},
                dependency_versions={"python": "3.14.3"},
                compatibility_row_id="fixture-tool-2.4.1-json-1",
                executable_resolver=lambda _name: tool,
            )
            output = json.loads(store.resolve(result.output_payloads[0]).read_text(encoding="utf-8"))

        self.assertEqual(output, {"reference": "validated-reference", "cwd": "reference-bundle"})

    def test_rejects_unsafe_zip_collection_before_tool_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "unsafe.zip"
            with zipfile.ZipFile(bundle, "w") as output:
                output.writestr("../escape.txt", "unsafe")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(bundle, role="reads", media_type="application/zip")
            aggregate = command(inputs=(CommandInput("reads", "reads", "reads", "qc-inputs", "zip-directory"),))
            tool = executable(root / "fixture-tool", "raise RuntimeError('must not execute')")

            with self.assertRaises(ScientificCommandError) as caught:
                execute_scientific_command(
                    aggregate,
                    store=store,
                    input_payloads={"reads": payload},
                    parameters={"label": "cohort"},
                    tool_versions={"fixture-tool": "2.4.1"},
                    dependency_versions={"python": "3.14.3"},
                    compatibility_row_id="fixture-tool-2.4.1-json-1",
                    executable_resolver=lambda _name: tool,
                )
        self.assertEqual(caught.exception.code, "INVALID_INPUT_ARCHIVE")

    def test_detects_extracted_collection_mutation_after_tool_execution(self):
        body = """
import argparse, json, pathlib
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
source = next(path for path in pathlib.Path(args.input).rglob('*') if path.is_file())
source.chmod(0o644)
source.write_text('mutated', encoding='utf-8')
json.dump({'status': 'completed'}, open(args.output, 'w', encoding='utf-8'))
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "reports.zip"
            with zipfile.ZipFile(bundle, "w") as output:
                output.writestr("sample/fastqc_data.txt", "PASS")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(bundle, role="reads", media_type="application/zip")
            aggregate = command(inputs=(CommandInput("reads", "reads", "reads", "qc-inputs", "zip-directory"),))
            tool = executable(root / "fixture-tool", body)

            with self.assertRaises(ScientificCommandError) as caught:
                execute_scientific_command(
                    aggregate,
                    store=store,
                    input_payloads={"reads": payload},
                    parameters={"label": "cohort"},
                    tool_versions={"fixture-tool": "2.4.1"},
                    dependency_versions={"python": "3.14.3"},
                    compatibility_row_id="fixture-tool-2.4.1-json-1",
                    executable_resolver=lambda _name: tool,
                )
        self.assertEqual(caught.exception.code, "INPUT_MUTATION")

    def test_output_directory_supports_tools_with_derived_declared_filenames(self):
        body = """
import argparse, pathlib
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--outdir', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
name = pathlib.Path(args.input).stem
pathlib.Path(args.outdir, f'{name}_qc.txt').write_text('PASS\\n', encoding='utf-8')
pathlib.Path(args.outdir, f'{name}_qc.html').write_text('<html></html>', encoding='utf-8')
"""
        derived = command(
            arguments=("--input", "{input:reads}", "--outdir", "{output-directory}", "--label", "{parameter:label}"),
            outputs=(
                CommandOutput("data", "report", "data", "reads_qc.txt", "text/plain"),
                CommandOutput("html", "report", "html", "reads_qc.html", "text/html"),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            source = root / "reads.fastq"
            source.write_text("acgt", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(source, role="reads", media_type="text/plain")

            result = execute_scientific_command(
                derived,
                store=store,
                input_payloads={"reads": payload},
                parameters={"label": "treated"},
                tool_versions={"fixture-tool": "2.4.1"},
                dependency_versions={"python": "3.14.3"},
                compatibility_row_id="fixture-tool-2.4.1-json-1",
                executable_resolver=lambda _name: tool,
            )

        self.assertEqual([payload.role for payload in result.output_payloads], ["data", "html"])

    def test_executes_declared_argv_and_imports_only_declared_outputs(self):
        body = """
import argparse, json
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
text = open(args.input, encoding='utf-8').read().upper()
json.dump({'label': args.label, 'text': text}, open(args.output, 'w', encoding='utf-8'))
print('completed')
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tool = executable(root / "fixture-tool", body)
            source = root / "private-sample.fastq"
            source.write_text("acgt", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(source, role="reads", media_type="text/plain")

            result = execute_scientific_command(
                command(),
                store=store,
                input_payloads={"reads": payload},
                parameters={"label": "treated"},
                tool_versions={"fixture-tool": "2.4.1"},
                dependency_versions={"python": "3.14.3"},
                compatibility_row_id="fixture-tool-2.4.1-json-1",
                executable_resolver=lambda _name: tool,
            )

            output = json.loads(store.resolve(result.output_payloads[0]).read_text(encoding="utf-8"))
            serialized_provenance = json.dumps(result.to_dict()["provenance"], sort_keys=True)
            self.assertEqual(output, {"label": "treated", "text": "ACGT"})
            self.assertEqual(result.stdout, "completed\n")
            self.assertEqual(result.provenance["tools"], {"fixture-tool": "2.4.1"})
            self.assertEqual(result.provenance["dependencies"], {"python": "3.14.3"})
            self.assertEqual(result.provenance["compatibility_row_id"], "fixture-tool-2.4.1-json-1")
            self.assertRegex(result.provenance["executable_sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(payload.sha256, serialized_provenance)
            self.assertNotIn(str(root), serialized_provenance)
            self.assertNotIn(source.name, serialized_provenance)

    def test_unknown_tool_version_and_path_shaped_parameter_block_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "reads.fastq"
            source.write_text("acgt", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(source, role="reads", media_type="text/plain")
            cases = (
                ({}, {"label": "treated"}, "UNVERIFIED_TOOL_VERSION"),
                ({"fixture-tool": "2.4.1"}, {"label": "/private/result"}, "INVALID_PARAMETER"),
            )
            for versions, parameters, code in cases:
                with self.subTest(code=code), self.assertRaises(ScientificCommandError) as caught:
                    execute_scientific_command(
                        command(),
                        store=store,
                        input_payloads={"reads": payload},
                        parameters=parameters,
                        tool_versions=versions,
                        dependency_versions={"python": "3.14.3"},
                        compatibility_row_id="fixture-tool-2.4.1-json-1",
                        executable_resolver=lambda _name: root / "never-called",
                    )
                self.assertEqual(caught.exception.code, code)

    def test_timeout_output_overflow_and_undeclared_output_fail_closed(self):
        scripts = {
            "PROCESS_TIMEOUT": "import time; time.sleep(2)",
            "OUTPUT_LIMIT_EXCEEDED": "print('x' * 10000)",
            "PAYLOAD_LIMIT_EXCEEDED": "import pathlib; pathlib.Path('outputs/report.json').write_text('x' * 10000)",
            "UNDECLARED_OUTPUT": "import pathlib; pathlib.Path('outputs/extra.txt').write_text('extra')",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "reads.fastq"
            source.write_text("acgt", encoding="utf-8")
            store = ProjectArtifactStore(root / "artifacts")
            payload = store.import_file(source, role="reads", media_type="text/plain")
            for code, body in scripts.items():
                tool = executable(root / f"tool-{code.lower()}", body)
                if code == "PROCESS_TIMEOUT":
                    limits = {"timeout_seconds": 1}
                elif code == "PAYLOAD_LIMIT_EXCEEDED":
                    limits = {"max_payload_bytes": 128}
                else:
                    limits = {"max_output_bytes": 128}
                with self.subTest(code=code), self.assertRaises(ScientificCommandError) as caught:
                    execute_scientific_command(
                        command(**limits),
                        store=store,
                        input_payloads={"reads": payload},
                        parameters={"label": "treated"},
                        tool_versions={"fixture-tool": "2.4.1"},
                        dependency_versions={"python": "3.14.3"},
                        compatibility_row_id="fixture-tool-2.4.1-json-1",
                        executable_resolver=lambda _name, tool=tool: tool,
                    )
                self.assertEqual(caught.exception.code, code)

    def test_contract_rejects_shell_or_path_injection_surfaces(self):
        invalid = (
            lambda: command(executable="/usr/bin/tool"),
            lambda: command(arguments=("--input", "{input:missing}")),
            lambda: command(arguments=("--label={parameter:label}",)),
            lambda: command(arguments=("prefix-{input:reads}", "{output:report}", "{parameter:label}")),
            lambda: command(arguments=("bad-{parameter:label", "{input:reads}", "{output:report}")),
            lambda: command(arguments=("{output-directory}", "{output:report}", "{input:reads}", "{parameter:label}")),
            lambda: command(inputs=(CommandInput("reads", "reads", "reads", "../reads.fastq"),)),
            lambda: command(inputs=(CommandInput("reads", "reads", "reads", "reads", "tar-directory"),)),
            lambda: command(inputs=(CommandInput("reads", "reads", "reads", "reads", "file", "config.txt"),)),
            lambda: command(inputs=(CommandInput("reads", "reads", "reads", "reads", "zip-directory", "../config.txt"),)),
            lambda: command(inputs=(CommandInput("reads", "reads", "reads", "reads.fastq"), CommandInput("index", "reads", "index", "index.tbi", sidecar_for="missing"))),
            lambda: command(inputs=(CommandInput("reads", "reads", "reads", "reads.fastq"), CommandInput("index", "reads", "index", "other.tbi", sidecar_for="reads"))),
            lambda: command(working_directory_input="missing"),
            lambda: command(path_mode="host-absolute"),
            lambda: command(outputs=(CommandOutput("report", "report", "report", "nested/report.json", "application/json"),)),
            lambda: command(outputs=(CommandOutput("report", "report", "report", "report.bin", "application/octet-stream", "stdout"),)),
            lambda: command(
                arguments=("{input:reads}", "{parameter:label}"),
                outputs=(
                    CommandOutput("one", "report", "one", "one.txt", "text/plain", "stdout"),
                    CommandOutput("two", "report", "two", "two.txt", "text/plain", "stdout"),
                ),
            ),
        )
        for factory in invalid:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()


if __name__ == "__main__":
    unittest.main()
