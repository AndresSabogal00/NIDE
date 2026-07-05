# Architecture & UX decisions — second pass

Engineering decisions taken during the second pass, with the reasoning.
Suggestions came from external (LLM-generated) feedback and were evaluated
independently against the actual state of the code, the physics-correctness
risk, and the value they add. "Accepted" means implemented in this repo.

---

## 1. Custom ENDF-6 parser to replace `openmc.data` — **REJECTED**

**Suggestion:** write an in-house ENDF-6 parser for full control over all
MF/MT sections and fewer external dependencies.

**Decision: rejected outright. No partial adoption.**

Reasoning:

1. **Correctness risk dominates.** ENDF-6 parsing is not lexing 80-column
   records — the hard parts are resonance reconstruction (MLBW, Reich–Moore,
   R-Matrix Limited), interpolation laws (INT=1–6 per region), and
   Doppler broadening. `openmc.data` (MIT/Argonne) implements these and is
   validated by an international user base running production transport
   calculations against criticality benchmarks. A subtle in-house bug (a
   wrong interpolation law, a mis-signed resonance parameter) produces
   *plausible-looking but wrong* cross sections — the worst possible failure
   mode for a tool whose entire pitch is trustworthy numbers. NIDE's 25
   physics validation tests pass against literature *through* openmc.data;
   replacing the foundation resets that evidence to zero.
2. **Effort is months, not hours.** The ENDF-102 format manual is ~400
   pages; openmc's data module is ~20k lines matured over a decade. This is
   a rewrite of the project's riskiest layer for zero user-visible gain.
3. **No coverage gap actually exists for NIDE's scope.** Everything in
   ARCHITECTURE.md is served: pointwise cross sections (processed HDF5),
   decay data (`openmc.data.Decay`, MF=8/MT=457), fission yields
   (`FissionProductYields`, MF=8/MT=454/459). The only notable thing
   openmc.data does not parse is covariance data (MF=31–40, for uncertainty
   bands) — which is outside NIDE's current scope.
4. **The "reasonable middle ground" already exists as a dependency.** Paul
   Romano's lightweight [`endf`](https://pypi.org/project/endf/) package
   (already installed transitively, v0.1.12) reads arbitrary MF/MT sections
   generically. If NIDE ever wants covariances, the path is `endf`, not a
   hand-rolled parser. Documented here so future contributors don't redo
   this evaluation.

## 2. Public Python API (`import nide`) — **ACCEPTED**

**Suggestion:** a pip-installable package exposing the existing logic as a
clean library API, independent of the web app.

**Decision: accepted and implemented** (`backend/nide/`,
`pip install -e backend`, tests in `backend/tests/test_python_api.py`).

Reasoning:

1. **Low effort, verified:** the physics lives in `app.core` services that
   are already stateless and cached; the API is a ~300-line facade adding
   only name resolution ("(n,f)" / "fission" / 18; "JEFF-3.3" / "jeff33")
   and ergonomic value objects. No physics was reimplemented, so the web
   API and Python API cannot disagree.
2. **Real platform value:** reproducible notebook analysis, scripted bulk
   comparisons, and use of NIDE's comparison engine and derived quantities
   from other tools — none of which want a running web server.

```python
from nide import NuclearLibrary, compare

u235 = NuclearLibrary("ENDF/B-VIII.0").nuclide("U235")
u235.cross_section("(n,f)").at(0.0253)        # 586.6 barns
u235.derived_quantities("capture").resonance_integral_barns

print(compare("U238", "(n,gamma)").summary)
```

**Scope limit (documented, deliberate):** the wheel currently packages both
`nide` and the backend package `app` (which `nide` wraps). That is fine for
local/git installs; before any PyPI publication the generic top-level name
`app` should be folded under `nide` — pure rename churn that isn't worth it
today.

---

## 3. Comparison-panel UX suggestions (7 items) — evaluated one by one

| # | Suggestion | Decision |
|---|---|---|
| 1 | Note that extreme max deviations often come from narrow resonances | **Accepted** — cheap, physically important context; a note is now part of the report and the max column tooltip. |
| 2 | Lead with the median, demote the max | **Accepted** — the median is the honest summary of region agreement; the max is dominated by grid-shift artifacts near sharp resonances. Summary lines and the region table now lead with the median; the max is kept as a complementary column with its energy. |
| 3 | Coverage metric (% of points above threshold) | **Accepted, adapted.** A raw *point* fraction is biased by grid density (evaluations put thousands of points inside resonances), so the implemented metric is **lethargy-weighted**: the fraction of the compared energy range — measured in ln(E), the natural spectral coordinate — where \|Δ\| exceeds the threshold. Documented in the engine docstring. |
| 4 | Threshold visually reflected in the plot | **Accepted** — above-threshold intervals are shaded on the deviation subplot (widest intervals first, capped so hundreds of one-point resonance artifacts don't smear the plot; the cap is stated in the caption). The ±threshold band was already drawn. |
| 5 | Selectable reference library | **Accepted** — the engine always supported it (first library = reference); now exposed as a UI selector and stored in the shared selection context. |
| 6 | Deviation formula stated in the UI | **Accepted** — formula line under the plot: Δ(E) = 100·(σ_lib − σ_ref)/σ_ref on the union grid, log-log interpolation. |
| 7 | "Explain discrepancies" button | **Accepted with a design change, LLM-free.** Per the no-LLM constraint this is a deterministic classifier in the engine: each above-threshold interval is classified by its lethargy width as a *narrow resonance-like spike* (< 0.1 lethargy) or a *broad systematic band*, and the report states the agreement coverage, the median per region, and the character of the largest differences. Because it is deterministic and cheap it runs on every comparison — a button adds a click for nothing, so there is no button; the explanation is always part of the report. |

None of the seven were rejected outright, but #3 and #7 were **adapted**
(lethargy weighting; always-on deterministic text instead of a button) and
#2 reframes rather than hides the max — dropping it entirely would hide real
localized disagreements, which are sometimes exactly what an evaluator is
looking for.
