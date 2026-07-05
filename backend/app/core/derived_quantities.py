"""Standard derived quantities computed from pointwise cross sections.

These are the integral quantities nuclear physicists and reactor engineers
routinely compute by hand from sigma(E); NIDE evaluates them for every
selected library so the comparison table is automatic. All integrals are
computed with the trapezoidal rule directly on the evaluation's own union
energy grid (which NJOY linearized to within its reconstruction tolerance,
typically 0.1%, so trapezoidal integration on that grid adds no significant
error of its own).

Definitions and conventions
---------------------------
Thermal value
    sigma at E_th = 0.0253 eV, the kinetic energy of a neutron at the
    conventional thermal velocity v0 = 2200 m/s (Maxwellian most-probable
    velocity at 293.6 K). Standard reporting convention, e.g. Mughabghab's
    Atlas of Neutron Resonances.

Resonance integral
    I = integral of sigma(E) dE/E from 0.5 eV to an upper limit (20 MeV by
    default, where the 1/E tail contributes negligibly). The 0.5 eV lower
    bound is the conventional cadmium cutoff; the 1/E weighting represents
    the ideal epithermal slowing-down spectrum. Same convention as the Atlas
    and JANIS.

Maxwellian-averaged cross section (MACS-style average)
    <sigma>_Maxw(T) = (2/sqrt(pi)) * integral(sigma(E) E exp(-E/kT) dE)
                                    / integral(E exp(-E/kT) dE)
    i.e. a flux-weighted (v * n(v)) average over a Maxwell-Boltzmann spectrum
    of temperature T, normalized so that a 1/v cross section yields exactly
    its 2200 m/s value at T = 293.6 K when multiplied by sqrt(pi)/2 — we
    report the spectrum average itself (Westcott g-factor convention:
    g = <sigma>_Maxw * (2/sqrt(pi))^-1 ... see Notes in `maxwellian_average`).

Watt fission-spectrum average
    <sigma>_Watt = integral(sigma(E) chi(E) dE) / integral(chi(E) dE) with
    chi(E) ~ exp(-E/a) sinh(sqrt(b E)), a = 0.988 MeV, b = 2.249 MeV^-1: the
    ENDF/B parameters for thermal-neutron-induced fission of U-235 (ENDF-102,
    MF=5 LF=11 parametrization). This is the standard one-group "fission
    spectrum averaged" cross section.

References
----------
.. [1] S.F. Mughabghab, "Atlas of Neutron Resonances", 6th ed., Elsevier
   (2018) — definitions of thermal value and resonance integral.
.. [2] ENDF-102: "ENDF-6 Formats Manual", CSEWG, BNL-203218-2018-INRE —
   Watt spectrum parametrization (MF=5, LF=11).
.. [3] C.H. Westcott, "Effective cross section values for well-moderated
   thermal reactor spectra", AECL-1101 (1960) — Maxwellian averaging.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Conventional thermal energy: E = (1/2) m_n v0^2 with v0 = 2200 m/s.
# 0.0253 eV is the exact conventional value used by all evaluations.
THERMAL_ENERGY_EV: float = 0.0253

# Boltzmann constant in eV/K, CODATA 2018 (exact since SI 2019 redefinition):
# k = 8.617333262e-5 eV/K.
BOLTZMANN_EV_PER_K: float = 8.617333262e-5

# Watt spectrum parameters for U-235 thermal fission, ENDF/B convention
# (ENDF-102 manual): chi(E) ~ exp(-E/a) sinh(sqrt(b*E)).
WATT_A_EV: float = 0.988e6
WATT_B_PER_EV: float = 2.249e-6

# Conventional cadmium cutoff for the resonance integral (Atlas convention).
RI_LOWER_EV: float = 0.5


@dataclass
class DerivedQuantities:
    """Derived integral quantities for one (library, nuclide, MT) curve.

    All cross sections in barns; ``None`` where the quantity is undefined
    (e.g. the curve is zero over the integration range for a threshold
    reaction, making a thermal value meaningless).
    """

    thermal_xs_barns: float | None
    resonance_integral_barns: float | None
    maxwellian_avg_barns: float | None
    maxwellian_temperature_k: float
    watt_avg_barns: float | None
    westcott_g_factor: float | None


def _interp_loglog(energy: np.ndarray, xs: np.ndarray, e_query: float) -> float:
    """Log-log interpolation of sigma at one energy.

    Pointwise ENDF data is linear-linear interpolable by construction, but at
    a single query point log-log is equally valid on a dense grid and behaves
    better across decades; for the 1/v region both agree to <0.01%.
    """
    if e_query <= energy[0] or e_query >= energy[-1]:
        return float("nan")
    i = int(np.searchsorted(energy, e_query))
    e0, e1, s0, s1 = energy[i - 1], energy[i], xs[i - 1], xs[i]
    if s0 <= 0.0 or s1 <= 0.0:
        # Fall back to lin-lin near zeros (log undefined).
        return float(s0 + (s1 - s0) * (e_query - e0) / (e1 - e0))
    return float(
        np.exp(np.log(s0) + np.log(s1 / s0) * np.log(e_query / e0) / np.log(e1 / e0))
    )


def thermal_value(energy: np.ndarray, xs: np.ndarray) -> float | None:
    """sigma at the conventional thermal point 0.0253 eV (2200 m/s)."""
    value = _interp_loglog(energy, xs, THERMAL_ENERGY_EV)
    return None if np.isnan(value) else value


def resonance_integral(
    energy: np.ndarray,
    xs: np.ndarray,
    e_low: float = RI_LOWER_EV,
    e_high: float = 20.0e6,
) -> float | None:
    """Resonance integral I = int_{e_low}^{e_high} sigma(E) dE/E, in barns.

    Trapezoidal integration of sigma/E on the evaluation grid restricted to
    [e_low, e_high], with the exact bounds inserted by interpolation so the
    conventional 0.5 eV cadmium cutoff is honored regardless of grid layout.
    """
    lo = max(e_low, energy[0])
    hi = min(e_high, energy[-1])
    if hi <= lo:
        return None
    inside = (energy > lo) & (energy < hi)
    e = np.concatenate(([lo], energy[inside], [hi]))
    s = np.concatenate(
        ([_interp_loglog(energy, xs, lo)], xs[inside], [_interp_loglog(energy, xs, hi)])
    )
    s = np.nan_to_num(s, nan=0.0)
    return float(np.trapezoid(s / e, e))


def maxwellian_average(
    energy: np.ndarray,
    xs: np.ndarray,
    temperature_k: float = 293.6,
) -> tuple[float | None, float | None]:
    """Maxwellian spectrum-averaged cross section and Westcott g-factor.

    Computes the flux-weighted average over a Maxwell-Boltzmann neutron
    spectrum at temperature ``temperature_k``::

        <sigma> = int sigma(E) * E * exp(-E/kT) dE / int E * exp(-E/kT) dE

    (E * exp(-E/kT) is the Maxwellian *flux* per unit energy, i.e. v * n(E)).

    The Westcott g-factor is reported as::

        g(T) = <sigma> * (2/sqrt(pi)) / sigma(E_T),  E_T = k*T

    which equals 1 exactly for a 1/v absorber — the standard diagnostic for
    non-1/v behavior (g(U-235 fission, 293.6 K) ~ 0.977 [3]_).

    Integration runs from the grid start to 30 kT, beyond which the
    Maxwellian weight is < 1e-11 of its peak.

    Returns
    -------
    (average, g_factor)
        Both in barns / dimensionless; ``(None, None)`` if the spectrum does
        not overlap the curve's energy range (threshold reactions).
    """
    kt = BOLTZMANN_EV_PER_K * temperature_k
    hi = min(30.0 * kt, energy[-1])
    if hi <= energy[0]:
        return None, None
    inside = (energy > energy[0]) & (energy < hi)
    e = np.concatenate(([energy[0]], energy[inside], [hi]))
    s = np.concatenate(([xs[0]], xs[inside], [_interp_loglog(energy, xs, hi)]))
    s = np.nan_to_num(s, nan=0.0)
    weight = e * np.exp(-e / kt)
    numerator = np.trapezoid(s * weight, e)
    denominator = np.trapezoid(weight, e)
    if denominator <= 0.0 or numerator <= 0.0:
        return None, None
    avg = float(numerator / denominator)
    sigma_at_kt = _interp_loglog(energy, xs, kt)
    g = None
    if not np.isnan(sigma_at_kt) and sigma_at_kt > 0.0:
        # 2/sqrt(pi) converts the flux average to the Westcott convention in
        # which a 1/v absorber gives g = 1 (see AECL-1101).
        g = float(avg * 2.0 / np.sqrt(np.pi) / sigma_at_kt)
    return avg, g


def watt_average(
    energy: np.ndarray,
    xs: np.ndarray,
    a_ev: float = WATT_A_EV,
    b_per_ev: float = WATT_B_PER_EV,
) -> float | None:
    """Cross section averaged over the Watt fission spectrum, in barns.

    chi(E) ~ exp(-E/a) sinh(sqrt(b E)) with the ENDF/B parameters for
    thermal fission of U-235 (a = 0.988 MeV, b = 2.249 MeV^-1) [2]_.
    Integration range: 1 keV to 20 MeV, which captures > 99.99% of the
    spectrum (the median fission-neutron energy is ~1.7 MeV).
    """
    lo, hi = max(1.0e3, energy[0]), min(20.0e6, energy[-1])
    if hi <= lo:
        return None
    inside = (energy > lo) & (energy < hi)
    e = np.concatenate(([lo], energy[inside], [hi]))
    s = np.concatenate(
        ([_interp_loglog(energy, xs, lo)], xs[inside], [_interp_loglog(energy, xs, hi)])
    )
    s = np.nan_to_num(s, nan=0.0)
    chi = np.exp(-e / a_ev) * np.sinh(np.sqrt(b_per_ev * e))
    denominator = np.trapezoid(chi, e)
    if denominator <= 0.0:
        return None
    return float(np.trapezoid(s * chi, e) / denominator)


def compute_all(
    energy: np.ndarray,
    xs: np.ndarray,
    maxwellian_temperature_k: float = 293.6,
    ri_upper_ev: float = 20.0e6,
) -> DerivedQuantities:
    """Evaluate every derived quantity for one curve."""
    maxw, g = maxwellian_average(energy, xs, maxwellian_temperature_k)
    return DerivedQuantities(
        thermal_xs_barns=thermal_value(energy, xs),
        resonance_integral_barns=resonance_integral(energy, xs, e_high=ri_upper_ev),
        maxwellian_avg_barns=maxw,
        maxwellian_temperature_k=maxwellian_temperature_k,
        watt_avg_barns=watt_average(energy, xs),
        westcott_g_factor=g,
    )
