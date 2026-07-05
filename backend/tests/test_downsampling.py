"""Regression tests for resonance-peak preservation in LTTB downsampling.

The first LTTB implementation (pure Steinarsson) picked a shoulder point of
the 6.67 eV U-238 resonance, underestimating the displayed peak by 14%. The
fix augments LTTB with per-bucket extrema (M4-style), which preserves peak
amplitudes exactly at the grid level. These tests pin that guarantee across
several nuclides with well-known narrow resonances, so any future change to
the downsampler that silently clips peaks fails loudly.

Reference resonances (energies from the Atlas of Neutron Resonances):
U-238 6.67 eV (capture), Au-197 4.9 eV (capture), Pu-240 1.056 eV (capture),
Th-232 21.8 eV (capture), Fe-56 1.15 keV (capture).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.library_manager import get_library_manager
from app.core.xs_service import get_xs_service, lttb_downsample

pytestmark = pytest.mark.skipif(
    not get_library_manager().has_nuclide("endfb80", "U238"),
    reason="ENDF/B-VIII.0 not downloaded",
)

# (nuclide, MT, window around a narrow resonance, eV)
RESONANCES = [
    ("U238", 102, 6.0, 7.5),
    ("Au197", 102, 4.0, 6.0),
    ("Pu240", 102, 0.8, 1.3),
    ("Th232", 102, 20.0, 24.0),
    ("Fe56", 102, 1.0e3, 1.3e3),
]


@pytest.mark.parametrize(("nuclide", "mt", "e_lo", "e_hi"), RESONANCES)
def test_peak_amplitude_survives_downsampling(nuclide, mt, e_lo, e_hi):
    service = get_xs_service()
    full = service.get_curve("endfb80", nuclide, mt, "294K")
    down, n_full = service.get_curve_downsampled("endfb80", nuclide, mt, "294K", 5000)
    assert len(down.energy_ev) < n_full, "downsampling did not reduce the grid"

    def window_max(curve):
        window = (curve.energy_ev >= e_lo) & (curve.energy_ev <= e_hi)
        assert window.any(), f"no points in [{e_lo}, {e_hi}] eV window"
        return float(curve.xs_barns[window].max())

    # Per-bucket max selection keeps the exact grid maximum: the peak point
    # of the window is the maximum of its bucket unless an even higher point
    # shares the bucket — which would itself be in the window for windows
    # spanning many buckets. Allow 1% for the corner case of a window edge
    # splitting a bucket.
    assert window_max(down) == pytest.approx(window_max(full), rel=0.01)


def test_valley_minima_survive_downsampling():
    # Interference dips matter as much as peaks (e.g. shielding windows).
    # Check the deep flux window of Fe-56 total XS near 24 keV.
    service = get_xs_service()
    full = service.get_curve("endfb80", "Fe56", 1, "294K")
    down, _ = service.get_curve_downsampled("endfb80", "Fe56", 1, "294K", 5000)
    window_full = (full.energy_ev >= 2.0e4) & (full.energy_ev <= 3.0e4)
    window_down = (down.energy_ev >= 2.0e4) & (down.energy_ev <= 3.0e4)
    assert down.xs_barns[window_down].min() == pytest.approx(
        float(full.xs_barns[window_full].min()), rel=0.01
    )


def test_lttb_handles_threshold_reaction_zeros():
    # U-238 (n,2n) is zero below ~6.1 MeV: the downsampler must not emit
    # NaN/inf and must keep the onset anchored at the threshold.
    service = get_xs_service()
    full = service.get_curve("endfb80", "U238", 16, "294K")
    idx = lttb_downsample(full.energy_ev, full.xs_barns, 500)
    xs = full.xs_barns[idx]
    assert np.isfinite(xs).all()
    first_positive_full = full.energy_ev[np.argmax(full.xs_barns > 0)]
    first_positive_down = full.energy_ev[idx][np.argmax(xs > 0)]
    # Onset must not shift by more than the local grid spacing (~1%).
    assert first_positive_down == pytest.approx(float(first_positive_full), rel=0.02)
