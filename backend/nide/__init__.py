"""NIDE as a Python library — evaluated nuclear data without the web app.

This package is a thin, stable facade over the same services that power the
NIDE web application, for use in notebooks, analysis scripts and other
software::

    from nide import NuclearLibrary

    u235 = NuclearLibrary("ENDF/B-VIII.0").nuclide("U235")
    xs = u235.cross_section("(n,f)")          # or 18, "n,f", "fission"
    xs.at(0.0253)                             # -> 586.6 (barns)
    u235.derived_quantities("(n,f)").thermal_xs_barns

    from nide import compare
    report = compare("U238", "(n,gamma)", ["ENDF/B-VIII.0", "JEFF-3.3"])
    print(report.summary)

Unit conventions match the rest of NIDE: energies in eV, cross sections in
barns. Every object carries the citation of its source evaluation.

The nuclear data libraries must be present under ``backend/data/`` (see
``scripts/download_data.py``); loading is lazy and cached exactly as in the
web backend, so the first access to a heavy actinide pays the HDF5 parse
once per process.
"""

from nide.api import (
    CrossSection,
    NuclearLibrary,
    Nuclide,
    available_libraries,
    compare,
    resolve_mt,
)

__all__ = [
    "CrossSection",
    "NuclearLibrary",
    "Nuclide",
    "available_libraries",
    "compare",
    "resolve_mt",
]

__version__ = "0.2.0"
