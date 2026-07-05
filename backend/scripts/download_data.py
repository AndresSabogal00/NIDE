#!/usr/bin/env python3
"""Download and extract the official OpenMC-distributed evaluated nuclear data
libraries used by NIDE.

The OpenMC project distributes pre-processed HDF5 libraries (generated with
NJOY from the official ENDF-6 sources) at https://openmc.org/data/. Each
archive contains continuous-energy incident-neutron data at six temperatures
(250, 293.6, 600, 900, 1200, 2500 K) plus a ``cross_sections.xml`` manifest
that :class:`openmc.data.DataLibrary` can read directly.

Archives are hosted on Argonne National Laboratory's Box service. The URLs
below were verified against https://openmc.org/data/ on 2026-07-04; if a
download 404s, check that page for updated links rather than editing blindly.

Usage
-----
Download one library (resumable; safe to re-run)::

    python scripts/download_data.py endfb80

Download everything NIDE supports, sequentially::

    python scripts/download_data.py all

Data lands in ``backend/data/<library-id>/`` and is git-ignored. Expect
roughly 2 GB compressed / 5-10 GB extracted per library.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class LibrarySource:
    """One downloadable evaluated-data library distribution."""

    library_id: str  # NIDE-internal identifier, used in API routes and cache keys
    name: str  # human-readable evaluation name
    url: str  # direct download URL (tar.xz), verified on openmc.org/data/
    citation: str  # official citation for the underlying evaluation


LIBRARIES: dict[str, LibrarySource] = {
    "endfb80": LibrarySource(
        library_id="endfb80",
        name="ENDF/B-VIII.0",
        url="https://anl.box.com/shared/static/uhbxlrx7hvxqw27psymfbhi7bx7s6u6a.xz",
        citation=(
            "D.A. Brown et al., \"ENDF/B-VIII.0: The 8th Major Release of the "
            "Nuclear Reaction Data Library\", Nucl. Data Sheets 148 (2018) 1-142. "
            "doi:10.1016/j.nds.2018.02.001"
        ),
    ),
    "jeff33": LibrarySource(
        library_id="jeff33",
        name="JEFF-3.3",
        url="https://anl.box.com/shared/static/4jwkvrr9pxlruuihcrgti75zde6g7bum.xz",
        citation=(
            "A.J.M. Plompen et al., \"The joint evaluated fission and fusion "
            "nuclear data library, JEFF-3.3\", Eur. Phys. J. A 56 (2020) 181. "
            "doi:10.1140/epja/s10050-020-00141-9"
        ),
    ),
    "jendl5": LibrarySource(
        library_id="jendl5",
        name="JENDL-5",
        url="https://anl.box.com/shared/static/bitsmk1bjkjfj01h4lh29mmlqs1v30bn.xz",
        citation=(
            "O. Iwamoto et al., \"Japanese evaluated nuclear data library "
            "version 5: JENDL-5\", J. Nucl. Sci. Technol. 60 (2023) 1-60. "
            "doi:10.1080/00223131.2022.2141903"
        ),
    ),
}


def download(source: LibrarySource, dest_dir: Path) -> Path:
    """Download one library archive with curl, resuming partial transfers.

    curl is used instead of urllib because the Box-hosted files involve
    redirects and multi-GB payloads where ``-C -`` resume support matters on
    flaky connections.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / f"{source.library_id}.tar.xz"
    marker = dest_dir / f"{source.library_id}.download-complete"
    if marker.exists():
        print(f"[{source.library_id}] archive already downloaded, skipping")
        return archive
    print(f"[{source.library_id}] downloading {source.url}")
    subprocess.run(
        ["curl", "-L", "-C", "-", "--fail", "--retry", "5", "--retry-delay", "10",
         "-o", str(archive), source.url],
        check=True,
    )
    marker.touch()
    return archive


def extract(source: LibrarySource, archive: Path) -> Path:
    """Extract the archive and return the directory containing cross_sections.xml.

    The upstream tarballs contain a single top-level directory whose name
    varies by library (e.g. ``endfb-viii.0-hdf5``); the extracted tree is left
    under that name and located by searching for the manifest, so this code
    does not depend on upstream naming conventions.
    """
    lib_dir = DATA_DIR / source.library_id
    existing = list(lib_dir.rglob("cross_sections.xml")) if lib_dir.exists() else []
    if existing:
        print(f"[{source.library_id}] already extracted at {existing[0].parent}")
        return existing[0].parent
    print(f"[{source.library_id}] extracting {archive.name} (this takes a few minutes)")
    lib_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:xz") as tar:
        tar.extractall(lib_dir, filter="data")
    manifests = list(lib_dir.rglob("cross_sections.xml"))
    if not manifests:
        raise RuntimeError(
            f"{archive} extracted but no cross_sections.xml found under {lib_dir}; "
            "the upstream archive layout may have changed"
        )
    archive.unlink()  # reclaim ~2 GB; the .download-complete marker remains
    print(f"[{source.library_id}] ready: {manifests[0]}")
    return manifests[0].parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "library",
        choices=[*LIBRARIES.keys(), "all"],
        help="library to download, or 'all' for every supported library",
    )
    args = parser.parse_args()

    targets = list(LIBRARIES.values()) if args.library == "all" else [LIBRARIES[args.library]]
    for source in targets:
        archive = download(source, DATA_DIR / source.library_id)
        extract(source, archive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
