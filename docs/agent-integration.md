# Codex-First Operation And Cross-Host Interoperability

Languages: [English](agent-integration.md) · [中文](agent-integration.zh-CN.md)

Biomed Workbench is an agent-driven biomedical research workbench released with Codex as its primary reference host. `.codex-plugin`, `.agents/plugins`, and `skills/biomed-workbench/SKILL.md` define the product path currently covered by the complete release suite; Codex file access, permission handling, runtime coordination, native image generation, and project delivery together provide that reference implementation.

“Codex-first” describes validation order and support depth; it does not make the scientific registry exclusive to Codex. Other agents may connect through a skills-directory convention or the bounded MCP interface. Adapters stay outside scientific modules and do not copy parameterized templates, rewrite quality gates, or rebind prior execution evidence. Another host may claim the same research node only after independently implementing and validating the corresponding responsibilities.

| Boundary | Codex reference path | Agent Skills host | Read-only MCP host |
| --- | --- | --- | --- |
| Unified skill and registry access | Fully validated | Readable; loading behavior is host-validated | Available through bounded tools |
| File writes, permission handling, and runtime management | Covered by the Codex product path | Host-supplied and host-validated | Not provided |
| External scientific software and browser authentication | Interactive execution under module contracts | Host-supplied and host-validated | Not provided |
| Artifact reload, scientific review, and evidence maps | Covered by the complete release flow | Host-supplied and host-validated | A bounded result is not a project deliverable |
| Native image generation and collaboration handoffs | Codex-native | Requires an independently validated equivalent | Not provided |

## Agent Skills adapter

An agent that supports Agent Skills or an equivalent skills-directory convention may read `skills/biomed-workbench/SKILL.md` and reuse its research process and module entry. This is entry compatibility rather than end-to-end certification: the host must provide file access, command execution, permission handling, runtime isolation, artifact reload, and evidence registration. A node remains unexecuted whenever the host cannot satisfy one of those responsibilities.

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

The complete release suite validates the Codex reference path. A separate adapter-boundary audit checks adapter location, read-only permissions, registry identity, and absence of reverse dependencies from scientific modules. That audit shows that an interface has not forked or overreached; it does not certify complete scientific execution in an external host, raise a module's maturity, or replace public-data, real-service-result, or real-project acceptance.
