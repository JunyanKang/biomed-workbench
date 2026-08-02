#!/usr/bin/env python3
"""Build the pinned RIPSeeker runtime without changing the host R installation."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / ".validation"
MIRROR = VALIDATION / "ripseeker-bioc-mirror"
SOURCE_EXPORT = VALIDATION / "ripseeker-official-e3"
SOURCE_CLONE = VALIDATION / "ripseeker-source-build"
DOCKERFILE = ROOT / "biomed_workbench/runtime_compat/ripseeker/Dockerfile"
RIPSEEKER_REPOSITORY = "https://git.bioconductor.org/packages/RIPSeeker"
RIPSEEKER_COMMIT = "e3eb1377fc9cd28851a7b301fc410848f7b1347f"
BIOCONDUCTOR_ARCHIVE = "https://bioconductor.statistik.tu-dortmund.de/packages/3.11"
DEFAULT_IMAGE = "biomed-workbench/ripseeker:1.28.0-e3eb137"

PACKAGES = (
    ("bioc", "Biobase_2.48.0.tar.gz", "17dbdfd9f06a7dcca5daeb067a7acf46391f155c3321e119b20b9edaed9be38e"),
    ("bioc", "BiocGenerics_0.34.0.tar.gz", "534f5640fe0f1c165f164ebb26e312c4140e336145af3c839dbff427a0c7db96"),
    ("bioc", "BiocParallel_1.22.0.tar.gz", "4fa0a5f777de5c9cda96cfe2e93cd34f2686df84bf4507cc2c9e0e596a2f4fd3"),
    ("bioc", "Biostrings_2.56.0.tar.gz", "286e06883c4c230b696e89b06fba78ba418db15559def871a163a1d7ce77b046"),
    ("bioc", "DelayedArray_0.14.1.tar.gz", "fbe892e62d8453863b15d92fd8219a9a9c1507b3a823a6739a87661884892076"),
    ("bioc", "GenomeInfoDb_1.24.2.tar.gz", "cdfe2c46273b3f5b1d112a77c2690cc0c3cbd812272b9e4a6e01974aee281ab3"),
    ("bioc", "GenomicAlignments_1.24.0.tar.gz", "0dcded5d0ca3d79a3fa1f0836e23f94b25ced099f193591922b7d4ec4e33136d"),
    ("bioc", "GenomicRanges_1.40.0.tar.gz", "a18bb9cddf7a147b8c8b53f0f024a3ed77637f7c54452e7eda37038c45fec172"),
    ("bioc", "IRanges_2.22.2.tar.gz", "2d111ede1d042795af6f98ce21c668473e00ace941fae894b8dc00240c9744f8"),
    ("bioc", "Rhtslib_1.20.0.tar.gz", "b13d3f20f483dedc778d1a386ce1d1fe394ddbb9710c4b588836ff99593cd9a0"),
    ("bioc", "Rsamtools_2.4.0.tar.gz", "78039e3781865d79af36bd4bd3926148e8bb94b78668abcf0c24b97034f8017c"),
    ("bioc", "S4Vectors_0.26.1.tar.gz", "ab761224c77fb6b936cc1b49e6567e541072a05121aac4bf18a37fe69f1db9b5"),
    ("bioc", "SummarizedExperiment_1.18.2.tar.gz", "3c8fe072841502c14e60a8710b1d089c7f583495a3cf61ff93cfe417992f5ce5"),
    ("bioc", "XVector_0.28.0.tar.gz", "6cdf01943177f9aeba808b028ad3261d2bba91fb26a3be5ec0281db2bf860186"),
    ("bioc", "rtracklayer_1.48.0.tar.gz", "ae974dbc4caa4ea0ecc3a340071d63160a38a725ba26cd8f271eb6a8459a8ffd"),
    ("bioc", "zlibbioc_1.34.0.tar.gz", "8026a46a06bf951481fe2281261c714f6996989dfc77176d609c892545013448"),
    ("data/annotation", "GenomeInfoDbData_1.2.3.tar.gz", "945d79fc542ce7914fc89ad95bd0ead827597cfa50f2f758cfef42a09fc78aeb"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_sha256: str) -> None:
    if destination.is_file() and sha256(destination) == expected_sha256:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, 5):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Biomed-Workbench/1"})
            with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            if sha256(partial) != expected_sha256:
                raise RuntimeError(f"checksum mismatch for {destination.name}")
            partial.replace(destination)
            return
        except Exception:
            partial.unlink(missing_ok=True)
            if attempt == 4:
                raise
            time.sleep(attempt * 2)


def write_packages_index(directory: Path) -> None:
    descriptions: list[str] = []
    for archive in sorted(directory.glob("*.tar.gz")):
        with tarfile.open(archive, "r:gz") as bundle:
            member = next((item for item in bundle.getmembers() if item.name.count("/") == 1 and item.name.endswith("/DESCRIPTION")), None)
            if member is None:
                raise RuntimeError(f"DESCRIPTION is missing from {archive.name}")
            extracted = bundle.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"DESCRIPTION is unreadable in {archive.name}")
            descriptions.append(extracted.read().decode("utf-8").strip())
    content = "\n\n".join(descriptions) + "\n"
    (directory / "PACKAGES").write_text(content, encoding="utf-8")
    with (directory / "PACKAGES.gz").open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(content.encode("utf-8"))


def prepare_mirror(archive_root: str) -> None:
    checksums: list[str] = []
    for repository, filename, expected in PACKAGES:
        destination = MIRROR / "packages/3.11" / repository / "src/contrib" / filename
        download(f"{archive_root.rstrip('/')}/{repository}/src/contrib/{filename}", destination, expected)
        checksums.append(f"{expected}  {destination.relative_to(ROOT)}")
    for repository in {item[0] for item in PACKAGES}:
        write_packages_index(MIRROR / "packages/3.11" / repository / "src/contrib")
    (MIRROR / "SHA256SUMS").write_text("\n".join(sorted(checksums)) + "\n", encoding="utf-8")


def prepare_source() -> None:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git is required to obtain the pinned official RIPSeeker source")
    subprocess.run([git, "clone", "--no-checkout", RIPSEEKER_REPOSITORY, str(SOURCE_CLONE)], check=True, timeout=600)
    observed = subprocess.run(
        [git, "-C", str(SOURCE_CLONE), "rev-parse", RIPSEEKER_COMMIT],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    if observed != RIPSEEKER_COMMIT:
        raise RuntimeError("official RIPSeeker commit could not be resolved exactly")
    with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
        subprocess.run([git, "-C", str(SOURCE_CLONE), "archive", "--format=tar", RIPSEEKER_COMMIT], check=True, stdout=archive, timeout=120)
        archive.flush()
        SOURCE_EXPORT.mkdir(parents=True, exist_ok=False)
        with tarfile.open(archive.name, "r:") as bundle:
            bundle.extractall(SOURCE_EXPORT, filter="data")
    (SOURCE_EXPORT / "OFFICIAL_COMMIT").write_text(RIPSEEKER_COMMIT + "\n", encoding="utf-8")


def clean_preparation() -> None:
    for path in (MIRROR, SOURCE_EXPORT, SOURCE_CLONE):
        if path.exists():
            shutil.rmtree(path)


def preparation_is_valid() -> bool:
    if not (SOURCE_EXPORT / "OFFICIAL_COMMIT").is_file():
        return False
    if (SOURCE_EXPORT / "OFFICIAL_COMMIT").read_text(encoding="utf-8").strip() != RIPSEEKER_COMMIT:
        return False
    return all(
        (MIRROR / "packages/3.11" / repository / "src/contrib" / filename).is_file()
        and sha256(MIRROR / "packages/3.11" / repository / "src/contrib" / filename) == expected
        for repository, filename, expected in PACKAGES
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--bioconductor-archive", default=BIOCONDUCTOR_ARCHIVE)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--keep-cache", action="store_true")
    parser.add_argument("--reuse-prepared", action="store_true")
    args = parser.parse_args()
    docker = shutil.which("docker")
    if not args.prepare_only and not docker:
        raise RuntimeError("Docker is required to build the isolated RIPSeeker runtime")
    reuse = args.reuse_prepared and preparation_is_valid()
    if not reuse:
        clean_preparation()
    try:
        if not reuse:
            prepare_mirror(args.bioconductor_archive)
            prepare_source()
        if args.prepare_only:
            result = {"prepared": True, "built": False, "package_count": len(PACKAGES), "commit": RIPSEEKER_COMMIT}
        else:
            subprocess.run(
                [docker, "build", "--platform", "linux/amd64", "-f", str(DOCKERFILE), "-t", args.image, "."],
                check=True,
                cwd=ROOT,
            )
            identity = subprocess.run(
                [docker, "image", "inspect", args.image, "--format", "{{.Id}}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            result = {"prepared": True, "built": True, "image": args.image, "image_id": identity, "package_count": len(PACKAGES), "commit": RIPSEEKER_COMMIT}
        print(json.dumps(result, sort_keys=True))
    finally:
        if not args.keep_cache:
            clean_preparation()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
