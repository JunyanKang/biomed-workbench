# Biomni Function Index

Biomni functions are indexed in `tools/catalog.json` and routed through the workbench catalog. They are not copied as source files because the upstream function library is large and environment-dependent.

Use these entries as capability metadata:

- `kind`: `biomni_function`
- `run_policy`: `import_requires_biomni_env`
- `path`: this reference file
- `source_path`: upstream relative module or tool-description file

Execution rule:

1. Search with `python3 tools/search_tools.py "query terms"`.
2. Inspect the selected catalog entry with `python3 tools/search_tools.py --id TOOL_ID --verbose`.
3. Use `BIOMNI_SOURCE_ROOT` or an installed Biomni environment when a task requires actual function execution.
4. Do not vendor the upstream Biomni tree into this project.

The workbench should present these as biomedical capabilities, not as a source-project hierarchy.
