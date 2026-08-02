#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(optparse)
  library(Matrix)
  library(SingleCellExperiment)
  library(SpatialExperiment)
  library(jsonlite)
})

options <- list(
  make_option("--output-directory", dest="output_directory", type="character"),
  make_option("--report", type="character")
)
o <- parse_args(OptionParser(option_list=options))
if (is.null(o$output_directory) || is.null(o$report)) stop("output directory and report are required")
if (dir.exists(o$output_directory) || file.exists(o$report)) stop("refusing to overwrite output")

package_root <- system.file("extdata", package="spacexr")
if (!nzchar(package_root)) stop("spacexr official example data are absent")
reference_directory <- file.path(package_root, "Reference", "Vignette")
spatial_directory <- file.path(package_root, "SpatialRNA", "Vignette")
reference_counts <- as.matrix(read.csv(file.path(reference_directory, "dge.csv"), row.names=1, check.names=FALSE))
reference_metadata <- read.csv(file.path(reference_directory, "meta_data.csv"), row.names=1, check.names=FALSE)
spatial_counts <- as.matrix(read.csv(file.path(spatial_directory, "MappedDGEForR.csv"), row.names=1, check.names=FALSE))
coordinates <- read.csv(file.path(spatial_directory, "BeadLocationsForR.csv"), row.names=1, check.names=FALSE)
if (!identical(colnames(reference_counts), rownames(reference_metadata))) stop("reference barcodes do not reconcile")
if (!identical(colnames(spatial_counts), rownames(coordinates))) stop("spatial barcodes do not reconcile")
if (any(reference_counts < 0) || any(spatial_counts < 0) ||
    any(reference_counts != round(reference_counts)) || any(spatial_counts != round(spatial_counts))) {
  stop("official example matrices must contain nonnegative integer counts")
}
storage.mode(reference_counts) <- "integer"
storage.mode(spatial_counts) <- "integer"
reference <- SingleCellExperiment(
  assays=list(counts=Matrix(reference_counts, sparse=TRUE)),
  colData=DataFrame(cell_type=factor(reference_metadata$cluster), nUMI=reference_metadata$nUMI)
)
spatial <- SpatialExperiment(
  assays=list(counts=Matrix(spatial_counts, sparse=TRUE)),
  colData=DataFrame(sample_id=rep("spacexr-slide-seq-vignette", ncol(spatial_counts))),
  spatialCoords=as.matrix(data.frame(x=coordinates$xcoord, y=coordinates$ycoord, row.names=rownames(coordinates)))
)
dir.create(o$output_directory, recursive=TRUE)
reference_path <- file.path(o$output_directory, "reference.rds")
spatial_path <- file.path(o$output_directory, "spatial.rds")
saveRDS(reference, reference_path)
saveRDS(spatial, spatial_path)
reference_reload <- readRDS(reference_path)
spatial_reload <- readRDS(spatial_path)
if (!identical(dim(reference_reload), dim(reference)) || !identical(dim(spatial_reload), dim(spatial))) {
  stop("prepared RDS files failed reload reconciliation")
}
write_json(list(
  schema_version=1,
  passed=TRUE,
  source=list(repository="https://github.com/dmcable/spacexr", commit="9f5dc33c8060f946c6072a138b70e189636e1435", package_version=as.character(packageVersion("spacexr"))),
  reference=list(genes=nrow(reference), cells=ncol(reference), cell_types=nlevels(reference$cell_type), total_counts=sum(counts(reference))),
  spatial=list(genes=nrow(spatial), locations=ncol(spatial), total_counts=sum(counts(spatial)), coordinate_columns=colnames(spatialCoords(spatial))),
  shared_genes=length(intersect(rownames(reference), rownames(spatial))),
  outputs=list(reference_rds=reference_path, spatial_rds=spatial_path, reloaded=TRUE)
), o$report, pretty=TRUE, auto_unbox=TRUE)
