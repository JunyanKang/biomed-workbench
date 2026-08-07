# Installation And Updates

Languages: [English](installation.md) · [中文](installation.zh-CN.md)

## Install

In Codex, say:

> Install the current release of [JunyanKang/biomed-workbench](https://github.com/JunyanKang/biomed-workbench). Preserve my existing local changes, check that the plugin loads correctly, and report the installed version and validation result in plain language.

After installation, reload the plugin and open a new task so the current research entry and tools are available in the session.

The Biomed Workbench core requires Python 3.10 or newer. Individual analyses may also require R, external scientific software, databases, or a container runtime. The workbench checks those requirements for the selected method; successful plugin installation does not imply that every optional analysis program is installed.

## Update

To update, say:

> Update Biomed Workbench to the current release. Check and preserve uncommitted local changes first; then reload the plugin, verify the version and capability list, and run the release-integrity checks.

If a project requires a fixed version, name the release or commit. Existing research results keep their original software, parameter, and version records and are not rewritten by a plugin update.

## Use With Other Agents

The complete release path currently uses Codex as its primary environment. Other agents that support Agent Skills or a similar skills directory may read the same research entry. Environments with local MCP support may also inspect the capability list and method information.

File access, runtime execution, permission handling, browser interaction, and result review differ among agents and must be checked in the environment being used. The small Codex configuration files included in the repository may remain present in another agent but are not loaded automatically. See [Using Biomed Workbench With Other Agents](agent-integration.md).

## Credentials

Most integrated public databases allow anonymous access. `NCBI_API_KEY` is optional and increases request capacity for NCBI E-utilities and Datasets. AlphaFold Server uses interactive Google sign-in on its official website; the user reviews and submits the job in the browser. Biomed Workbench does not store account passwords, access tokens, or browser sessions.

Users may ask Codex to configure, update, or remove credentials through hidden input. Sensitive values are not written to command arguments, analysis inputs, logs, reports, or scientific evidence maps. See [Data Access And Credentials](data-access-and-credentials.md) for service-specific requirements.

## Troubleshooting

- **A new capability is missing:** reload the plugin and open a new task.
- **The repository cannot be found:** use the full GitHub URL and confirm the requested release or branch.
- **The Python version is incompatible:** provide Python 3.10 or newer; no environment needs to remain globally active.
- **An analysis program is unavailable:** ask Codex to inspect existing environments and create an isolated environment only if needed.
- **The computation ended but no conclusion was produced:** review the quality checks and scientific assessment; completed computation is not the same as reliable evidence.

Maintainer installation and release checks are documented in [Development And Release](development.md).
