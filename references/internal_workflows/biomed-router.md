---
name: biomed-router
description: Route broad biomedical research tasks across the unified local workbench. Use first for ambiguous or end-to-end biomedical workflows spanning literature, omics, molecular design, imaging, clinical translation, protocols, or runtime execution.
category: biology
metadata:
  workbench: biomed-workbench
  catalog: tools/catalog.json
---

# biomed-router

General routing layer for the workbench.

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

## Publication Layer

Use `biomed-publication` for manuscript writing, Nature-style review, citation grounding, paper-to-patent, paper-to-PPT, proposal, figure narrative, and reviewer-response workflows.
