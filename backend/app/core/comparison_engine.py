"""Automatic multi-library cross-section comparison.

The core value proposition of NIDE over a plain plotter: given a nuclide,
reaction and a set of evaluated libraries, quantify exactly where and by how
much the evaluations disagree, without the user eyeballing overlaid curves.

Method
------
1. Build the union of the libraries' energy grids restricted to their common
   domain, so every evaluation is compared where it is actually defined and
   no resonance structure from any library is lost.
2. Interpolate each library onto that grid. Interpolation is log-log
   (linear in log sigma vs log E) wherever both bracketing values are
   positive — the natural scheme for cross sections spanning many decades —
   with linear-linear fallback around zeros (threshold onsets).
3. Compute, per energy point, the relative deviation of each library from
   the *reference* library (the first requested), in percent.
4. Reduce to statistics per conventional energy region (thermal < 0.625 eV,
   epithermal 0.625 eV - 100 keV, fast > 100 keV; the 0.625 eV boundary is
   the standard cadmium cutoff used in reactor analysis) and detect
   contiguous energy intervals where |deviation| exceeds a user threshold.

The point-by-point deviations are exact within interpolation error; near
sharp resonances an apparent discrepancy can be dominated by tiny energy
mesh shifts between evaluations rather than by genuine disagreement in
resonance parameters — this is intrinsic to comparing pointwise data and is
the same behavior JANIS exhibited. The region statistics are robust against
it because they also report the median.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Conventional region boundaries (eV). 0.625 eV: cadmium cutoff used for
# thermal/epithermal split in reactor physics; 100 keV: customary start of
# the fast range (e.g. WIMS/JANIS convention).
THERMAL_EPITHERMAL_BOUNDARY_EV: float = 0.625
EPITHERMAL_FAST_BOUNDARY_EV: float = 1.0e5

REGIONS: tuple[tuple[str, float, float], ...] = (
    ("thermal", 0.0, THERMAL_EPITHERMAL_BOUNDARY_EV),
    ("epithermal", THERMAL_EPITHERMAL_BOUNDARY_EV, EPITHERMAL_FAST_BOUNDARY_EV),
    ("fast", EPITHERMAL_FAST_BOUNDARY_EV, np.inf),
)


@dataclass
class RegionStats:
    """Deviation statistics of one library vs the reference in one region."""

    region: str
    e_min_ev: float
    e_max_ev: float
    n_points: int
    max_abs_diff_percent: float
    mean_abs_diff_percent: float
    median_abs_diff_percent: float
    energy_at_max_ev: float


@dataclass
class DiscrepancyInterval:
    """Contiguous energy interval where |deviation| exceeds the threshold."""

    library_id: str
    e_min_ev: float
    e_max_ev: float
    max_abs_diff_percent: float


@dataclass
class ComparisonResult:
    """Full comparison payload, ready for plotting and CSV export.

    ``curves`` maps library_id -> sigma on the common grid; ``diff_percent``
    maps non-reference library_id -> 100 * (sigma_lib / sigma_ref - 1).
    Points where the reference is zero have NaN deviation (serialized as
    null) rather than an arbitrary sentinel.
    """

    nuclide: str
    mt: int
    reference_library: str
    energy_ev: np.ndarray
    curves: dict[str, np.ndarray]
    diff_percent: dict[str, np.ndarray] = field(default_factory=dict)
    ratio: dict[str, np.ndarray] = field(default_factory=dict)
    region_stats: list[RegionStats] = field(default_factory=list)
    discrepancies: list[DiscrepancyInterval] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)


def interp_loglog_grid(
    energy: np.ndarray, xs: np.ndarray, grid: np.ndarray
) -> np.ndarray:
    """Interpolate a curve onto ``grid``, log-log with lin-lin near zeros.

    Vectorized: log-log interpolation is linear interpolation of log(sigma)
    in log(E). Zeros are handled by interpolating in linear space and using
    that result wherever either bracketing sigma is nonpositive. Outside the
    curve's domain the result is NaN (never extrapolated).
    """
    loge = np.log(energy)
    with np.errstate(divide="ignore"):
        logs = np.log(xs)
    loggrid = np.log(grid)

    lin = np.interp(grid, energy, xs)
    loglog = np.exp(np.interp(loggrid, loge, logs))

    # Identify grid points whose bracketing interval contains a nonpositive
    # sigma: there log-log is undefined, use lin-lin.
    idx = np.searchsorted(energy, grid, side="right")
    lo = np.clip(idx - 1, 0, len(xs) - 1)
    hi = np.clip(idx, 0, len(xs) - 1)
    bad = (xs[lo] <= 0.0) | (xs[hi] <= 0.0)
    out = np.where(bad, lin, loglog)
    out[(grid < energy[0]) | (grid > energy[-1])] = np.nan
    return out


def _contiguous_intervals(
    energy: np.ndarray, exceed: np.ndarray, diff: np.ndarray, library_id: str
) -> list[DiscrepancyInterval]:
    """Group consecutive above-threshold points into energy intervals."""
    intervals: list[DiscrepancyInterval] = []
    if not exceed.any():
        return intervals
    boundaries = np.flatnonzero(np.diff(exceed.astype(np.int8)))
    starts = [0] if exceed[0] else []
    starts += [b + 1 for b in boundaries if exceed[b + 1]]
    ends = [b for b in boundaries if exceed[b]]
    if exceed[-1]:
        ends.append(len(exceed) - 1)
    for s, e in zip(starts, ends):
        segment = np.abs(diff[s : e + 1])
        intervals.append(
            DiscrepancyInterval(
                library_id=library_id,
                e_min_ev=float(energy[s]),
                e_max_ev=float(energy[e]),
                max_abs_diff_percent=float(np.nanmax(segment)),
            )
        )
    return intervals


def compare(
    nuclide: str,
    mt: int,
    curves: dict[str, tuple[np.ndarray, np.ndarray]],
    threshold_percent: float = 5.0,
    max_grid_points: int = 200_000,
) -> ComparisonResult:
    """Compare evaluated curves from several libraries.

    Parameters
    ----------
    curves : dict
        ``library_id -> (energy_ev, xs_barns)`` full-resolution curves. The
        first key is the reference against which deviations are computed.
    threshold_percent : float
        |deviation| above which a region is flagged as a discrepancy.
    max_grid_points : int
        Safety cap on the union grid (three actinide grids can union to
        >400k points); if exceeded, the union grid is thinned uniformly,
        which slightly smooths the deviation profile but keeps the response
        size and compute bounded.

    Returns
    -------
    ComparisonResult
        Curves on the common grid, deviations, per-region statistics,
        flagged discrepancy intervals, and human-readable summary lines of
        the form "JEFF-3.3 deviates from ENDF/B-VIII.0 by up to 12.3% in the
        epithermal region (max at 6.7 eV)".
    """
    if len(curves) < 2:
        raise ValueError("Comparison requires at least two libraries")

    library_ids = list(curves)
    reference = library_ids[0]

    # Common domain: intersection of ranges, union of grid points within it.
    lo = max(energy[0] for energy, _ in curves.values())
    hi = min(energy[-1] for energy, _ in curves.values())
    if hi <= lo:
        raise ValueError("Libraries have no overlapping energy range")
    union = np.unique(np.concatenate([energy for energy, _ in curves.values()]))
    union = union[(union >= lo) & (union <= hi)]
    if len(union) > max_grid_points:
        union = union[:: len(union) // max_grid_points + 1]

    on_grid = {
        lib: interp_loglog_grid(energy, xs, union)
        for lib, (energy, xs) in curves.items()
    }

    result = ComparisonResult(
        nuclide=nuclide,
        mt=mt,
        reference_library=reference,
        energy_ev=union,
        curves=on_grid,
    )

    ref = on_grid[reference]
    with np.errstate(divide="ignore", invalid="ignore"):
        for lib in library_ids[1:]:
            ratio = np.where(ref > 0.0, on_grid[lib] / ref, np.nan)
            result.ratio[lib] = ratio
            result.diff_percent[lib] = 100.0 * (ratio - 1.0)

    for lib in library_ids[1:]:
        diff = result.diff_percent[lib]
        for region, r_lo, r_hi in REGIONS:
            mask = (union >= r_lo) & (union < r_hi) & np.isfinite(diff)
            if not mask.any():
                continue
            absd = np.abs(diff[mask])
            i_max = int(np.argmax(absd))
            stats = RegionStats(
                region=region,
                e_min_ev=float(union[mask][0]),
                e_max_ev=float(union[mask][-1]),
                n_points=int(mask.sum()),
                max_abs_diff_percent=float(absd[i_max]),
                mean_abs_diff_percent=float(absd.mean()),
                median_abs_diff_percent=float(np.median(absd)),
                energy_at_max_ev=float(union[mask][i_max]),
            )
            result.region_stats.append(stats)
            if stats.max_abs_diff_percent > threshold_percent:
                result.summary.append(
                    f"{lib} deviates from {reference} by up to "
                    f"{stats.max_abs_diff_percent:.1f}% in the {region} region "
                    f"(max at {stats.energy_at_max_ev:.4g} eV; median "
                    f"{stats.median_abs_diff_percent:.1f}%)"
                )

        finite = np.isfinite(diff)
        exceed = np.zeros_like(finite)
        exceed[finite] = np.abs(diff[finite]) > threshold_percent
        result.discrepancies.extend(_contiguous_intervals(union, exceed, diff, lib))

    if not result.summary:
        result.summary.append(
            f"No region exceeds {threshold_percent:.1f}% deviation from {reference}: "
            "the evaluations agree within the threshold everywhere."
        )
    return result
