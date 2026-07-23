# Capability Maturity And Evidence

Biomed Workbench separates module maturity from the strength of evidence
available for a particular scientific use. A module marked `validated` has a
valid package, executable contract, compatibility row, regression case, and
representative end-to-end evidence. It is not automatically validated for every
organism, assay, cohort, chemistry, endpoint, or user dataset.

## Evidence Levels

| Level | What has been demonstrated | What remains unproven |
| --- | --- | --- |
| Contract | Manifest, schemas, artifacts, quality gates, entrypoint, and extension rules are structurally valid | Scientific runtime and outputs |
| Compatibility | A declared tool/dependency/input/output combination passes regression and representative execution | Other versions, platforms, formats, and study designs |
| Live acceptance | A current external tool, database, or stable public dataset passes the recorded quality gates | Generalization beyond the recorded source and parameters |
| Project validation | The user's actual inputs execute, reload, reconcile, and pass project-specific scientific gates | Claims beyond the sampled units, design, and observed evidence |

These levels are cumulative for a specific compatibility row. Evidence from one
row must not be transferred to another row merely because its version appears
inside an allowed range.

## Operational Labels

- `validated`: the checked package and its declared compatibility evidence pass.
- `experimental`: the module contract and templates are usable, but the
  scientific surface still needs broader backend, public-data, or project
  acceptance before routine use.
- `agent_generated`: Codex must inspect the project, adapt the packaged template,
  review generated code, execute it, inspect every output, and record observed
  versions and gates. The protocol handoff is not evidence.
- `offline`, `public_api`, and `codex_native`: these describe access and
  execution boundaries, not scientific maturity.

## Release Evidence

The release validator binds the registry to compatibility execution evidence,
live tool and database reports, public-data cases, template coverage, the
research-state engine, and source reconciliation. The [public-data acceptance
case index](cases/README.md) shows the strongest current live examples.

For a user project, the final maturity decision is always made at project
validation level. Failed or unrun gates remain visible, experimental modules are
not promoted by prose, and a successful process exit is never sufficient.
