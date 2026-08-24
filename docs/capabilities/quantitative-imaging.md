# Quantitative Image Analysis

Languages: [English](quantitative-imaging.md) · [中文](quantitative-imaging.zh-CN.md)

## Scientific Role

Quantitative image analysis turns pixels, channels, and time series into reviewable measurements. It answers what was measured in an image, not how a result should be laid out for publication. Objects, thresholds, spatial calibration, time intervals, and quality checks are defined before visual styling.

## Current Capabilities

- inspect image dimensions, channels, bit depth, intensity distributions, and basic format information;
- segment objects with explicit parameters and return masks, connected-component tables, and segmentation review images;
- measure two-channel colocalisation while retaining channel pairing, thresholds, analysis regions, and method assumptions;
- track declared objects across frames and preserve object-level trajectories plus loss, merge, and break states;
- calculate path length, net displacement, speed, and directionality from pixel size and time interval;
- align equal-sized two-dimensional images by a bounded integer translation and report overlap and error. This is a baseline alignment check, not affine, deformable, or three-dimensional registration.

Tissue images, cell boundaries, coordinate transforms, and multi-section registration in spatial transcriptomics are handled by the dedicated [spatial analysis workflow](trajectory-spatial-complete-analysis.md). General quantitative imaging does not automatically cover microscopy-vendor raw formats, histology deep-learning models, or clinical image diagnosis.

## How Results Enter Scientific Figures

Masks, object-level tables, colocalisation statistics, trajectories, and migration measurements are analysis results. After scientific review, they can become source data for main figures, supplementary figures, or quality-control views. Typography, strokes, colour, legends, statistical annotations, layout, and export follow the project-wide [Scientific Figure Standards And Delivery](scientific-figure-standards.md). Figure standards cannot alter segmentation results, remove inconvenient objects, or replace source images.

## Interpretation Boundaries

Background removal, cropping, brightness adjustment, or explanatory illustration cannot establish segmentation, morphology, localisation, intensity, or colocalisation. Whether images, fields, or object-level observations are independent statistical units depends on the sampling design; multiple fields from the same animal, specimen, or culture do not automatically become independent biological replicates.

## Typical Deliverables

Image-inspection reports, parameter records, masks, component tables, colocalisation statistics, object-level trajectories, migration measurements, alignment error, quality-control views, and result notes linked to source images and experimental units.
