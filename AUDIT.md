# Project audit — second pass

Systematic review of physics formulas, error handling, state management,
downsampling and unit consistency. Each item lists what was checked, the
method, and the outcome — including the cases where **no problem was found**,
so the review scope is on record. Backend suite after the audit: **72 tests
passing** (25 physics-validation, 20 Python-API, 8 downsampling, 19
edge-case/error-handling).

## 1. Formula review (`derived_quantities.py`)

| Quantity | Reference | Verdict |
|---|---|---|
| Thermal value σ(0.0253 eV) | Atlas [Mughabghab 2018] | ✅ Correct. Log-log interpolation at the conventional 2200 m/s point; validated against 5 Atlas values within 2% (U-235, U-238, H-1, B-10, Pu-239). |
| Resonance integral | Atlas convention | ✅ Correct. I = ∫σ dE/E over [0.5 eV, 20 MeV], trapezoid on the evaluation grid with exact bound insertion at the Cd cutoff. Reproduces I_γ(U-238) = 275.0 b vs 275 ± 3 b. |
| Maxwellian average | Westcott, AECL-1101 | ✅ Correct. Flux weighting E·exp(−E/kT); integration to 30 kT (weight < 1e-11 of peak beyond); H-1 (pure 1/v) reproduces its 2200 m/s value exactly. |
| **Westcott g-factor** | AECL-1101 | ⚠️ **FIXED.** The implementation normalized by σ(kT), which coincides with Westcott's definition at T = 293.6 K and for 1/v absorbers, but is *not* g(T) at other temperatures for non-1/v nuclides — and the API exposes the temperature as a parameter. Replaced with the strict definition g(T) = ⟨σv⟩/(σ₀v₀) = (2/√π)·√(T/T₀)·⟨σ⟩(T)/σ₀ with σ₀ fixed at 0.0253 eV. Values at 293.6 K unchanged (g_f(U-235) = 0.979); at 600 K now gives g_f(U-235) = 0.940, consistent with Westcott tables (~0.93–0.94). New test pins g = 1 for H-1 at 293.6 / 600 / 1200 K, which only the strict definition satisfies. |
| Watt average | ENDF-102 (MF=5, LF=11) | ✅ Correct. χ ∝ exp(−E/a)·sinh(√(bE)), a = 0.988 MeV, b = 2.249 MeV⁻¹ (U-235 thermal parameters, stated in UI). Integration 1 keV–20 MeV; χ(1 keV)/χ_max < 1e-2 and falling — truncation error ≪ tolerance. ⟨σ_f(U-238)⟩ = 0.31 b matches one-group literature values. |
| Boltzmann constant | CODATA 2018 (exact, SI 2019) | ✅ 8.617333262e-5 eV/K, source cited at the definition. |

## 2. Formula review (`comparison_engine.py`)

- **Deviation / ratio**: Δ = 100·(σ_lib/σ_ref − 1) on the union grid over the
  common domain; log-log interpolation with lin-lin fallback around zeros;
  no extrapolation (NaN outside domains, serialized as null). ✅ Verified by
  synthetic tests (exact on power laws; +10% step detected at 10.0 ± 0.2%).
- **Lethargy weighting** (new): midpoint trapezoid ownership du_i =
  (ln E_{i+1} − ln E_{i−1})/2. ✅ Sums to the total ln-range by construction.
- **Union-grid thinning** (>200k points): uniform index stride. Display-only
  effect; exports and statistics still cover the full common domain. ✅
  Accepted; noted here for transparency.
- 🐛 **FIXED — region-stats/library pairing.** `RegionStats` carried no
  library id; the API route re-paired the flat stats list by *chunking it
  evenly* across libraries. With a threshold reaction (a library with no
  finite points in the thermal region skips that region), the chunks
  misalign and **statistics get attributed to the wrong library**. Fixed by
  carrying `library_id` in the engine dataclass; the fragile regrouping was
  deleted. (Found during this audit; shipped with the Block-4 commit that
  touched the same code.)

## 3. Downsampling (LTTB) — regression sweep

The first-pass fix (per-bucket extrema, M4-style) was re-verified against
additional nuclides with well-known narrow resonances, exactly as the audit
brief requested (`tests/test_downsampling.py`):

