args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 5L) stop("expected manifest, gff, parameters JSON, output directory, and required version")
manifest_path <- normalizePath(args[[1]], mustWork = TRUE)
gff_path <- normalizePath(args[[2]], mustWork = TRUE)
parameters_path <- normalizePath(args[[3]], mustWork = TRUE)
output_dir <- args[[4]]
required_version <- args[[5]]
if (!requireNamespace("exomePeak2", quietly = TRUE)) stop("exomePeak2 is not installed")
if (!requireNamespace("jsonlite", quietly = TRUE)) stop("jsonlite is not installed")
observed_version <- as.character(utils::packageVersion("exomePeak2"))
if (!identical(observed_version, required_version)) stop("exomePeak2 version mismatch")
manifest <- utils::read.delim(manifest_path, stringsAsFactors = FALSE, check.names = FALSE)
if (!identical(names(manifest), c("group", "path", "sha256"))) stop("invalid BAM manifest columns")
if (any(!file.exists(manifest$path))) stop("BAM manifest contains missing files")
parameters <- jsonlite::fromJSON(parameters_path, simplifyVector = TRUE)
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
if (length(list.files(output_dir, all.files = TRUE, no.. = TRUE)) != 0L) stop("output directory is not empty")
select_group <- function(name) manifest$path[manifest$group == name]
control_ip <- select_group("control_ip")
control_input <- select_group("control_input")
treated_ip <- select_group("treated_ip")
treated_input <- select_group("treated_input")
null_if_empty <- function(x) if (length(x) == 0L) NULL else x
genome <- if (nzchar(parameters$genome)) parameters$genome else NULL
result <- exomePeak2::exomePeak2(
  bam_ip = control_ip,
  bam_input = control_input,
  bam_ip_treated = null_if_empty(treated_ip),
  bam_input_treated = null_if_empty(treated_input),
  gff = gff_path,
  genome = genome,
  strandness = parameters$strandness,
  fragment_length = parameters$fragment_length,
  bin_size = parameters$bin_size,
  step_size = parameters$step_size,
  test_method = parameters$test_method,
  p_cutoff = parameters$p_cutoff,
  diff_p_cutoff = parameters$diff_p_cutoff,
  parallel = parameters$parallel,
  plot_gc = parameters$plot_gc,
  save_output = TRUE,
  save_dir = output_dir,
  experiment_name = "exomePeak2_output",
  mode = parameters$mode,
  motif_based = parameters$motif_based,
  motif_sequence = parameters$motif_sequence,
  absolute_diff = parameters$absolute_diff
)
result_path <- file.path(output_dir, "exomePeak2_result.rds")
saveRDS(result, result_path)
reloaded <- readRDS(result_path)
if (!identical(length(reloaded), length(result))) stop("exomePeak2 result failed RDS reload reconciliation")
writeLines(observed_version, file.path(output_dir, "exomePeak2_version.txt"))
