# Radiotracer Biodistribution

The radiotracer-biodistribution module calculates organ-level percent injected dose per gram from declared injected dose, tissue activity, and tissue mass. It retains every sample, summarizes each organ-timepoint, integrates only the observed interval by the trapezoidal rule, and optionally reports tumor-to-blood ratios at matching timepoints.

The caller must preserve radionuclide identity, dose calibration, decay-correction reference time, counting efficiency, recovery, dissection, weighing, and sample identity. The output does not apply decay correction, fit pharmacokinetics, extrapolate exposure, estimate residence time, or calculate absorbed dose or MIRD dosimetry.

Technical measurements and multiple organs from one animal are not independent biological replicates. The generated Python template retains the request, module contract, and output provenance; it was verified with Python 3.14.3.
