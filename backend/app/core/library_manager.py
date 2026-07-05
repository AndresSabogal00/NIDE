"""Registry and lazy loader for evaluated nuclear data libraries.

NIDE works with the HDF5 libraries distributed by the OpenMC project
(https://openmc.org/data/), which are NJOY-processed versions of the official
ENDF/B, JEFF and JENDL evaluations. Each library ships a
``cross_sections.xml`` manifest mapping nuclide names to HDF5 files; this
module discovers those manifests under ``backend/data/<library-id>/`` and
loads individual nuclides on demand via
:class:`openmc.data.IncidentNeutron`, which performs the heavy lifting
(pointwise cross sections already resonance-reconstructed and
Doppler-broadened by NJOY at several fixed temperatures).

Loaded nuclides are kept in a bounded LRU cache: a heavy actinide with a
dense resonance grid costs tens of MB in memory, so we cap the number of
simultaneously loaded (library, nuclide) pairs rather than the byte count.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import openmc.data

from app.core.config import settings


@dataclass(frozen=True)
class LibraryMetadata:
    """Static metadata for one supported evaluation.

    ``citation`` is the official reference for the *evaluation* (not the
    OpenMC processing); it is attached to every export and plot so that any
    number shown in NIDE is traceable to its source, one of the project's
    hard requirements.
    """

    library_id: str
    name: str
    version: str
    citation: str
    doi: str


SUPPORTED_LIBRARIES: dict[str, LibraryMetadata] = {
    "endfb80": LibraryMetadata(
        library_id="endfb80",
        name="ENDF/B-VIII.0",
        version="VIII.0",
        citation=(
            'D.A. Brown et al., "ENDF/B-VIII.0: The 8th Major Release of the '
            'Nuclear Reaction Data Library", Nucl. Data Sheets 148 (2018) 1-142.'
        ),
        doi="10.1016/j.nds.2018.02.001",
    ),
    "jeff33": LibraryMetadata(
        library_id="jeff33",
        name="JEFF-3.3",
        version="3.3",
        citation=(
            'A.J.M. Plompen et al., "The joint evaluated fission and fusion '
            'nuclear data library, JEFF-3.3", Eur. Phys. J. A 56 (2020) 181.'
        ),
        doi="10.1140/epja/s10050-020-00141-9",
    ),
    "jendl5": LibraryMetadata(
        library_id="jendl5",
        name="JENDL-5",
        version="5",
        citation=(
            'O. Iwamoto et al., "Japanese evaluated nuclear data library '
            'version 5: JENDL-5", J. Nucl. Sci. Technol. 60 (2023) 1-60.'
        ),
        doi="10.1080/00223131.2022.2141903",
    ),
}


class LibraryManager:
    """Discovers installed libraries and lazily loads nuclide data.

    Parameters
    ----------
    data_dir : Path
        Directory containing one subdirectory per library id (as produced by
        ``scripts/download_data.py``), each with a ``cross_sections.xml``
        manifest somewhere below it.
    cache_size : int
        Maximum number of (library, nuclide) IncidentNeutron objects held in
        memory simultaneously (LRU eviction).
    """

    def __init__(self, data_dir: Path | None = None, cache_size: int | None = None):
        self._data_dir = data_dir or settings.data_dir
        self._cache_size = cache_size or settings.nuclide_cache_size
        self._lock = Lock()
        self._nuclide_cache: OrderedDict[tuple[str, str], openmc.data.IncidentNeutron] = (
            OrderedDict()
        )
        # library_id -> {nuclide name -> HDF5 path}
        self._index: dict[str, dict[str, Path]] = {}
        self.refresh()

    def refresh(self) -> None:
        """Re-scan the data directory for library manifests.

        Called at startup and exposed via the API so that a library that
        finishes downloading while the server runs becomes visible without a
        restart.
        """
        index: dict[str, dict[str, Path]] = {}
        for library_id in SUPPORTED_LIBRARIES:
            lib_dir = self._data_dir / library_id
            if not lib_dir.is_dir():
                continue
            manifests = sorted(lib_dir.rglob("cross_sections.xml"))
            if not manifests:
                continue
            data_lib = openmc.data.DataLibrary.from_xml(manifests[0])
            nuclides: dict[str, Path] = {}
            for entry in data_lib.libraries:
                # Only continuous-energy neutron data is served; thermal
                # scattering (S(a,b)) and photon sublibraries are out of scope.
                if entry["type"] != "neutron":
                    continue
                for material in entry["materials"]:
                    nuclides[material] = Path(entry["path"])
            if nuclides:
                index[library_id] = nuclides
        with self._lock:
            self._index = index

    @property
    def available_libraries(self) -> list[LibraryMetadata]:
        """Metadata for every library found on disk, in canonical order."""
        return [SUPPORTED_LIBRARIES[lid] for lid in SUPPORTED_LIBRARIES if lid in self._index]

    def metadata(self, library_id: str) -> LibraryMetadata:
        if library_id not in SUPPORTED_LIBRARIES:
            raise KeyError(f"Unknown library '{library_id}'")
        return SUPPORTED_LIBRARIES[library_id]

    def nuclides(self, library_id: str) -> list[str]:
        """Sorted nuclide names (GNDS style, e.g. ``U235``, ``Am242_m1``)."""
        self._require(library_id)
        return sorted(self._index[library_id])

    def has_nuclide(self, library_id: str, nuclide: str) -> bool:
        return library_id in self._index and nuclide in self._index[library_id]

    def hdf5_path(self, library_id: str, nuclide: str) -> Path:
        """Path to the HDF5 file for one nuclide, for callers that need
        direct low-level access (e.g. bulk single-value scans that should
        bypass the LRU and curve caches)."""
        self._require(library_id)
        if nuclide not in self._index[library_id]:
            raise KeyError(f"Nuclide '{nuclide}' not available in {library_id}")
        return self._index[library_id][nuclide]

    def load(self, library_id: str, nuclide: str) -> openmc.data.IncidentNeutron:
        """Load one nuclide's incident-neutron data, with LRU caching.

        Raises
        ------
        KeyError
            If the library is not installed or the nuclide is not in it.
        """
        self._require(library_id)
        if nuclide not in self._index[library_id]:
            raise KeyError(f"Nuclide '{nuclide}' not available in {library_id}")
        key = (library_id, nuclide)
        with self._lock:
            if key in self._nuclide_cache:
                self._nuclide_cache.move_to_end(key)
                return self._nuclide_cache[key]
        # HDF5 parsing happens outside the lock: it can take ~seconds for
        # actinides and must not block concurrent requests for cached nuclides.
        nuc = openmc.data.IncidentNeutron.from_hdf5(self._index[library_id][nuclide])
        with self._lock:
            self._nuclide_cache[key] = nuc
            self._nuclide_cache.move_to_end(key)
            while len(self._nuclide_cache) > self._cache_size:
                self._nuclide_cache.popitem(last=False)
        return nuc

    def _require(self, library_id: str) -> None:
        if library_id not in self._index:
            installed = ", ".join(self._index) or "none"
            raise KeyError(
                f"Library '{library_id}' is not installed (installed: {installed}). "
                "Run backend/scripts/download_data.py."
            )


# Singleton shared by all request handlers; FastAPI dependency functions
# return this instance so tests can substitute their own manager.
_manager: LibraryManager | None = None


def get_library_manager() -> LibraryManager:
    global _manager
    if _manager is None:
        _manager = LibraryManager()
    return _manager
