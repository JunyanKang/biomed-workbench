---
name: biomed-clinical-translation
description: Prepare clinical and translational research artifacts, including biomarker reports, cohort tables, treatment plans, clinical report validation, survival analysis, patient-level deidentification checks, and clinical evidence synthesis.
category: biology
metadata:
  workbench: biomed-workbench
  catalog: tools/catalog.json
---

# biomed-clinical-translation

Clinical and translational layer.

## Local Tool Commands

Search the unified catalog:

```bash
python3 tools/search_tools.py --workflow auto "query terms"
```

Inspect one tool:

```bash
python3 tools/search_tools.py --id TOOL_ID
```

Run a direct script or runtime entry when `run_policy` allows it:

```bash
python3 tools/run_tool.py TOOL_ID -- --help
```

## Rules

- Use unified `biomed-*` workflow names when talking to the user.
- Treat Biomni, OpenScience, and Claude Science as source metadata, not user-facing hierarchy.
- Read the relevant tool entry and source file before execution.
- Do not start long-running services or install heavy environments unless the user explicitly asks.
- Avoid credentials and token directories under the Claude Science home directory.
