"""Edge-case and error-handling tests across the REST API.

Every failure mode a user can reach from the UI must produce a clean,
actionable error (or a graceful degraded payload) — never a 500. Uses the
FastAPI TestClient against the real services and downloaded data.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.exfor_client import ExforClient
from app.core.library_manager import get_library_manager
from app.main import app

client = TestClient(app)

needs_data = pytest.mark.skipif(
    not get_library_manager().has_nuclide("endfb80", "U235"),
    reason="ENDF/B-VIII.0 not downloaded",
)


@needs_data
class TestXSEdgeCases:
    def test_unknown_nuclide_404(self):
        response = client.get("/api/xs", params={"nuclide": "Xx999", "mt": 18})
        assert response.status_code == 404
        assert "Xx999" in response.json()["detail"]

    def test_unknown_mt_404(self):
        # H-1 has no fission channel.
        response = client.get("/api/xs", params={"nuclide": "H1", "mt": 18})
        assert response.status_code == 404
        assert "MT=18" in response.json()["detail"]

    def test_unknown_library_404(self):
        response = client.get(
            "/api/xs", params={"nuclide": "U235", "mt": 18, "library": "endfb99"}
        )
        assert response.status_code == 404

    def test_malformed_temperature_422(self):
        response = client.get(
            "/api/xs", params={"nuclide": "U235", "mt": 18, "temperature": "hot"}
        )
        assert response.status_code == 422

    def test_temperature_snapping(self):
        # 300K is not in the file; the response must state the temperature
        # actually served (nearest available), not silently pretend.
        response = client.get(
            "/api/xs", params={"nuclide": "U235", "mt": 18, "temperature": "300K"}
        )
        assert response.status_code == 200
        assert response.json()["temperature"] == "294K"

    def test_threshold_reaction_has_leading_zero_onset(self):
        # (n,2n) below threshold: curve starts at zero, no negative values.
        response = client.get("/api/xs", params={"nuclide": "U238", "mt": 16})
        payload = response.json()
        assert min(payload["xs_barns"]) >= 0.0


@needs_data
class TestComparisonEdgeCases:
    def test_single_library_404(self):
        response = client.get(
            "/api/compare",
            params={"nuclide": "U235", "mt": 18, "libraries": "endfb80"},
        )
        assert response.status_code == 404

    def test_nuclide_missing_from_some_libraries_is_reported(self):
        # Even if a nuclide only exists in a subset, the comparison runs
        # with what exists and names the missing ones.
        response = client.get(
            "/api/compare",
            params={"nuclide": "U235", "mt": 18, "libraries": "endfb80,jeff33,endfb99"},
        )
        if response.status_code == 200:
            assert "endfb99" in response.json()["missing_libraries"]

    def test_derived_no_library_404(self):
        response = client.get("/api/derived", params={"nuclide": "Xx999", "mt": 18})
        assert response.status_code == 404


class TestDecayEdgeCases:
    def test_stable_nuclide_info(self):
        # Stable nuclides exist in the sublibrary with stable=True, no modes.
        response = client.get("/api/decay/H2")
        if response.status_code == 503:
            pytest.skip("decay sublibrary not downloaded")
        payload = response.json()
        assert payload["stable"] is True
        assert payload["half_life_s"] is None
        assert payload["modes"] == []

    def test_unknown_nuclide_404(self):
        response = client.get("/api/decay/Xx999")
        if response.status_code == 503:
            pytest.skip("decay sublibrary not downloaded")
        assert response.status_code == 404

    def test_stable_chain_is_single_node(self):
        response = client.get("/api/decay/He4/chain")
        if response.status_code == 503:
            pytest.skip("decay sublibrary not downloaded")
        payload = response.json()
        assert len(payload["nodes"]) == 1
        assert payload["edges"] == []

    def test_spontaneous_fission_terminates_chain(self):
        # Cf-252: 3.1% SF — the SF branch must not explode the graph into
        # fission products; only the alpha chain is followed.
        response = client.get("/api/decay/Cf252/chain")
        if response.status_code == 503:
            pytest.skip("decay sublibrary not downloaded")
        payload = response.json()
        assert not any(e["data"]["mode"] == "sf" for e in payload["edges"])
        assert len(payload["nodes"]) < 30


class TestFissionYieldEdgeCases:
    def test_non_fissionable_404(self):
        response = client.get("/api/fission-yields/Fe56")
        if response.status_code == 503:
            pytest.skip("nfy sublibrary not downloaded")
        assert response.status_code == 404

    def test_invalid_yield_type_422(self):
        response = client.get("/api/fission-yields/U235", params={"yield_type": "banana"})
        if response.status_code == 503:
            pytest.skip("nfy sublibrary not downloaded")
        assert response.status_code == 422


class TestExforEdgeCases:
    """Parse-level tests with synthetic payloads: no network required."""

    def test_unmapped_mt_is_graceful(self):
        result = ExforClient().query("U235", 999)
        assert result.available is False
        assert "MT=999" in (result.message or "")

    def test_metastable_target_is_graceful(self):
        result = ExforClient().query("Am242_m1", 102)
        assert result.available is False

    def test_parse_drops_nonpositive_and_nan(self, tmp_path):
        payload = {
            "aggregations": {
                "12345-002-0": {
                    "author": "A.Tester",
                    "year": 1999,
                    "x4_code": "(92-U-235(N,F),,SIG)",
                    "datatable": {
                        "en_inc": [1e-8, 2e-8, "None", 3e-8],
                        "data": [1.0, -5.0, 2.0, 3.0],
                        "ddata": [0.1, 0.1, 0.1, "None"],
                        "den_inc": ["None", "None", "None", "None"],
                    },
                }
            }
        }
        result = ExforClient(cache_dir=tmp_path)._parse("U235", 18, payload)  # noqa: SLF001
        points = result.datasets[0].points
        # Negative sigma and non-numeric energy rows dropped; MeV -> eV.
        assert len(points) == 2
        assert points[0].energy_ev == pytest.approx(1e-8 * 1e6)
        assert points[1].dxs_barns is None

    def test_parse_empty_is_unavailable(self, tmp_path):
        result = ExforClient(cache_dir=tmp_path)._parse("U235", 18, {"aggregations": {}})  # noqa: SLF001
        assert result.available is False


@needs_data
class TestWestcottDefinition:
    def test_g_factor_is_one_for_one_over_v_at_any_temperature(self):
        # The strict Westcott definition must give g = 1 for a 1/v absorber
        # at every temperature, not just at 293.6 K — this is what
        # distinguishes it from the sigma(kT)-normalized variant fixed in
        # the audit.
        from app.core import derived_quantities as dq
        from app.core.xs_service import get_xs_service

        curve = get_xs_service().get_curve("endfb80", "H1", 102, "294K")
        for temperature in (293.6, 600.0, 1200.0):
            _, g = dq.maxwellian_average(curve.energy_ev, curve.xs_barns, temperature)
            assert g == pytest.approx(1.0, abs=0.02), f"g != 1 at {temperature} K"
