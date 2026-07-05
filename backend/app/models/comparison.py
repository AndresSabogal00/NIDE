"""Pydantic schemas for the comparison and derived-quantities endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegionStatsModel(BaseModel):
    library_id: str
    region: str = Field(description="'thermal' (<0.625 eV), 'epithermal', or 'fast' (>100 keV)")
    e_min_ev: float
    e_max_ev: float
    n_points: int
    max_abs_diff_percent: float = Field(
        description=(
            "Complementary statistic: near sharp resonances the max is often "
            "a mesh-shift artifact of a single narrow feature, not regional disagreement"
        )
    )
    mean_abs_diff_percent: float
    median_abs_diff_percent: float = Field(
        description="Headline statistic: typical agreement across the region"
    )
    energy_at_max_ev: float
    lethargy_fraction_above: float = Field(
        description=(
            "Fraction of the region's ln(E) range where |deviation| exceeds the "
            "threshold (lethargy-weighted: immune to grid-density bias)"
        )
    )


class DiscrepancyModel(BaseModel):
    library_id: str
    e_min_ev: float
    e_max_ev: float
    max_abs_diff_percent: float
    median_abs_diff_percent: float
    lethargy_width: float = Field(description="ln(e_max/e_min) of the interval")
    character: str = Field(
        description="'narrow' (<0.1 lethargy, resonance-like spike) or 'broad' (systematic band)"
    )


class ComparisonResponse(BaseModel):
    nuclide: str
    mt: int
    reaction_name: str
    reference_library: str
    threshold_percent: float
    missing_libraries: list[str] = Field(
        description="Requested libraries that lack this nuclide/reaction"
    )
    energy_ev: list[float]
    curves: dict[str, list[float | None]] = Field(
        description="library_id -> sigma (barns) on the common grid; null outside domain"
    )
    diff_percent: dict[str, list[float | None]] = Field(
        description="library_id -> 100*(sigma/sigma_ref - 1); reference library omitted"
    )
    region_stats: list[RegionStatsModel]
    discrepancies: list[DiscrepancyModel]
    summary: list[str] = Field(description="Human-readable discrepancy report lines")
    explanation: list[str] = Field(
        description=(
            "Deterministic (rule-based, LLM-free) reading of the deviation "
            "profile: agreement coverage and narrow-spike vs broad-band character"
        )
    )
    citations: dict[str, str]


class DerivedQuantitiesModel(BaseModel):
    library_id: str
    library_name: str
    thermal_xs_barns: float | None = Field(description="sigma at 0.0253 eV (2200 m/s)")
    resonance_integral_barns: float | None = Field(
        description="I = int sigma dE/E, 0.5 eV to 20 MeV (cadmium cutoff convention)"
    )
    maxwellian_avg_barns: float | None
    maxwellian_temperature_k: float
    watt_avg_barns: float | None = Field(
        description="Averaged over Watt spectrum, U-235 thermal parameters a=0.988 MeV, b=2.249/MeV"
    )
    westcott_g_factor: float | None


class DerivedResponse(BaseModel):
    nuclide: str
    mt: int
    reaction_name: str
    temperature: str
    results: list[DerivedQuantitiesModel]
    definitions: dict[str, str] = Field(
        description="Formula/convention for each quantity, for display in the UI"
    )
