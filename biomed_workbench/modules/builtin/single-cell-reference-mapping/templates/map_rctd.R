#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(spacexr)
  library(Matrix)
  library(jsonlite)
})

parse_args <- function(args) {
  if (length(args) %% 2 != 0) stop("arguments must be supplied as --name value pairs")
  setNames(as.list(args[seq(2, length(args), by = 2)]),
           gsub("-", "_", sub("^--", "", args[seq(1, length(args), by = 2)])))
}
required <- function(args, keys) {
  missing <- keys[!keys %in% names(args)]
  if (length(missing)) stop(paste("missing arguments:", paste(missing, collapse = ", ")))
}
stop_existing <- function(path) {
  if (file.exists(path) || dir.exists(path)) stop(paste("refusing to overwrite:", basename(path)))
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required(args, c("reference_rds", "spatial_rds", "output_rds", "weights_tsv", "report",
                 "mode", "max_cores", "cell_min_instance", "seed"))
if (!args$mode %in% c("full", "doublet")) stop("RCTD mode must be full or doublet")
for (path in c(args$output_rds, args$weights_tsv, args$report)) stop_existing(path)
set.seed(as.integer(args$seed))

reference_input <- readRDS(args$reference_rds)
spatial_input <- readRDS(args$spatial_rds)
reference_fields <- c("counts", "cell_types")
spatial_fields <- c("counts", "coords")
if (!is.list(reference_input) || any(!reference_fields %in% names(reference_input))) {
  stop("reference RDS must be a list containing counts and cell_types")
}
if (!is.list(spatial_input) || any(!spatial_fields %in% names(spatial_input))) {
  stop("spatial RDS must be a list containing counts and coords")
}
reference_counts <- as(reference_input$counts, "dgCMatrix")
spatial_counts <- as(spatial_input$counts, "dgCMatrix")
cell_types <- factor(reference_input$cell_types)
coords <- as.data.frame(spatial_input$coords)
if (ncol(reference_counts) != length(cell_types)) stop("reference cell-type length differs from cells")
if (ncol(spatial_counts) != nrow(coords)) stop("spatial coordinate rows differ from locations")
if (!identical(colnames(spatial_counts), rownames(coords))) stop("spatial count and coordinate identifiers differ")
if (length(intersect(rownames(reference_counts), rownames(spatial_counts))) < 100) {
  stop("reference-spatial shared genes are inadequate")
}
if (any(reference_counts@x < 0) || any(spatial_counts@x < 0)) stop("counts must be nonnegative")
if (any(abs(reference_counts@x - round(reference_counts@x)) > 1e-8) ||
    any(abs(spatial_counts@x - round(spatial_counts@x)) > 1e-8)) {
  stop("RCTD requires integer-like counts")
}
reference_numi <- Matrix::colSums(reference_counts)
spatial_numi <- Matrix::colSums(spatial_counts)
reference <- Reference(reference_counts, cell_types, reference_numi)
spatial <- SpatialRNA(coords, spatial_counts, spatial_numi)
rctd <- create.RCTD(
  spatial, reference, max_cores = as.integer(args$max_cores),
  CELL_MIN_INSTANCE = as.integer(args$cell_min_instance)
)
rctd <- run.RCTD(rctd, doublet_mode = args$mode)
weights <- if (args$mode == "full") {
  rctd@results$weights
} else {
  rctd@results$weights_doublet
}
if (is.null(weights) || nrow(weights) != ncol(spatial_counts)) stop("RCTD weights are absent or incomplete")
weights <- as.matrix(weights)
if (any(!is.finite(weights)) || any(weights < 0)) stop("RCTD weights are invalid")
normalized <- weights / pmax(rowSums(weights), .Machine$double.eps)
write.table(
  data.frame(location_id = rownames(normalized), normalized, check.names = FALSE),
  args$weights_tsv, sep = "\t", quote = FALSE, row.names = FALSE
)
saveRDS(rctd, args$output_rds)
reloaded <- readRDS(args$output_rds)
if (is.null(reloaded@results)) stop("reloaded RCTD object has no results")

payload <- list(
  schema_version = 1,
  passed = TRUE,
  mode = args$mode,
  locations = nrow(normalized),
  cell_types = ncol(normalized),
  shared_genes = length(intersect(rownames(reference_counts), rownames(spatial_counts))),
  parameters = list(
    max_cores = as.integer(args$max_cores),
    cell_min_instance = as.integer(args$cell_min_instance),
    seed = as.integer(args$seed)
  ),
  versions = list(R = paste(R.version$major, R.version$minor, sep = "."),
                  spacexr = as.character(packageVersion("spacexr"))),
  interpretation = if (args$mode == "doublet")
    "near-single-cell locations constrained to singlet or doublet assignments"
  else
    "multi-cell locations represented by nonnegative cell-type mixture weights",
  preservation = list(raw_counts_not_overwritten = TRUE, native_object_saved = TRUE,
                      normalized_weights_saved = TRUE, output_reloaded = TRUE)
)
write_json(payload, args$report, pretty = TRUE, auto_unbox = TRUE)

