#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(optparse)
  library(Matrix)
  library(jsonlite)
})

options <- list(
  make_option("--backend", type="character"),
  make_option("--spatial-rds", dest="spatial_rds", type="character"),
  make_option("--reference-rds", dest="reference_rds", type="character"),
  make_option("--cell-type-column", dest="cell_type_column", type="character"),
  make_option("--sample-column", dest="sample_column", type="character"),
  make_option("--marker-tsv", dest="marker_tsv", type="character", default=NULL),
  make_option("--x-column", dest="x_column", type="character", default="x"),
  make_option("--y-column", dest="y_column", type="character", default="y"),
  make_option("--doublet-mode", dest="doublet_mode", type="character", default="full"),
  make_option("--minimum-shared-genes", dest="minimum_shared_genes", type="integer", default=500),
  make_option("--minimum-proportion", dest="minimum_proportion", type="double", default=0.01),
  make_option("--nmf-iterations", dest="nmf_iterations", type="integer", default=100),
  make_option("--max-cores", dest="max_cores", type="integer", default=1),
  make_option("--seed", type="integer"),
  make_option("--abundance-output", dest="abundance_output", type="character"),
  make_option("--model-output", dest="model_output", type="character"),
  make_option("--report", type="character")
)
o <- parse_args(OptionParser(option_list=options))
validate_options <- function(o) {
  required <- c("backend", "spatial_rds", "reference_rds", "cell_type_column", "sample_column", "seed", "abundance_output", "model_output", "report")
  if (any(vapply(required, function(x) is.null(o[[x]]) || !nzchar(as.character(o[[x]])), logical(1)))) stop("missing required option")
  if (!o$backend %in% c("rctd", "spotlight")) stop("backend must be rctd or spotlight")
  if (!o$doublet_mode %in% c("full", "doublet", "multi")) stop("unsupported RCTD doublet mode")
  if (o$backend == "spotlight" && (is.null(o$marker_tsv) || !file.exists(o$marker_tsv))) {
    stop("SPOTlight requires a frozen marker TSV")
  }
  if (!is.finite(o$minimum_proportion) || o$minimum_proportion < 0 || o$minimum_proportion > 1) {
    stop("minimum proportion must be between zero and one")
  }
  if (any(file.exists(c(o$abundance_output, o$model_output, o$report)))) stop("refusing to overwrite output")
}
validate_options(o)
set.seed(o$seed)
count_values <- function(x) {
  if (inherits(x, "sparseMatrix")) x@x else as.vector(x)
}
spatial <- readRDS(o$spatial_rds)
reference <- readRDS(o$reference_rds)
if (!inherits(spatial, "SpatialExperiment") || !inherits(reference, "SingleCellExperiment")) stop("expected SpatialExperiment and SingleCellExperiment RDS inputs")
if (!o$sample_column %in% colnames(colData(spatial))) stop("spatial sample column absent")
if (!o$cell_type_column %in% colnames(colData(reference))) stop("reference cell type column absent")
if (anyNA(colData(spatial)[[o$sample_column]]) || anyNA(colData(reference)[[o$cell_type_column]])) stop("sample and cell-type metadata must be complete")
if (length(unique(colData(spatial)[[o$sample_column]])) != 1) {
  stop("run one biological spatial sample per invocation")
}
shared <- intersect(rownames(spatial), rownames(reference))
if (length(shared) < o$minimum_shared_genes) stop("insufficient shared genes")
spatial_counts <- counts(spatial[shared, ])
reference_counts <- counts(reference[shared, ])
spatial_values <- count_values(spatial_counts)
reference_values <- count_values(reference_counts)
if (any(!is.finite(spatial_values)) || any(spatial_values < 0) ||
    any(abs(spatial_values - round(spatial_values)) > 1e-8)) {
  stop("spatial data require finite nonnegative integer counts")
}
if (any(!is.finite(reference_values)) || any(reference_values < 0) ||
    any(abs(reference_values - round(reference_values)) > 1e-8)) {
  stop("reference data require finite nonnegative integer counts")
}

