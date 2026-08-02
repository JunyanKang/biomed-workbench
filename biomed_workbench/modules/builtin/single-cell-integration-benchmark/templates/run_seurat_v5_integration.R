#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(Seurat)
  library(jsonlite)
})

parse_args <- function(args) {
  if (length(args) %% 2 != 0) stop("arguments must be supplied as --name value pairs")
  keys <- sub("^--", "", args[seq(1, length(args), by = 2)])
  if (any(keys == args[seq(1, length(args), by = 2)])) stop("argument names must start with --")
  setNames(as.list(args[seq(2, length(args), by = 2)]), gsub("-", "_", keys))
}

required <- function(args, names) {
  missing <- names[!names %in% names(args)]
  if (length(missing)) stop(paste("missing arguments:", paste(missing, collapse = ", ")))
}

stop_existing <- function(path) {
  if (file.exists(path) || dir.exists(path)) stop(paste("refusing to overwrite:", basename(path)))
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
required(args, c("input_rds", "output_rds", "report", "batch_key", "assay", "methods",
                 "nfeatures", "dims", "seed"))
stop_existing(args$output_rds)
stop_existing(args$report)

methods <- unique(strsplit(tolower(args$methods), ",", fixed = TRUE)[[1]])
allowed <- c("cca", "rpca", "fastmnn")
if (!length(methods) || any(!methods %in% allowed)) stop("methods must be cca,rpca,fastmnn")
if ("fastmnn" %in% methods && !requireNamespace("SeuratWrappers", quietly = TRUE)) {
  stop("FastMNNIntegration requires SeuratWrappers")
}
nfeatures <- as.integer(args$nfeatures)
dims <- seq_len(as.integer(args$dims))
seed <- as.integer(args$seed)
if (!is.finite(nfeatures) || nfeatures < 100) stop("nfeatures must be at least 100")
if (!length(dims) || max(dims) < 2) stop("dims must be at least 2")
set.seed(seed)

object <- readRDS(args$input_rds)
if (!inherits(object, "Seurat")) stop("input_rds must contain a Seurat object")
if (!args$assay %in% Assays(object)) stop("declared assay is absent")
if (!args$batch_key %in% colnames(object[[]])) stop("batch metadata is absent")
batch <- trimws(as.character(object[[args$batch_key]][, 1]))
if (anyNA(batch) || any(batch == "") || length(unique(batch)) < 2) {
  stop("batch metadata requires at least two nonempty levels")
}
if (anyDuplicated(Cells(object))) stop("cell identifiers must be unique")

DefaultAssay(object) <- args$assay
count_layers <- Layers(object[[args$assay]], search = "^counts")
if (!length(count_layers)) stop("an immutable count layer is required")
if (length(count_layers) == 1L) {
  object[[args$assay]] <- split(object[[args$assay]], f = batch)
}

object <- NormalizeData(object, verbose = FALSE)
object <- FindVariableFeatures(object, nfeatures = nfeatures, verbose = FALSE)
object <- ScaleData(object, verbose = FALSE)
object <- RunPCA(object, npcs = max(dims), verbose = FALSE, seed.use = seed)
baseline_cells <- Cells(object)
baseline_counts <- LayerData(JoinLayers(object[[args$assay]]), layer = "counts")
baseline_count_sum <- sum(baseline_counts)

reductions <- list()
for (method in methods) {
  reduction_name <- paste0("integrated.", method)
  if (method == "cca") {
    object <- IntegrateLayers(
      object = object, method = CCAIntegration, orig.reduction = "pca",
      new.reduction = reduction_name, dims = dims, verbose = FALSE
    )
  } else if (method == "rpca") {
    object <- IntegrateLayers(
      object = object, method = RPCAIntegration, orig.reduction = "pca",
      new.reduction = reduction_name, dims = dims, verbose = FALSE
    )
  } else {
    object <- IntegrateLayers(
      object = object, method = SeuratWrappers::FastMNNIntegration,
      new.reduction = reduction_name, dims = dims, verbose = FALSE
    )
  }
  embedding <- Embeddings(object, reduction = reduction_name)
  if (!identical(rownames(embedding), baseline_cells)) stop("integration changed cell identity or order")
  if (any(!is.finite(embedding))) stop("integration produced nonfinite coordinates")
  reductions[[method]] <- list(
    reduction = reduction_name,
    cells = nrow(embedding),
    dimensions = ncol(embedding)
  )
}

joined <- JoinLayers(object)
if (!identical(Cells(joined), baseline_cells)) stop("output cell identity changed")
if (!isTRUE(all.equal(sum(LayerData(joined[[args$assay]], layer = "counts")),
                      baseline_count_sum, tolerance = 0))) {
  stop("raw count sum changed")
}
saveRDS(object, args$output_rds)
reloaded <- readRDS(args$output_rds)
if (!identical(Cells(reloaded), baseline_cells)) stop("reloaded output changed cell identity")

report <- list(
  schema_version = 1,
  passed = TRUE,
  method_results = reductions,
  parameters = list(
    batch_key = args$batch_key, assay = args$assay, nfeatures = nfeatures,
    dims = dims, seed = seed
  ),
  preservation = list(
    source_cells_preserved = TRUE, raw_counts_preserved = TRUE,
    output_reloaded = TRUE, corrected_expression_not_created = TRUE
  ),
  versions = list(
    R = paste(R.version$major, R.version$minor, sep = "."),
    Seurat = as.character(packageVersion("Seurat")),
    SeuratObject = as.character(packageVersion("SeuratObject")),
    SeuratWrappers = if (requireNamespace("SeuratWrappers", quietly = TRUE))
      as.character(packageVersion("SeuratWrappers")) else NA
  )
)
write_json(report, args$report, pretty = TRUE, auto_unbox = TRUE, na = "null")

