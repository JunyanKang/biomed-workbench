---
name: biomed-publication
description: Plan, draft, polish, verify, and package biomedical manuscripts and high-impact research artifacts. Use for paper reading, Nature-style writing, citation grounding, figure/storyline planning, reviewer response, proposal writing, patent conversion, paper-to-PPT, data availability, and publication-grade quality audits.
category: biology
metadata:
  workbench: biomed-workbench
  catalog: tools/catalog.json
---

# biomed-publication

Publication, writing, review, and research packaging layer for the workbench.

## Local Tool Commands

Search publication tools:

```bash
python3 tools/search_tools.py --workflow publication "citation"
python3 tools/search_tools.py --workflow publication "patent"
python3 tools/search_tools.py --workflow publication "reviewer"
```

Inspect one tool:

```bash
python3 tools/search_tools.py --id TOOL_ID
```

Run a direct helper only when `run_policy=direct`:

```bash
python3 tools/run_tool.py TOOL_ID -- --help
```

## Rules

- Use `biomed-publication` as the user-facing layer, not `nature-*`.
- Treat Nature-style source skills as absorbed workflow patterns.
- Keep citation, claim, figure, patent, and reviewer-response work evidence-grounded.
- Do not run browser downloaders, MCP servers, or external publisher integrations unless explicitly requested.
