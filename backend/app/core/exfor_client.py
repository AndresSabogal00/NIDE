"""Client for experimental cross-section data from EXFOR (IAEA-NDS).

Data source
-----------
The IAEA Nuclear Data Section's *Data Explorer* REST API
(https://nds.iaea.org/dataexplorer/), which serves the EXFOR experimental
reaction database [1]_ parsed to JSON — free, no API key. Endpoint used::

    GET /dataexplorer/api/reactions/xs
        ?target_elem=U&target_mass=235&reaction=n,f&table=True

With ``table=True`` each returned dataset carries a ``datatable`` of
(en_inc, data, ddata) columns. Units as served: incident energy in **MeV**,
cross sections in **barns**; energies are converted to eV here to match the
NIDE-wide convention. (Endpoint shape verified against the live service on
2026-07-05.)

Caching and failure policy
--------------------------
Experimental data is immutable at the resolution NIDE cares about (EXFOR is
append-mostly, updated monthly), so responses are cached on disk
indefinitely — one JSON file per (nuclide, MT). Network failures degrade
gracefully: the client returns an "unavailable" payload with a message and
the app keeps working without the experimental overlay (hard requirement:
EXFOR is an enhancement, never a dependency).

References
----------
.. [1] N. Otuka et al., "Towards a More Complete and Accurate Experimental
   Nuclear Reaction Data Library (EXFOR)", Nucl. Data Sheets 120 (2014)
   272-276. doi:10.1016/j.nds.2014.07.065
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

from app.core.config import settings

API_URL = "https://nds.iaea.org/dataexplorer/api/reactions/xs"
TIMEOUT_S = 30.0

# ENDF MT -> Data Explorer reaction notation. Only channels commonly
# measured as cross sections are mapped; anything else returns "no mapping"
# rather than guessing (traceability over coverage).
MT_TO_REACTION: dict[int, str] = {
    1: "n,tot",
    2: "n,el",
    4: "n,inl",
    16: "n,2n",
    17: "n,3n",
    18: "n,f",
    102: "n,g",
    103: "n,p",
    104: "n,d",
    105: "n,t",
    106: "n,he3",
    107: "n,a",
}

# Response-size guards: EXFOR has >400 datasets for U-235(n,f); the overlay
# is meant for visual comparison, not bulk retrieval, so we keep the largest
# datasets and thin very dense ones by uniform stride (they are plotted on
# top of the evaluated curve, where visual density saturates anyway).
MAX_DATASETS = 12
MAX_POINTS_PER_DATASET = 2000

_GNDS_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


@dataclass
class ExforPoint:
    energy_ev: float
    xs_barns: float
    denergy_ev: float | None
    dxs_barns: float | None


@dataclass
class ExforDataset:
    """One EXFOR (sub)entry: a single measurement series with provenance."""

    entry: str  # EXFOR dataset id, e.g. '13519-002-0'
    author: str  # first author, as EXFOR reports it
    year: int | None
    reference: str  # human-readable provenance line for the plot legend
    points: list[ExforPoint] = field(default_factory=list)


@dataclass
class ExforResult:
    nuclide: str
    mt: int
    available: bool
    message: str | None
    datasets: list[ExforDataset] = field(default_factory=list)


class ExforClient:
    def __init__(self, cache_dir: Path | None = None):
        self._cache_dir = (cache_dir or settings.cache_dir) / "exfor"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def query(self, nuclide: str, mt: int) -> ExforResult:
        """Experimental datasets for one nuclide + MT, cached forever."""
        cached = self._cache_load(nuclide, mt)
        if cached is not None:
            return cached

        match = _GNDS_RE.match(nuclide)
        if not match:
            # Metastable targets (U235_m1 etc.) have a different EXFOR
            # notation not wired up here; report cleanly instead of guessing.
            return ExforResult(nuclide, mt, False, f"No EXFOR mapping for '{nuclide}'")
        if mt not in MT_TO_REACTION:
            return ExforResult(
                nuclide, mt, False, f"No EXFOR reaction notation mapped for MT={mt}"
            )

        symbol, mass = match.groups()
        try:
            response = requests.get(
                API_URL,
                params={
                    "target_elem": symbol,
                    "target_mass": mass,
                    "reaction": MT_TO_REACTION[mt],
                    "table": "True",
                },
                timeout=TIMEOUT_S,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            # Not cached: a transient outage should not poison future calls.
            return ExforResult(nuclide, mt, False, f"EXFOR API unreachable: {exc}")

        result = self._parse(nuclide, mt, payload)
        self._cache_store(result)
        return result

    def _parse(self, nuclide: str, mt: int, payload: dict) -> ExforResult:
        datasets: list[ExforDataset] = []
        aggregations = payload.get("aggregations") or {}
        for entry_id, meta in aggregations.items():
            table = meta.get("datatable") or {}
            energies = table.get("en_inc") or []
            values = table.get("data") or []
            dvalues = table.get("ddata") or []
            denergies = table.get("den_inc") or []
            points: list[ExforPoint] = []
            for i, (energy, value) in enumerate(zip(energies, values)):
                if not _is_number(energy) or not _is_number(value) or value <= 0:
                    continue
                de = denergies[i] if i < len(denergies) else None
                dv = dvalues[i] if i < len(dvalues) else None
                points.append(
                    ExforPoint(
                        energy_ev=float(energy) * 1e6,  # MeV -> eV
                        xs_barns=float(value),
                        denergy_ev=float(de) * 1e6 if _is_number(de) else None,
                        dxs_barns=float(dv) if _is_number(dv) else None,
                    )
                )
            if not points:
                continue
            points.sort(key=lambda p: p.energy_ev)
            if len(points) > MAX_POINTS_PER_DATASET:
                stride = len(points) // MAX_POINTS_PER_DATASET + 1
                points = points[::stride]
            year = meta.get("year")
            datasets.append(
                ExforDataset(
                    entry=entry_id,
                    author=str(meta.get("author") or "unknown"),
                    year=int(year) if year else None,
                    reference=(
                        f"{meta.get('author', 'unknown')} ({year or 'n.d.'}), "
                        f"EXFOR {entry_id}, {meta.get('x4_code', '')}"
                    ),
                    points=points,
                )
            )
        # Keep the most informative datasets (by point count) so the overlay
        # stays readable; the legend tells users how many were kept.
        datasets.sort(key=lambda d: -len(d.points))
        total = len(datasets)
        datasets = datasets[:MAX_DATASETS]
        message = None
        if total > MAX_DATASETS:
            message = f"Showing {MAX_DATASETS} largest of {total} EXFOR datasets"
        elif total == 0:
            message = "No experimental datasets found in EXFOR for this reaction"
        return ExforResult(nuclide, mt, total > 0, message, datasets)

    # ------------------------------------------------------------------ #
    # Disk cache                                                          #
    # ------------------------------------------------------------------ #

    def _cache_path(self, nuclide: str, mt: int) -> Path:
        return self._cache_dir / f"{nuclide}_mt{mt}.json"

    def _cache_load(self, nuclide: str, mt: int) -> ExforResult | None:
        path = self._cache_path(nuclide, mt)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
            return ExforResult(
                nuclide=raw["nuclide"],
                mt=raw["mt"],
                available=raw["available"],
                message=raw["message"],
                datasets=[
                    ExforDataset(
                        entry=d["entry"],
                        author=d["author"],
                        year=d["year"],
                        reference=d["reference"],
                        points=[ExforPoint(**p) for p in d["points"]],
                    )
                    for d in raw["datasets"]
                ],
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            path.unlink(missing_ok=True)
            return None

    def _cache_store(self, result: ExforResult) -> None:
        path = self._cache_path(result.nuclide, result.mt)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(result)))
        tmp.replace(path)


def _is_number(x) -> bool:
    if x is None:
        return False
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


_client: ExforClient | None = None


def get_exfor_client() -> ExforClient:
    global _client
    if _client is None:
        _client = ExforClient()
    return _client
