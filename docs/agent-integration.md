# Using Biomed Workbench With Other Agents

Languages: [English](agent-integration.md) · [中文](agent-integration.zh-CN.md)

Biomed Workbench currently uses Codex as its primary release and validation environment. Its scientific methods, parameter guidance, and capability list are stored in the repository, so other agents that support skills directories or local MCP can read part of the same research capability.

## Levels Of Support

| Environment | What is available | What must be checked separately |
| --- | --- | --- |
| Codex | Complete research entry, file handling, runtime coordination, browser interaction, output review, and project delivery | Each method must still satisfy its own software, data, and study-design requirements |
| Agent with Agent Skills support | Research process, method guidance, and module entry | File permissions, command execution, environment isolation, output review, and evidence preparation |
| Agent with local MCP support | Capability discovery, request routing, method information, and bounded read-only calls | Project writes, external software, browser authentication, figure production, and complete research delivery |

Reading the skill guidance means that an agent understands the entry point; it does not mean that the agent already has a complete scientific runtime. Before using another agent, confirm that it can access the project files, run the required software, reopen the outputs, and perform scientific review.

Some steps rely on tools provided by Codex. Another agent can complete them only after providing and validating equivalent capabilities; otherwise the relevant work remains unexecuted.

## Codex Files In The Repository

A complete checkout includes `.codex-plugin` and `.agents/plugins`. These small files support Codex installation. Another agent may leave them in place, but it will not load them automatically or become a Codex plugin simply because they are present.

There is one scientific module collection. Other agents read the same capability list and should not copy analysis templates, change quality standards, or relabel previous acceptance results as new execution evidence.

## Suggested Request For Another Agent

> Obtain the current release of [JunyanKang/biomed-workbench](https://github.com/JunyanKang/biomed-workbench). If you support Agent Skills, load `skills/biomed-workbench/SKILL.md`; if you support only local MCP, inspect the available capabilities first. State whether you can access project files, run external scientific software, reopen outputs, and complete scientific review. Do not treat discovery of a capability as a completed analysis.

If the agent cannot provide one of those responsibilities, the corresponding analysis should remain unexecuted or be continued in a validated environment.

Interface and test requirements for integrators are documented in [Development And Release](development.md).