| Nuclide | Feature | Result |
|---|---|---|
| U-238 | 6.67 eV capture resonance | peak preserved within 1% |
| Au-197 | 4.9 eV capture resonance | ✅ |
| Pu-240 | 1.056 eV capture resonance | ✅ |
| Th-232 | 21.8 eV capture resonance | ✅ |
| Fe-56 | ~1.15 keV capture resonance | ✅ |
| Fe-56 | 24 keV total-XS interference *minimum* (shielding window) | ✅ dips preserved too |
| U-238 (n,2n) | threshold onset position, zero handling | ✅ finite, onset within grid spacing |

## 4. Error handling / edge cases (`tests/test_edge_cases.py`)

All reachable failure modes return clean 4xx errors or graceful degraded
payloads — never a 500. Checked: unknown nuclide / MT / library (404 with
actionable message), malformed temperature (422), temperature snapping is
*reported* (response carries the temperature actually served), single-library
comparison (404), partially-missing libraries (reported in
`missing_libraries`), stable nuclides in decay views (single-node chain, no
modes), spontaneous fission terminating chains (Cf-252 stays < 30 nodes,
no `sf` edges), non-fissionable nuclide in yields (404), invalid yield type
(422), EXFOR unmapped MT / metastable target (graceful `available=false`),
EXFOR parse of negative σ and non-numeric fields (rows dropped). **No code
changes were needed** — the handlers were already correct; the tests now pin
that behavior.

## 5. Unit consistency sweep

- **eV everywhere in the backend**: xs grids (openmc, eV native), derived
  quantities, comparison, decay energies (ENDF eV; frontend divides by 1e6
  for MeV display — checked). ✅
- **EXFOR MeV → eV**: the IAEA Data Explorer serves `en_inc` in MeV; the
  client multiplies by 1e6, unit-tested with a synthetic payload and
  cross-checked against reality (U-235 thermal-range points arrive at
  ~0.015–0.025 eV; Au-197 capture 0.6178 b at 23 keV matches the known
  MACS-region value). ✅
- **barns everywhere**: openmc (barns native), EXFOR `data` (barns,
  verified against known values), exports labeled `cross_section_barns`. ✅
- **Mass excess keV** (NUBASE native) labeled keV in UI. ✅
- **Year conventions**: backend and frontend half-life humanizers use the
  Julian year (3.15576e7 s). NUBASE2020's own year unit differs by ≤ 2e-5
  relative (tropical vs Julian) — negligible against every tolerance used
  (2%) and against NUBASE's own uncertainties. Accepted; documented here.
- 🐛 **FIXED — NUBASE limit-valued half-lives.** Values with *leading*
  comparators (`>1.9 Ey`, `<300 ns`, `~5 s`) failed the float parse (only
  trailing markers were stripped) and rendered as "unknown" in the chart.
  Now stripped on both sides; 3471/3558 ground states carry a half-life or
  stability flag.

## 6. Frontend state audit

- 🐛 **FIXED (Block 1)** — selection reset on navigation. Root cause:
  per-view URL-param defaults with no shared state. Nuclide, MT, libraries,
  temperature, EXFOR toggle, threshold and reference library now live in a
  sessionStorage-backed context with URL-param precedence. Verified with a
  headless-browser regression test (Th-227 + MT=102 survive a 4-view round
  trip).
- 🐛 **FIXED** — chart decay-mode colors: NUBASE multi-particle modes with
  leading counts (`2B-`, `2p`) fell through to "unknown"; the classifier now
  strips the count prefix.
- **Reviewed, deliberately view-local** (presentation preferences, not
  selection): fission-yield type/axis, decay-chain min-branching filter,
  chart color mode. Persisting these across views adds no continuity value
  (they are meaningless in the other views); documented as intended.

## 7. Reviewed with no findings

- `xs_service` disk cache: atomic writes (`tmp` + `replace`), corrupt-entry
  self-healing, negative-sum clipping for synthesized redundant MTs.
- Fission-yield aggregation conventions (independent = sum per A; cumulative
  = max per chain, England & Rider chain-yield convention) — re-derived and
  re-checked against A=134 (7.87%) and Cs-137 (6.19%).
- EXFOR failure handling: transient network errors are *not* cached (an
  outage cannot poison the cache).
- CSV exports: Python floats serialized with `repr` (shortest round-trip);
  the numpy-scalar `repr` bug was fixed in the first pass and is covered by
  inspection of current output.
- Decay chain builder: BFS bounded (200 nodes), missing daughters become
  terminal nodes, isomer naming (`_m1`) consistent with GNDS across
  services.
