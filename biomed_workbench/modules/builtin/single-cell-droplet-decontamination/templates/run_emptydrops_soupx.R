#!/usr/bin/env Rscript
# Execute emptyDrops and SoupX with barcode-level accounting and immutable inputs.

parse_args <- function(values) {
  if (length(values) %% 2L != 0L) stop("arguments must be --name value pairs")
  result <- list()
  for (index in seq(1L, length(values), by = 2L)) {
    result[[sub("^--", "", values[[index]])]] <- values[[index + 1L]]
  }
  required <- c("raw-mtx", "filtered-mtx", "output-dir", "report", "lower", "fdr", "niters", "contamination-mode", "seed")
  if (!all(required %in% names(result))) stop("required input, output, and scientific parameters are missing")
  result
}

validate_counts <- function(matrix, label) {
  if (nrow(matrix) < 20L || ncol(matrix) < 20L) stop(paste(label, "matrix is too small"))
  if (any(!is.finite(matrix@x)) || any(matrix@x < 0) || any(abs(matrix@x - round(matrix@x)) > 1e-8)) {
    stop(paste(label, "counts must be finite, nonnegative, and integer-like"))
  }
}

read_counts <- function(path) {
  sce <- DropletUtils::read10xCounts(normalizePath(path, mustWork = TRUE), col.names = TRUE)
  matrix <- SingleCellExperiment::counts(sce)
  rownames(matrix) <- rowData(sce)$ID
  list(matrix = matrix, symbols = as.character(rowData(sce)$Symbol))
}

