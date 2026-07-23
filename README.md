<p align="center">
  <img src="assets/biomed-workbench-mark.svg" width="112" alt="Biomed Workbench logo">
</p>

<h1 align="center">Biomed Workbench</h1>

<p align="center"><strong>A unified biomedical research assistant for Codex.</strong></p>

<p align="center">
  <a href="https://github.com/JunyanKang/biomed-workbench/actions"><img alt="Quality" src="https://img.shields.io/github/actions/workflow/status/JunyanKang/biomed-workbench/quality.yml?branch=main&amp;label=quality"></a>
  <a href="LICENSE"><img alt="Apache-2.0 license" src="https://img.shields.io/badge/license-Apache--2.0-4388C7"></a>
  <img alt="Dynamic scientific modules" src="https://img.shields.io/badge/modules-dynamic-36A58B">
  <img alt="One Codex skill" src="https://img.shields.io/badge/Codex%20skills-1-E05A47">
</p>

<p align="center">
  <img src="assets/research-loop.png" width="100%" alt="Biomed Workbench turns a research question into a quality-gated biomedical research loop and research-grade delivery">
</p>

Biomed Workbench gives Codex one entry point for biomedical research. Describe the scientific problem in ordinary language; the workbench frames the question, selects the relevant capabilities, coordinates independent and dependent analyses, challenges the evidence, revises the plan when quality gates fail, and prepares research-grade deliverables.

The workbench dynamically discovers its registered scientific modules behind one Codex skill: `biomed-workbench`. Tasks can be routed as a single operation, a serial workflow, parallel analyses, or a mixed research program without asking the user to invoke separate skills.

## Professional Capabilities

| Research area | What the workbench coordinates |
| --- | --- |
| [Evidence and literature](docs/capabilities/evidence-and-literature.md) | Literature discovery, public biomedical databases, citation resolution, evidence synthesis, contradiction and freshness checks |
| [Omics and single-cell](docs/capabilities/omics-and-single-cell.md) | Sequencing and expression analysis, donor-aware inference, droplet and doublet review, atlas annotation, cell-state dynamics, multimodal integration, regulatory networks, and spatial analysis |
| [Molecular and structural biology](docs/capabilities/molecular-and-structural.md) | Sequence analysis, CRISPR and primer design, molecular evidence, structure retrieval, quality assessment, comparison, docking review, and chemical filtering |
| [Imaging and visualization](docs/capabilities/imaging-and-visualization.md) | Image profiling, segmentation, colocalization, tracking, quantitative checks, scientific figures, and molecular visualization |
| [Clinical and experimental research](docs/capabilities/clinical-and-experimental.md) | Cohort and survival analysis, biomarkers, adverse events, de-identification, assay design, dose response, growth curves, and experimental interpretation |
| [Publication and translation](docs/capabilities/publication-and-translation.md) | Claim-evidence integrity, figures, manuscript revision, peer review, response letters, patents, and publication-ready research packages |

See the [complete capability map](docs/capabilities/README.md) for scope, orchestration patterns, quality boundaries, and current limitations.

Single-cell projects can be coordinated as complete research programs: validate raw inputs, challenge technical artifacts, establish cell states, test donor-aware hypotheses, connect trajectories and interactions, integrate modalities, examine regulatory or spatial evidence, and revise the analysis when quality gates fail. The [omics and single-cell guide](docs/capabilities/omics-and-single-cell.md) describes the supported workflows, scientific safeguards, and expected deliverables.

## How It Works

1. **Frame** the question, study design, evidence landscape, and decision criteria.
2. **Plan** the smallest scientifically complete set of modules and their dependencies.
3. **Analyze** with explicit inputs, version-aware tools, and traceable artifacts.
4. **Challenge** assumptions, statistical validity, conflicts, missing evidence, and failed quality gates.
5. **Revise** the hypothesis or workflow when the evidence does not support the current path.
6. **Deliver** interpretable results, figures, methods, manuscripts, reviews, or translational outputs.

This is a research assistant, not a source of automatic scientific truth. It preserves uncertainty, separates observation from interpretation, keeps unsupported claims out of deliverables, and records the evidence needed to reproduce consequential results.

## Use In Codex

After installation, start a new Codex task and describe the research goal naturally. For example:

> Use Biomed Workbench to compare the literature, gene, variant, and structure evidence for TP53, identify disagreements, and propose the next decisive analyses.

> Analyze this donor-aware single-cell and spatial study from input validation and artifact review through annotation, multimodal integration, communication, trajectory, regulatory analysis, hypothesis revision, and a manuscript-ready results package.

> Review these docking results together with protein structure quality and chemical filters, then explain which conclusions are supported and which require experimental validation.

The [usage guide](docs/using-biomed-workbench.md) explains project inputs, checkpoints, deliverables, and how to add a new scientific module.

## Install

Add the GitHub repository as a personal Codex marketplace and install the plugin:

```bash
codex plugin marketplace add JunyanKang/biomed-workbench --ref main
codex plugin add biomed-workbench@biomed-workbench
codex plugin list
```

Then open a **new Codex task** so the `biomed-workbench` skill is loaded. See [installation and updates](docs/installation.md) for local development, updating, verification, and troubleshooting.

## Documentation

- [Capability map](docs/capabilities/README.md)
- [Using Biomed Workbench](docs/using-biomed-workbench.md)
- [Installation and updates](docs/installation.md)
- [Reproducibility and compatibility](docs/reproducibility.md)
- [Public-data acceptance cases](docs/cases/README.md)
- [Capability maturity and evidence](docs/maturity.md)
- [Architecture and module extension](docs/architecture.md)
- [Format contracts](docs/format-contracts.md)
- [Development and release](docs/development.md)

## Scope And Trust

Biomed Workbench is an independent, source-neutral implementation. It does not vendor or route through the research projects that informed its design. Compatibility evidence, public-database checks, template coverage, source reconciliation, and release verification are published in [`reports/`](reports/); attribution and clean-room boundaries are documented in [NOTICE.md](NOTICE.md).

The plugin may use public scientific services and compatible project-local scientific packages. It does not manage CPUs, GPUs, containers, schedulers, remote compute, or local foundation models. Optional credentials are kept outside the repository and are never embedded in module code or research artifacts.

Licensed under [Apache-2.0](LICENSE).
