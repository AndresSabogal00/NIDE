"""CSV export endpoints with full provenance headers.

Every CSV starts with '#'-prefixed metadata lines: what was exported, from
which library/version, when, and the official citation of each evaluation —
so a file found on disk three years later is still traceable (project
requirement: no number leaves NIDE without its source).

Exports serve the *full* evaluation grid, not the LTTB-decimated curves the
plots use.
"""

from __future__ import annotations

import io
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.core.comparison_engine import compare
from app.core.fission_yields import get_fission_yield_service
from app.core.library_manager import get_library_manager
from app.core.xs_service import get_xs_service

router = APIRouter(prefix="/api/export", tags=["export"])

NIDE_LINE = "# Exported by NIDE (Nuclear Information and Data Explorer), https://github.com/"


def _header(title: str, citations: dict[str, str]) -> list[str]:
    lines = [f"# {title}", f"# Access date: {date.today().isoformat()}", NIDE_LINE]
    for lib, citation in citations.items():
        lines.append(f"# Source [{lib}]: {citation}")
    return lines


def _csv_response(lines: list[str], filename: str) -> PlainTextResponse:
    return PlainTextResponse(
        "\n".join(lines) + "\n",
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/csv")
def export_xs_csv(
    nuclide: str = Query(...),
    mt: int = Query(...),
    libraries: str = Query(default="endfb80"),
    temperature: str = Query(default="294K"),
):
    """Full-resolution sigma(E) per library, aligned per-library blocks."""
    manager = get_library_manager()
    service = get_xs_service()
    requested = [x.strip() for x in libraries.split(",") if x.strip()]
    curves = []
    citations: dict[str, str] = {}
    for lib in requested:
        try:
            curve = service.get_curve(lib, nuclide, mt, temperature)
        except KeyError:
            continue
        curves.append(curve)
        citations[manager.metadata(lib).name] = manager.metadata(lib).citation
    if not curves:
        raise HTTPException(status_code=404, detail=f"No data for {nuclide} MT={mt}")

    buffer = io.StringIO()
    title = (
        f"Cross section: {nuclide}, MT={mt} ({curves[0].reaction_name}), "
        f"T={curves[0].temperature}. Units: energy eV, cross section barns."
    )
    buffer.write("\n".join(_header(title, citations)) + "\n")
    for curve in curves:
        buffer.write(f"# --- library: {curve.library_id}, {len(curve.energy_ev)} points ---\n")
        buffer.write("library,energy_eV,cross_section_barns\n")
        for energy, xs in zip(curve.energy_ev, curve.xs_barns):
            buffer.write(f"{curve.library_id},{float(energy)!r},{float(xs)!r}\n")
    return _csv_response([buffer.getvalue().rstrip("\n")], f"nide_{nuclide}_mt{mt}.csv")


@router.get("/comparison-csv")
def export_comparison_csv(
    nuclide: str = Query(...),
    mt: int = Query(...),
    libraries: str = Query(default="endfb80,jeff33,jendl5"),
    threshold: float = Query(default=5.0),
    temperature: str = Query(default="294K"),
):
    """Comparison report: common grid, per-library sigma, deviations, and the
    discrepancy summary as comment lines."""
    manager = get_library_manager()
    service = get_xs_service()
    requested = [x.strip() for x in libraries.split(",") if x.strip()]
    curves = {}
    citations: dict[str, str] = {}
    for lib in requested:
        try:
            curve = service.get_curve(lib, nuclide, mt, temperature)
        except KeyError:
            continue
        curves[lib] = (curve.energy_ev, curve.xs_barns)
        citations[manager.metadata(lib).name] = manager.metadata(lib).citation
    if len(curves) < 2:
        raise HTTPException(status_code=404, detail="Need two or more libraries with data")

    result = compare(nuclide, mt, curves, threshold_percent=threshold)
    lines = _header(
        f"Library comparison: {nuclide}, MT={mt}. Reference: {result.reference_library}. "
        f"Units: energy eV, cross sections barns, deviations percent.",
        citations,
    )
    for summary_line in (*result.summary, *result.explanation):
        lines.append(f"# {summary_line}")
    libs = list(result.curves)
    header = (
        ["energy_eV"]
        + [f"sigma_{lib}_barns" for lib in libs]
        + [
            f"diff_{lib}_vs_{result.reference_library}_pct"
            for lib in libs
            if lib in result.diff_percent
        ]
    )
    lines.append(",".join(header))
    diff_libs = [lib for lib in libs if lib in result.diff_percent]
    for i, energy in enumerate(result.energy_ev):
        row = [repr(float(energy))]
        row += [_fmt(result.curves[lib][i]) for lib in libs]
        row += [_fmt(result.diff_percent[lib][i]) for lib in diff_libs]
        lines.append(",".join(row))
    return _csv_response(lines, f"nide_compare_{nuclide}_mt{mt}.csv")


@router.get("/yields-csv")
def export_yields_csv(
    nuclide: str = Query(...),
    yield_type: str = Query(default="cumulative", pattern="^(independent|cumulative)$"),
):
    """Per-product fission yields at every available incident energy."""
    service = get_fission_yield_service()
    try:
        sets = service.yields(nuclide)[yield_type]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    citations = {
        "ENDF/B-VIII.0 nfy": (
            "D.A. Brown et al., Nucl. Data Sheets 148 (2018) 1-142; yields evaluation: "
            "T.R. England, B.F. Rider, LA-UR-94-3106 (1994)."
        )
    }
    lines = _header(
        f"Fission product yields ({yield_type}): {nuclide}(n,f). Yields are fractions per fission.",
        citations,
    )
    lines.append("energy_label,energy_eV,product,yield_per_fission")
    for label, yield_set in sets.items():
        for product, value in sorted(yield_set.by_nuclide.items()):
            lines.append(f"{label},{yield_set.energy_ev!r},{product},{value!r}")
    return _csv_response(lines, f"nide_yields_{nuclide}_{yield_type}.csv")


def _fmt(x) -> str:
    import math

    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return ""
    return repr(float(x))
