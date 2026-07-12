---
name: biomed-workbench
description: Use when a biomedical task may require evidence search, bioinformatics, omics, single-cell analysis, molecular or drug design, imaging, clinical translation, wet-lab protocols, Nature-style publication work, patents, presentations, or local scientific runtimes, especially when one request spans dependent or parallel capabilities.
---

# Biomed Workbench

Use this as the only user-facing entry point for the workbench. Do not ask the user to invoke separate workflow skills. Interpret "用 biomed-workbench", "用这个工具", or a biomedical task as permission to route internally.

## Core Workflow

1. Resolve `WORKBENCH_ROOT` as the directory two levels above this `SKILL.md`. Do not assume the user's current working directory is the plugin root.
2. Run the router to classify the task and propose an execution shape:

```bash
python3 "$WORKBENCH_ROOT/tools/route_task.py" "USER TASK"
```

3. Use `matched_workflows`, `plan_type`, `steps`, and `candidate_tools` to execute the task. Routing is an internal planning step, not the final user deliverable.
4. Search the catalog when the router output is too broad:

```bash
python3 "$WORKBENCH_ROOT/tools/search_tools.py" "query terms"
python3 "$WORKBENCH_ROOT/tools/search_tools.py" --workflow publication reviewer
python3 "$WORKBENCH_ROOT/tools/search_tools.py" --id TOOL_ID
```

5. Run only direct, bounded tools through the generic runner. Inspect the selected entry and tool help before supplying user data:

```bash
python3 "$WORKBENCH_ROOT/tools/run_tool.py" TOOL_ID -- ARGUMENTS
```

6. For non-direct entries, read the referenced local guidance and adapt it to the user's data and available runtime. Do not claim execution when only a reference pattern was used.

## Routing Rules

- Prefer one coherent plan over exposing internal workflow names to the user.
- Choose `single` when one workflow and one obvious direct tool or pattern is enough.
- Choose `serial` when later steps depend on earlier outputs, especially evidence -> analysis/design -> publication.
- Choose `parallel` when multiple independent searches, checks, or direct tools can run without shared intermediate state.
- Choose `mixed` when the request contains both independent subtasks and dependent downstream synthesis.
- For publication-grade writing, reviewer response, patent, PPT, or Nature-style output, ground claims in evidence and route analysis or database checks before polishing.
- Treat router scores as recommendations. Check input compatibility, dependencies, output paths, and scientific assumptions before execution.
- For heavy setup, services, MCP servers, browser automation, downloads, or external credentials, ask or confirm unless the user explicitly requested that action.
- Keep source projects as metadata only. Do not present Biomni, OpenScience, Claude Science, or Nature skills as the user-facing hierarchy.

## Internal References

Load only when needed:

- `$WORKBENCH_ROOT/references/workflow_map.md`: high-level workflow coverage.
- `$WORKBENCH_ROOT/references/tool_catalog.md`: readable catalog summary.
- `$WORKBENCH_ROOT/references/dependency_matrix.md`: runtime and dependency notes.
- `$WORKBENCH_ROOT/references/nature_workflows.md`: absorbed publication/reviewer/writing patterns.
- `$WORKBENCH_ROOT/references/internal_workflows/`: detailed internal workflow guides.

## Safety

- Do not expose or persist credentials in project files.
- Do not write machine-local absolute paths into publishable files.
- Prefer relative paths, environment-variable adapters, and reproducible command snippets.
