"""Fission product yields from the ENDF/B-VIII.0 nfy sublibrary.

Parsed with :class:`openmc.data.FissionProductYields` from the raw ENDF-6
files (MF=8, MT=454 independent / MT=459 cumulative). Each fissionable
nuclide provides yields at up to three incident-neutron energies —
conventionally 0.0253 eV ("thermal"), ~500 keV ("fast") and 14 MeV ("high"),
per the ENDF/B evaluation of England & Rider data.

Independent yields are per-fission fractions of each product *before*
delayed decay; cumulative yields include all decay feeding from precursors.
Summing independent yields over all products gives ~2 (two fragments per
fission).

The mass-number aggregation A -> sum of yields reproduces the classic
double-humped asymmetric fission distribution for thermal U-235.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import openmc.data

from app.core.config import settings
from app.core.decay_service import _parse_gnds_name

_FILENAME_RE = re.compile(r"nfy-(\d{3})_([A-Za-z]+)_(\d{3})(m\d+)?\.endf$")

# Conventional labels for the incident energies present in ENDF/B nfy files.
# Matching is by proximity because evaluations store e.g. 0.0253 eV or
# 500 keV with slight variations.
_ENERGY_LABELS: tuple[tuple[str, float], ...] = (
    ("thermal", 0.0253),
    ("fast", 5.0e5),
    ("14MeV", 1.4e7),
)


@dataclass
class YieldSet:
    """Yields at one incident energy, both raw and aggregated.

    ``by_nuclide`` maps product (GNDS name) to fractional yield per fission;
    ``by_mass_number`` / ``by_atomic_number`` are sums over A and Z.
    """

    energy_ev: float
    energy_label: str
    by_nuclide: dict[str, float]
    by_mass_number: dict[int, float]
    by_atomic_number: dict[int, float]


class FissionYieldService:
    """Index over the nfy sublibrary; parses one fissioning system on demand."""

    def __init__(self, nfy_dir: Path | None = None):
        base = nfy_dir or (settings.data_dir / "nfy")
        self._files: dict[str, Path] = {}
        for path in sorted(base.rglob("nfy-*.endf")) if base.exists() else []:
            m = _FILENAME_RE.search(path.name)
            if m:
                _, symbol, a, meta = m.groups()
                name = f"{symbol}{int(a)}" + (f"_{meta}" if meta else "")
                self._files[name] = path
        self._cache: dict[str, dict[str, dict[str, YieldSet]]] = {}
        self._lock = Lock()

    @property
    def available(self) -> bool:
        return bool(self._files)

    def fissionable_nuclides(self) -> list[str]:
        return sorted(self._files)

    def yields(self, nuclide: str) -> dict[str, dict[str, YieldSet]]:
        """All yield sets for one fissioning nuclide.

        Returns
        -------
        dict
            ``{"independent" | "cumulative": {energy_label: YieldSet}}``.
        """
        with self._lock:
            if nuclide in self._cache:
                return self._cache[nuclide]
        if nuclide not in self._files:
            raise KeyError(
                f"No fission yield data for '{nuclide}' in ENDF/B-VIII.0 nfy"
            )
        fpy = openmc.data.FissionProductYields(self._files[nuclide])
        result = {
            "independent": self._package(
                fpy.energies, fpy.independent, cumulative=False
            ),
            "cumulative": self._package(fpy.energies, fpy.cumulative, cumulative=True),
        }
        with self._lock:
            self._cache[nuclide] = result
        return result

    @staticmethod
    def _label_for(energy_ev: float) -> str:
        label, _ = min(_ENERGY_LABELS, key=lambda pair: abs(pair[1] - energy_ev))
        return label

    def _package(
        self, energies, tables: list[dict], cumulative: bool
    ) -> dict[str, YieldSet]:
        """Convert openmc's per-energy yield dicts into aggregated YieldSets.

        ``energies`` is the numpy array (or None) from
        ``FissionProductYields.energies``.

        Aggregation over A and Z depends on the yield type. Independent
        yields of the members of an isobaric chain are disjoint events, so
        the chain (mass) yield is their *sum*. Cumulative yields, however,
        each already include the decay feeding from all precursors in the
        chain: summing them would count the same fissions once per chain
        member (A=99 would come out ~6x too high). The mass-chain value for
        cumulative yields is the *maximum* over the chain, which equals the
        cumulative yield of the last beta-decaying member — the standard
        "chain yield" (England & Rider, LA-UR-94-3106, convention).
        """
        out: dict[str, YieldSet] = {}
        if energies is None:
            return out
        combine = (lambda a, b: max(a, b)) if cumulative else (lambda a, b: a + b)
        for energy, table in zip(energies, tables):
            by_nuclide: dict[str, float] = {}
            by_a: dict[int, float] = {}
            by_z: dict[int, float] = {}
            for product, value in table.items():
                y = float(value.n)  # uncertainties.ufloat -> nominal
                if y <= 0.0:
                    continue
                by_nuclide[product] = y
                z, a, _ = _parse_gnds_name(product)
                if a:
                    by_a[a] = combine(by_a.get(a, 0.0), y)
                if z:
                    by_z[z] = combine(by_z.get(z, 0.0), y)
            label = self._label_for(float(energy))
            out[label] = YieldSet(
                energy_ev=float(energy),
                energy_label=label,
                by_nuclide=by_nuclide,
                by_mass_number=dict(sorted(by_a.items())),
                by_atomic_number=dict(sorted(by_z.items())),
            )
        return out


_yield_service: FissionYieldService | None = None


def get_fission_yield_service() -> FissionYieldService:
    global _yield_service
    if _yield_service is None:
        _yield_service = FissionYieldService()
    return _yield_service
