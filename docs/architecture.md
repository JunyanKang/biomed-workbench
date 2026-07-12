# Architecture

Biomed Workbench has one Codex entry and a small, source-neutral execution core. Scientific domains extend the core through validated contracts rather than custom routers or additional user-facing skills.

## Layers

1. `skills/biomed-workbench/SKILL.md` defines the Codex research lifecycle and is the only user-facing entry.
2. `biomed_workbench/router.py`, `assistant.py`, `research.py`, and `runner.py` coordinate planning, execution, evidence, and delivery.
3. `biomed_workbench/capability_specs/` contains one versioned JSON contract per scientific domain.
4. `biomed_workbench/capabilities/` contains independently implemented scientific functions.
5. `biomed_workbench/services/` contains bounded public-database clients and the optional credential allowlist.
6. `tools/catalog.json` is generated from the domain specifications; it is never edited manually.

The central `catalog.py` only loads, validates, resolves, and serializes contracts. It contains no domain capability definitions.

## Add A Capability

1. Implement a bounded function in the closest domain module under `biomed_workbench/capabilities/`.
2. Define an object input schema with explicit types, bounds, required fields, and `additionalProperties: false`.
3. Add the contract with `tools/add_capability.py`, or edit the matching domain JSON file directly.
4. Add a scientific unit fixture and a CLI end-to-end case.
5. Rebuild and verify the generated catalog.

```bash
python3 tools/add_capability.py CAPABILITY_ID \
  --workflow omics \
  --title "Human-readable title" \
  --description "A bounded description of the scientific operation." \
  --entrypoint biomed_workbench.capabilities.omics:FUNCTION \
  --input-schema schema.json

python3 tools/build_catalog.py
python3 tools/validate_workbench.py
python3 -m unittest discover -s tests -v
```

## Compatibility Rules

- Capability IDs and required input fields are stable within a minor release.
- New optional fields and new capabilities may be added in a minor release.
- Removing an ID, changing units, changing output meaning, or making an optional field required needs a major release or an explicit migration.
- Every capability returns structured data and states limitations; routing diagnostics are never a scientific deliverable.
- Source attribution belongs in provenance, never in operational IDs, module names, routes, or schemas.
- The plugin does not own compute infrastructure or another general-purpose reasoning model.

## Release Flow

The plugin manifest is the version source. Package metadata and the generated capability catalog read it automatically.

```bash
python3 tools/build_catalog.py
python3 tools/validate_workbench.py --release
python3 -m unittest discover -s tests -v
```

Publish only when the generated catalog is unchanged after rebuilding, all end-to-end cases pass, and release validation reports no legacy or bridge surfaces.

For local Codex iteration, apply a cachebuster and reinstall from the configured marketplace:

```bash
python3 tools/prepare_local_update.py
codex plugin add biomed-workbench@biomed-workbench
```

Start a new Codex task after reinstalling so the updated Skill metadata is loaded.
