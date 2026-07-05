"""Cross-section curve endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.library_manager import get_library_manager
from app.core.xs_service import get_xs_service
from app.models.xs import XSCurveResponse

router = APIRouter(prefix="/api", tags=["cross-sections"])


@router.get("/xs", response_model=XSCurveResponse)
def get_cross_section(
    nuclide: str = Query(description="GNDS nuclide name, e.g. U235"),
    mt: int = Query(description="ENDF MT number (18=fission, 102=(n,gamma), 2=elastic, 1=total)"),
    library: str = Query(default="endfb80"),
    temperature: str = Query(default="294K", description="Snapped to nearest available"),
    max_points: int = Query(
        default=5000,
        ge=2,
        le=2_000_000,
        description="LTTB decimation target; set very high to get the full grid",
    ),
) -> XSCurveResponse:
    """sigma(E) for one nuclide/reaction/library, decimated for plotting.

    The full evaluation grid (often >100k points for resonant heavy nuclei)
    is decimated with LTTB in log-log space, which preserves resonance peaks.
    Exports that need every point should pass a large ``max_points``.
    """
    service = get_xs_service()
    manager = get_library_manager()
    try:
        curve, n_full = service.get_curve_downsampled(
            library, nuclide, mt, temperature, max_points
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    meta = manager.metadata(library)
    return XSCurveResponse(
        library_id=curve.library_id,
        library_name=meta.name,
        nuclide=curve.nuclide,
        mt=curve.mt,
        reaction_name=curve.reaction_name,
        temperature=curve.temperature,
        energy_ev=curve.energy_ev.tolist(),
        xs_barns=curve.xs_barns.tolist(),
        n_points_full=n_full,
        downsampled=len(curve.energy_ev) < n_full,
        citation=meta.citation,
    )
