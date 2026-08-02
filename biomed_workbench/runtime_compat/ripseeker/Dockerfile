FROM --platform=linux/amd64 bioconductor/bioconductor_docker@sha256:cbd868b0543608c917cef2003cc8f051ba15e6633bf941f35802825b1e5551ab

ARG RIPSEEKER_COMMIT=e3eb1377fc9cd28851a7b301fc410848f7b1347f
COPY .validation/ripseeker-bioc-mirror /opt/ripseeker-bioc-mirror
RUN R -q -e "options(timeout=1200, pkgType='source', BioC_mirror='https://mirrors.tuna.tsinghua.edu.cn/bioconductor', repos=c(BioCsoft='file:///opt/ripseeker-bioc-mirror/packages/3.11/bioc', BioCann='file:///opt/ripseeker-bioc-mirror/packages/3.11/data/annotation', CRAN='https://mirrors.tuna.tsinghua.edu.cn/CRAN/')); pkgs <- c('S4Vectors', 'IRanges', 'GenomicRanges', 'SummarizedExperiment', 'Rsamtools', 'GenomicAlignments', 'rtracklayer'); for (attempt in seq_len(5L)) { missing <- pkgs[!vapply(pkgs, requireNamespace, logical(1), quietly=TRUE)]; if (!length(missing)) break; message('R/Bioconductor dependency attempt ', attempt, '; missing: ', paste(missing, collapse=', ')); try(install.packages(missing, dependencies=NA, type='source'), silent=FALSE); Sys.sleep(attempt * 2L) }; stopifnot(all(vapply(pkgs, requireNamespace, logical(1), quietly=TRUE)))"

COPY .validation/ripseeker-official-e3 /opt/RIPSeeker
COPY biomed_workbench/runtime_compat/ripseeker/bioconductor-3.11-namespace.patch /opt/ripseeker-bioconductor-3.11-namespace.patch
RUN test "$(cat /opt/RIPSeeker/OFFICIAL_COMMIT)" = "${RIPSEEKER_COMMIT}" \
    && patch --directory=/opt/RIPSeeker --strip=1 --forward --input=/opt/ripseeker-bioconductor-3.11-namespace.patch \
    && grep -Fq "import(methods, S4Vectors, IRanges, GenomeInfoDb, GenomicRanges" /opt/RIPSeeker/NAMESPACE \
    && R CMD INSTALL /opt/RIPSeeker \
    && R -q -e "stopifnot(as.character(packageVersion('RIPSeeker')) == '1.28.0')" \
    && rm -rf /opt/RIPSeeker /opt/ripseeker-bioconductor-3.11-namespace.patch

LABEL org.opencontainers.image.source="https://git.bioconductor.org/packages/RIPSeeker" \
      org.opencontainers.image.revision="${RIPSEEKER_COMMIT}" \
      org.opencontainers.image.version="1.28.0" \
      org.bioconductor.release="3.11" \
      org.biomed-workbench.compatibility-patch="GenomeInfoDb namespace import" \
      org.bioconductor.mirror="https://mirrors.tuna.tsinghua.edu.cn/bioconductor" \
      org.r-project.cran-mirror="https://mirrors.tuna.tsinghua.edu.cn/CRAN/"
