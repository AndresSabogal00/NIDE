"""Tests for the public Python API (`import nide`).

The API is a facade over the validated service layer, so these tests focus
on the facade's own responsibilities: name resolution, value-object
plumbing, and agreement with the underlying services — not re-validating
the physics (that is test_physics_validation.py's job).
"""

from __future__ import annotations

import pytest

from app.core.library_manager import get_library_manager
from nide import NuclearLibrary, available_libraries, compare, resolve_mt

needs_data = pytest.mark.skipif(
    not get_library_manager().has_nuclide("endfb80", "U235"),
    reason="ENDF/B-VIII.0 not downloaded",
)


class TestResolveMt:
    @pytest.mark.parametrize(
        ("reaction", "mt"),
        [
            (18, 18),
            ("(n,fission)", 18),
            ("(n,f)", 18),
            ("n,f", 18),
            ("fission", 18),
            ("(n,gamma)", 102),
            ("n,g", 102),
            ("capture", 102),
            ("elastic", 2),
            ("total", 1),
            ("(n,2n)", 16),
            ("absorption", 27),
        ],
    )
    def test_resolves(self, reaction, mt):
        assert resolve_mt(reaction) == mt

    def test_unknown_reaction_raises(self):
        with pytest.raises(ValueError, match="Unknown reaction"):
            resolve_mt("n,unicorn")


class TestLibraryResolution:
    def test_names_and_ids(self):
        assert NuclearLibrary("ENDF/B-VIII.0").name == "ENDF/B-VIII.0"
        assert NuclearLibrary("endfb80").name == "ENDF/B-VIII.0"
        assert NuclearLibrary("jeff-3.3").name == "JEFF-3.3"
        assert NuclearLibrary("JENDL5").name == "JENDL-5"

    def test_unknown_library_raises(self):
        with pytest.raises(ValueError, match="Unknown library"):
            NuclearLibrary("ENDF/B-IX")


@needs_data
class TestEndToEnd:
    def test_readme_example(self):
        u235 = NuclearLibrary("ENDF/B-VIII.0").nuclide("U235")
        xs = u235.cross_section("(n,f)")
        # Same number the physics suite validates against the Atlas.
        assert xs.at(0.0253) == pytest.approx(585.0, rel=0.02)
        assert xs.citation.startswith("D.A. Brown")
        assert xs.temperature == "294K"
        assert 18 in u235.reactions

    def test_derived_quantities_match_service(self):
        u238 = NuclearLibrary("endfb80").nuclide("U238")
        quantities = u238.derived_quantities("capture")
        assert quantities.resonance_integral_barns == pytest.approx(275.0, rel=0.02)

    def test_unknown_nuclide_raises(self):
        with pytest.raises(KeyError):
            NuclearLibrary("endfb80").nuclide("Unobtainium300")

    def test_available_libraries_nonempty(self):
        assert "ENDF/B-VIII.0" in available_libraries()

    def test_compare_two_libraries(self):
        if not get_library_manager().has_nuclide("jeff33", "U235"):
            pytest.skip("JEFF-3.3 not downloaded")
        result = compare("U235", "fission", ["ENDF/B-VIII.0", "JEFF-3.3"])
        assert result.reference_library == "endfb80"
        assert "jeff33" in result.curves
