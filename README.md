# NIDE — Nuclear Information and Data Explorer

**A free, local, open-source successor to JANIS.** Browse, visualize and
*automatically compare* evaluated nuclear data — cross sections, decay data,
fission yields — from ENDF/B-VIII.0, JEFF-3.3 and JENDL-5, with experimental
data from EXFOR overlaid on every plot. Runs entirely on your machine: no
accounts, no API keys, no cloud.

![Cross-section viewer: U-235 fission across three libraries with EXFOR overlay](docs/screenshots/xs_viewer.png)

## Why

For two decades, [JANIS](https://www.oecd-nea.org/janis/) (NEA) has been the
tool physicists reach for to look up a cross section. **Its web service is
scheduled for decommissioning in December 2026**, and the desktop version is
a Java application with no public source. NIDE is a modern replacement built
only on open, official data sources and open-source physics code:

- **Parsing & physics** — [`openmc.data`](https://docs.openmc.org/en/stable/pythonapi/data.html)
  (MIT/Argonne): community-validated ENDF-6/HDF5 parsing, resonance
  reconstruction and Doppler-broadened pointwise data.
- **Evaluated libraries** — the official HDF5 distributions from
  [openmc.org/data](https://openmc.org/data/) (NJOY-processed ENDF/B-VIII.0,
  JEFF-3.3, JENDL-5).
- **Decay & fission yields** — ENDF/B-VIII.0 sublibraries from
  [NNDC, Brookhaven](https://www.nndc.bnl.gov/endf-b8.0/).
- **Experimental data** — the [EXFOR](https://nds.iaea.org/exfor/) database
  via the IAEA Data Explorer API.
- **Nuclide properties** — [NUBASE2020](https://www-nds.iaea.org/amdc/)
  (IAEA Atomic Mass Data Center).

Everything NIDE shows is **deterministic and traceable**: every plot, table
and CSV carries the citation of the evaluation it came from. No LLMs, no
interpolation magic — just the libraries, compared honestly.

## What it does

| View | |
|---|---|
| **Chart of nuclides** | ~3 500 ground states (NUBASE2020) on canvas; color by decay mode, half-life, abundance or thermal capture σ; click through to any other view. |
| **Cross sections** | Log-log σ(E) for any nuclide/reaction/temperature, multi-library, with EXFOR experimental points (author + year + entry in the legend). Peak-preserving LTTB decimation; full grid in exports. |
| **Compare** ★ | The differentiator: union-grid log-log interpolation, point-by-point deviations vs a reference library, statistics per energy region (thermal / epithermal / fast), automatic discrepancy report ("JEFF-3.3 deviates up to 9.1% in the epithermal region…"), and a derived-quantities table. |
| **Derived quantities** ★ | Thermal (2200 m/s) value, resonance integral (0.5 eV Cd cutoff), Maxwellian average + Westcott g-factor, Watt fission-spectrum average — per library, with the formula and convention documented in code and UI. |
| **Decay chains** | Directed graph (Cytoscape) to stability on physical (N, Z) coordinates; half-lives on nodes, modes and branching ratios on edges. |
| **Fission yields** | Independent & cumulative yields (thermal / fast / 14 MeV) by A and Z — the classic double-humped curve. |
| **Export** | CSV with citation headers (library, version, access date, official reference) and publication-quality PNG with citations stamped in the footer. |

![Comparison panel: automatic discrepancy report for U-238 capture](docs/screenshots/comparison.png)
![Chart of nuclides colored by decay mode](docs/screenshots/chart.png)
![U-238 decay series to Pb-206](docs/screenshots/decay.png)
![U-235 fission yields: thermal vs fast vs 14 MeV](docs/screenshots/yields.png)

## Installation (macOS, 3 commands)

Prerequisites: Python ≥ 3.11, Node ≥ 20, Homebrew.

```sh
brew install cmake hdf5 node   # build deps for openmc (native arm64)
./setup.sh                     # venv + backend deps + frontend deps (~5 min)
./run.sh                       # first run downloads data, then starts the app
```

Then open http://localhost:5173. The first `./run.sh` downloads
ENDF/B-VIII.0 (~2 GB) plus the small decay/yield/NUBASE files in the
foreground, and JEFF-3.3 + JENDL-5 in the background — the comparison views
light up as each finishes. Everything lands in `backend/data/` (git-ignored;
~30 GB extracted for all three libraries).

> **Linux note:** replace the brew line with your package manager's `cmake`
> and `hdf5` dev packages, or install openmc from conda-forge and point the
> venv at it — everything else is identical.

## Physics validation

`pytest` runs 72 checks: 25 physics validations against reference values
from the literature (Mughabghab's *Atlas of Neutron Resonances*, NUBASE2020,
England & Rider), plus downsampling regressions on five nuclides with narrow
resonances, API edge cases, and the Python API — each documented with its
source in [`backend/tests/`](backend/tests/test_physics_validation.py).
A formula-by-formula audit against the cited references is recorded in
[`AUDIT.md`](AUDIT.md); architecture decisions in [`DECISIONS.md`](DECISIONS.md).

| Quantity | NIDE (ENDF/B-VIII.0) | Reference |
|---|---|---|
| σ_f(U-235) at 0.0253 eV | 586.6 b | 584.3 ± 1.0 b (Atlas) |
| σ_γ(U-238) at 0.0253 eV | 2.683 b | 2.683 ± 0.012 b |
| σ_γ(H-1) at 0.0253 eV | 0.3326 b | 0.3326 ± 0.0007 b |
| σ_abs(B-10) at 0.0253 eV | 3845 b | 3844 ± 21 b |
| RI_γ(U-238), Cd cutoff 0.5 eV | 275.0 b | 275 ± 3 b |
| Westcott g(U-235 fission) | 0.979 | ~0.977 |
| T½(Co-60) | 5.271 yr | 5.2711 yr (NUBASE2020) |
| U-238 chain | reaches stable Pb-206 | 4n+2 series |
| Y_cum(Cs-137), U-235 thermal | 6.19 % | 6.19 % (England & Rider) |

```sh
cd backend && .venv/bin/python -m pytest tests -q
```

## Architecture

```
backend/   FastAPI + openmc.data
  app/core/         library_manager, xs_service (LTTB cache), comparison_engine ★,
                    derived_quantities ★, decay_service, fission_yields,
                    exfor_client, nuclide_properties
  app/api/routes/   REST endpoints (Swagger at :8000/docs)
  scripts/          download_data.py (all data sources, resumable)
  tests/            physics validation
frontend/  React + Vite + Tailwind + Plotly.js + Cytoscape.js
  src/components/   NuclideChart, XSViewer, ComparisonPanel,
                    DecayChainGraph, FissionYieldsView, ExportDialog
```

Design notes are in [`ARQUITECTURA_NIDE.md`](ARQUITECTURA_NIDE.md). Key
decisions: cross-section curves are cached on disk after first extraction;
downsampling is LTTB in log-log space augmented with per-bucket extrema so
resonance peak *amplitudes* survive decimation; EXFOR responses are cached
indefinitely and the app degrades gracefully when the IAEA API is offline.

## Data citations

- **ENDF/B-VIII.0** — D.A. Brown et al., *Nucl. Data Sheets* **148** (2018) 1-142.
- **JEFF-3.3** — A.J.M. Plompen et al., *Eur. Phys. J. A* **56** (2020) 181.
- **JENDL-5** — O. Iwamoto et al., *J. Nucl. Sci. Technol.* **60** (2023) 1-60.
- **EXFOR** — N. Otuka et al., *Nucl. Data Sheets* **120** (2014) 272-276.
- **NUBASE2020** — F.G. Kondev et al., *Chin. Phys. C* **45** (2021) 030001.
- **Fission yields** — T.R. England, B.F. Rider, LA-UR-94-3106 (1994).
- **HDF5 processing** — the [OpenMC project](https://openmc.org), P.K. Romano
  et al., *Ann. Nucl. Energy* **82** (2015) 90-97.

## Python API

NIDE is also a library — no server needed:

```python
from nide import NuclearLibrary, compare

u235 = NuclearLibrary("ENDF/B-VIII.0").nuclide("U235")
u235.cross_section("(n,f)").at(0.0253)        # 586.6 barns
u235.derived_quantities("capture").resonance_integral_barns
print(compare("U238", "(n,gamma)").summary)
```

Installed by `setup.sh` (`pip install -e backend`); see `backend/nide/`.

## License

MIT. The nuclear data libraries themselves are distributed by their
respective evaluation projects under their own terms.
