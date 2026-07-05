"""EXFOR experimental data endpoint (graceful when the IAEA API is down)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from app.core.exfor_client import get_exfor_client

router = APIRouter(prefix="/api", tags=["exfor"])


@router.get("/exfor")
def exfor(
    nuclide: str = Query(description="GNDS nuclide name, e.g. U235"),
    mt: int = Query(description="ENDF MT number (mapped to EXFOR notation, e.g. 102 -> n,g)"),
):
    """Experimental datasets from EXFOR via the IAEA Data Explorer API.

    Always returns 200: when EXFOR is unreachable or has no data the payload
    says so (``available=false`` + message) so the frontend overlay simply
    stays empty — the evaluated-data views never depend on this endpoint.
    """
    return asdict(get_exfor_client().query(nuclide, mt))
