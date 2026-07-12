# Dependency Matrix

- `direct`: copied local script or runtime command can be invoked by `tools/run_tool.py`; dependencies may still be required by that script.
- `import_requires_biomni_env`: indexed Biomni function; inspect source and run inside a Biomni-compatible environment before execution.
- `manual-heavy`: setup or environment mutation script; do not run unless the user explicitly asks.
- `manual-service`: long-running service or browser daemon; do not start unless the user explicitly asks.
- `source_reference`: connector/source implementation is indexed for reuse; not wrapped as a standalone command.
- `read_only`: artifact example for pattern reuse only.
