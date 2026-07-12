# Runtime Adapters

Runtime entries are implemented through environment-variable adapters rather than vendored local installations.

Supported environment variables:

- `CLAUDE_SCIENCE_HOME`
- `CLAUDE_SCIENCE_CLI`
- `CLAUDE_SCIENCE_PYTHON`
- `CLAUDE_SCIENCE_RSCRIPT`
- `CLAUDE_SCIENCE_MICROMAMBA`
- `BIOMNI_SOURCE_ROOT`
- `OPENSCIENCE_SOURCE_ROOT`

Rules:

1. Keep credentials, generated workspaces, caches, and local runtime artifacts out of this project.
2. Use `tools/run_tool.py runtime_status` for a safe runtime check.
3. Start services, browser flows, or heavy setup scripts only when the user explicitly asks.
