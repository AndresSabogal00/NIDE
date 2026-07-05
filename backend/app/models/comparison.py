"""Pydantic schemas for the comparison and derived-quantities endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegionStatsModel(BaseModel):
    library_id: str
    region: str = Field(
        description="'thermal' (<0.625 eV), 'epithermal', or 'fast' (>100 keV)"
    )
    e_min_ev: float
    e_max_ev: float
    n_points: int
    max_abs_diff_percent: float
    mean_abs_diff_percent: float
    median_abs_diff_percent: float
    energy_at_max_ev: float


class DiscrepancyModel(BaseModel):
    library_id: str
    e_min_ev: float
    e_max_ev: float
    max_abs_diff_percent: float


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
