#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(Seurat)
  library(symphony)
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
required(args, c("reference_rds", "query_rds", "reference_output", "query_output",
                 "report", "assay", "batch_key", "label_key", "k", "knn_k", "seed"))
for (path in c(args$reference_output, args$query_output, args$report)) stop_existing(path)
set.seed(as.integer(args$seed))

reference <- readRDS(args$reference_rds)
query <- readRDS(args$query_rds)
if (!inherits(reference, "Seurat") || !inherits(query, "Seurat")) stop("inputs must be Seurat objects")
if (!args$assay %in% Assays(reference) || !args$assay %in% Assays(query)) stop("declared assay is absent")
if (!args$batch_key %in% colnames(reference[[]])) stop("reference batch metadata is absent")
if (!args$label_key %in% colnames(reference[[]])) stop("reference label metadata is absent")
if (anyDuplicated(Cells(reference)) || anyDuplicated(Cells(query))) stop("cell identifiers must be unique")

reference <- NormalizeData(reference, assay = args$assay, verbose = FALSE)
reference <- FindVariableFeatures(reference, assay = args$assay, nfeatures = 3000, verbose = FALSE)
query <- NormalizeData(query, assay = args$assay, verbose = FALSE)
features <- intersect(VariableFeatures(reference), rownames(query[[args$assay]]))
if (length(features) < 200) stop("reference-query feature overlap is inadequate")
exp_ref <- as.matrix(GetAssayData(reference, assay = args$assay, layer = "data")[features, , drop = FALSE])
exp_query <- as.matrix(GetAssayData(query, assay = args$assay, layer = "data")[features, , drop = FALSE])
ref_meta <- reference[[]]
query_meta <- query[[]]
query_meta[[args$batch_key]] <- if (args$batch_key %in% colnames(query_meta)) {
  as.character(query_meta[[args$batch_key]])
} else {
  "query"
}

ref_obj <- buildReference(
  exp_ref, ref_meta, vars = args$batch_key, K = as.integer(args$k),
  verbose = FALSE, do_umap = TRUE
)
query_obj <- mapQuery(
  exp_query, query_meta, ref_obj, vars = args$batch_key,
  verbose = FALSE, do_normalize = FALSE
)
pred <- knnPredict(
  query_obj$Zq_pca, ref_obj$Z_corr, as.character(ref_meta[[args$label_key]]),
  k = as.integer(args$knn_k)
)
if (length(pred) != ncol(exp_query)) stop("prediction length differs from query cells")
if (anyNA(pred) || any(!nzchar(as.character(pred)))) {
  stop("scientific validation failed: incomplete label suggestions")
}
query[["symphony"]] <- CreateDimReducObject(
  embeddings = query_obj$Zq_corr, key = "SYMPHONY_", assay = args$assay
)
query$`symphony.suggested.label` <- as.character(pred)
saveRDS(ref_obj, args$reference_output)
saveRDS(query, args$query_output)
ref_reload <- readRDS(args$reference_output)
query_reload <- readRDS(args$query_output)
if (!identical(Cells(query_reload), Cells(query))) stop("query reload changed cells")
if (nrow(Embeddings(query_reload, "symphony")) != ncol(query_reload)) {
  stop("scientific validation failed: invalid Symphony embedding")
}

payload <- list(
  schema_version = 1,
  passed = TRUE,
  cells = list(reference = ncol(exp_ref), query = ncol(exp_query)),
  shared_features = length(features),
  predictions = as.list(table(pred)),
  parameters = list(batch_key = args$batch_key, label_key = args$label_key,
                    K = as.integer(args$k), knn_k = as.integer(args$knn_k),
                    seed = as.integer(args$seed)),
  versions = list(
    R = paste(R.version$major, R.version$minor, sep = "."),
    Seurat = as.character(packageVersion("Seurat")),
    symphony = as.character(packageVersion("symphony"))
  ),
  preservation = list(
    reference_saved = !is.null(ref_reload), query_cells_preserved = TRUE,
    output_reloaded = TRUE, predictions_are_suggestions = TRUE
  )
)
write_json(payload, args$report, pretty = TRUE, auto_unbox = TRUE)
