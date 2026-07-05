"""Pydantic response schemas for library and cross-section endpoints.

Arrays are serialized as plain JSON lists of floats. Energies are eV, cross
sections barns — everywhere, no exceptions; the field names carry the units
so clients cannot mistake them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LibraryInfo(BaseModel):
    library_id: str = Field(
        description="NIDE identifier used in API calls, e.g. 'endfb80'"
    )
    name: str = Field(description="Evaluation name, e.g. 'ENDF/B-VIII.0'")
    version: str
    citation: str = Field(description="Official citation of the evaluation")
    doi: str
    n_nuclides: int


class ReactionEntry(BaseModel):
    mt: int = Field(description="ENDF MT reaction number (ENDF-102 Appendix B)")
    name: str = Field(description="Human-readable reaction label, e.g. '(n,gamma)'")
    redundant: bool = Field(
        description="True if synthesized by summing stored partials (ENDF sum rules)"
    )


class NuclideReactions(BaseModel):
    library_id: str
    nuclide: str
    temperatures: list[str] = Field(
        description="Available temperatures, e.g. ['250K', '294K']"
    )
    reactions: list[ReactionEntry]


class XSCurveResponse(BaseModel):
    library_id: str
    library_name: str
    nuclide: str
    mt: int
    reaction_name: str
    temperature: str = Field(
        description="Temperature actually served (nearest available)"
    )
    energy_ev: list[float]
    xs_barns: list[float]
    n_points_full: int = Field(
        description="Size of the full evaluation grid before decimation"
    )
    downsampled: bool
    citation: str
