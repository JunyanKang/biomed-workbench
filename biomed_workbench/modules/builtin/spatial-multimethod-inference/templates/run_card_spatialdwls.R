#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(optparse)
  library(Matrix)
  library(SingleCellExperiment)
  library(SpatialExperiment)
  library(jsonlite)
})

options <- list(
  make_option("--backend", type="character"),
  make_option("--spatial-rds", dest="spatial_rds", type="character"),
  make_option("--reference-rds", dest="reference_rds", type="character"),
  make_option("--cell-type-column", dest="cell_type_column", type="character"),
  make_option("--reference-sample-column", dest="reference_sample_column", type="character"),
  make_option("--spatial-sample-column", dest="spatial_sample_column", type="character"),
  make_option("--marker-tsv", dest="marker_tsv", type="character", default=NULL),
  make_option("--x-column", dest="x_column", type="character", default="x"),
  make_option("--y-column", dest="y_column", type="character", default="y"),
  make_option("--minimum-shared-genes", dest="minimum_shared_genes", type="integer", default=500),
  make_option("--minimum-count-gene", dest="minimum_count_gene", type="integer", default=100),
  make_option("--minimum-count-spot", dest="minimum_count_spot", type="integer", default=5),
  make_option("--dwls-cells-per-spot", dest="dwls_cells_per_spot", type="integer", default=50),
  make_option("--dwls-cutoff", dest="dwls_cutoff", type="double", default=2),
  make_option("--seed", type="integer"),
  make_option("--abundance-output", dest="abundance_output", type="character"),
  make_option("--model-output", dest="model_output", type="character"),
  make_option("--report", type="character")
)

parse_and_validate <- function() {
  o <- parse_args(OptionParser(option_list=options))
  required <- c(
    "backend", "spatial_rds", "reference_rds", "cell_type_column",
    "reference_sample_column", "spatial_sample_column", "seed",
    "abundance_output", "model_output", "report"
  )
  if (any(vapply(required, function(x) is.null(o[[x]]) || !nzchar(as.character(o[[x]])), logical(1)))) {
    stop("missing required option")
  }
  if (!o$backend %in% c("card", "spatialdwls")) stop("backend must be card or spatialdwls")
  if (o$backend == "spatialdwls" && (is.null(o$marker_tsv) || !file.exists(o$marker_tsv))) {
    stop("SpatialDWLS requires a frozen marker TSV")
  }
  if (any(file.exists(c(o$abundance_output, o$model_output, o$report)))) {
    stop("refusing to overwrite output")
  }
  o
}

count_values <- function(x) {
  if (inherits(x, "sparseMatrix")) x@x else as.vector(x)
}

validate_count_matrix <- function(x, label) {
  values <- count_values(x)
  if (!length(values) || any(!is.finite(values)) || any(values < 0) ||
      any(abs(values - round(values)) > 1e-8)) {
    stop(paste(label, "requires finite nonnegative integer counts"))
  }
}

normalize_proportions <- function(weights, location_ids) {
  weights <- as.data.frame(weights, check.names=FALSE)
  id_candidates <- intersect(colnames(weights), c("location_id", "cell_ID", "cell_IDs", "spot"))
  if (length(id_candidates)) {
    rownames(weights) <- as.character(weights[[id_candidates[[1]]]])
    weights <- weights[, setdiff(colnames(weights), id_candidates), drop=FALSE]
  }
  if (is.null(rownames(weights)) || identical(rownames(weights), as.character(seq_len(nrow(weights))))) {
    rownames(weights) <- location_ids
  }
  weights <- weights[location_ids, , drop=FALSE]
  numeric_columns <- vapply(weights, is.numeric, logical(1))
  weights <- weights[, numeric_columns, drop=FALSE]
  matrix_values <- as.matrix(weights)
  if (ncol(matrix_values) < 2 || any(!is.finite(matrix_values)) || any(matrix_values < 0)) {
    stop("scientific validation failed: invalid deconvolution output")
  }
  totals <- rowSums(matrix_values)
  if (any(totals <= 0)) stop("scientific validation failed: zero-mass location")
  result <- as.data.frame(matrix_values / totals, check.names=FALSE)
  result$location_id <- rownames(result)
  result[, c("location_id", setdiff(colnames(result), "location_id")), drop=FALSE]
}

