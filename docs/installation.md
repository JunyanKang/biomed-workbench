# Installation And Updates

Languages: [English](installation.md) · [中文](installation.zh-CN.md)

## Brief installation

In Codex, say:

> Install the current release of [JunyanKang/biomed-workbench](https://github.com/JunyanKang/biomed-workbench). Verify the Codex plugin identity, unified research entry, scientific-module registry, and exact revision; preserve existing local changes; then report the validation result and any scientific backend still missing for my project in plain language.

After installation or update, ask Codex to reload the plugin and open a new task so the current skill and tool entries are discovered.

## Reference host and other agents

Codex reads the installation metadata in `.codex-plugin` and `.agents/plugins`, uses `skills/biomed-workbench/SKILL.md` as the unified research entry, and maps file operations, permission interaction, runtime coordination, and native image generation to explicit scientific contracts. This is the reference implementation currently covered by the complete release path. The project permits other agents to access the same scientific core without treating interface readability as end-to-end capability certification.

## Optional interoperability adapters

Another agent should not copy the Codex plugin-install request verbatim. Tell it:

> Obtain the current release of [JunyanKang/biomed-workbench](https://github.com/JunyanKang/biomed-workbench) as a local research-capability package. If this host supports Agent Skills, load the unified research entry; if it supports local stdio MCP, configure the bounded interoperability interface. Do not treat the repository's Codex plugin metadata as proof that this host has installed or validated the complete product path. Report which file-access, permission, runtime, artifact-reload, and evidence-delivery responsibilities this host can actually satisfy.

- **Agent Skills:** another agent that supports Agent Skills or an equivalent skills-directory convention may read the same skill guidance, but it must independently provide and validate file access, permission checks, runtime execution, artifact reload and evidence registration.
- **Read-only MCP:** an agent with local stdio MCP support may register `tools/mcp_server.py` for capability discovery, natural-language routing, contract inspection and read-only execution. Output-writing research workflows, Codex-native tools and project-level scientific decisions are not automatically proxied through MCP.

A full checkout still includes `.codex-plugin` and `.agents/plugins`. These are small Codex release metadata and may remain present but unloaded in another host. Keeping them preserves version alignment among scientific modules, the registry, and release records; do not manually prune them from a working checkout. The adapters sit outside scientific modules and read the same registry. They do not duplicate modules, rewrite templates, or rebind prior execution evidence. They establish an interoperability path, not host-level parity with Codex. See [Codex-First Operation And Cross-Host Interoperability](agent-integration.md).

## Local development and updates

For development, give Codex a stable repository directory and require it to preserve unrelated changes, report both source and loaded revisions, and run the release-integrity checks after edits. For updates, name the branch or release, reload the plugin and verify the registry digest. A remote revision must not silently overwrite uncommitted local work.

## Installation verification

Before first use, Codex runs the strict health check and reports whether the plugin identity, unified entry, module count, registry, router, credential policy and generated evidence agree. The core requires Python 3.10 or newer and the launcher discovers a compatible interpreter. Scientific packages, databases and command versions remain module-level compatibility and provenance records; the core health check does not imply that every optional backend is installed.

Maintainer-level repository, release and isolated-install checks are documented in [Development And Release](development.md).

## Credentials

Credential need is determined by the implemented endpoint. Most current public-database endpoints are anonymous; `NCBI_API_KEY` is an optional capacity credential for NCBI E-utilities and Datasets. AlphaFold Server instead uses interactive Google sign-in on the official website: Codex checks an access state and prepares a package, while the user reviews and submits it manually; the workbench stores no password, token, or browser session. A user may ask Codex to inspect, configure, rotate or remove an API credential through hidden input. Sensitive values must remain outside command arguments, module inputs, logs, reports, research artifacts and scientific evidence maps. See [Data Access And Credentials](data-access-and-credentials.md) for the full service inventory.

## Troubleshooting

- **New capabilities are missing:** reload the plugin and open a new task.
- **The repository cannot be resolved:** use the full GitHub URL and verify the requested branch or release.
- **The core runtime is unavailable:** provide Python 3.10 or newer; no global environment activation is required.
- **A scientific backend is unavailable:** ask Codex to discover a compatible existing environment or create an isolated one. Register an analysis result only after observed execution and output review.
- **A result is not admitted:** inspect the named input, compatibility or scientific-quality condition, then decide whether to add data, tune declared parameters or change method.
