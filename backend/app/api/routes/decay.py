"""Decay data and decay-chain endpoints (Cytoscape-ready graphs)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.decay_service import get_decay_service
from app.models.decay import (
    CytoscapeEdge,
    CytoscapeNode,
    DecayChainResponse,
    DecayInfoModel,
    DecayModeModel,
)

router = APIRouter(prefix="/api", tags=["decay"])

_TIME_UNITS: tuple[tuple[float, str], ...] = (
    (3.15576e16, "Gyr"),
    (3.15576e13, "Myr"),
    (3.15576e10, "kyr"),
    (3.15576e7, "yr"),
    (86400.0, "d"),
    (3600.0, "h"),
    (60.0, "min"),
    (1.0, "s"),
    (1e-3, "ms"),
    (1e-6, "us"),
    (1e-9, "ns"),
)


def humanize_half_life(seconds: float | None) -> str | None:
    """'1.664e8 s' -> '5.27 yr'; picks the largest unit giving value >= 1."""
    if seconds is None:
        return None
    for factor, unit in _TIME_UNITS:
        if seconds >= factor:
            return f"{seconds / factor:.3g} {unit}"
    return f"{seconds:.3g} s"


@router.get("/decay/{nuclide}", response_model=DecayInfoModel)
def decay_info(nuclide: str) -> DecayInfoModel:
    """Decay summary for one nuclide: half-life, modes, branching ratios."""
    service = get_decay_service()
    if not service.available:
        raise HTTPException(status_code=503, detail="Decay sublibrary not downloaded")
    try:
        info = service.info(nuclide)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DecayInfoModel(
        **{
            **info.__dict__,
            "modes": [DecayModeModel(**m.__dict__) for m in info.modes],
            "half_life_human": humanize_half_life(info.half_life_s),
        }
    )


@router.get("/decay/{nuclide}/chain", response_model=DecayChainResponse)
def decay_chain(
    nuclide: str,
    min_br: float = Query(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Prune branches below this branching ratio (e.g. 1e-4 for main paths)",
    ),
) -> DecayChainResponse:
    """Decay chain from a nuclide down to stability, as a Cytoscape graph."""
    service = get_decay_service()
    if not service.available:
        raise HTTPException(status_code=503, detail="Decay sublibrary not downloaded")
    try:
        nodes, edges = service.chain(nuclide, min_branching_ratio=min_br)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DecayChainResponse(
        start=nuclide,
        nodes=[
            CytoscapeNode(
                data={
                    "id": n.nuclide,
                    "z": n.z,
                    "a": n.a,
                    "stable": n.stable,
                    "half_life_s": n.half_life_s,
                    "half_life_human": humanize_half_life(n.half_life_s),
                }
            )
            for n in nodes
        ],
        edges=[
            CytoscapeEdge(
                data={
                    "id": f"{src}->{dst}:{mode.mode}",
                    "source": src,
                    "target": dst,
                    "mode": mode.mode,
                    "branching_ratio": mode.branching_ratio,
                }
            )
            for src, dst, mode in edges
        ],
    )
