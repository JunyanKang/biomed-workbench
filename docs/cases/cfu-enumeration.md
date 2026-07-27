# Dilution-Plate CFU Enumeration Case

This deterministic acceptance case uses two observed countable plates from
independently labelled cultures, a low-count plate, and a TNTC plate. The
module retains all four plate records and pools only the countable plates using
their cumulative dilution factors and plated volumes.

The result reports CFU per mL with an exact Poisson confidence interval and a
Pearson diagnostic for disagreement between the countable plates. It does not
average incompatible back-calculated concentrations, turn TNTC into a numeric
count, or invent missing plate measurements.

The case is a single-sample measurement check. It does not establish strain
fitness, treatment response, viability, contamination status, or plating
recovery. Those questions require the relevant controls, independently cultured
biological replicates, and a design-aware comparison.
