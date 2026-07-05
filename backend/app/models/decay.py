"""Pydantic schemas for decay data, decay chains and fission yields."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DecayModeModel(BaseModel):
    mode: str = Field(description="ENSDF-style mode: 'beta-', 'alpha', 'ec/beta+', 'it', 'sf'")
    daughter: str | None
    branching_ratio: float
    branching_ratio_uncertainty: float


class DecayInfoModel(BaseModel):
    nuclide: str
    z: int
    a: int
    isomeric_state: int
    stable: bool
    half_life_s: float | None
    half_life_uncertainty_s: float | None
    half_life_human: str | None = Field(description="e.g. '5.27 yr', '2.3 ms'")
    decay_energy_ev: float | None = Field(
        description="Mean total energy released per decay (ENDF MF=8 MT=457)"
    )
    modes: list[DecayModeModel]
    source: str = Field(default="ENDF/B-VIII.0 decay sublibrary (from ENSDF)")


class CytoscapeNode(BaseModel):
    data: dict


class CytoscapeEdge(BaseModel):
    data: dict


class DecayChainResponse(BaseModel):
    """Directed decay graph in Cytoscape.js elements format.

    Node ``data``: id (GNDS name), z, a, stable, half_life_s,
    half_life_human. Edge ``data``: source, target, mode, branching_ratio.
    """

    start: str
    nodes: list[CytoscapeNode]
    edges: list[CytoscapeEdge]
    source: str = Field(default="ENDF/B-VIII.0 decay sublibrary (from ENSDF)")


class YieldSetModel(BaseModel):
    energy_ev: float
    energy_label: str = Field(description="'thermal' (0.0253 eV), 'fast' (~500 keV), '14MeV'")
    by_mass_number: dict[int, float] = Field(
        description=(
            "Mass-chain yields: sum of independent yields per A, or max of "
            "cumulative yields per A (England & Rider chain-yield convention)"
        )
    )
    by_atomic_number: dict[int, float]
    top_products: list[tuple[str, float]] = Field(
        description="20 highest-yield products (nuclide, yield/fission)"
    )


class FissionYieldResponse(BaseModel):
    nuclide: str
    yield_type: str = Field(description="'independent' or 'cumulative'")
    sets: list[YieldSetModel]
    source: str = Field(default="ENDF/B-VIII.0 nfy sublibrary (England & Rider evaluation)")
