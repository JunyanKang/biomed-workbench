---
name: biomed-imaging-phenotyping
description: Analyze biomedical images and phenotypes, including microscopy, pathology, clinical imaging, DICOM, cell morphology, colocalization, cell tracking, plaques, hemodynamics, and neurophysiology signals.
category: biology
metadata:
  workbench: biomed-workbench
  catalog: tools/catalog.json
---

# biomed-imaging-phenotyping

Imaging and phenotyping layer.

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
