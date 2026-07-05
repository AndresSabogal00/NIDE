"""Application configuration.

All paths are resolved relative to the ``backend/`` directory so the app can
be launched from anywhere (``uvicorn app.main:app`` from ``backend/``, pytest
from the repo root, etc.).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Runtime settings, overridable via environment variables (``NIDE_`` prefix)."""

    data_dir: Path = BACKEND_DIR / "data"
    cache_dir: Path = BACKEND_DIR / "cache"

    # Maximum number of IncidentNeutron objects kept in memory. Each holds the
    # full resonance-reconstructed pointwise data for one nuclide (tens of MB
    # for heavy actinides), so this bounds memory to a few hundred MB.
    nuclide_cache_size: int = 24

    # Default number of points returned to the plotting frontend. ~5000 points
    # keeps Plotly interactive while the LTTB selection preserves resonance
    # peaks (see xs_service.lttb_downsample).
    default_max_points: int = 5000

    model_config = {"env_prefix": "NIDE_"}


settings = Settings()
