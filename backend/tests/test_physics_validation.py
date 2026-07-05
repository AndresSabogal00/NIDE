"""Physics validation against reference values from the literature.

These tests are the project's credibility anchor: they demonstrate that the
numbers NIDE serves reproduce well-known benchmark quantities. Reference
values and their sources are documented per test; tolerance is +/-2% unless
noted, since "textbook" values are themselves evaluation-dependent at the
sub-percent level.

Reference sources
-----------------
.. [Atlas] S.F. Mughabghab, "Atlas of Neutron Resonances: Resonance
   Properties and Thermal Cross Sections Z=1-102", 6th ed., Elsevier (2018).
   Thermal (2200 m/s) cross sections and resonance integrals.
.. [ENDF8] D.A. Brown et al., Nucl. Data Sheets 148 (2018) 1-142 —
   the evaluation actually served, so agreement is expected to be tighter
   than the quoted literature tolerance.
.. [NUBASE] F.G. Kondev et al., "The NUBASE2020 evaluation of nuclear
   physics properties", Chin. Phys. C 45 (2021) 030001. Half-lives.
.. [ER] T.R. England and B.F. Rider, "Evaluation and Compilation of Fission
   Product Yields", LA-UR-94-3106 (1994). Fission yields.

Requires the ENDF/B-VIII.0 HDF5 library plus the decay/nfy sublibraries
under ``backend/data/`` (see ``scripts/download_data.py``); tests skip if
data is absent so the suite can run in a fresh checkout.
"""

from __future__ import annotations

import pytest

from app.core import derived_quantities as dq
from app.core.decay_service import get_decay_service
from app.core.fission_yields import get_fission_yield_service
from app.core.library_manager import get_library_manager
from app.core.xs_service import get_xs_service

SECONDS_PER_JULIAN_YEAR = 365.25 * 86400.0

pytestmark = pytest.mark.skipif(
    not get_library_manager().has_nuclide("endfb80", "U235"),
    reason="ENDF/B-VIII.0 HDF5 library not downloaded",
)


def thermal(nuclide: str, mt: int) -> float:
    curve = get_xs_service().get_curve("endfb80", nuclide, mt, "294K")
    value = dq.thermal_value(curve.energy_ev, curve.xs_barns)
    assert value is not None
    return value


class TestThermalCrossSections:
    """2200 m/s values vs the Atlas of Neutron Resonances [Atlas]."""

    def test_u235_thermal_fission(self):
        # Atlas: 584.3 +/- 1.0 b; ENDF/B-VIII.0 evaluates 586.7 b.
        assert thermal("U235", 18) == pytest.approx(585.0, rel=0.02)

    def test_u238_thermal_capture(self):
        # Atlas: 2.683 +/- 0.012 b.
        assert thermal("U238", 102) == pytest.approx(2.68, rel=0.02)

    def test_h1_thermal_capture(self):
        # Atlas: 0.3326 +/- 0.0007 b.
        assert thermal("H1", 102) == pytest.approx(0.332, rel=0.02)

    def test_b10_thermal_absorption(self):
        # Atlas: 3844 +/- 21 b, overwhelmingly the (n,alpha) channel.
        # MT=27 (absorption) is synthesized by openmc from stored partials.
        assert thermal("B10", 27) == pytest.approx(3840.0, rel=0.02)

    def test_pu239_thermal_fission(self):
        # Atlas: 748.1 +/- 2.0 b.
        assert thermal("Pu239", 18) == pytest.approx(748.0, rel=0.02)


class TestDerivedQuantities:
    def test_u238_capture_resonance_integral(self):
        # Atlas: I_gamma(U-238) = 275 +/- 3 b (cadmium cutoff 0.5 eV).
        curve = get_xs_service().get_curve("endfb80", "U238", 102, "294K")
        ri = dq.resonance_integral(curve.energy_ev, curve.xs_barns)
        assert ri == pytest.approx(275.0, rel=0.02)

    def test_h1_is_one_over_v(self):
        # For a pure 1/v absorber the Westcott g-factor is 1 by construction
        # (AECL-1101); H-1 capture is 1/v to high accuracy below ~1 keV.
        curve = get_xs_service().get_curve("endfb80", "H1", 102, "294K")
        _, g = dq.maxwellian_average(curve.energy_ev, curve.xs_barns, 293.6)
        assert g == pytest.approx(1.0, abs=0.01)

    def test_u235_fission_g_factor(self):
        # Westcott g(U-235 fission, 293.6 K) ~ 0.977 [Atlas]; slightly
        # evaluation-dependent, admit 1%.
        curve = get_xs_service().get_curve("endfb80", "U235", 18, "294K")
        _, g = dq.maxwellian_average(curve.energy_ev, curve.xs_barns, 293.6)
        assert g == pytest.approx(0.977, rel=0.01)

    def test_u238_fission_watt_average(self):
        # Fission-spectrum-averaged U-238 fission: ~0.31 b (fast reactor
        # one-group constant; e.g. ANL-5800 quotes 0.29-0.31 depending on
        # spectrum). Threshold reaction: thermal value is zero, spectrum
        # average is not. Wide 15% tolerance -- the quantity is very
        # sensitive to the spectrum representation.
        curve = get_xs_service().get_curve("endfb80", "U238", 18, "294K")
        watt = dq.watt_average(curve.energy_ev, curve.xs_barns)
        assert watt == pytest.approx(0.31, rel=0.15)


