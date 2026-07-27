# Installation And Updates

Languages: [English](installation.md) · [中文](installation.zh-CN.md)

## Install From GitHub

Add the repository as a Codex marketplace and install the plugin:

```bash
codex plugin marketplace add JunyanKang/biomed-workbench --ref main
codex plugin add biomed-workbench@biomed-workbench
codex plugin list
```

The marketplace name is `biomed-workbench`, so the installed package is `biomed-workbench@biomed-workbench`.

After installation, open a new Codex task. Skills and MCP tools are discovered when a task starts, so an already-open task may not show the newly installed version.

## Install From A Full Git URL

```bash
codex plugin marketplace add https://github.com/JunyanKang/biomed-workbench --ref main
codex plugin add biomed-workbench@biomed-workbench
```

## Local Development Install

For local development, clone the repository into a stable directory and add that directory as a marketplace:

```bash
mkdir -p ~/plugins
git clone https://github.com/JunyanKang/biomed-workbench ~/plugins/biomed-workbench
codex plugin marketplace add ~/plugins/biomed-workbench
codex plugin add biomed-workbench@biomed-workbench
codex plugin list
```

## Update

Pull the desired repository revision, then reinstall or refresh the marketplace package using the Codex plugin commands available in the installed Codex release. Start a new task after the update and confirm that the skill list contains `biomed-workbench`.

## Verify The Installation

`codex plugin list` should show the marketplace and installed plugin. In a new task, ask Codex to use Biomed Workbench for a small scientific request, such as inspecting a DNA sequence or planning a literature search. The agent runs the packaged health check before first use and reports whether the plugin manifest, unified skill, module registry, routing, and optional credential policy are ready.

Maintainers can run the same health check directly:

```bash
tools/workbench doctor --strict
```

The plugin core requires Python 3.10 or newer. The launcher discovers a compatible interpreter instead of assuming that the operating system's `python3` is suitable. Scientific package and command versions remain module-level compatibility and provenance records: the health check does not claim that every optional analysis backend is already installed.

For maintainers who need repository, release, and isolated-install checks, see [development and release](development.md).

## Credentials

Most public evidence clients require no credential. When a scientific service supports an optional API key, configure it in the user's environment or approved Codex secret surface. Never place credentials in the repository, module manifests, examples, logs, or research artifacts.

## Troubleshooting

- **Skill is missing:** start a new Codex task after installation or update.
- **Marketplace cannot be resolved:** confirm the repository URL, branch, and marketplace name.
- **Core runtime is blocked:** install Python 3.10 or newer. The workbench launcher will select it automatically; no global environment activation is required.
- **A scientific backend is unavailable:** the skill can still provide guidance and routing, but execution must wait for a compatible project environment or use a validated alternative.
- **A result is blocked:** inspect the named input, compatibility, or scientific quality gate; blocked evidence is not silently promoted into a conclusion.
