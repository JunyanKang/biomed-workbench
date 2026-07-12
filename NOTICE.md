# Biomed Workbench Notice

Biomed Workbench is an independent Codex plugin that organizes biomedical research capabilities into one user-facing skill and a local tool catalog.

## Integrated Sources

- Biomni: https://github.com/snap-stanford/Biomni (Apache-2.0; inspected commit `400c1f366b96a35ca253e13c9b06c5076af41d65`)
- OpenScience: https://github.com/synthetic-sciences/openscience (Apache-2.0; inspected commit `e9844a49f1f4d93cbf5f88b8f4880c003adc6e61`)
- Claude Science: inspected local research workflow snapshot; concepts only
- Nature Skills: https://github.com/Yuan1z0825/nature-skills (Apache-2.0; integrated metadata snapshot aligned to `74a322725ff2d36984762ca146f7e28cbb49e32d`)

## Redistribution Boundary

This repository does not vendor upstream source trees, local workspaces, credentials, generated artifacts, or third-party scientific datasets. Operational code is independently rewritten and does not import or dispatch into the inspected projects.

Biomni, OpenScience, and the Nature Skills upstream repository are Apache-2.0 licensed at the inspected source snapshots. Some Nature components also carry compatible MIT declarations. OpenScience notes that its scientific database connectors access third-party APIs governed by their own terms. Biomni includes data-source license notes indicating that some biological datasets require separate licenses or restrict commercial use.

Users are responsible for complying with the terms of external databases, datasets, and APIs they use through this workbench.
