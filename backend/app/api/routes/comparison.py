"""Endpoints for multi-library comparison and derived quantities."""

from __future__ import annotations

import numpy as np
import openmc.data
from fastapi import APIRouter, HTTPException, Query

from app.core import derived_quantities as dq
from app.core.comparison_engine import compare
from app.core.library_manager import get_library_manager
from app.core.xs_service import get_xs_service, lttb_downsample
from app.models.comparison import ComparisonResponse, DerivedResponse

router = APIRouter(prefix="/api", tags=["comparison"])

# Human-readable definitions surfaced next to the derived-quantities table so
# every number in the UI states its convention (traceability requirement).
_DEFINITIONS = {
    "thermal_xs_barns": "sigma(0.0253 eV), the 2200 m/s conventional thermal value",
    "resonance_integral_barns": (
        "I = integral sigma(E) dE/E from 0.5 eV (Cd cutoff) to 20 MeV, "
        "1/E epithermal spectrum"
    ),
    "maxwellian_avg_barns": (
        "Flux-weighted average over a Maxwell-Boltzmann spectrum at T "
        "(integral sigma E exp(-E/kT) dE / integral E exp(-E/kT) dE)"
    ),
    "watt_avg_barns": (
        "Average over Watt fission spectrum chi ~ exp(-E/a) sinh(sqrt(bE)), "
        "a = 0.988 MeV, b = 2.249 MeV^-1 (ENDF/B U-235 thermal fission)"
    ),
    "westcott_g_factor": (
        "g(T) = Maxwellian average x (2/sqrt(pi)) / sigma(kT); equals 1 for a 1/v absorber"
    ),
}


def _nan_to_none(values: np.ndarray) -> list[float | None]:
    return [None if not np.isfinite(v) else float(v) for v in values]


@router.get("/compare", response_model=ComparisonResponse)
def compare_libraries(
    nuclide: str = Query(description="GNDS nuclide name, e.g. U235"),
    mt: int = Query(description="ENDF MT number"),
    libraries: str = Query(
        default="endfb80,jeff33,jendl5",
        description="Comma-separated library ids; the first is the reference",
    ),
    temperature: str = Query(default="294K"),
    threshold: float = Query(
        default=5.0, gt=0.0, description="Discrepancy threshold in percent"
    ),
    max_points: int = Query(default=5000, ge=100, le=200_000),
):
    """Compare sigma(E) across libraries with automatic discrepancy detection.

    Returns curves on a common grid (LTTB-decimated for plotting), percent
    deviations from the reference library, per-region statistics and
    flagged discrepancy intervals. See ``comparison_engine`` for method.
    """
    manager = get_library_manager()
    service = get_xs_service()
    requested = [lib.strip() for lib in libraries.split(",") if lib.strip()]

    curves: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    missing: list[str] = []
    for lib in requested:
        try:
            curve = service.get_curve(lib, nuclide, mt, temperature)
            curves[lib] = (curve.energy_ev, curve.xs_barns)
        except KeyError:
            missing.append(lib)
    if len(curves) < 2:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Need at least two libraries with {nuclide} MT={mt}; "
                f"available: {list(curves)}, missing/lacking data: {missing}"
            ),
        )

    result = compare(nuclide, mt, curves, threshold_percent=threshold)

    # Decimate the common-grid arrays for the response. Indices are selected
    # on the reference curve so all series stay aligned point-for-point.
    idx = lttb_downsample(
        result.energy_ev,
        np.nan_to_num(result.curves[result.reference_library], nan=0.0),
        max_points,
    )
    return {
        "nuclide": nuclide,
        "mt": mt,
        "reaction_name": openmc.data.REACTION_NAME.get(mt, f"MT={mt}"),
        "reference_library": result.reference_library,
        "threshold_percent": threshold,
        "missing_libraries": missing,
        "energy_ev": result.energy_ev[idx].tolist(),
        "curves": {lib: _nan_to_none(arr[idx]) for lib, arr in result.curves.items()},
        "diff_percent": {
            lib: _nan_to_none(arr[idx]) for lib, arr in result.diff_percent.items()
        },
        "region_stats": [stats.__dict__ for stats in result.region_stats],
        "discrepancies": [d.__dict__ for d in result.discrepancies],
        "summary": result.summary,
        "explanation": result.explanation,
        "citations": {lib: manager.metadata(lib).citation for lib in curves},
    }


@router.get("/derived", response_model=DerivedResponse)
def derived_quantities(
    nuclide: str = Query(description="GNDS nuclide name"),
    mt: int = Query(description="ENDF MT number"),
    libraries: str = Query(default="endfb80,jeff33,jendl5"),
    temperature: str = Query(default="294K"),
    maxwellian_t: float = Query(
        default=293.6, gt=0.0, description="Maxwellian temperature (K)"
    ),
):
    """Derived integral quantities per library — the automatic comparison table."""
    manager = get_library_manager()
    service = get_xs_service()
    results = []
    served_temperature = temperature
    for lib in [x.strip() for x in libraries.split(",") if x.strip()]:
        try:
            curve = service.get_curve(lib, nuclide, mt, temperature)
        except KeyError:
            continue
        served_temperature = curve.temperature
        quantities = dq.compute_all(curve.energy_ev, curve.xs_barns, maxwellian_t)
        results.append(
            {
                "library_id": lib,
                "library_name": manager.metadata(lib).name,
                **quantities.__dict__,
            }
        )
    if not results:
        raise HTTPException(
            status_code=404, detail=f"No library provides {nuclide} MT={mt}"
        )
    return {
        "nuclide": nuclide,
        "mt": mt,
        "reaction_name": openmc.data.REACTION_NAME.get(mt, f"MT={mt}"),
        "temperature": served_temperature,
        "results": results,
        "definitions": _DEFINITIONS,
    }
