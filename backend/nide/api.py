"""Public Python API implementation (see package docstring in __init__).

Everything here delegates to the validated service layer (``app.core``);
this module adds only name resolution and ergonomic value objects. Keeping
it dependency-thin means the web API and the Python API can never disagree
about physics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property

import numpy as np
import openmc.data

from app.core import derived_quantities as dq
from app.core.comparison_engine import ComparisonResult, compare as _compare
from app.core.library_manager import SUPPORTED_LIBRARIES, get_library_manager
from app.core.xs_service import get_xs_service

# ---------------------------------------------------------------------- #
# Name resolution                                                         #
# ---------------------------------------------------------------------- #

# Reverse of openmc's MT -> "(n,fission)" map, keyed by a normalized form
# (lowercase, no parentheses/spaces) so users can write "(n,f)", "n,f",
# "N,F" or "fission" interchangeably.
_MT_BY_NAME: dict[str, int] = {}
for _mt, _name in openmc.data.REACTION_NAME.items():
    _MT_BY_NAME[re.sub(r"[\s()]", "", _name).lower()] = _mt

_ALIASES: dict[str, int] = {
    "n,f": 18,
    "fission": 18,
    "n,g": 102,
    "capture": 102,
    "radiativecapture": 102,
    "elastic": 2,
    "total": 1,
    "absorption": 27,
    "inelastic": 4,
}


def resolve_mt(reaction: int | str) -> int:
    """Resolve a reaction given as MT number or common string notation.

    Parameters
    ----------
    reaction : int or str
        ENDF MT number, an openmc-style name (``"(n,gamma)"``), a compact
        form (``"n,g"``, ``"(n,f)"``), or a word alias (``"fission"``,
        ``"capture"``, ``"elastic"``, ``"total"``).

    Returns
    -------
    int
        The ENDF MT number.

    Raises
    ------
    ValueError
        If the string cannot be resolved.
    """
    if isinstance(reaction, int):
        return reaction
    key = re.sub(r"[\s()]", "", reaction).lower()
    if key in _ALIASES:
        return _ALIASES[key]
    if key in _MT_BY_NAME:
        return _MT_BY_NAME[key]
    raise ValueError(
        f"Unknown reaction '{reaction}'. Use an ENDF MT number or a name "
        "like '(n,gamma)', 'n,f', 'fission', 'capture', 'elastic', 'total'."
    )


def _resolve_library_id(name: str) -> str:
    """'ENDF/B-VIII.0' | 'endfb80' | 'jeff-3.3' ... -> internal library id."""
    for library_id, meta in SUPPORTED_LIBRARIES.items():
        if name == library_id or name.lower() == meta.name.lower():
            return library_id
    # Forgiving fallback: strip punctuation ("jeff33" == "JEFF-3.3").
    compact = re.sub(r"[^a-z0-9]", "", name.lower())
    for library_id, meta in SUPPORTED_LIBRARIES.items():
        if compact in (library_id, re.sub(r"[^a-z0-9]", "", meta.name.lower())):
            return library_id
    known = ", ".join(f"'{m.name}'" for m in SUPPORTED_LIBRARIES.values())
    raise ValueError(f"Unknown library '{name}'. Known: {known}")


def available_libraries() -> list[str]:
    """Names of the libraries actually installed under ``backend/data/``."""
    return [meta.name for meta in get_library_manager().available_libraries]


# ---------------------------------------------------------------------- #
# Value objects                                                           #
# ---------------------------------------------------------------------- #


@dataclass(frozen=True)
class CrossSection:
    """One evaluated cross-section curve on the full evaluation grid.

    Attributes
    ----------
    energy_ev, xs_barns : numpy.ndarray
        Pointwise sigma(E); the evaluation's own union grid, never decimated.
    """

    library: str
    nuclide: str
    mt: int
    reaction_name: str
    temperature: str
    energy_ev: np.ndarray
    xs_barns: np.ndarray
    citation: str

    def at(self, energy_ev: float) -> float:
        """sigma at one energy (log-log interpolation, barns)."""
        return dq._interp_loglog(self.energy_ev, self.xs_barns, energy_ev)  # noqa: SLF001

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"<CrossSection {self.nuclide} {self.reaction_name} "
            f"[{self.library}] {len(self.energy_ev)} pts>"
        )


class Nuclide:
    """One nuclide within one library. Obtain via :meth:`NuclearLibrary.nuclide`."""

    def __init__(self, library_id: str, name: str):
        self._library_id = library_id
        self._name = name
        self._meta = SUPPORTED_LIBRARIES[library_id]

    @property
    def name(self) -> str:
        return self._name

    @cached_property
    def reactions(self) -> dict[int, str]:
        """Available reactions: ``{MT: human-readable name}`` (includes
        redundant MTs synthesizable from stored partials, e.g. MT=1)."""
        infos = get_xs_service().reactions(self._library_id, self._name)
        return {r.mt: r.name for r in infos}

    @cached_property
    def temperatures(self) -> list[str]:
        return get_xs_service().temperatures(self._library_id, self._name)

    def cross_section(self, reaction: int | str, temperature: str = "294K") -> CrossSection:
        """Full-resolution sigma(E) for one reaction.

        Parameters
        ----------
        reaction : int or str
            See :func:`resolve_mt`.
        temperature : str
            Snapped to the nearest temperature in the processed library.
        """
        mt = resolve_mt(reaction)
        curve = get_xs_service().get_curve(self._library_id, self._name, mt, temperature)
        return CrossSection(
            library=self._meta.name,
            nuclide=self._name,
            mt=mt,
            reaction_name=curve.reaction_name,
            temperature=curve.temperature,
            energy_ev=curve.energy_ev,
            xs_barns=curve.xs_barns,
            citation=self._meta.citation,
        )

    def derived_quantities(
        self,
        reaction: int | str,
        temperature: str = "294K",
        maxwellian_temperature_k: float = 293.6,
    ) -> dq.DerivedQuantities:
        """Thermal value, resonance integral, Maxwellian and Watt averages.

        See :mod:`app.core.derived_quantities` for definitions, conventions
        and literature references of each quantity.
        """
        xs = self.cross_section(reaction, temperature)
        return dq.compute_all(xs.energy_ev, xs.xs_barns, maxwellian_temperature_k)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Nuclide {self._name} [{self._meta.name}]>"


class NuclearLibrary:
    """One evaluated data library, e.g. ``NuclearLibrary("ENDF/B-VIII.0")``.

    Parameters
    ----------
    name : str
        Evaluation name or NIDE id: ``"ENDF/B-VIII.0"``/``"endfb80"``,
        ``"JEFF-3.3"``/``"jeff33"``, ``"JENDL-5"``/``"jendl5"``.

    Raises
    ------
    ValueError
        If the name is unknown.
    KeyError
        On first data access, if the library is not downloaded.
    """

    def __init__(self, name: str):
        self._library_id = _resolve_library_id(name)
        self._meta = SUPPORTED_LIBRARIES[self._library_id]

    @property
    def name(self) -> str:
        return self._meta.name

    @property
    def citation(self) -> str:
        return self._meta.citation

    @cached_property
    def nuclides(self) -> list[str]:
        """All nuclides in the library (GNDS names, e.g. ``'U235'``)."""
        return get_library_manager().nuclides(self._library_id)

    def nuclide(self, name: str) -> Nuclide:
        if not get_library_manager().has_nuclide(self._library_id, name):
            raise KeyError(f"Nuclide '{name}' not available in {self._meta.name}")
        return Nuclide(self._library_id, name)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<NuclearLibrary {self._meta.name}>"


def compare(
    nuclide: str,
    reaction: int | str,
    libraries: list[str] | None = None,
    threshold_percent: float = 5.0,
    temperature: str = "294K",
) -> ComparisonResult:
    """Multi-library comparison, identical to the web comparison panel.

    Parameters
    ----------
    libraries : list of str, optional
        Library names/ids; the first is the reference. Defaults to every
        installed library (canonical order, ENDF/B-VIII.0 first).

    Returns
    -------
    app.core.comparison_engine.ComparisonResult
        Curves on the union grid, per-library deviations, region statistics
        and the human-readable discrepancy ``summary``.
    """
    mt = resolve_mt(reaction)
    if libraries is None:
        ids = [m.library_id for m in get_library_manager().available_libraries]
    else:
        ids = [_resolve_library_id(x) for x in libraries]
    service = get_xs_service()
    curves = {}
    for library_id in ids:
        try:
            curve = service.get_curve(library_id, nuclide, mt, temperature)
        except KeyError:
            continue
        curves[library_id] = (curve.energy_ev, curve.xs_barns)
    return _compare(nuclide, mt, curves, threshold_percent=threshold_percent)
