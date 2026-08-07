# Imaging And Scientific Visualisation

Languages: [English](imaging-and-visualization.md) · [中文](imaging-and-visualization.zh-CN.md)

## Scientific Role

This area covers two distinct kinds of work: quantitative measurement from images and scientific figures made from existing data and conclusions. Illustrations created for communication do not replace source images or quantitative results.

## Quantitative Imaging

- inspect image dimensions, channels, bit depth, and intensity distributions;
- segment objects with explicit parameters and return masks, component tables, and quality-review images;
- measure two-channel colocalisation while retaining channel pairing, thresholds, and method assumptions;
- track declared objects across frames and preserve object-level trajectories;
- calculate path length, net displacement, speed, and directionality from pixel size and time interval;
- align equal-sized two-dimensional images by a bounded integer translation and report overlap and error. This is a baseline check, not affine or deformable registration.

## Scientific Visualisation

- define a figure from the scientific conclusion, data source, uncertainty, and purpose of each figure part;
- use image generation for illustrations when appropriate and review both scientific content and layout before delivery;
- create provenance-linked interactive protein-structure views;
- perform bounded edits such as background removal on purpose-made communication images while preserving the original and the limits of the edit.

Tissue images, cell boundaries, and registration in spatial transcriptomics are handled by the dedicated [spatial analysis workflow](trajectory-spatial-complete-analysis.md). Current general imaging coverage focuses on image inspection, masks, colocalisation, trajectories, and figures; it does not claim complete support for every microscopy vendor's native format.

## Interpretation Boundaries

A rendered or edited communication image cannot replace a primary measurement. Background-removed output is not evidence for segmentation, morphology, localisation, intensity, or colocalisation. A generated illustration must not invent an experimental observation. Each scientific figure should preserve the statistical unit, data source, uncertainty, and direction of the conclusion it communicates.

## Typical Deliverables

Image-inspection reports, masks and component tables, colocalisation statistics, object trajectories, migration measurements, interactive structure views, scientific-figure plans, illustrations, and figure-to-conclusion consistency review.