write_matrix_bundle <- function(matrix, symbols, output) {
  dir.create(output, recursive = TRUE, showWarnings = FALSE)
  Matrix::writeMM(methods::as(matrix, "dgTMatrix"), file.path(output, "matrix.mtx"))
  write.table(colnames(matrix), file.path(output, "barcodes.tsv"), quote = FALSE, row.names = FALSE, col.names = FALSE)
  features <- data.frame(id = rownames(matrix), symbol = symbols, type = "Gene Expression", stringsAsFactors = FALSE)
  write.table(features, file.path(output, "features.tsv"), quote = FALSE, sep = "\t", row.names = FALSE, col.names = FALSE)
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  output_dir <- args[["output-dir"]]
  report_path <- args$report
  if (dir.exists(output_dir) || file.exists(report_path)) stop("refusing to overwrite declared outputs")
  lower <- as.integer(args$lower)
  fdr <- as.numeric(args$fdr)
  niters <- as.integer(args$niters)
  mode <- args[["contamination-mode"]]
  if (lower < 1L || niters < 100L || !is.finite(fdr) || fdr <= 0 || fdr >= 1) stop("invalid emptyDrops parameters")
  if (!mode %in% c("auto", "fixed")) stop("contamination-mode must be auto or fixed")
  set.seed(as.integer(args$seed))

  suppressPackageStartupMessages({
    library(DropletUtils)
    library(SingleCellExperiment)
    library(SoupX)
    library(Matrix)
    library(jsonlite)
  })
  raw <- read_counts(args[["raw-mtx"]])
  filtered <- read_counts(args[["filtered-mtx"]])
  validate_counts(raw$matrix, "raw droplet")
  validate_counts(filtered$matrix, "filtered cell")
  if (!identical(rownames(raw$matrix), rownames(filtered$matrix))) stop("raw and filtered feature identifiers or order differ")
  if (anyDuplicated(colnames(raw$matrix)) || anyDuplicated(colnames(filtered$matrix))) stop("barcodes must be unique")
  if (!all(colnames(filtered$matrix) %in% colnames(raw$matrix))) stop("filtered barcodes are not a subset of raw droplets")
  raw_filtered_slice <- raw$matrix[, colnames(filtered$matrix), drop = FALSE]
  if (!isTRUE(all.equal(raw_filtered_slice, filtered$matrix, check.attributes = FALSE))) {
    stop("filtered counts do not reconcile to raw droplet counts")
  }

  empty <- DropletUtils::emptyDrops(raw$matrix, lower = lower, niters = niters, BPPARAM = BiocParallel::SerialParam())
  empty_table <- data.frame(
    barcode = colnames(raw$matrix), total = as.numeric(empty$Total), log_probability = as.numeric(empty$LogProb),
    p_value = as.numeric(empty$PValue), limited = as.logical(empty$Limited), fdr = as.numeric(empty$FDR),
    emptydrops_call = !is.na(empty$FDR) & empty$FDR <= fdr, stringsAsFactors = FALSE
  )
  if (nrow(empty_table) != ncol(raw$matrix)) stop("emptyDrops did not account for every raw barcode")

  channel <- SoupX::SoupChannel(raw$matrix, filtered$matrix, calcSoupProfile = TRUE)
  if (mode == "auto") {
    cluster_path <- args[["cluster-tsv"]]
    if (is.null(cluster_path)) stop("auto contamination requires --cluster-tsv")
    clusters <- read.delim(cluster_path, stringsAsFactors = FALSE)
    if (!identical(names(clusters), c("barcode", "cluster")) || anyDuplicated(clusters$barcode)) stop("cluster TSV must have unique barcode and cluster columns")
    cluster_map <- setNames(as.character(clusters$cluster), clusters$barcode)
    if (!all(colnames(filtered$matrix) %in% names(cluster_map))) stop("cluster TSV does not cover every filtered barcode")
    channel <- SoupX::setClusters(channel, cluster_map[colnames(filtered$matrix)])
    tfidf_min <- if (is.null(args[["tfidf-min"]])) 1 else as.numeric(args[["tfidf-min"]])
    soup_quantile <- if (is.null(args[["soup-quantile"]])) 0.9 else as.numeric(args[["soup-quantile"]])
    if (!is.finite(tfidf_min) || tfidf_min <= 0 || !is.finite(soup_quantile) || soup_quantile <= 0 || soup_quantile >= 1) {
      stop("invalid SoupX marker-selection parameters")
    }
    channel <- SoupX::autoEstCont(channel, tfidfMin = tfidf_min, soupQuantile = soup_quantile, doPlot = FALSE, forceAccept = FALSE, verbose = FALSE)
  } else {
    fraction <- as.numeric(args[["contamination-fraction"]])
    if (!is.finite(fraction) || fraction <= 0 || fraction >= 0.8) stop("fixed contamination fraction must be in (0, 0.8)")
    channel <- SoupX::setContaminationFraction(channel, fraction, forceAccept = FALSE)
  }
  corrected <- SoupX::adjustCounts(channel, roundToInt = TRUE, verbose = 0)
  if (!identical(dim(corrected), dim(filtered$matrix)) || any(!is.finite(corrected@x)) || any(corrected@x < 0)) {
    stop("SoupX corrected matrix failed shape, finite-value, or nonnegative checks")
  }
  if (!identical(rownames(corrected), rownames(filtered$matrix)) || !identical(colnames(corrected), colnames(filtered$matrix))) {
    stop("SoupX changed feature or barcode identity")
  }
  if (sum(corrected) > sum(filtered$matrix) + 1e-8) stop("SoupX correction increased total counts")

  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  write.table(empty_table, file.path(output_dir, "emptydrops_calls.tsv"), quote = FALSE, sep = "\t", row.names = FALSE)
  write_matrix_bundle(corrected, filtered$symbols, file.path(output_dir, "soupx_corrected"))
  reloaded <- Matrix::readMM(file.path(output_dir, "soupx_corrected", "matrix.mtx"))
  if (!identical(dim(reloaded), dim(corrected)) || !isTRUE(all.equal(as.numeric(reloaded), as.numeric(corrected)))) {
    stop("serialized SoupX matrix did not reload exactly")
  }
  rho <- as.numeric(channel$metaData$rho)
  report <- list(
    raw_droplets = ncol(raw$matrix), filtered_cells = ncol(filtered$matrix), features = nrow(raw$matrix),
    emptydrops_tested = sum(!is.na(empty_table$p_value)), emptydrops_called = sum(empty_table$emptydrops_call), emptydrops_fdr = fdr,
    contamination_mode = mode, contamination_fraction_min = min(rho), contamination_fraction_median = median(rho), contamination_fraction_max = max(rho),
    source_filtered_counts = sum(filtered$matrix), corrected_counts = sum(corrected), removed_counts = sum(filtered$matrix) - sum(corrected),
    source_identifiers_preserved = TRUE, serialized_output_reloaded = TRUE, source_artifacts_mutated = FALSE,
    versions = list(R = as.character(getRversion()), DropletUtils = as.character(packageVersion("DropletUtils")), SoupX = as.character(packageVersion("SoupX"))),
    quality_status = "review-required"
  )
  write_json(report, report_path, pretty = TRUE, auto_unbox = TRUE)
}

tryCatch(main(), error = function(error) {
  message(conditionMessage(error))
  quit(status = 1L)
})
