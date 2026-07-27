# One-Site ITC Binding

The itc-single-site-binding module fits one declared series of integrated ITC
injection heats using a dilution-aware one-site equilibrium model. It reports
fitted thermodynamic parameters, per-injection predictions and residuals,
parameter uncertainty when identifiable, convergence, and parameter-bound
warnings.

It requires integrated heats rather than raw thermograms. It does not select a
binding model, perform global fitting, correct concentration uncertainty, or
establish a biological interaction. Blank titrations, technical and biological
replicates, injection anomalies, and residual structure remain mandatory
review inputs.
