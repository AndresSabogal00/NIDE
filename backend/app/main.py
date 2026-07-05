"""NIDE backend — FastAPI application.

Nuclear Information and Data Explorer: a free, local, open-source successor
to the NEA's JANIS browser (web service scheduled for decommissioning in
December 2026). Serves evaluated nuclear data (ENDF/B-VIII.0, JEFF-3.3,
JENDL-5) processed to HDF5 by the OpenMC project, with automatic
multi-library comparison, derived quantities, decay chains, fission yields
and EXFOR experimental overlays.

Run from ``backend/`` with::

    uvicorn app.main:app --reload

Interactive API docs at http://localhost:8000/docs.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    chart,
    comparison,
    decay,
    exfor,
    export,
    fission_yields,
    libraries,
    xs,
)

app = FastAPI(
    title="NIDE — Nuclear Information and Data Explorer",
    description=(
        "REST API for evaluated nuclear data: cross sections, multi-library "
        "comparison, derived quantities, decay data, fission yields and "
        "EXFOR experimental data. Every value is traceable to its evaluation."
    ),
    version="0.1.0",
    license_info={"name": "MIT"},
)

# The frontend dev server (Vite) runs on another localhost port; the app is
# local-only, so a permissive localhost CORS policy is appropriate.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(libraries.router)
app.include_router(xs.router)
app.include_router(comparison.router)
app.include_router(decay.router)
app.include_router(fission_yields.router)
app.include_router(chart.router)
app.include_router(exfor.router)
app.include_router(export.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
