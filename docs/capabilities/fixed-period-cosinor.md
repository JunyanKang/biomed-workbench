# Declared-Period Cosinor Rhythm

## Purpose

The fixed-period-cosinor module fits one transparent harmonic model to a time series when the period has been declared in advance. It returns mesor, amplitude, acrophase, fitted values, residuals, a nominal zero-amplitude test, time coverage, and phase-bin coverage.

## Required Inputs

The module accepts paired numeric time and values arrays plus a positive period (24 by default). The input artifact must retain time and outcome units, sampling protocol, and the pre-analysis period declaration.

## Scientific Boundaries

This is not a period-discovery method, a nonlinear trend model, or a repeated-measures model. The nominal p-value is conditional on the declared period and independent homoscedastic residuals. A single fitted series cannot establish circadian causality or replace replicate-aware inference.

## Quality Review

The module requires an identifiable design and flags sparse sampling when the observations span less than three quarters of the declared period or cover fewer than four eighth-period bins. Review residuals, sampling design, biological replication, and any multiple-period testing before interpreting an apparent rhythm.

## Execution Contract

The generated Python template is bound to the module contract and retains provenance, dependency compatibility, and quality-gate identifiers in its output. It was verified with Python 3.14.3, NumPy 2.4.4, and SciPy 1.17.1.
