"""Cross-section extraction, disk caching and plot-oriented downsampling.

Responsibilities
----------------
1. Evaluate sigma(E) for a (library, nuclide, MT, temperature) tuple on the
   evaluation's own union energy grid, using :mod:`openmc.data` (which also
   synthesizes redundant MTs such as MT=1 total or MT=101 absorption by
   summing their components per the ENDF-102 sum rules).
2. Cache the full pointwise curve on disk (compressed ``.npz``, two float64
   arrays) so repeated requests never re-parse HDF5.
3. Downsample for the frontend with Largest-Triangle-Three-Buckets (LTTB)
   applied in log-log space, which is the space in which the curves are
   drawn; this preserves resonance peaks that uniform decimation would erase.

Unit conventions (used across the whole backend): energy in eV, cross
sections in barns (1 b = 1e-24 cm^2), temperatures as the strings used by the
OpenMC HDF5 files (e.g. ``"294K"``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import openmc.data

from app.core.config import settings
from app.core.library_manager import LibraryManager, get_library_manager

# MTs that are usually absent from the processed files but that openmc can
# synthesize from stored partials (ENDF-102, Table 14 sum rules). Offered in
# the reaction list whenever their components exist because they are the
# quantities practitioners ask for first.
_REDUNDANT_MTS: tuple[int, ...] = (1, 3, 4, 27, 101)


@dataclass
class XSCurve:
    """One evaluated cross-section curve on its native energy grid."""

    library_id: str
    nuclide: str
    mt: int
    reaction_name: str
    temperature: str
    energy_ev: np.ndarray
    xs_barns: np.ndarray


@dataclass
class ReactionInfo:
    mt: int
    name: str
    redundant: bool  # True if synthesized by summing partials, not stored


def lttb_downsample(x: np.ndarray, y: np.ndarray, n_out: int) -> np.ndarray:
    """Select indices with Largest-Triangle-Three-Buckets in log-log space.

    LTTB [1]_ partitions the series into ``n_out - 2`` buckets and keeps, per
    bucket, the point forming the largest triangle with the previously kept
    point and the next bucket's centroid — the standard choice for preserving
    visual extrema (here: resonance peaks and interference dips) when
    decimating for display.

    The triangle areas are computed on ``(log10 x, log10 y)`` because the
    frontend draws log-log axes: a resonance spanning two decades of sigma
    within a few eV is visually huge but has negligible *linear* area. Points
    with ``y <= 0`` (below reaction threshold) carry no information on a log
    plot and are excluded from selection, except that the last zero before
    the threshold rise is kept so the onset is drawn at the right energy.

    Parameters
    ----------
    x, y : numpy.ndarray
        Monotonic energy grid (eV) and cross section (barns).
    n_out : int
        Target number of points; if ``len(x) <= n_out`` all indices return.

    Returns
    -------
    numpy.ndarray
        Sorted integer indices into ``x``/``y``.

    References
    ----------
    .. [1] S. Steinarsson, "Downsampling Time Series for Visual
       Representation", M.Sc. thesis, University of Iceland (2013).
    """
    n = len(x)
    if n <= n_out:
        return np.arange(n)

    positive = y > 0.0
    # Keep the last zero-valued point immediately preceding a positive value:
    # for threshold reactions it anchors the curve onset.
    onset = np.zeros(n, dtype=bool)
    rises = np.where(~positive[:-1] & positive[1:])[0]
    onset[rises] = True
    candidate = np.where(positive | onset)[0]
    if len(candidate) <= n_out:
        return candidate

    lx = np.log10(x[candidate])
    # Zeros kept as onset anchors get a floor value for area computation only.
    ly = np.log10(np.maximum(y[candidate], np.min(y[candidate][y[candidate] > 0]) * 1e-3))

    m = len(candidate)
    selected = np.empty(n_out, dtype=np.int64)
    selected[0] = 0
    selected[-1] = m - 1
    # Bucket boundaries over the interior points.
    bounds = np.linspace(1, m - 1, n_out - 1).astype(np.int64)

    prev = 0
    for i in range(n_out - 2):
        lo, hi = bounds[i], bounds[i + 1]
        nxt_lo, nxt_hi = bounds[i + 1], (bounds[i + 2] if i + 2 < len(bounds) else m)
        cx = lx[nxt_lo:nxt_hi].mean() if nxt_hi > nxt_lo else lx[-1]
        cy = ly[nxt_lo:nxt_hi].mean() if nxt_hi > nxt_lo else ly[-1]
        # Triangle area (up to factor 1/2) of (prev, candidate, next-centroid).
        area = np.abs(
            (lx[prev] - cx) * (ly[lo:hi] - ly[prev]) - (lx[prev] - lx[lo:hi]) * (cy - ly[prev])
        )
        prev = lo + int(np.argmax(area)) if hi > lo else lo
        selected[i + 1] = prev

    return candidate[np.unique(selected)]


class XSService:
    """Extracts cross-section curves with a persistent on-disk cache."""

    def __init__(self, manager: LibraryManager | None = None, cache_dir: Path | None = None):
        self._manager = manager or get_library_manager()
        self._cache_dir = (cache_dir or settings.cache_dir) / "xs"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Reaction discovery                                                  #
    # ------------------------------------------------------------------ #

    def reactions(self, library_id: str, nuclide: str) -> list[ReactionInfo]:
        """All MTs servable for a nuclide: stored ones plus synthesizable sums."""
        nuc = self._manager.load(library_id, nuclide)
        infos = [
            ReactionInfo(mt=mt, name=openmc.data.REACTION_NAME.get(mt, f"MT={mt}"), redundant=False)
            for mt in sorted(nuc.reactions)
        ]
        stored = set(nuc.reactions)
        for mt in _REDUNDANT_MTS:
            if mt in stored:
                continue
            components = [c for c in nuc.get_reaction_components(mt) if c in stored]
            if components:
                infos.append(
                    ReactionInfo(
                        mt=mt,
                        name=openmc.data.REACTION_NAME.get(mt, f"MT={mt}"),
                        redundant=True,
                    )
                )
        infos.sort(key=lambda r: r.mt)
        return infos

    def temperatures(self, library_id: str, nuclide: str) -> list[str]:
        """Temperatures at which the processed library provides this nuclide."""
        nuc = self._manager.load(library_id, nuclide)
        return sorted(nuc.temperatures, key=lambda t: float(t[:-1]))

    # ------------------------------------------------------------------ #
    # Curve extraction                                                    #
    # ------------------------------------------------------------------ #

    def get_curve(
        self,
        library_id: str,
        nuclide: str,
        mt: int,
        temperature: str = "294K",
    ) -> XSCurve:
        """Full-resolution sigma(E) on the evaluation's union energy grid.

        The union grid stored by openmc for the requested temperature is used
        directly (no re-gridding): it is the grid on which NJOY linearized the
        evaluation to within its reconstruction tolerance, so it is the
        highest-fidelity representation available.
        """
        temperature = self._resolve_temperature(library_id, nuclide, temperature)
        cached = self._cache_load(library_id, nuclide, mt, temperature)
        if cached is not None:
            energy, xs = cached
        else:
            nuc = self._manager.load(library_id, nuclide)
            try:
                reaction = nuc[mt]
            except KeyError:
                raise KeyError(
                    f"MT={mt} not available for {nuclide} in {library_id}"
                ) from None
            energy = nuc.energy[temperature]
            xs = reaction.xs[temperature](energy)
            # Numerical noise from summed redundant reactions can produce
            # tiny negatives; clip since sigma >= 0 physically.
            xs = np.clip(xs, 0.0, None)
            self._cache_store(library_id, nuclide, mt, temperature, energy, xs)
        return XSCurve(
            library_id=library_id,
            nuclide=nuclide,
            mt=mt,
            reaction_name=openmc.data.REACTION_NAME.get(mt, f"MT={mt}"),
            temperature=temperature,
            energy_ev=energy,
            xs_barns=xs,
        )

    def get_curve_downsampled(
        self,
        library_id: str,
        nuclide: str,
        mt: int,
        temperature: str = "294K",
        max_points: int | None = None,
    ) -> tuple[XSCurve, int]:
        """Curve decimated for plotting; returns (curve, full_grid_size)."""
        max_points = max_points or settings.default_max_points
        full = self.get_curve(library_id, nuclide, mt, temperature)
        n_full = len(full.energy_ev)
        idx = lttb_downsample(full.energy_ev, full.xs_barns, max_points)
        full.energy_ev = full.energy_ev[idx]
        full.xs_barns = full.xs_barns[idx]
        return full, n_full

    def _resolve_temperature(self, library_id: str, nuclide: str, requested: str) -> str:
        """Map a requested temperature to the nearest one in the file.

        Processed libraries carry a small fixed set of temperatures (e.g.
        250, 293.6, 600 ... 2500 K). Rather than failing on "294K" vs
        "293.6K" naming differences between libraries, snap to the closest
        available temperature — the standard practice for pointwise data
        (proper intermediate temperatures would require Doppler broadening,
        out of scope here).
        """
        available = self._manager.load(library_id, nuclide).temperatures
        if requested in available:
            return requested
        try:
            target = float(requested.rstrip("Kk"))
        except ValueError:
            raise ValueError(f"Bad temperature '{requested}'; expected e.g. '294K'") from None
        return min(available, key=lambda t: abs(float(t[:-1]) - target))

    # ------------------------------------------------------------------ #
    # Disk cache                                                          #
    # ------------------------------------------------------------------ #

    def _cache_path(self, library_id: str, nuclide: str, mt: int, temperature: str) -> Path:
        return self._cache_dir / library_id / f"{nuclide}_mt{mt}_{temperature}.npz"

    def _cache_load(
        self, library_id: str, nuclide: str, mt: int, temperature: str
    ) -> tuple[np.ndarray, np.ndarray] | None:
        path = self._cache_path(library_id, nuclide, mt, temperature)
        if not path.exists():
            return None
        try:
            with np.load(path) as data:
                return data["energy_ev"], data["xs_barns"]
        except (OSError, KeyError, ValueError):
            path.unlink(missing_ok=True)  # corrupt cache entry: rebuild
            return None

    def _cache_store(
        self,
        library_id: str,
        nuclide: str,
        mt: int,
        temperature: str,
        energy: np.ndarray,
        xs: np.ndarray,
    ) -> None:
        path = self._cache_path(library_id, nuclide, mt, temperature)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, energy_ev=energy, xs_barns=xs)
        tmp.replace(path)  # atomic: concurrent readers never see partial files


_service: XSService | None = None


def get_xs_service() -> XSService:
    global _service
    if _service is None:
        _service = XSService()
    return _service
