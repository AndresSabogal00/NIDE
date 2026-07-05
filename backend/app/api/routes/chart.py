"""Chart-of-nuclides endpoints.

``/api/chart/nuclides`` serves the NUBASE2020 ground-state table (fast,
cached JSON). ``/api/chart/thermal-capture`` additionally serves the
2200 m/s (n,gamma) cross section for every nuclide present in a transport
library — an expensive one-time computation (one HDF5 load per nuclide,
~2 min for ENDF/B-VIII.0) that is cached on disk forever after.
"""

from __future__ import annotations

import json

import openmc.data
from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.core.library_manager import get_library_manager
from app.core.nuclide_properties import (
    NUBASE_CITATION,
    get_nuclide_properties_service,
)

router = APIRouter(prefix="/api", tags=["chart"])

THERMAL_ENERGY_EV = 0.0253


@router.get("/chart/nuclides")
def chart_nuclides(library: str = Query(default="endfb80")):
    """All ground-state nuclides with chart properties (NUBASE2020).

    ``has_xs_data`` marks nuclides present in the requested transport
    library, so the chart can distinguish evaluated from structure-only
    nuclides.
    """
    service = get_nuclide_properties_service()
    if not service.available:
        raise HTTPException(status_code=503, detail="NUBASE2020 file not downloaded")
    manager = get_library_manager()
    try:
        with_xs = set(manager.nuclides(library))
    except KeyError:
        with_xs = set()
    return {
        "citation": NUBASE_CITATION,
        "nuclides": [
            {**p.__dict__, "has_xs_data": p.nuclide in with_xs} for p in service.all()
        ],
    }


@router.get("/chart/thermal-capture")
def thermal_capture_map(library: str = Query(default="endfb80")):
    """2200 m/s (n,gamma) cross section for every nuclide in a library.

    Used to color the chart by thermal capture. First call per library
    computes the whole map (loads every HDF5 file once); subsequent calls
    are served from the JSON cache.
    """
    manager = get_library_manager()
    try:
        nuclides = manager.nuclides(library)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    cache_file = settings.cache_dir / f"thermal_capture_{library}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    # Evaluate sigma(0.0253 eV) directly from each nuclide's Tabulated1D
    # rather than through XSService: extracting and disk-caching ~800 full
    # curves would cost hundreds of MB for one number each.
    values: dict[str, float] = {}
    for nuclide in nuclides:
        try:
            nuc = openmc.data.IncidentNeutron.from_hdf5(
                manager.hdf5_path(library, nuclide)
            )
        except (OSError, KeyError):
            continue
        if 102 not in nuc.reactions:
            continue
        temperature = min(nuc.temperatures, key=lambda t: abs(float(t[:-1]) - 294.0))
        sigma = float(nuc.reactions[102].xs[temperature](THERMAL_ENERGY_EV))
        if sigma > 0.0:
            values[nuclide] = sigma
    payload = {
        "library": library,
        "citation": manager.metadata(library).citation,
        "sigma_thermal_capture_barns": values,
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload))
    return payload
