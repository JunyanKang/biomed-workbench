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

md5 <- function(path) {
  unname(tools::md5sum(path))
}

matrix_market_file <- function(input) {
  candidates <- file.path(input, c("matrix.mtx.gz", "matrix.mtx"))
  available <- candidates[file.exists(candidates)]
  if (length(available) != 1L) {
    stop("Matrix Market input must contain exactly one of matrix.mtx.gz or matrix.mtx")
  }
  available[[1L]]
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
  expected_rate <- as.numeric(args[["expected-doublet-rate"]])
  if (!is.finite(expected_rate) || expected_rate <= 0 || expected_rate >= 1) stop("expected doublet rate must be between zero and one")
  set.seed(as.integer(args$seed))

  suppressPackageStartupMessages({
    library(DropletUtils)
    library(SingleCellExperiment)
    library(scDblFinder)
    library(jsonlite)
  })
  sce <- read10xCounts(input, col.names = TRUE)
  validate_counts(counts(sce))
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
  report <- list(
    input_matrix_md5 = md5(matrix_market_file(input)),
    input_cells = ncol(sce),
    input_features = nrow(sce),
    sample_id = args[["sample-id"]],
    called_doublets = sum(call == "doublet"),
    called_fraction = mean(call == "doublet"),
    output_rows_reloaded = nrow(reloaded),
    versions = list(
      R = as.character(getRversion()),
      scDblFinder = as.character(packageVersion("scDblFinder")),
      SingleCellExperiment = as.character(packageVersion("SingleCellExperiment"))
    ),
    quality_status = "review-required"
  )
  write_json(report, report_path, pretty = TRUE, auto_unbox = TRUE)
}

tryCatch(main(), error = function(error) {
  message(conditionMessage(error))
  quit(status = 1L)
})
