# Installation And Updates

Languages: [English](installation.md) · [中文](installation.zh-CN.md)

## Install From GitHub

Tell Codex or another compatible agent:

> Install Biomed Workbench from the `JunyanKang/biomed-workbench` GitHub repository. Use the current main release, verify the installed plugin identity and scientific-module registry, and report the exact installed revision and validation result.

The agent should add the repository as the Biomed Workbench marketplace, install the plugin, and verify that the installed package is `biomed-workbench@biomed-workbench`.

After installation, open a new Codex task. Skills and MCP tools are discovered when a task starts, so an already-open task may not show the newly installed version.

## Install From A Full Git URL

If repository shorthand is unavailable, ask the agent to use the full GitHub address `https://github.com/JunyanKang/biomed-workbench`, stay on the requested branch or release, and perform the same identity and registry checks.

## Local Development Install

For local development, give the agent a stable development directory and ask it to clone or use the repository there, register that exact directory as a local marketplace, install the plugin, and report both the source revision and the loaded plugin revision. The agent must preserve unrelated working-tree changes and must not silently replace a local development checkout with the remote branch.

## Update

Pull the desired repository revision, then reinstall or refresh the marketplace package using the Codex plugin commands available in the installed Codex release. Start a new task after the update and confirm that the skill list contains `biomed-workbench`.

## Verify The Installation

Ask the agent to show that the marketplace and installed plugin are present, then open a new task and use Biomed Workbench for a small scientific request such as inspecting a DNA sequence or planning a literature search. The agent runs the packaged strict health check before first use and reports whether the plugin manifest, unified skill, module registry, routing, credential policy and generated evidence reports agree.

The plugin core requires Python 3.10 or newer. The launcher discovers a compatible interpreter instead of assuming that the operating system's `python3` is suitable. Scientific package and command versions remain module-level compatibility and provenance records: the health check does not claim that every optional analysis backend is already installed.

For maintainers who need repository, release, and isolated-install checks, see [development and release](development.md).

## Credentials

Credential needs are endpoint-specific. The current public modules do not require a key; `NCBI_API_KEY` is optional for the implemented NCBI E-utilities and Datasets requests and increases service capacity without changing scientific interpretation.

Ask the agent to inspect credential status, configure the NCBI key through hidden input, show only the repository-external storage location, rotate the key, or remove it. Values remain outside command arguments, module inputs, logs, reports, research artifacts, and scientific evidence maps. Cluster and institutional secret-manager options are described in [Data Access and Credentials](data-access-and-credentials.md).

## Troubleshooting

- **Skill is missing:** start a new Codex task after installation or update.
- **Marketplace cannot be resolved:** confirm the repository URL, branch, and marketplace name.
- **Core runtime is blocked:** install Python 3.10 or newer. The workbench launcher will select it automatically; no global environment activation is required.
- **A scientific backend is unavailable:** the skill can still provide guidance and routing, but execution must wait for a compatible project environment or use a validated alternative.
- **A result is blocked:** inspect the named input, compatibility, or scientific quality gate; blocked evidence is not silently promoted into a conclusion.
