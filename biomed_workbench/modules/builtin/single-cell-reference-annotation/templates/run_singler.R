#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(BiocParallel)
  library(jsonlite)
  library(Matrix)
  library(SingleR)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 8L) {
  stop("expected query matrix, reference matrix, genes, query cells, reference cells, labels, predictions, and versions")
}

query <- readMM(args[[1L]])
reference <- readMM(args[[2L]])
genes <- readLines(args[[3L]], warn = FALSE)
query_cells <- readLines(args[[4L]], warn = FALSE)
reference_cells <- readLines(args[[5L]], warn = FALSE)
labels <- readLines(args[[6L]], warn = FALSE)
if (nrow(query) != length(genes) || nrow(reference) != length(genes)) {
  stop("matrix rows do not match the common gene list")
}
if (ncol(query) != length(query_cells) || ncol(reference) != length(reference_cells)) {
  stop("matrix columns do not match cell identifiers")
}
if (length(labels) != ncol(reference) || anyNA(labels) || any(labels == "")) {
  stop("reference labels do not match reference cells")
}
rownames(query) <- genes
rownames(reference) <- genes
colnames(query) <- query_cells
colnames(reference) <- reference_cells

prediction <- SingleR(
  test = query,
  ref = reference,
  labels = labels,
  genes = "de",
  de.method = "classic",
  fine.tune = TRUE,
  prune = TRUE,
  BPPARAM = SerialParam()
)
scores <- as.matrix(prediction$scores)
result <- data.frame(
  cell_id = query_cells,
  singler_label = as.character(prediction$labels),
  singler_pruned_label = ifelse(is.na(prediction$pruned.labels), "", as.character(prediction$pruned.labels)),
  singler_delta_next = as.numeric(prediction$delta.next),
  singler_max_score = apply(scores, 1L, max),
  stringsAsFactors = FALSE,
  check.names = FALSE
)
for (label in colnames(scores)) {
  result[[paste0("score::", label)]] <- scores[, label]
}
write.table(result, args[[7L]], sep = "\t", quote = FALSE, row.names = FALSE, na = "")

versions <- list(
  r = paste(R.version$major, R.version$minor, sep = "."),
  SingleR = as.character(packageVersion("SingleR")),
  Matrix = as.character(packageVersion("Matrix")),
  BiocParallel = as.character(packageVersion("BiocParallel")),
  jsonlite = as.character(packageVersion("jsonlite"))
)
write_json(versions, args[[8L]], auto_unbox = TRUE, pretty = TRUE)