class TestDecayData:
    def test_co60_half_life(self):
        # NUBASE2020: T1/2(Co-60) = 5.2711 yr.
        info = get_decay_service().info("Co60")
        assert info.half_life_s is not None
        years = info.half_life_s / SECONDS_PER_JULIAN_YEAR
        assert years == pytest.approx(5.27, rel=0.02)

    def test_co60_decays_to_ni60(self):
        info = get_decay_service().info("Co60")
        assert [(m.mode, m.daughter) for m in info.modes] == [("beta-", "Ni60")]

    def test_u238_chain_reaches_pb206(self):
        # The 4n+2 (uranium) natural decay series terminates at stable
        # Pb-206 through the well-known sequence U-238 -> Th-234 ->
        # Pa-234 -> U-234 -> Th-230 -> Ra-226 -> Rn-222 -> ... -> Pb-206.
        nodes, edges = get_decay_service().chain("U238")
        names = {n.nuclide for n in nodes}
        for member in ("Th234", "U234", "Th230", "Ra226", "Rn222", "Po210", "Pb206"):
            assert member in names, f"{member} missing from U-238 chain"
        pb206 = next(n for n in nodes if n.nuclide == "Pb206")
        assert pb206.stable

    def test_u238_half_life(self):
        # NUBASE2020: 4.468e9 yr.
        info = get_decay_service().info("U238")
        assert info.half_life_s / SECONDS_PER_JULIAN_YEAR == pytest.approx(4.468e9, rel=0.02)


class TestFissionYields:
    def test_u235_thermal_cs137_cumulative(self):
        # England & Rider / ENDF/B: Y_cum(Cs-137) = 6.19% per fission.
        yields = get_fission_yield_service().yields("U235")
        cs137 = yields["cumulative"]["thermal"].by_nuclide["Cs137"]
        assert cs137 == pytest.approx(0.0619, rel=0.02)

    def test_u235_independent_yields_sum_to_two(self):
        # Two fragments per fission: independent yields sum to ~2 exactly
        # (the evaluation is normalized that way).
        yields = get_fission_yield_service().yields("U235")
        total = sum(yields["independent"]["thermal"].by_nuclide.values())
        assert total == pytest.approx(2.0, rel=0.01)

    def test_u235_double_hump(self):
        # Thermal U-235 mass-yield curve: asymmetric double hump with peaks
        # ~6-8% near A~92-100 and A~133-140, and a deep valley (<0.1%) at
        # symmetric masses A~115-117.
        by_a = get_fission_yield_service().yields("U235")["cumulative"]["thermal"].by_mass_number
        light_peak = max(v for a, v in by_a.items() if 90 <= a <= 102)
        heavy_peak = max(v for a, v in by_a.items() if 130 <= a <= 144)
        valley = min(v for a, v in by_a.items() if 113 <= a <= 118)
        assert light_peak > 0.05 and heavy_peak > 0.05
        assert valley < 0.001


class TestConsistency:
    """Internal consistency checks that don't depend on external references."""

    def test_lttb_preserves_resonance_peak(self):
        # The 6.67 eV resonance of U-238 capture peaks at ~7900 b at 294 K
        # (Doppler-broadened). Downsampling to 5000 points must keep a point
        # within 5% of the full-grid maximum in that window.
        svc = get_xs_service()
        full = svc.get_curve("endfb80", "U238", 102, "294K")
        down, _ = svc.get_curve_downsampled("endfb80", "U238", 102, "294K", 5000)

        def peak(curve):
            window = (curve.energy_ev > 6.0) & (curve.energy_ev < 7.5)
            return curve.xs_barns[window].max()

        assert peak(down) == pytest.approx(peak(full), rel=0.05)

    def test_total_equals_sum_of_parts_at_thermal(self):
        # MT=1 synthesized by openmc must equal elastic + absorption-ish sum;
        # verify total > fission + capture and total ~ elastic+18+102 for
        # U-235 at thermal within 2% (other partials are tiny there).
        total = thermal("U235", 1)
        parts = thermal("U235", 2) + thermal("U235", 18) + thermal("U235", 102)
        assert total == pytest.approx(parts, rel=0.02)
