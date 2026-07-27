# Tests

This directory is part of the public plugin product.

- `unit/`, `contract/`, and `e2e/` verify package behavior, schemas, routing, execution boundaries, and module contracts.
- `release/` verifies the published plugin surface, generated evidence, public case reports, and installation contract.
- `fixtures/` contains small deterministic fixtures used by tests and template checks.
- `evidence/` contains scripts that regenerate or validate scientific evidence reports. They are not user-facing plugin commands.

Process-only migration audits, local cache refresh checks, private source-review ledgers, and temporary development files are intentionally excluded from the public product.
