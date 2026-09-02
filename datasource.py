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


class SentinelHubImagerySource(TerrainDataSource):
    """Sentinel Hub satellite-imagery data source (Sentinel-2 L2A).

    DESIGN NOTE — why this does NOT reuse the plain `fetch(bbox, api_key)`
    shape the way VWorldDemSource/OpenTopographyDemSource do (documented
    per this project's research-verification discipline, not left silent):
    Sentinel Hub authentication is genuinely different, not just a second
    string. Verified (grade (a), official docs,
    https://docs.sentinel-hub.com/api/latest/api/overview/authentication/,
    fetched 2026-09-02): it is OAuth2 client-credentials, requiring a
    `client_id` **and** `client_secret` pair (registered as an "OAuth
    client" in the account dashboard — NOT a single copy-pasteable API
    key like OpenTopography's `API_Key` or V-World's 인증키). So credentials
    are supplied once at construction time (like a `requests.Session`)
    rather than forced into the single `api_key` positional argument the
    simpler single-key sources use. `fetch()` still accepts an `api_key`
    parameter for `TerrainDataSource` interface compatibility, but ignores
    it — see the parameter's own docstring note below.

    VERIFIED 2026-09-02 (grade (a) unless noted otherwise):
    - OAuth2 token endpoint:
      https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token
      (official docs). This project does not cache the token beyond a
      single `fetch()` call; Sentinel Hub's own docs warn "do not fetch a
      new token for each API request" for high-volume use — grade (a),
      worth revisiting if this source is called in a tight loop, but out
      of scope for this plugin's one-map-export-at-a-time usage pattern.
    - Process API endpoint: `POST https://services.sentinel-hub.com/api/v1/process`
      (official docs + sentinelhub-py's own documented example — cross-checked
      across two official/semi-official sources, grade (a)).
    - Request body shape (grade (a), from the same sources): a JSON object
      with `input.bounds.bbox` ([min_lon, min_lat, max_lon, max_lat]),
      `input.data[0].type` (e.g. `"S2L2A"` for Sentinel-2 L2A),
      `input.data[0].dataFilter.timeRange` ({"from", "to"}, ISO 8601),
      `output.width`/`output.height`, `output.responses[0].format.type`
      (e.g. `"image/tiff"`), and a top-level `evalscript` string that
      selects/combines bands (a true-color RGB evalscript using bands
      B04/B03/B02 is the documented minimal example).
    - Free-tier reality — **honest, not glossed over**: unlike
      OpenTopography's permanently-free API-key tier, Sentinel Hub is a
      commercial/subscription service (now under Planet's Sentinel Hub
      product). Search results (grade (c) — a Planet community forum post
      and search-result summaries, NOT a single definitive pricing page
      that could be fetched directly in this session) describe a
      time-limited trial with a **limited monthly "processing unit"**
      allowance, not an unlimited/forever-free tier — do not tell the user
      this is "free" the way OpenTopography is. Confirm current trial
      terms directly at https://www.sentinel-hub.com/pricing/ before
      relying on it (this session could not fetch that page's live content
      — it redirected without rendering pricing details).
    - Korea coverage: Sentinel-2 is a global-coverage ESA mission; not
      independently re-probed with a live request in this session (no
      OAuth credentials were available to test with — see module note),
      so Korea coverage here is grade (b) (general mission knowledge) not
      (a), unlike OpenTopography's directly-probed Korea bbox.

    NOT execution-tested end-to-end in this session: obtaining this
    requires creating a real Sentinel Hub account and registering an
    OAuth client (a multi-step signup, not a same-session self-service
    form) — not attempted, not fabricated. The request-building logic
    below (`build_sentinelhub_process_request`) is unit-tested without
    network I/O; the actual token-fetch and image-fetch network calls
    follow the documented shape above but have not been run against the
    live API with real credentials.
    """

    name = "sentinelhub_imagery"
    TOKEN_URL = "https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token"
    PROCESS_URL = "https://services.sentinel-hub.com/api/v1/process"

    #: Minimal true-color (RGB from B04/B03/B02) evalscript — the documented
    #: minimal example from Sentinel Hub's own Process API examples.
    TRUE_COLOR_EVALSCRIPT = (
        "//VERSION=3\n"
        "function setup() {\n"
        "  return {\n"
        "    input: [\"B02\", \"B03\", \"B04\"],\n"
        "    output: { bands: 3 }\n"
        "  }\n"
        "}\n"
        "function evaluatePixel(sample) {\n"
        "  return [sample.B04, sample.B03, sample.B02];\n"
        "}"
    )

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        data_collection: str = "S2L2A",
        evalscript: str = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.data_collection = data_collection
        self.evalscript = evalscript or self.TRUE_COLOR_EVALSCRIPT

    def _fetch_oauth_token(self) -> str:
        """Real OAuth2 client-credentials token request. Not unit-tested
        without real credentials (see class docstring) — kept as its own
        method so it's the only part of this class that needs a live
        network call and real secrets, everything else is pure/testable.
        """
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Sentinel Hub requires both a client_id and client_secret "
                "(OAuth2 client-credentials) — register a free OAuth client "
                "at https://apps.sentinel-hub.com/dashboard/#/account/settings "
                "before calling fetch()."
            )
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                token_response = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise urllib.error.URLError(
                f"Sentinel Hub OAuth token request failed with HTTP {exc.code}: "
                f"{exc.read().decode('utf-8', errors='replace')}"
            ) from exc
        return token_response["access_token"]

    def fetch(
        self,
        bbox: BoundingBox,
        api_key: str = "",
        time_from: str = "2026-06-01T00:00:00Z",
        time_to: str = "2026-06-30T00:00:00Z",
        width: int = 512,
        height: int = 512,
    ) -> bytes:
        """Fetch a Sentinel-2 L2A true-color image for bbox.

        `api_key` is accepted (unused) for TerrainDataSource interface
        compatibility only — real credentials are `self.client_id`/
        `self.client_secret`, supplied at construction time (see class
        docstring for why OAuth2 doesn't fit the single-string-key shape).
        """
        bbox.validate()
        request_body = build_sentinelhub_process_request(
            bbox=bbox,
            data_collection=self.data_collection,
            time_from=time_from,
            time_to=time_to,
            width=width,
            height=height,
            evalscript=self.evalscript,
        )
        token = self._fetch_oauth_token()
        request = urllib.request.Request(
            self.PROCESS_URL,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise urllib.error.URLError(
                f"Sentinel Hub Process API returned HTTP {exc.code}: "
                f"{exc.read().decode('utf-8', errors='replace')}"
            ) from exc


def build_sentinelhub_process_request(
    bbox: BoundingBox,
    data_collection: str,
    time_from: str,
    time_to: str,
    width: int,
    height: int,
    evalscript: str,
) -> dict:
    """Build a Sentinel Hub Process API request body (a plain dict, ready
    for json.dumps). Pure function, no network I/O, directly unit-testable
    — mirrors this module's build_vworld_request_url/
    build_opentopography_request_url pattern, adapted to a JSON-body API
    rather than a query-string one.
    """
    return {
        "input": {
            "bounds": {
                "bbox": [bbox.min_lon, bbox.min_lat, bbox.max_lon, bbox.max_lat],
                "properties": {"crs": "http://www.opengis.net/gml/srs/epsg.xml#4326"},
            },
            "data": [
                {
                    "type": data_collection,
                    "dataFilter": {
                        "timeRange": {"from": time_from, "to": time_to},
                        "mosaickingOrder": "leastCC",
                    },
                }
            ],
        },
        "output": {
            "width": width,
            "height": height,
            "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}],
        },
        "evalscript": evalscript,
    }
