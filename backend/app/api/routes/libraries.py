"""Endpoints for library discovery and per-nuclide reaction listings."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.library_manager import get_library_manager
from app.core.xs_service import get_xs_service
from app.models.xs import LibraryInfo, NuclideReactions, ReactionEntry

router = APIRouter(prefix="/api", tags=["libraries"])


@router.get("/libraries", response_model=list[LibraryInfo])
def list_libraries() -> list[LibraryInfo]:
    """Libraries currently installed under ``backend/data/``."""
    manager = get_library_manager()
    manager.refresh()  # pick up libraries whose download finished after startup
    return [
        LibraryInfo(
            library_id=meta.library_id,
            name=meta.name,
            version=meta.version,
            citation=meta.citation,
            doi=meta.doi,
            n_nuclides=len(manager.nuclides(meta.library_id)),
        )
        for meta in manager.available_libraries
    ]


@router.get("/libraries/{library_id}/nuclides", response_model=list[str])
def list_nuclides(library_id: str) -> list[str]:
    """All nuclides in one library (GNDS names, e.g. ``U235``, ``Am242_m1``)."""
    try:
        return get_library_manager().nuclides(library_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/nuclides/{nuclide}/reactions", response_model=NuclideReactions)
def nuclide_reactions(nuclide: str, library: str = "endfb80") -> NuclideReactions:
    """Reactions (MT numbers) and temperatures available for a nuclide."""
    service = get_xs_service()
    try:
        reactions = service.reactions(library, nuclide)
        temperatures = service.temperatures(library, nuclide)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return NuclideReactions(
        library_id=library,
        nuclide=nuclide,
        temperatures=temperatures,
        reactions=[
            ReactionEntry(mt=r.mt, name=r.name, redundant=r.redundant)
            for r in reactions
        ],
    )
