# Biomed Workbench development contract

Biomed Workbench is developed and released as a Codex scientific plugin. Use `skills/biomed-workbench/SKILL.md` as the single research entry and treat every module manifest as a versioned scientific contract rather than a suggestion list.

Inspect actual project inputs and study design before analysis. Run the packaged health check, select only modules whose preconditions and compatibility rows are satisfied, execute packaged parameterized workflows without editing their source, reload outputs, and preserve experimental units, parameter provenance, artifact digests, scientific review, and evidence-map lineage.

Optional Agent Skills and read-only MCP adapters may expose the existing registry to another host. Keep those adapters outside `biomed_workbench/modules/builtin`; never rewrite scientific templates or reissue execution evidence merely to change host terminology. Codex-native handoffs remain Codex-owned unless another host has an independently validated equivalent.

Registration, routing, a dry run, or an audit report does not establish scientific completion. Claims must remain bound to the observed execution and public-case evidence for the exact module slice.

When Codex starts a desktop application or background service for a bounded workflow, record the exact process identity and treat it as task-owned. Save required artifacts, request a normal application exit, verify that the owned process has disappeared, and only then finish or clean temporary data. Never terminate a user-owned process that was already running before the task.
