# Genomic Prediction

`rrblup-genomic-prediction` evaluates an additive RR-BLUP model only on individuals held out by a project-declared biological grouping. It validates 0/1/2 dosage coding, phenotype and individual identity, fixed folds, model versions, fold isolation, held-out predictions, fold-level variance components, RMSE, correlation and calibration slope.

Its performance is conditional on the trait definition, genotyping, fold design and prediction population. It is not evidence of causal markers, heritability, parent value, clinical utility or transportability to a new population.