o <- parse_and_validate()
set.seed(o$seed)
spatial <- readRDS(o$spatial_rds)
reference <- readRDS(o$reference_rds)
if (!inherits(spatial, "SpatialExperiment") || !inherits(reference, "SingleCellExperiment")) {
  stop("expected SpatialExperiment and SingleCellExperiment inputs")
}
if (!o$cell_type_column %in% colnames(colData(reference)) ||
    !o$reference_sample_column %in% colnames(colData(reference)) ||
    !o$spatial_sample_column %in% colnames(colData(spatial))) {
  stop("declared cell-type or sample metadata is absent")
}
if (anyNA(colData(reference)[[o$cell_type_column]]) ||
    anyNA(colData(reference)[[o$reference_sample_column]]) ||
    anyNA(colData(spatial)[[o$spatial_sample_column]])) {
  stop("cell-type and sample metadata must be complete")
}
if (length(unique(colData(spatial)[[o$spatial_sample_column]])) != 1) {
  stop("run one biological spatial sample per invocation")
}
shared <- intersect(rownames(spatial), rownames(reference))
if (length(shared) < o$minimum_shared_genes) stop("insufficient shared genes")
spatial_counts <- counts(spatial[shared, ])
reference_counts <- counts(reference[shared, ])
validate_count_matrix(spatial_counts, "spatial data")
validate_count_matrix(reference_counts, "single-cell reference")
coordinates <- as.data.frame(spatialCoords(spatial))
if (!all(c(o$x_column, o$y_column) %in% colnames(coordinates))) {
  stop("declared coordinate columns are absent")
}
coordinates <- coordinates[, c(o$x_column, o$y_column), drop=FALSE]
rownames(coordinates) <- colnames(spatial_counts)
labels <- as.character(colData(reference)[[o$cell_type_column]])

if (o$backend == "card") {
  suppressPackageStartupMessages(library(CARD))
  reference_meta <- data.frame(
    cell_type = labels,
    sample = as.character(colData(reference)[[o$reference_sample_column]]),
    row.names = colnames(reference_counts),
    stringsAsFactors=FALSE
  )
  model <- createCARDObject(
    sc_count = reference_counts,
    sc_meta = reference_meta,
    spatial_count = spatial_counts,
    spatial_location = coordinates,
    ct.varname = "cell_type",
    ct.select = sort(unique(reference_meta$cell_type)),
    sample.varname = "sample",
    minCountGene = o$minimum_count_gene,
    minCountSpot = o$minimum_count_spot
  )
  model <- CARD_deconvolution(CARD_object=model)
  weights <- model@Proportion_CARD
  method_version <- as.character(packageVersion("CARD"))
  semantics <- "spatially regularized cell-type proportions"
} else {
  suppressPackageStartupMessages(library(Giotto))
  markers <- read.delim(o$marker_tsv, check.names=FALSE, stringsAsFactors=FALSE)
  if (!all(c("gene", "cell_type") %in% colnames(markers)) || anyNA(markers[, c("gene", "cell_type")])) {
    stop("marker TSV requires complete gene and cell_type columns")
  }
  marker_genes <- unique(markers$gene[
    markers$gene %in% shared & markers$cell_type %in% unique(labels)
  ])
  if (length(marker_genes) < 20 || length(unique(markers$cell_type)) < 2) {
    stop("marker table does not retain enough reviewed markers or cell types")
  }
  library_sizes <- Matrix::colSums(reference_counts)
  normalized_reference <- log2(
    t(t(as.matrix(reference_counts)) / pmax(library_sizes, 1) * 1e4) + 1
  )
  signature <- makeSignMatrixDWLSfromMatrix(
    matrix=normalized_reference,
    sign_gene=marker_genes,
    cell_type_vector=labels
  )
  model <- createGiottoObject(
    raw_exprs=spatial_counts,
    spatial_locs=coordinates
  )
  model <- normalizeGiotto(model)
  model <- runDWLSDeconv(
    gobject=model,
    expression_values="normalized",
    sign_matrix=signature,
    n_cell=o$dwls_cells_per_spot,
    cutoff=o$dwls_cutoff,
    name="DWLS",
    return_gobject=TRUE
  )
  weights <- getSpatialEnrichment(
    model,
    name="DWLS",
    output="data.table"
  )
  method_version <- as.character(packageVersion("Giotto"))
  semantics <- "marker-screened dampened weighted least-squares proportions"
}

normalized <- normalize_proportions(weights, colnames(spatial_counts))
dir.create(dirname(o$abundance_output), recursive=TRUE, showWarnings=FALSE)
write.table(normalized, o$abundance_output, sep="\t", quote=FALSE, row.names=FALSE)
saveRDS(model, o$model_output)
write_json(
  list(
    schema_version=1,
    passed=TRUE,
    backend=o$backend,
    method_version=method_version,
    shared_genes=length(shared),
    locations=ncol(spatial_counts),
    reference_cells=ncol(reference_counts),
    cell_types=length(unique(labels)),
    sample=as.character(unique(colData(spatial)[[o$spatial_sample_column]])),
    parameters=list(
      minimum_count_gene=o$minimum_count_gene,
      minimum_count_spot=o$minimum_count_spot,
      dwls_cells_per_spot=o$dwls_cells_per_spot,
      dwls_cutoff=o$dwls_cutoff,
      seed=o$seed
    ),
    output_semantics=semantics,
    claim_boundary=paste(
      "Proportions are reference- and marker-dependent estimates.",
      "Review residuals, reference subsampling, held-out genes and sample-level reproducibility."
    )
  ),
  o$report,
  pretty=TRUE,
  auto_unbox=TRUE
)
reloaded <- read.delim(o$abundance_output, check.names=FALSE)
if (nrow(reloaded) != ncol(spatial_counts) || anyNA(reloaded)) {
  stop("serialized abundance output failed reload validation")
}
