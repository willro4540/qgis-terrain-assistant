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
import urllib.error
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


class OpenTopographyDemSource(TerrainDataSource):
    """OpenTopography Global DEM data source — the RECOMMENDED, working
    elevation data source for this plugin (replaces the dead-end
    VWorldDemSource above).

    VERIFIED 2026-09-02 (grade (a) — directly observed, not guessed):
    - Base URL, live and reachable:
      https://portal.opentopography.org/API/globaldem
    - Confirmed by sending real requests to the live endpoint (via curl)
      and reading the actual responses:
        * No API key -> HTTP 401, body:
          `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><error>Error: API Key required for access. Please register for an API key at www.opentopography.org</error>`
        * Invalid demtype -> HTTP 400, same XML `<error>...</error>` shape
          with a different message.
      So errors are XML, NOT JSON (the JSON assumption in this class's
      original task description was wrong — corrected here based on the
      actual live response, per this project's research-verification
      discipline: never guess a format when you can just check it).
    - Query parameters accepted by the live endpoint (grade (a), same
      probe): `demtype`, `south`, `north`, `west`, `east`, `outputFormat`,
      `API_Key`. A request with `south=37.0&north=38.0&west=126.0&east=127.0`
      (a Korea/Seoul-area bbox) was accepted past parameter validation
      (it reached the API-key check, rather than failing on the bbox) —
      this is direct evidence the endpoint accepts Korean coordinates.
    - `demtype=COP30` (Copernicus GLO-30, ~30m global DEM) is a valid
      dataset identifier — confirmed because using it did NOT trigger the
      "not a valid dataset" error that an invalid demtype does (grade (a)).
      `SRTMGL1` (SRTM 30m global) is documented by OpenTopography as
      another valid demtype (grade (b) — from OpenTopography's own
      developer page, not independently probed in this session).
    - Free API key signup: https://portal.opentopography.org/requestService?service=api
      (grade (b) — stated on OpenTopography's official developers page,
      https://opentopography.org/developers; signup itself was not
      completed in this session — see module note below).
    - Free-tier rate limits per OpenTopography's developers page (grade (b),
      official page, not independently re-verified by hitting the limit):
      200 calls/24h for accounts registered as academic, 50/24h otherwise.
    - Korea coverage: Copernicus GLO-30 and SRTM GL1 are near-global
      datasets (SRTM covers roughly 56°S-60°N; Copernicus GLO-30 covers a
      wider band including all of South Korea, ~33-39°N). Combined with the
      direct probe above accepting a Seoul-area bbox, Korea coverage is
      grade (b) — strongly inferable, not just assumed.
    """

    name = "opentopography_dem"
    BASE_URL = "https://portal.opentopography.org/API/globaldem"

    def __init__(self, demtype: str = "COP30"):
        self.demtype = demtype

    def fetch(self, bbox: BoundingBox, api_key: str) -> bytes:
        bbox.validate()
        if not api_key:
            raise ValueError(
                "OpenTopography requires an API key. Get a free one at "
                "https://portal.opentopography.org/requestService?service=api "
                "before calling fetch()."
            )
        url = build_opentopography_request_url(
            self.BASE_URL,
            {
                "demtype": self.demtype,
                "south": bbox.min_lat,
                "north": bbox.max_lat,
                "west": bbox.min_lon,
                "east": bbox.max_lon,
                "outputFormat": "GTiff",
                "API_Key": api_key,
            },
        )
        try:
            with urllib.request.urlopen(url) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            # urlopen raises on non-2xx rather than returning it silently.
            # OpenTopography's error body is XML (verified live, see class
            # docstring), e.g. <error>Error: ...</error> — surface it
            # directly rather than swallowing it, so a bad API key or bad
            # demtype is diagnosable from the exception message alone.
            body = exc.read().decode("utf-8", errors="replace")
            raise urllib.error.URLError(
                f"OpenTopography returned HTTP {exc.code}: {body}"
            ) from exc


def build_opentopography_request_url(base_url: str, params: dict) -> str:
    """Build an OpenTopography globaldem request URL. Pure function, no
    network I/O, directly unit-testable — mirrors build_vworld_request_url's
    pattern.
    """
    return f"{base_url}?{urllib.parse.urlencode(params)}"
