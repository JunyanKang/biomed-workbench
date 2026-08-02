# Installation And Updates

Languages: [English](installation.md) · [中文](installation.zh-CN.md)

## Brief installation

Give `https://github.com/JunyanKang/biomed-workbench` to Codex and ask:

> Install the current release from this repository. Verify the Codex plugin identity, unified research entry, scientific-module registry and exact revision; preserve existing local changes; then report the validation result and any scientific backend still missing for my project in plain language.

After installation or update, ask Codex to reload the plugin and open a new task so the current skill and tool entries are discovered.

## Codex-native entry

Codex reads the installation metadata in `.codex-plugin` and `.agents/plugins`, uses `skills/biomed-workbench/SKILL.md` as the unified research entry, and maps native features such as image generation to explicit scientific contracts. This is the primary, release-validated product path.

## Optional interoperability adapters

- **Agent Skills:** another agent that supports a skills-directory convention may read the same skill guidance, but it must provide its own file access, permission checks, runtime execution, artifact reload and evidence registration.
- **Read-only MCP:** an agent with local stdio MCP support may register `tools/mcp_server.py` for capability discovery, natural-language routing, contract inspection and read-only execution. Output-writing research workflows, Codex-native tools and project-level scientific decisions are not automatically proxied through MCP.

These adapters sit outside the scientific modules and read the same registry. They do not duplicate modules, rewrite templates or rebind prior execution evidence. See [Optional Interoperability Adapters](agent-integration.md).

## Local development and updates

For development, give Codex a stable repository directory and require it to preserve unrelated changes, report both source and loaded revisions, and run the release-integrity checks after edits. For updates, name the branch or release, reload the plugin and verify the registry digest. A remote revision must not silently overwrite uncommitted local work.

## Installation verification

Before first use, Codex runs the strict health check and reports whether the plugin identity, unified entry, module count, registry, router, credential policy and generated evidence agree. The core requires Python 3.10 or newer and the launcher discovers a compatible interpreter. Scientific packages, databases and command versions remain module-level compatibility and provenance records; the core health check does not imply that every optional backend is installed.

Maintainer-level repository, release and isolated-install checks are documented in [Development And Release](development.md).

## Credentials

Credential need is determined by the implemented endpoint. Most current public endpoints are anonymous; `NCBI_API_KEY` is an optional capacity credential for NCBI E-utilities and Datasets. A user may ask Codex to inspect, configure, rotate or remove a credential through hidden input. Values must remain outside chat text, command arguments, module inputs, logs, reports, research artifacts and scientific evidence maps. See [Data Access And Credentials](data-access-and-credentials.md) for the full service inventory.

## Troubleshooting

- **New capabilities are missing:** reload the plugin and open a new task.
- **The repository cannot be resolved:** use the full GitHub URL and verify the requested branch or release.
- **The core runtime is unavailable:** provide Python 3.10 or newer; no global environment activation is required.
- **A scientific backend is unavailable:** ask Codex to discover a compatible existing environment or create an isolated one. Register an analysis result only after observed execution and output review.
- **A result is not admitted:** inspect the named input, compatibility or scientific-quality condition, then decide whether to add data, tune declared parameters or change method.