if (o$backend == "rctd") {
  suppressPackageStartupMessages(library(spacexr))
  coords <- as.data.frame(spatialCoords(spatial))
  if (!all(c(o$x_column, o$y_column) %in% colnames(coords))) stop("declared coordinate columns are absent")
  puck <- SpatialRNA(
    coords[, c(o$x_column, o$y_column), drop=FALSE],
    spatial_counts,
    colSums(spatial_counts)
  )
  reference_cell_types <- factor(colData(reference)[[o$cell_type_column]])
  names(reference_cell_types) <- colnames(reference_counts)
  reference_n_umi <- colSums(reference_counts)
  names(reference_n_umi) <- colnames(reference_counts)
  ref <- Reference(reference_counts, reference_cell_types, reference_n_umi)
  model <- create.RCTD(puck, ref, max_cores=o$max_cores)
  model <- run.RCTD(model, doublet_mode=o$doublet_mode)
  weights <- as.data.frame(as.matrix(model@results$weights), check.names=FALSE)
  method_version <- as.character(packageVersion("spacexr"))
} else {
  suppressPackageStartupMessages(library(SPOTlight))
  markers <- read.delim(o$marker_tsv, check.names=FALSE, stringsAsFactors=FALSE)
  required_markers <- c("gene", "cell_type", "weight")
  if (!all(required_markers %in% colnames(markers))) {
    stop("marker TSV requires gene, cell_type and weight columns")
  }
  if (anyNA(markers[, required_markers]) || any(!is.finite(markers$weight)) ||
      any(markers$weight <= 0)) {
    stop("marker table contains incomplete or invalid weights")
  }
  markers <- markers[
    markers$gene %in% shared &
      markers$cell_type %in% unique(as.character(colData(reference)[[o$cell_type_column]])),
    , drop=FALSE
  ]
  if (nrow(markers) < 20 || length(unique(markers$cell_type)) < 2) {
    stop("marker table does not retain enough reviewed markers or cell types")
  }
  marker_input <- data.frame(
    gene = markers$gene,
    type = markers$cell_type,
    weight = markers$weight,
    stringsAsFactors=FALSE
  )
  weights <- SPOTlight(
    x = reference_counts,
    y = spatial_counts,
    groups = as.character(colData(reference)[[o$cell_type_column]]),
    mgs = marker_input,
    hvg = NULL,
    gene_id = "gene",
    group_id = "type",
    weight_id = "weight",
    min_prop = o$minimum_proportion,
    maxit = o$nmf_iterations,
    threads = o$max_cores,
    verbose = FALSE
  )
  weights <- as.data.frame(weights)
  model <- list(
    backend = "SPOTlight",
    marker_table = marker_input,
    parameters = list(
      min_prop = o$minimum_proportion,
      maxit = o$nmf_iterations,
      threads = o$max_cores
    )
  )
  method_version <- as.character(packageVersion("SPOTlight"))
}
residual_columns <- intersect(colnames(weights), c("res_ss", "residual", "unknown"))
abundance_columns <- setdiff(colnames(weights), residual_columns)
if (length(abundance_columns) < 2) stop("scientific validation failed: fewer than two abundance columns")
abundance <- as.matrix(weights[, abundance_columns, drop=FALSE])
if (any(!is.finite(abundance)) || any(abundance < 0)) {
  stop("scientific validation failed: abundance values are nonfinite or negative")
}
row_totals <- rowSums(abundance)
if (any(row_totals <= 0)) stop("scientific validation failed: zero-mass spatial location")
weights[, abundance_columns] <- abundance / row_totals
weights$location_id <- rownames(weights)
weights <- weights[, c("location_id", setdiff(colnames(weights), "location_id")), drop=FALSE]
dir.create(dirname(o$abundance_output), recursive=TRUE, showWarnings=FALSE)
write.table(weights, o$abundance_output, sep="\t", quote=FALSE, row.names=FALSE)
saveRDS(model, o$model_output)
model_reload <- readRDS(o$model_output)
if (o$backend == "rctd" && !inherits(model_reload, "RCTD")) stop("native RCTD model failed reload validation")
reloaded <- read.delim(o$abundance_output, check.names=FALSE)
if (nrow(reloaded) != nrow(weights) || anyNA(reloaded) || anyDuplicated(reloaded$location_id) ||
    !all(reloaded$location_id %in% colnames(spatial))) stop("output reload reconciliation failed")
write_json(list(schema_version=1, passed=TRUE, backend=o$backend, method_version=method_version, shared_genes=length(shared), seed=o$seed,
  parameters=list(doublet_mode=o$doublet_mode, minimum_proportion=o$minimum_proportion,
    nmf_iterations=o$nmf_iterations, max_cores=o$max_cores),
  sample=as.character(unique(colData(spatial)[[o$sample_column]])),
  spatial_locations_input=ncol(spatial), spatial_locations_retained=nrow(weights), reference_cells=ncol(reference), cell_types=length(unique(colData(reference)[[o$cell_type_column]])),
  abundance_columns=abundance_columns,
  outputs=list(abundance_tsv=o$abundance_output, native_model_rds=o$model_output, model_reloaded=TRUE),
  interpretation_scope="Cell-type abundance estimates retain the selected reference, backend, parameters, biological sample identity and RCTD location filtering for sensitivity review."), o$report, pretty=TRUE, auto_unbox=TRUE)
