#!/usr/bin/env Rscript
# Run sample-aware scDblFinder from a declared Matrix Market input without mutating source data.

parse_args <- function(values) {
  if (length(values) %% 2 != 0L) stop("arguments must be --name value pairs")
  result <- list()
  for (index in seq(1L, length(values), by = 2L)) {
    key <- sub("^--", "", values[[index]])
    result[[key]] <- values[[index + 1L]]
  }
  required <- c("input-mtx", "sample-id", "output-tsv", "report", "expected-doublet-rate", "seed")
  if (!all(required %in% names(result))) stop("required input, output, and scientific parameters are missing")
  result
}

sha256 <- function(path) {
  digest::digest(file = path, algo = "sha256", serialize = FALSE)
}

matrix_market_file <- function(input) {
  candidates <- file.path(input, c("matrix.mtx.gz", "matrix.mtx"))
  available <- candidates[file.exists(candidates)]
  if (length(available) != 1L) {
    stop("Matrix Market input must contain exactly one of matrix.mtx.gz or matrix.mtx")
  }
  available[[1L]]
}

input_files <- function(input) {
  matrix <- matrix_market_file(input)
  barcodes <- file.path(input, c("barcodes.tsv.gz", "barcodes.tsv"))
  features <- file.path(input, c("features.tsv.gz", "features.tsv", "genes.tsv.gz", "genes.tsv"))
  barcodes <- barcodes[file.exists(barcodes)]
  features <- features[file.exists(features)]
  if (length(barcodes) != 1L || length(features) != 1L) {
    stop("Matrix Market input requires exactly one barcode and one feature table")
  }
  c(matrix = matrix, barcodes = barcodes[[1L]], features = features[[1L]])
}

validate_counts <- function(matrix) {
  if (nrow(matrix) < 20L || ncol(matrix) < 20L) stop("input matrix is too small for doublet detection")
  if (any(!is.finite(matrix@x)) || any(matrix@x < 0) || any(abs(matrix@x - round(matrix@x)) > 1e-8)) {
    stop("input counts must be finite, nonnegative, and integer-like")
  }
  invisible(TRUE)
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  input <- normalizePath(args[["input-mtx"]], mustWork = TRUE)
  output <- args[["output-tsv"]]
  report_path <- args[["report"]]
  if (file.exists(output) || file.exists(report_path)) stop("refusing to overwrite output artifacts")
  if (normalizePath(output, mustWork = FALSE) == input || normalizePath(report_path, mustWork = FALSE) == input) {
    stop("output artifacts must not replace the input directory")
  }
  expected_rate <- as.numeric(args[["expected-doublet-rate"]])
  if (!is.finite(expected_rate) || expected_rate <= 0 || expected_rate >= 1) stop("expected doublet rate must be between zero and one")
  set.seed(as.integer(args$seed))

  suppressPackageStartupMessages({
    library(DropletUtils)
    library(SingleCellExperiment)
    library(scDblFinder)
    library(jsonlite)
    library(digest)
  })
  source_files <- input_files(input)
  source_digests <- vapply(source_files, sha256, character(1L))
  sce <- read10xCounts(input, col.names = TRUE)
  validate_counts(counts(sce))
  input_count_sum <- sum(counts(sce))
  colData(sce)$biological_sample <- args[["sample-id"]]
  sce <- scDblFinder(sce, samples = "biological_sample", dbr = expected_rate, BPPARAM = BiocParallel::SerialParam())
  score <- colData(sce)$scDblFinder.score
  call <- as.character(colData(sce)$scDblFinder.class)
  if (length(score) != ncol(sce) || any(!is.finite(score)) || any(!call %in% c("singlet", "doublet"))) {
    stop("scDblFinder output failed score or class validation")
  }
  result <- data.frame(
    cell_id = colnames(sce),
    biological_sample = as.character(colData(sce)$biological_sample),
    scDblFinder_score = as.numeric(score),
    scDblFinder_class = call,
    stringsAsFactors = FALSE
  )
  dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
  dir.create(dirname(report_path), recursive = TRUE, showWarnings = FALSE)
  write.table(result, output, quote = FALSE, sep = "\t", row.names = FALSE)
  reloaded <- read.delim(output, check.names = FALSE)
  if (nrow(reloaded) != ncol(sce) || !identical(reloaded$cell_id, colnames(sce))) stop("serialized doublet calls do not reconcile to source cells")
  if (!identical(source_digests, vapply(source_files, sha256, character(1L)))) {
    stop("Matrix Market source files changed during scDblFinder execution")
  }
  score_summary <- list(
    minimum = min(score),
    median = median(score),
    maximum = max(score),
    singlet_median = median(score[call == "singlet"]),
    doublet_median = if (any(call == "doublet")) median(score[call == "doublet"]) else NULL
  )
  report <- list(
    schema_version = 2L,
    input = list(
      directory_name = basename(input),
      file_sha256 = as.list(source_digests),
      cells = ncol(sce),
      features = nrow(sce),
      total_counts = input_count_sum,
      sample_id = args[["sample-id"]]
    ),
    input_cells = ncol(sce),
    input_features = nrow(sce),
    sample_id = args[["sample-id"]],
    called_doublets = sum(call == "doublet"),
    called_fraction = mean(call == "doublet"),
    score_summary = score_summary,
    output_rows_reloaded = nrow(reloaded),
    source_immutable = TRUE,
    cell_identity_preserved = TRUE,
    automatic_cell_removal_performed = FALSE,
    versions = list(
      R = as.character(getRversion()),
      scDblFinder = as.character(packageVersion("scDblFinder")),
      SingleCellExperiment = as.character(packageVersion("SingleCellExperiment")),
      DropletUtils = as.character(packageVersion("DropletUtils")),
      BiocParallel = as.character(packageVersion("BiocParallel")),
      jsonlite = as.character(packageVersion("jsonlite")),
      digest = as.character(packageVersion("digest"))
    ),
    quality_status = "review-required"
  )
  write_json(report, report_path, pretty = TRUE, auto_unbox = TRUE)
}

tryCatch(main(), error = function(error) {
  message(conditionMessage(error))
  quit(status = 1L)
})
