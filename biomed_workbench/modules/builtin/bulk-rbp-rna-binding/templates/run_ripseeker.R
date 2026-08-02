args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 4L) stop("expected localized BAM directory, parameters JSON, output directory, and required version")
if (!requireNamespace("RIPSeeker", quietly = TRUE)) stop("RIPSeeker is not installed")
if (!requireNamespace("jsonlite", quietly = TRUE)) stop("jsonlite is not installed")
observed <- as.character(utils::packageVersion("RIPSeeker")); if (!identical(observed, args[[4]])) stop("RIPSeeker version mismatch")
bams <- list.files(normalizePath(args[[1]], mustWork = TRUE), pattern = "\\.bam$", full.names = TRUE)
if (length(bams) < 2L || !any(grepl("CONTROL_", basename(bams)))) stop("localized RIP/control BAM set is invalid")
p <- jsonlite::fromJSON(normalizePath(args[[2]], mustWork = TRUE), simplifyVector = TRUE)
out <- args[[3]]; dir.create(out, recursive = TRUE, showWarnings = FALSE)
null_value <- function(x) if (is.null(x) || length(x) == 0L) NULL else x
set.seed(as.integer(p$seed))
result <- RIPSeeker::ripSeek(
  bamPath = bams, cNAME = "CONTROL_", binSize = null_value(p$bin_size), strandType = null_value(p$strand_type),
  paired = p$paired, outDir = out, padjMethod = p$padj_method, logOddCutoff = p$log_odd_cutoff,
  pvalCutoff = p$pvalue_cutoff, pvalAdjCutoff = p$adjusted_pvalue_cutoff, eFDRCutoff = p$empirical_fdr_cutoff,
  minBinSize = p$min_bin_size, maxBinSize = p$max_bin_size, reverseComplement = p$reverse_complement,
  genomeBuild = p$genome_build, uniqueHit = p$unique_hit, assignMultihits = p$assign_multihits,
  rerunWithDisambiguatedMultihits = p$rerun_disambiguated_multihits, multicore = p$multicore
)
result_rds <- file.path(out, "RIPSeeker_result.rds")
saveRDS(result, result_rds)
writeLines(observed, file.path(out, "RIPSeeker_version.txt"))

region_files <- list.files(out, pattern = "^RIPregions\\.", full.names = TRUE)
if (!length(region_files)) stop("RIPSeeker did not produce a region file")
region_rows <- vapply(region_files, function(path) {
  lines <- readLines(path, warn = FALSE)
  sum(nzchar(lines) & !grepl("^#", lines))
}, integer(1))
model_files <- list.files(out, pattern = "\\.RData$", full.names = TRUE)
if (!length(model_files)) stop("RIPSeeker did not produce an RData model")
model_objects <- lapply(model_files, function(path) {
  environment <- new.env(parent = emptyenv())
  loaded <- load(path, envir = environment)
  list(file = basename(path), objects = loaded, object_count = length(loaded))
})
reloaded <- readRDS(result_rds)
validation <- list(
  ripseeker_version = observed,
  region_files = lapply(seq_along(region_files), function(index) list(
    file = basename(region_files[[index]]), row_count = unname(region_rows[[index]])
  )),
  total_region_rows = sum(region_rows),
  model_files = model_objects,
  result_rds = list(file = basename(result_rds), class = class(reloaded), length = length(reloaded)),
  reload_passed = TRUE
)
jsonlite::write_json(validation, file.path(out, "RIPSeeker_validation.json"), auto_unbox = TRUE, pretty = TRUE)
