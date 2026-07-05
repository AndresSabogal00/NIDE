"""Fission product yield endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.fission_yields import get_fission_yield_service
from app.models.decay import FissionYieldResponse, YieldSetModel

router = APIRouter(prefix="/api", tags=["fission-yields"])


@router.get("/fission-yields/nuclides", response_model=list[str])
def fissionable_nuclides() -> list[str]:
    """Nuclides with fission-yield evaluations in ENDF/B-VIII.0 (31 systems)."""
    service = get_fission_yield_service()
    if not service.available:
        raise HTTPException(status_code=503, detail="nfy sublibrary not downloaded")
    return service.fissionable_nuclides()


@router.get("/fission-yields/{nuclide}", response_model=FissionYieldResponse)
def fission_yields(
    nuclide: str,
    yield_type: str = Query(
        default="cumulative",
        pattern="^(independent|cumulative)$",
        description="independent: prompt fragment yields; cumulative: after decay feeding",
    ),
) -> FissionYieldResponse:
    """Yield distributions (by A, by Z, top products) at each incident energy."""
    service = get_fission_yield_service()
    if not service.available:
        raise HTTPException(status_code=503, detail="nfy sublibrary not downloaded")
    try:
        sets = service.yields(nuclide)[yield_type]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FissionYieldResponse(
        nuclide=nuclide,
        yield_type=yield_type,
        sets=[
            YieldSetModel(
                energy_ev=s.energy_ev,
                energy_label=s.energy_label,
                by_mass_number=s.by_mass_number,
                by_atomic_number=s.by_atomic_number,
                top_products=sorted(s.by_nuclide.items(), key=lambda kv: -kv[1])[:20],
            )
            for s in sets.values()
        ],
    )
