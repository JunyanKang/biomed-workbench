# Clinical And Experimental Research

Languages: [English](clinical-and-experimental.md) · [中文](clinical-and-experimental.zh-CN.md)

## Scientific Role

This capability area supports structured clinical analysis, translational evidence, experimental calculations, assay interpretation, and report quality. It is intended for research workflows and does not replace clinical judgment, regulated systems, or laboratory validation.

## Unified Statistics And Clinical Program

For broad statistics, modelling, and translational requests, the workbench first examines the cohort or data matrix and then organises inferential analyses, model evaluation, adverse-event summaries, and clinical and reporting-boundary review. Survival analysis, biomarker performance, classification gold-set evaluation, cosinor modelling, differential expression, dose response, growth curves, and qPCR retain their own input requirements and quality checks.

The plan preserves experimental units, denominators, censoring, threshold dependence, missingness, and model limitations. Clinical translation modules can summarize and audit research evidence, but they block patient-specific diagnosis, treatment, triage, prognosis, or regulated clinical decision support.

## Clinical And Translational Analysis

- Summarize research cohorts with explicit denominators and variable availability.
- Estimate Kaplan-Meier survival with event and censoring context.
- Evaluate binary biomarker performance and preserve threshold dependence.
- Summarize research adverse events without hiding severity or denominator differences.
- De-identify structured clinical records under explicit field rules.
- Audit clinical report structure and retrieve design-aware ClinicalTrials.gov evidence.
- Block patient-specific diagnosis, treatment, triage, and prognosis requests before interpretation, while preserving safe research-summary actions.

## Experimental Planning And Quantification

- Calculate PCR master mixes and serial dilution plans.
- Quantify relative qPCR expression under declared reference and calibrator choices.
- Fit replicate-preserving bacterial growth curves with declared blank correction, logistic and modified Gompertz comparison, residual diagnostics, and explicit biological-replication boundaries.
- Estimate CFU per mL from observed serial-dilution plates while retaining TNTC, low-count, and invalid plates, with exposure-aware pooling, uncertainty, and agreement diagnostics.
- Summarize crystal-violet biofilm assays from explicit blank, control, and replicate-level measurements without converting single readings into significance claims.
- Explore clearly declared bacterial growth-and-clearance scenarios while preserving the boundary between simulation and observed experimental evidence.
- Import complete FCS 2.0, 3.0, or 3.1 event tables with channel identity preserved, then apply sequential flow-cytometry gating plans.
- Calculate CFSE or CellTrace precursor-equivalent frequency, division index, proliferation index, and percent divided from reviewed dye-dilution generations.
- Summarize reviewed Annexin and viability-dye quadrants without substituting default thresholds for compensation and control evidence.
- Fit reviewed DNA-content distributions only when constrained peak separation, convergence, and residual diagnostics support phase interpretation.
- Quantify immunoassay calibration curves and retain model and range limitations.
- Fit steady-state enzyme kinetics and retain uncertainty and model assumptions.
- Fit a predeclared-period cosinor model while retaining sampling coverage, residual diagnostics, and the boundary between descriptive rhythmicity and causal circadian inference.
- Summarize one exported electrophysiology trace with baseline, sampling, peak, and threshold-crossing metrics while blocking spike-class, cell-state, and disease-state overinterpretation.
- Normalize reviewed Western blot ROI measurements by background, optional matched loading control, and declared reference lanes while retaining the technical versus biological repeat boundary.
- Summarize calibrated and decay-correction-declared radiotracer organ measurements as percent injected dose per gram, observed-interval AUC, and matching-time tumor-to-blood ratios without claiming pharmacokinetics or dosimetry.
- Preserve animal-level xenograft tumour-volume trajectories and calculate descriptive endpoint TGI only when the control and analysis endpoint are explicit.
- Compare zero- and first-order accelerated-stability fits and perform explicitly bounded Arrhenius extrapolation only when one kinetic model is supported across temperatures.

## Requirements For Interpretation

The workbench preserves independent experimental units, denominators, censoring, assay range, controls, gating order, calibration assumptions, and missingness. It blocks clinical or causal interpretations that exceed the research design, and it does not treat a computational plan as evidence that an experiment was performed successfully.

For flow cytometry, the workbench can preserve unsampled FCS events, apply declared sequential gates, and quantify explicit marker-rule patterns within retained parent-gate event sets. Marker patterns remain descriptive unless compensation, transformation, threshold basis, panel identity, sample identity, independent evidence, and replicate-aware design support a stronger claim.

## Typical Deliverables

Cohort tables, survival summaries, biomarker reports, adverse-event tables, de-identification outputs, assay calculations, calibration results, gating summaries, experimental plans, methods text, and explicit next-step validation criteria.
