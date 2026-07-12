import json
import tempfile
import unittest
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
            lambda: command(inputs=(CommandInput("reads", "reads", "reads", "../reads.fastq"),)),
            lambda: command(outputs=(CommandOutput("report", "report", "report", "nested/report.json", "application/json"),)),
        )
        for factory in invalid:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()


if __name__ == "__main__":
    unittest.main()
