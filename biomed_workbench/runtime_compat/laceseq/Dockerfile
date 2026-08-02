FROM quay.io/biocontainers/bowtie@sha256:f29fc740b5d50d6b305c480c5eba5b42c28e0bfb7dd5d4b9b720ac529a5d61ee AS bowtie

FROM quay.io/biocontainers/cutadapt@sha256:949d08d76446d48af457b5d485ec4d93cb8f49fab407f9eb1e0e0104ebbc3777

COPY --from=bowtie /usr/local/bin/bowtie /usr/local/bin/bowtie
COPY --from=bowtie /usr/local/bin/bowtie-align-l /usr/local/bin/bowtie-align-l
COPY --from=bowtie /usr/local/bin/bowtie-align-s /usr/local/bin/bowtie-align-s
COPY --from=bowtie /usr/local/bin/bowtie-build /usr/local/bin/bowtie-build
COPY --from=bowtie /usr/local/bin/bowtie-build-l /usr/local/bin/bowtie-build-l
COPY --from=bowtie /usr/local/bin/bowtie-build-s /usr/local/bin/bowtie-build-s
COPY --from=bowtie /usr/local/bin/bowtie-inspect /usr/local/bin/bowtie-inspect
COPY --from=bowtie /usr/local/bin/bowtie-inspect-l /usr/local/bin/bowtie-inspect-l
COPY --from=bowtie /usr/local/bin/bowtie-inspect-s /usr/local/bin/bowtie-inspect-s
COPY --from=bowtie /usr/local/lib/libtbb.so.2 /opt/bowtie-lib/libtbb.so.2
COPY --from=bowtie /usr/local/lib/libtbbmalloc.so.2 /opt/bowtie-lib/libtbbmalloc.so.2
COPY --from=bowtie /usr/local/lib/libtbbmalloc_proxy.so.2 /opt/bowtie-lib/libtbbmalloc_proxy.so.2
COPY --from=bowtie /usr/local/lib/libstdc++.so.6.0.27 /opt/bowtie-lib/libstdc++.so.6
COPY --from=bowtie /usr/local/lib/libgcc_s.so.1 /opt/bowtie-lib/libgcc_s.so.1
COPY --from=bowtie /usr/local/lib/libz.so.1.2.11 /opt/bowtie-lib/libz.so.1

ENV LD_LIBRARY_PATH=/opt/bowtie-lib

LABEL org.opencontainers.image.title="Biomed Workbench LACE-seq runtime" \
      org.opencontainers.image.description="Published Cutadapt 1.15 and Bowtie 1.2.3 preprocessing runtime for LACE-seq" \
      org.opencontainers.image.source="https://github.com/JunyanKang/biomed-workbench"

WORKDIR /work
ENTRYPOINT []
CMD ["python", "--version"]
