"""Unit tests for the comparison engine on synthetic and real curves."""

from __future__ import annotations

import numpy as np
import pytest

from app.core.comparison_engine import compare, interp_loglog_grid
from app.core.library_manager import get_library_manager
from app.core.xs_service import get_xs_service


class TestInterpolation:
    def test_loglog_exact_on_power_law(self):
        # A 1/v cross section (sigma ~ E^-1/2) is exactly representable in
        # log-log, so interpolation onto any interior grid must be exact.
        energy = np.logspace(-4, 3, 50)
        xs = 10.0 * energy**-0.5
        grid = np.logspace(-3.5, 2.5, 333)
        out = interp_loglog_grid(energy, xs, grid)
        assert np.allclose(out, 10.0 * grid**-0.5, rtol=1e-12)

    def test_no_extrapolation(self):
        energy = np.array([1.0, 10.0])
        xs = np.array([5.0, 5.0])
        out = interp_loglog_grid(energy, xs, np.array([0.5, 2.0, 20.0]))
        assert np.isnan(out[0]) and out[1] == pytest.approx(5.0) and np.isnan(out[2])

    def test_zero_handling_uses_linear(self):
        # Threshold reaction: sigma = 0 below 2 eV. Log-log is undefined
        # there; the lin-lin fallback must produce finite, non-negative
        # values rather than NaN/inf.
        energy = np.array([1.0, 2.0, 4.0, 8.0])
        xs = np.array([0.0, 0.0, 2.0, 4.0])
        out = interp_loglog_grid(energy, xs, np.array([1.5, 3.0, 6.0]))
        assert out[0] == pytest.approx(0.0)
        assert out[1] == pytest.approx(1.0)  # lin-lin between 0 and 2
        assert np.isfinite(out).all()


class TestCompare:
    def test_flags_known_deviation(self):
        # Second "library" is the first scaled by +10% above 1 keV: the
        # engine must flag fast-region discrepancy of ~10% and stay quiet
        # in the thermal region.
        energy = np.logspace(-5, 7, 2000)
        xs = 3.0 * energy**-0.5
        xs2 = xs * np.where(energy > 1e3, 1.10, 1.0)
        result = compare("X1", 102, {"libA": (energy, xs), "libB": (energy, xs2)}, 5.0)
        fast = [s for s in result.region_stats if s.region == "fast"]
        thermal = [s for s in result.region_stats if s.region == "thermal"]
        assert fast[0].max_abs_diff_percent == pytest.approx(10.0, abs=0.2)
        assert thermal[0].max_abs_diff_percent < 0.01
        assert any("fast" in line for line in result.summary)
        assert any(
            d.library_id == "libB" and d.e_min_ev > 900 for d in result.discrepancies
        )

    def test_identical_curves_report_agreement(self):
        energy = np.logspace(-5, 7, 500)
        xs = np.ones_like(energy)
        result = compare("X1", 1, {"a": (energy, xs), "b": (energy, xs.copy())}, 5.0)
        assert "agree within the threshold" in result.summary[0]
        assert result.discrepancies == []

    def test_requires_two_libraries(self):
        with pytest.raises(ValueError):
            compare("X1", 1, {"a": (np.array([1.0, 2.0]), np.array([1.0, 1.0]))})


@pytest.mark.skipif(
    not (
        get_library_manager().has_nuclide("endfb80", "U235")
        and get_library_manager().has_nuclide("jeff33", "U235")
    ),
    reason="needs both ENDF/B-VIII.0 and JEFF-3.3 downloaded",
)
class TestRealLibraries:
    def test_u235_fission_endf_vs_jeff_thermal_agreement(self):
        # Independent evaluations agree on U-235 thermal fission to well
        # under 1% (both anchored to the same standards); the comparison
        # engine must reproduce that, validating grid unification and
        # interpolation on real data.
        svc = get_xs_service()
        curves = {
            lib: (c.energy_ev, c.xs_barns)
            for lib, c in (
                (lib, svc.get_curve(lib, "U235", 18, "294K"))
                for lib in ("endfb80", "jeff33")
            )
        }
        result = compare("U235", 18, curves, threshold_percent=5.0)
        thermal = [s for s in result.region_stats if s.region == "thermal"][0]
        assert thermal.median_abs_diff_percent < 1.0
