# Source File Audit

This audit maps source files to integration actions. It is generated from current local source inventories.

## Summary

### Biomni
- `learned_reference`: 106
- `source_reference`: 59
- `indexed_source`: 24
- `indexed_function`: 22
- `copied_script`: 9
- `runtime_reference`: 8

### OpenScience
- `ignored_platform`: 1854
- `source_reference`: 1632
- `learned_reference`: 155
- `copied_script`: 88
- `indexed_connector`: 55
- `learned_skill_pattern`: 43
- `learned_agent_pattern`: 4
- `learned_tool_api`: 4

### Nature Skills
- `learned_reference`: 144
- `source_reference`: 105
- `copied_script`: 29
- `adapted_mcp_support`: 18
- `workflow_pattern`: 17
- `runtime_reference`: 15

### Claude Science
- `ignored_generated_runtime`: 5033
- `runtime_reference`: 1160
- `adapted_runtime`: 4
- `excluded_sensitive`: 3
- `indexed_runtime_metadata`: 3

## Integration Rules

- Copy only portable scripts that directly help biomedical workbench execution.
- Index large function libraries and database connectors instead of copying full source trees.
- Adapt local runtimes through environment variables; never vendor local credentials, caches, or generated environments.
- Learn from documentation, prompts, and references by turning them into workflow guidance.
- Keep user-facing hierarchy workflow-based, not source-project-based.
