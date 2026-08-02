#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(optparse)
  library(BayesSpace)
})
options <- list(
  make_option("--input", type="character"),
  make_option("--output", type="character"),
  make_option("--clusters", type="integer"),
  make_option("--seed", type="integer"),
  make_option("--platform", type="character", default="Visium"),
  make_option("--nrep", type="integer", default=50000),
  make_option("--gamma", type="numeric", default=3),
  make_option("--d", type="integer", default=15)
)
o <- parse_args(OptionParser(option_list=options))

validate_options <- function(o) {
  required <- c("input", "output", "clusters", "seed", "platform", "nrep", "gamma", "d")
  if (any(vapply(required, function(x) is.null(o[[x]]) || !nzchar(as.character(o[[x]])), logical(1)))) {
    stop("missing required BayesSpace option")
  }
  if (file.exists(o$output)) stop("refusing to overwrite output")
  if (o$clusters < 2L || o$nrep < 1000L || o$d < 2L || !is.finite(o$gamma) || o$gamma <= 0) {
    stop("invalid cluster, iteration, dimension or gamma parameter")
  }
}

validate_spatial_experiment <- function(spe) {
  if (!inherits(spe, "SpatialExperiment")) stop("BayesSpace input must be a SpatialExperiment RDS")
  if (is.null(spatialCoords(spe)) || ncol(spatialCoords(spe)) < 2) stop("spatial coordinates are absent")
  if (ncol(spe) < 20L || nrow(spe) < 100L) stop("input is too small for spatial-domain analysis")
  coords <- as.matrix(spatialCoords(spe)[, 1:2, drop=FALSE])
  if (any(!is.finite(coords))) stop("spatial coordinates are nonfinite")
  if (anyDuplicated(colnames(spe))) stop("observation identifiers are duplicated")
}

validate_options(o)
spe <- readRDS(o$input)
validate_spatial_experiment(spe)
input_observations <- colnames(spe)
method_version <- as.character(packageVersion("BayesSpace"))
set.seed(o$seed)
spe <- spatialPreprocess(spe, platform=o$platform, n.PCs=o$d, log.normalize=TRUE)
spe <- spatialCluster(spe, q=o$clusters, d=o$d, platform=o$platform, nrep=o$nrep, gamma=o$gamma, seed=o$seed)
labels <- as.character(colData(spe)$spatial.cluster)
if (length(labels) != length(input_observations) || anyNA(labels)) stop("BayesSpace labels are incomplete")
if (length(unique(labels)) < 2L) stop("BayesSpace returned fewer than two domains")
if (!identical(colnames(spe), input_observations)) stop("BayesSpace changed observation order")
dir.create(dirname(o$output), recursive=TRUE, showWarnings=FALSE)
write.table(data.frame(observation_id=input_observations, domain=labels),
  o$output, sep="\t", quote=FALSE, row.names=FALSE)
reloaded <- read.delim(o$output, check.names=FALSE, stringsAsFactors=FALSE)
if (!identical(reloaded$observation_id, input_observations)) stop("output reload changed observation order")
message(sprintf("BayesSpace version %s emitted %d validated labels", method_version, nrow(reloaded)))
