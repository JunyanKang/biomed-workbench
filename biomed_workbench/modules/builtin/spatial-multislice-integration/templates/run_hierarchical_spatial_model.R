#!/usr/bin/env Rscript
suppressPackageStartupMessages({library(optparse); library(lme4); library(jsonlite)})
options <- list(
  make_option("--input-tsv", dest="input_tsv", type="character"),
  make_option("--response", type="character"),
  make_option("--condition", type="character"),
  make_option("--sample", type="character"),
  make_option("--section", type="character"),
  make_option("--domain", type="character"),
  make_option("--covariates", type="character", default=""),
  make_option("--minimum-samples-per-condition", dest="minimum_samples_per_condition", type="integer", default=2),
  make_option("--results-output", dest="results_output", type="character"),
  make_option("--report", type="character")
)
o <- parse_args(OptionParser(option_list=options))

validate_options <- function(o) {
  required <- c("input_tsv","response","condition","sample","section","domain","results_output","report")
  if (any(vapply(required, function(x) is.null(o[[x]]) || !nzchar(o[[x]]), logical(1)))) stop("missing required option")
  if (any(file.exists(c(o$results_output, o$report)))) stop("refusing to overwrite output")
  if (o$minimum_samples_per_condition < 2L) stop("minimum independent sample threshold must be at least two")
}

validate_model_table <- function(d, o, covariates) {
  columns <- c(o$response,o$condition,o$sample,o$section,o$domain)
  if (!all(columns %in% names(d)) || anyNA(d[, columns])) stop("required model fields are absent or incomplete")
  if (!all(covariates %in% names(d))) stop("covariate absent")
  if (any(!is.finite(as.numeric(d[[o$response]])))) stop("response contains nonfinite values")
  design <- unique(d[, c(o$sample,o$condition), drop=FALSE])
  if (any(table(design[[o$condition]]) < o$minimum_samples_per_condition)) stop("insufficient independent biological samples per condition")
  nested <- unique(d[, c(o$sample,o$section), drop=FALSE])
  if (nrow(nested) < nrow(design)) stop("section nesting is invalid")
}

validate_options(o)
d <- read.delim(o$input_tsv, check.names=FALSE)
covariates <- Filter(nzchar, strsplit(o$covariates, ",", fixed=TRUE)[[1]])
validate_model_table(d, o, covariates)
fixed <- paste(c(o$condition, o$domain, paste0(o$condition, ":", o$domain), covariates), collapse=" + ")
formula <- as.formula(paste(o$response, "~", fixed, "+ (1|", o$sample, ") + (1|", o$sample, ":", o$section, ")"))
fit <- lmer(formula, data=d, REML=FALSE)
method_version <- as.character(packageVersion("lme4"))
coefs <- as.data.frame(coef(summary(fit)))
coefs$term <- rownames(coefs)
rownames(coefs) <- NULL
if (!nrow(coefs) || any(!is.finite(coefs$Estimate))) stop("model coefficient validation failed")
dir.create(dirname(o$results_output), recursive=TRUE, showWarnings=FALSE)
write.table(coefs, o$results_output, sep="\t", quote=FALSE, row.names=FALSE)
write_json(list(schema_version=1, formula=deparse(formula), observations=nrow(d), biological_samples=length(unique(d[[o$sample]])),
  lme4_version=method_version, singular=isSingular(fit), convergence=fit@optinfo$conv$lme4$messages,
  claim_boundary="Condition effects use biological samples as the experimental unit; cells/spots and sections are nested observations."),
  o$report, pretty=TRUE, auto_unbox=TRUE, null="null")
reloaded <- read.delim(o$results_output, check.names=FALSE)
if (nrow(reloaded) != nrow(coefs) || anyNA(reloaded$term)) stop("model output reload validation failed")
