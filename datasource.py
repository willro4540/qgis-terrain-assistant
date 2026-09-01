"""Pluggable terrain/elevation data-source layer.

Design: every concrete source implements TerrainDataSource so the plugin's
UI and export pipeline never need to know which provider is behind them.
This lets a v2 data source (e.g. Sentinel imagery, a different elevation
provider) be added later without touching the UI or export code.

This module contains NO QGIS imports, so it can be unit-tested with plain
pytest outside the QGIS application (see tests/test_datasource.py).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass
class BoundingBox:
    """A geographic bounding box in EPSG:4326 (lon/lat) degrees."""
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def validate(self) -> None:
        if not (-180 <= self.min_lon < self.max_lon <= 180):
            raise ValueError(f"invalid longitude range: {self.min_lon}..{self.max_lon}")
        if not (-90 <= self.min_lat < self.max_lat <= 90):
            raise ValueError(f"invalid latitude range: {self.min_lat}..{self.max_lat}")


class DataSourceUnavailableError(RuntimeError):
    """Raised when a data source cannot serve the requested data at all
    (as opposed to a transient network failure) — e.g. because the
    underlying API has been discontinued by its provider.
    """


class TerrainDataSource:
    """Abstract interface every concrete terrain data source implements."""

    name: str = "unknown"

    def fetch(self, bbox: BoundingBox, api_key: str) -> bytes:
        """Return raw response bytes for the given bounding box.

        Raises:
            ValueError: bbox is invalid.
            DataSourceUnavailableError: this source cannot serve this kind
                of data at all (see subclass docstrings for why).
            urllib.error.URLError: network/HTTP failure.
        """
        raise NotImplementedError


class VWorldDemSource(TerrainDataSource):
    """V-World DEM (수치표고모델) data source.

    KNOWN LIMITATION (verified 2026-09-01, not guessed):
    V-World's dedicated "3D Data Open API" — the API that used to serve DEM
    as .bil raster tiles — was discontinued by V-World in 2019. Independently
    re-checked V-World's current "WMS/WFS API 2.0" layer catalog
    (https://www.vworld.kr/dev/v4dv_wmsguide2_s001.do) and confirmed there is
    no elevation/DEM/contour-line layer among its published layers as of this
    check. There is currently no verified, working V-World endpoint that
    serves DEM data through the public Open API.

    This class therefore always raises DataSourceUnavailableError rather than
    sending a request to a made-up endpoint. Do not "fix" this by guessing an
    endpoint — if V-World later reintroduces elevation data, or the user
    decides on a different real elevation provider (e.g. a global open DEM
    such as Copernicus GLO-30 / OpenTopography, or Korea's National
    Geographic Information Institute's own distribution channel), implement
    a new TerrainDataSource subclass against that provider's actual,
    currently-documented API instead.
    """

    name = "vworld_dem"

    def fetch(self, bbox: BoundingBox, api_key: str) -> bytes:
        bbox.validate()
        raise DataSourceUnavailableError(
            "V-World's 3D Data Open API (which served DEM as .bil tiles) was "
            "discontinued in 2019, and V-World's current WMS/WFS 2.0 API has "
            "no elevation/DEM layer. See this class's docstring for sources "
            "checked. Pick a different, currently-live elevation data "
            "provider before using this feature."
        )


def build_vworld_request_url(base_url: str, params: dict) -> str:
    """Build a V-World-style request URL. Kept as a standalone, pure
    function (no network I/O) so it's directly unit-testable — used by
    any future V-World-backed source (e.g. the background-map WMS, which
    IS still live, unlike the DEM API above).
    """
    return f"{base_url}?{urllib.parse.urlencode(params)}"
