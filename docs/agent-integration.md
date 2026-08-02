# Optional Interoperability Adapters

Languages: [English](agent-integration.md) · [中文](agent-integration.zh-CN.md)

Biomed Workbench is Codex-first. `.codex-plugin`, `.agents/plugins`, and `skills/biomed-workbench/SKILL.md` define the release-validated native entry; Codex file access, permission handling, native image generation, and project collaboration provide the complete product experience.

Other agents may connect through isolated adapters. Those adapters do not enter scientific modules, parameterized templates, quality gates, or prior execution evidence.

## Agent Skills adapter

An agent that supports a skills-directory convention may read `skills/biomed-workbench/SKILL.md` and reuse its research process and module entry. This is guidance-level compatibility: the host must provide file access, command execution, permission handling, runtime isolation, artifact reload, and evidence registration. A node remains unexecuted whenever the host cannot satisfy one of those responsibilities.

## Read-only MCP adapter

`tools/mcp_server.py` exposes four bounded tools: capability listing, natural-language routing, single-capability contract inspection, and read-only module execution. It reads the same registry and runner as the Codex plugin and does not maintain a second scientific catalog.

MCP does not proxy output-writing research workflows, replace Codex-native image tools, create scientific runtimes, or turn a route into a result. For project writes, external scientific software, or project conclusions, the host must independently perform authorization, execution, output review, and evidence registration under the module contract.

## Stable boundaries

- A new host adds an adapter; it does not copy or rewrite scientific modules.
- Adapter changes trigger adapter tests and do not invalidate prior scientific execution evidence.
- Every entry reads the same module registry; capability counts and contracts must agree.
- `access: codex_native` continues to mean a Codex-native tool handoff. Another host completes that node only through an independently validated equivalent.
- `access: agent_generated` is a historical registry value for Codex-managed packaged parameterized workflows. It does not authorize template edits or arbitrary analysis-code generation.

## Verification

The complete release suite validates the Codex-native path. A separate adapter-boundary audit checks adapter location, read-only permissions, registry identity, and absence of reverse dependencies from scientific modules. Adapter validation cannot raise a scientific module's maturity or replace public-data or real-project acceptance.
