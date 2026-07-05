"""Ground-state nuclide properties from NUBASE2020 for the chart of nuclides.

NUBASE2020 [1]_ is the IAEA-AMDC evaluation of nuclear ground-state and
isomer properties (masses, half-lives, spins, decay branches, isotopic
abundances), distributed as a fixed-width text file. Only ground states
(state index ``i = 0`` in column 8) are parsed: the chart of nuclides is a
(N, Z) grid of ground states; isomer data is served by the decay endpoints.

Column positions follow the format block in the file header (1-indexed,
inclusive):

====== ======= =========================================
 cols   field   notes
====== ======= =========================================
 1-3    A
 5-8    ZZZi    Z in 5-7, state index in 8
 12-16  A El    element symbol
 19-31  mass    mass excess (keV)
 70-78  T       half-life value; 'stbl' = stable
 79-80  unit    half-life unit ('ys' to 'Yy')
 89-102 Jpi
 120-   BR      decay modes / abundance ('IS=...')
====== ======= =========================================

Values flagged ``#`` (from systematics, not measurement) are parsed like
measured ones but marked ``from_systematics`` so the UI can render them
distinctly, as the printed NUBASE tables do.

References
----------
.. [1] F.G. Kondev, M. Wang, W.J. Huang, S. Naimi, G. Audi, "The NUBASE2020
   evaluation of nuclear physics properties", Chin. Phys. C 45 (2021)
   030001. doi:10.1088/1674-1137/abddae
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock

from app.core.config import settings

NUBASE_CITATION = (
    'F.G. Kondev et al., "The NUBASE2020 evaluation of nuclear physics '
    'properties", Chin. Phys. C 45 (2021) 030001.'
)

# NUBASE half-life units -> seconds. Year = Julian year (365.25 d), the
# convention used by NUBASE for 'y' and its multiples.
_SECONDS_PER_YEAR = 365.25 * 86400.0
_TIME_UNIT_S: dict[str, float] = {
    "ys": 1e-24,
    "zs": 1e-21,
    "as": 1e-18,
    "fs": 1e-15,
    "ps": 1e-12,
    "ns": 1e-9,
    "us": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
    "d": 86400.0,
    "y": _SECONDS_PER_YEAR,
    "ky": 1e3 * _SECONDS_PER_YEAR,
    "My": 1e6 * _SECONDS_PER_YEAR,
    "Gy": 1e9 * _SECONDS_PER_YEAR,
    "Ty": 1e12 * _SECONDS_PER_YEAR,
    "Py": 1e15 * _SECONDS_PER_YEAR,
    "Ey": 1e18 * _SECONDS_PER_YEAR,
    "Zy": 1e21 * _SECONDS_PER_YEAR,
    "Yy": 1e24 * _SECONDS_PER_YEAR,
}

# One decay-mode token, e.g. 'B-=100', 'A~76', 'SF=7e-9'. The BR field is
# ';'-separated and may lead with the isotopic abundance ('IS=...') for
# long-lived natural nuclides (e.g. U-235: 'IS=0.7204 6;A=100;SF=7e-9'), so
# the primary mode is the first non-IS segment.
_MODE_RE = re.compile(r"^\s*([0-9]*[A-Za-z+\-]+)\s*[=~<>?]")
_ABUNDANCE_RE = re.compile(r"IS\s*=\s*([0-9.]+)")


@dataclass
class NuclideProperties:
    """Ground-state properties of one nuclide (chart-of-nuclides payload)."""

    nuclide: str  # GNDS name, e.g. 'U235'
    z: int
    n: int
    a: int
    symbol: str
    stable: bool
    half_life_s: float | None  # None if stable or unknown
    half_life_from_systematics: bool
    primary_decay_mode: str | None  # NUBASE notation: 'B-', 'A', 'EC', 'SF', ...
    abundance_pct: float | None  # isotopic abundance, stable nuclides only
    mass_excess_kev: float | None
    spin_parity: str | None


class NuclidePropertiesService:
    """Parses NUBASE2020 once and caches the chart payload as JSON."""

    def __init__(self, nubase_file: Path | None = None, cache_dir: Path | None = None):
        default = settings.data_dir / "nubase" / "nubase_4.mas20.txt"
        self._file = nubase_file or default
        self._cache_file = (cache_dir or settings.cache_dir) / "nuclide_properties.json"
        self._data: list[NuclideProperties] | None = None
        self._lock = Lock()

    @property
    def available(self) -> bool:
        return self._file.exists()

    def all(self) -> list[NuclideProperties]:
        with self._lock:
            if self._data is not None:
                return self._data
            if self._cache_file.exists():
                try:
                    raw = json.loads(self._cache_file.read_text())
                    self._data = [NuclideProperties(**item) for item in raw]
                    return self._data
                except (json.JSONDecodeError, TypeError):
                    self._cache_file.unlink(missing_ok=True)
            self._data = self._parse()
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(json.dumps([asdict(p) for p in self._data]))
            return self._data

    def _parse(self) -> list[NuclideProperties]:
        nuclides: list[NuclideProperties] = []
        for line in self._file.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            try:
                a = int(line[0:3])
                z = int(line[4:7])
                state = int(line[7:8])
            except ValueError:
                continue
            if state != 0:  # ground states only
                continue
            symbol_field = line[11:16].strip()
            # 'A El' field, e.g. '235U' -> symbol without mass number.
            symbol = symbol_field.lstrip("0123456789")
            if not symbol:
                continue

            mass_field = line[18:31].strip()
            mass_excess = None
            if mass_field:
                try:
                    mass_excess = float(mass_field.replace("#", ""))
                except ValueError:
                    mass_excess = None

            half_field = line[69:78].strip()
            unit_field = line[78:80].strip()
            stable = half_field == "stbl"
            from_systematics = "#" in half_field
            half_life_s: float | None = None
            if not stable and half_field and half_field not in ("p-unst",):
                try:
                    # Limit/estimate markers ('>1.9', '<300', '~5') can lead
                    # or trail the value; the numeric part is still the best
                    # available estimate for chart coloring.
                    value = float(half_field.replace("#", "").strip("<>~ "))
                    half_life_s = value * _TIME_UNIT_S[unit_field]
                except (ValueError, KeyError):
                    half_life_s = None

            jpi = line[88:102].strip() or None

            br_field = line[119:].strip() if len(line) > 119 else ""
            abundance = None
            match = _ABUNDANCE_RE.search(br_field)
            if match:
                abundance = float(match.group(1))
            mode = None
            for segment in br_field.split(";"):
                mode_match = _MODE_RE.match(segment)
                if mode_match and mode_match.group(1) != "IS":
                    mode = mode_match.group(1)
                    break

            nuclides.append(
                NuclideProperties(
                    nuclide=f"{symbol}{a}",
                    z=z,
                    n=a - z,
                    a=a,
                    symbol=symbol,
                    stable=stable,
                    half_life_s=half_life_s,
                    half_life_from_systematics=from_systematics,
                    primary_decay_mode=mode,
                    abundance_pct=abundance,
                    mass_excess_kev=mass_excess,
                    spin_parity=jpi,
                )
            )
        return nuclides


_properties_service: NuclidePropertiesService | None = None


def get_nuclide_properties_service() -> NuclidePropertiesService:
    global _properties_service
    if _properties_service is None:
        _properties_service = NuclidePropertiesService()
    return _properties_service
