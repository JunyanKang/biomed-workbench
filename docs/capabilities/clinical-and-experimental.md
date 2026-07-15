# Clinical And Experimental Research

## Scientific Role

This capability area supports structured clinical analysis, translational evidence, experimental calculations, assay interpretation, and report quality. It is intended for research workflows and does not replace clinical judgment, regulated systems, or laboratory validation.

## Clinical And Translational Analysis

- Summarize research cohorts with explicit denominators and variable availability.
- Estimate Kaplan-Meier survival with event and censoring context.
- Evaluate binary biomarker performance and preserve threshold dependence.
- Summarize research adverse events without hiding severity or denominator differences.
- De-identify structured clinical records under explicit field rules.
- Audit clinical report structure and retrieve design-aware ClinicalTrials.gov evidence.

Representative modules include `cohort-summary`, `survival-analysis`, `biomarker-performance`, `adverse-event-summary`, `clinical-deidentify`, `clinical-report-audit`, and `clinical-trial-evidence`.

## Experimental Planning And Quantification

- Calculate PCR master mixes and serial dilution plans.
- Quantify relative qPCR expression under declared reference and calibrator choices.
- Summarize dose-response and growth-curve measurements.
- Apply sequential flow-cytometry gating plans to structured measurements.
- Quantify immunoassay calibration curves and retain model and range limitations.
- Fit steady-state enzyme kinetics and retain uncertainty and model assumptions.

Representative modules include `pcr-plan`, `dilution-plan`, `qpcr-relative-expression`, `dose-response`, `growth-curve`, `flow-cytometry-summary`, `immunoassay-quantification`, and `enzyme-kinetics`.

## Quality Gates

The workbench preserves independent experimental units, denominators, censoring, assay range, controls, gating order, calibration assumptions, and missingness. It blocks clinical or causal interpretations that exceed the research design, and it does not treat a computational plan as evidence that an experiment was performed successfully.

## Typical Deliverables

Cohort tables, survival summaries, biomarker reports, adverse-event tables, de-identification outputs, assay calculations, calibration results, gating summaries, experimental plans, methods text, and explicit next-step validation criteria.
