#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(optparse)
  library(ggplot2)
  library(patchwork)
  library(jsonlite)
  library(svglite)
  library(ragg)
  library(digest)
})

options <- list(
  make_option("--figure-manifest", dest="figure_manifest", type="character"),
  make_option("--figure-contract", dest="figure_contract", type="character"),
  make_option("--output-directory", dest="output_directory", type="character"),
  make_option("--basename", type="character", default="analysis-figure"),
  make_option("--width-mm", dest="width_mm", type="double", default=183),
  make_option("--height-mm", dest="height_mm", type="double", default=170),
  make_option("--dpi", type="integer", default=600),
  make_option("--allow-incomplete-profile", dest="allow_incomplete_profile", action="store_true", default=FALSE)
)
o <- parse_args(OptionParser(option_list=options))
if (is.null(o$figure_manifest) || is.null(o$figure_contract) || is.null(o$output_directory)) stop("manifest, contract and output directory are required")
if (dir.exists(o$output_directory)) stop("refusing to overwrite output directory")
manifest <- fromJSON(o$figure_manifest, simplifyVector=FALSE)
contract <- fromJSON(o$figure_contract, simplifyVector=TRUE)
panels <- manifest$panels
if (length(panels) == 0) stop("figure manifest has no panels")
ids <- vapply(panels, function(x) as.character(x$id), character(1))
if (any(!nzchar(ids)) || anyDuplicated(ids)) stop("panel ids must be nonempty and unique")
missing_required <- setdiff(contract$required_plots, ids)
if (length(missing_required) && !o$allow_incomplete_profile) stop(paste("required analysis figures are missing:", paste(missing_required, collapse=", ")))
if (o$width_mm <= 0 || o$height_mm <= 0 || o$height_mm > contract$style$canvas$maximum_height_mm || o$dpi < 300) stop("invalid final-size export dimensions or dpi")

theme_workbench <- function() {
  theme_classic(base_family="Arial", base_size=7) +
    theme(
      plot.title=element_text(size=7, face="plain"),
      axis.title=element_text(size=7),
      axis.text=element_text(size=6, color="black"),
      legend.title=element_text(size=6),
      legend.text=element_text(size=6),
      legend.position="right",
      legend.key.size=grid::unit(7, "pt"),
      axis.line=element_line(linewidth=0.5 * 0.3528),
      axis.ticks=element_line(linewidth=0.5 * 0.3528),
      panel.grid.minor=element_blank(),
      plot.margin=margin(2,2,2,2,"mm")
    )
}

read_panel <- function(panel) {
  if (is.null(panel$data) || !file.exists(panel$data)) stop(paste("panel data absent:", panel$id))
  d <- read.delim(panel$data, check.names=FALSE)
  if (!all(c("x","y") %in% names(d)) && !panel$type %in% c("bar","heatmap")) stop(paste("panel requires x and y:", panel$id))
  d
}

make_plot <- function(panel) {
  d <- read_panel(panel)
  title <- ifelse(is.null(panel$title), panel$id, panel$title)
  type <- panel$type
  if (type %in% c("scatter","spatial-map")) {
    if ("color" %in% names(d)) {
      p <- ggplot(d, aes(x=x, y=y, color=color)) + geom_point(size=0.85, alpha=0.9)
    } else {
      p <- ggplot(d, aes(x=x, y=y)) + geom_point(size=0.85, color="#0072B2", alpha=0.9)
    }
    if (type == "spatial-map") p <- p + coord_fixed()
  } else if (type == "line") {
    if ("group" %in% names(d)) p <- ggplot(d, aes(x=x,y=y,group=group,color=group)) + geom_line(linewidth=0.5)
    else p <- ggplot(d, aes(x=x,y=y)) + geom_line(linewidth=0.5,color="#0072B2")
  } else if (type == "vector") {
    if (!all(c("x2","y2") %in% names(d))) stop(paste("vector panel requires x2 and y2:", panel$id))
    p <- ggplot(d, aes(x=x,y=y,xend=x2,yend=y2)) + geom_segment(arrow=arrow(length=grid::unit(2,"pt")), linewidth=0.5, color="#0072B2") + coord_fixed()
  } else if (type == "bar") {
    if (!all(c("label","value") %in% names(d))) stop(paste("bar panel requires label and value:", panel$id))
    p <- ggplot(d, aes(x=reorder(label,value),y=value,fill=if ("color" %in% names(d)) color else label)) + geom_col(linewidth=0.5) + coord_flip() + guides(fill="none")
  } else if (type == "heatmap") {
    if (!all(c("row","column","value") %in% names(d))) stop(paste("heatmap panel requires row, column and value:", panel$id))
    p <- ggplot(d, aes(x=column,y=row,fill=value)) + geom_tile() + scale_fill_gradient2(low="#3B4CC0",mid="#F7F7F7",high="#B40426")
  } else stop(paste("unsupported panel type:", type))
  p + labs(title=title, x=ifelse(is.null(panel$x_label),"",panel$x_label), y=ifelse(is.null(panel$y_label),"",panel$y_label), color=ifelse(is.null(panel$legend_title),"",panel$legend_title), fill=ifelse(is.null(panel$legend_title),"",panel$legend_title)) + theme_workbench()
}

dir.create(o$output_directory, recursive=TRUE)
plots <- lapply(panels, make_plot)
names(plots) <- ids
for (i in seq_along(plots)) {
  ggsave(file.path(o$output_directory, paste0(ids[i], ".pdf")), plots[[i]], width=89, height=70, units="mm", device=cairo_pdf)
  ggsave(file.path(o$output_directory, paste0(ids[i], ".svg")), plots[[i]], width=89, height=70, units="mm", device=svglite)
}
combined <- wrap_plots(plots, ncol=ifelse(length(plots) <= 2, 1, 2)) + plot_annotation(tag_levels="A")
pdf_path <- file.path(o$output_directory, paste0(o$basename, ".pdf"))
svg_path <- file.path(o$output_directory, paste0(o$basename, ".svg"))
tiff_path <- file.path(o$output_directory, paste0(o$basename, ".tiff"))
ggsave(pdf_path, combined, width=o$width_mm, height=o$height_mm, units="mm", device=cairo_pdf)
ggsave(svg_path, combined, width=o$width_mm, height=o$height_mm, units="mm", device=svglite)
ggsave(tiff_path, combined, width=o$width_mm, height=o$height_mm, units="mm", dpi=o$dpi, device=ragg::agg_tiff, compression="lzw")
files <- list.files(o$output_directory, full.names=TRUE)
report <- list(
  schema_version=1, analysis_type=contract$analysis_type, style_version=contract$style$version,
  journal_profile=contract$journal_profile, required_plots=contract$required_plots,
  rendered_panel_ids=ids, missing_required=missing_required,
  complete_profile=length(missing_required)==0, width_mm=o$width_mm, height_mm=o$height_mm, dpi=o$dpi,
  backend="R/ggplot2/patchwork/svglite/ragg", input_manifest_sha256=digest(file=o$figure_manifest, algo="sha256"),
  outputs=lapply(files, function(x) list(path=normalizePath(x), sha256=digest(file=x, algo="sha256"), bytes=file.info(x)$size))
)
write_json(report, file.path(o$output_directory, "figure-package-report.json"), pretty=TRUE, auto_unbox=TRUE)
if (!all(file.info(c(pdf_path,svg_path,tiff_path))$size > 1000)) stop("one or more aggregate exports are empty")
