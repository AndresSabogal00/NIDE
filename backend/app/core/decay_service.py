"""Radioactive decay data and decay-chain construction.

Data source: the ENDF/B-VIII.0 decay sublibrary (raw ENDF-6 files from NNDC,
one file per nuclide, fetched by ``scripts/download_data.py``), parsed with
:class:`openmc.data.Decay`. That sublibrary is itself derived from ENSDF, so
half-lives and branching ratios match the evaluated nuclear structure data.

A lightweight summary (half-life, stability, decay modes with branching
ratios, mean emission energies) for all ~3800 nuclides is built on first use
(~1 s of parsing) and cached as JSON on disk; full spectra are parsed
per-nuclide on demand.

Decay chains are built by breadth-first traversal over the summary graph,
following every decay mode with nonzero branching ratio until stable
nuclides (or nuclides absent from the sublibrary) are reached. Spontaneous
fission is represented as a terminal edge (the fragment distribution belongs
to the fission-yield service, not the chain graph).

Nuclide naming follows the GNDS convention used across NIDE and openmc:
``U235``, ``Co60``, metastable states ``Am242_m1``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock

import openmc.data

from app.core.config import settings

_FILENAME_RE = re.compile(r"dec-(\d{3})_([A-Za-z]+)_(\d{3})(m\d+)?\.endf$")


@dataclass
class DecayModeInfo:
    """One decay branch: mode string per ENDF/ENSDF (e.g. 'beta-', 'alpha',
    'ec/beta+', 'it', 'sf'), daughter in GNDS naming, branching ratio in
    [0, 1]."""

    mode: str
    daughter: str | None
    branching_ratio: float
    branching_ratio_uncertainty: float


@dataclass
class NuclideDecayInfo:
    """Summary decay data for one nuclide (units: seconds, eV)."""

    nuclide: str
    z: int
    a: int
    isomeric_state: int
    stable: bool
    half_life_s: float | None
    half_life_uncertainty_s: float | None
    decay_energy_ev: float | None
    modes: list[DecayModeInfo]


class DecayService:
    """Index over the ENDF/B-VIII.0 decay sublibrary with chain building."""

    def __init__(self, decay_dir: Path | None = None, cache_dir: Path | None = None):
        base = decay_dir or (settings.data_dir / "decay")
        # The NNDC zip extracts into a single subdirectory; search for it so
        # the service does not depend on the archive's internal name.
        candidates = sorted(base.rglob("dec-*.endf")) if base.exists() else []
        self._files: dict[str, Path] = {}
        for path in candidates:
            name = self._nuclide_from_filename(path.name)
            if name:
                self._files[name] = path
        self._cache_file = (cache_dir or settings.cache_dir) / "decay_summary.json"
        self._summary: dict[str, NuclideDecayInfo] | None = None
        self._lock = Lock()

    @property
    def available(self) -> bool:
        return bool(self._files)

    @staticmethod
    def _nuclide_from_filename(filename: str) -> str | None:
        m = _FILENAME_RE.search(filename)
        if not m:
            return None
        _, symbol, a, meta = m.groups()
        name = f"{symbol}{int(a)}"
        if meta:
            name += f"_{meta}"
        return name

    # ------------------------------------------------------------------ #
    # Summary index                                                       #
    # ------------------------------------------------------------------ #

    def summary(self) -> dict[str, NuclideDecayInfo]:
        """Decay summary for every nuclide, built once and cached on disk."""
        with self._lock:
            if self._summary is not None:
                return self._summary
            if self._cache_file.exists():
                try:
                    raw = json.loads(self._cache_file.read_text())
                    self._summary = {
                        k: NuclideDecayInfo(
                            **{**v, "modes": [DecayModeInfo(**m) for m in v["modes"]]}
                        )
                        for k, v in raw.items()
                    }
                    return self._summary
                except (json.JSONDecodeError, TypeError, KeyError):
                    self._cache_file.unlink(missing_ok=True)
            self._summary = self._build_summary()
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(
                json.dumps({k: asdict(v) for k, v in self._summary.items()})
            )
            return self._summary

    def _build_summary(self) -> dict[str, NuclideDecayInfo]:
        summary: dict[str, NuclideDecayInfo] = {}
        for name, path in self._files.items():
            try:
                dec = openmc.data.Decay(path)
            except Exception:
                # A malformed upstream file must not take down the whole
                # index; the nuclide is simply absent from decay views.
                continue
            nuc = dec.nuclide
            stable = bool(nuc.get("stable", False))
            half_life = None if stable or dec.half_life is None else float(dec.half_life.n)
            half_life_unc = None if stable or dec.half_life is None else float(dec.half_life.s)
            # Total mean decay energy released (eV): sum of the average
            # light-particle, electromagnetic and heavy-particle components
            # (ENDF MF=8 MT=457 average energies).
            decay_energy = None
            if not stable and dec.decay_energy is not None:
                decay_energy = float(dec.decay_energy.n)
            modes = [
                DecayModeInfo(
                    mode=",".join(m.modes) if isinstance(m.modes, list) else str(m.modes),
                    daughter=m.daughter,
                    branching_ratio=float(m.branching_ratio.n),
                    branching_ratio_uncertainty=float(m.branching_ratio.s),
                )
                for m in dec.modes
            ]
            summary[name] = NuclideDecayInfo(
                nuclide=name,
                z=int(nuc["atomic_number"]),
                a=int(nuc["mass_number"]),
                isomeric_state=int(nuc.get("isomeric_state", 0)),
                stable=stable,
                half_life_s=half_life,
                half_life_uncertainty_s=half_life_unc,
                decay_energy_ev=decay_energy,
                modes=modes,
            )
        return summary

    def info(self, nuclide: str) -> NuclideDecayInfo:
        data = self.summary()
        if nuclide not in data:
            raise KeyError(f"No decay data for '{nuclide}' in ENDF/B-VIII.0 decay sublibrary")
        return data[nuclide]

    # ------------------------------------------------------------------ #
    # Chain construction                                                  #
    # ------------------------------------------------------------------ #

    def chain(
        self, start: str, min_branching_ratio: float = 0.0, max_nuclides: int = 200
    ) -> tuple[list[NuclideDecayInfo], list[tuple[str, str, DecayModeInfo]]]:
        """Decay chain from ``start`` as (nodes, edges), BFS to stability.

        Parameters
        ----------
        min_branching_ratio : float
            Branches below this ratio are pruned — useful to reduce, e.g.,
            the U-238 series to its main path (prune < 1e-4 removes the
            rare beta branches of Bi-214 etc.).
        max_nuclides : int
            Hard cap against pathological graphs (defensive; natural chains
            reach ~20 nuclides).

        Notes
        -----
        Spontaneous fission edges carry ``daughter=None`` and terminate the
        branch. Daughters missing from the sublibrary become terminal nodes
        with only identity information.
        """
        data = self.summary()
        if start not in data:
            raise KeyError(f"No decay data for '{start}'")
        nodes: dict[str, NuclideDecayInfo] = {}
        edges: list[tuple[str, str, DecayModeInfo]] = []
        queue = [start]
        while queue and len(nodes) < max_nuclides:
            current = queue.pop(0)
            if current in nodes:
                continue
            if current not in data:
                # Daughter without decay file (e.g. very exotic): synthesize
                # a terminal node from its name so the graph stays connected.
                z, a, m = _parse_gnds_name(current)
                nodes[current] = NuclideDecayInfo(
                    nuclide=current,
                    z=z,
                    a=a,
                    isomeric_state=m,
                    stable=True,
                    half_life_s=None,
                    half_life_uncertainty_s=None,
                    decay_energy_ev=None,
                    modes=[],
                )
                continue
            info = data[current]
            nodes[current] = info
            if info.stable:
                continue
            for mode in info.modes:
                if mode.branching_ratio < min_branching_ratio:
                    continue
                if mode.daughter is None or mode.mode == "sf":
                    continue
                edges.append((current, mode.daughter, mode))
                if mode.daughter not in nodes:
                    queue.append(mode.daughter)
        return list(nodes.values()), edges


_SYMBOL_RE = re.compile(r"^([A-Za-z]+)(\d+)(?:_m(\d+))?$")

# Symbol -> Z for synthesizing terminal nodes; generated from openmc's
# canonical element list so it never drifts from the parser's convention.
_Z_OF_SYMBOL = {sym: z for z, sym in openmc.data.ATOMIC_SYMBOL.items()}


def _parse_gnds_name(name: str) -> tuple[int, int, int]:
    """('U238' | 'Am242_m1') -> (Z, A, isomeric state); (0,0,0) if unparseable."""
    m = _SYMBOL_RE.match(name)
    if not m:
        return 0, 0, 0
    symbol, a, meta = m.groups()
    return _Z_OF_SYMBOL.get(symbol, 0), int(a), int(meta or 0)


_decay_service: DecayService | None = None


def get_decay_service() -> DecayService:
    global _decay_service
    if _decay_service is None:
        _decay_service = DecayService()
    return _decay_service
