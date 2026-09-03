"""Unit tests for datasource.py — no QGIS import needed, runs with plain pytest.

Run with:
    cd qgis-terrain-assistant
    python -m pytest tests/ -v
"""

import sys
import os
import urllib.error
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datasource import (
    BoundingBox,
    VWorldDemSource,
    DataSourceUnavailableError,
    build_vworld_request_url,
    OpenTopographyDemSource,
    build_opentopography_request_url,
    SentinelHubImagerySource,
    build_sentinelhub_process_request,
    KoreaBasemapSource,
    build_xyz_layer_uri,
    probe_tile_reachable,
)


def test_bounding_box_valid():
    bbox = BoundingBox(min_lon=126.0, min_lat=37.0, max_lon=127.0, max_lat=38.0)
    bbox.validate()  # should not raise


def test_bounding_box_invalid_longitude():
    bbox = BoundingBox(min_lon=127.0, min_lat=37.0, max_lon=126.0, max_lat=38.0)
    with pytest.raises(ValueError):
        bbox.validate()


def test_bounding_box_invalid_latitude():
    bbox = BoundingBox(min_lon=126.0, min_lat=38.0, max_lon=127.0, max_lat=37.0)
    with pytest.raises(ValueError):
        bbox.validate()


def test_vworld_dem_source_raises_unavailable():
    """This is the documented, honest behavior: V-World's DEM-serving API
    (3D Data Open API) was discontinued in 2019, and its current WMS/WFS 2.0
    API has no elevation layer — see VWorldDemSource's docstring. This test
    pins that behavior so nobody accidentally "fixes" it into silently
    hitting a fake endpoint.
    """
    source = VWorldDemSource()
    bbox = BoundingBox(min_lon=126.0, min_lat=37.0, max_lon=127.0, max_lat=38.0)
    with pytest.raises(DataSourceUnavailableError):
        source.fetch(bbox, api_key="FAKE-PLACEHOLDER-KEY-NOT-REAL")


def test_build_vworld_request_url():
    url = build_vworld_request_url(
        "https://api.vworld.kr/req/wms",
        {"key": "FAKE-PLACEHOLDER-KEY-NOT-REAL", "service": "WMS"},
    )
    assert url.startswith("https://api.vworld.kr/req/wms?")
    assert "key=FAKE-PLACEHOLDER-KEY-NOT-REAL" in url
    assert "service=WMS" in url


def test_build_opentopography_request_url():
    url = build_opentopography_request_url(
        OpenTopographyDemSource.BASE_URL,
        {
            "demtype": "COP30",
            "south": 37.0,
            "north": 38.0,
            "west": 126.0,
            "east": 127.0,
            "outputFormat": "GTiff",
            "API_Key": "FAKE-PLACEHOLDER-KEY-NOT-REAL",
        },
    )
    assert url.startswith("https://portal.opentopography.org/API/globaldem?")
    assert "demtype=COP30" in url
    assert "API_Key=FAKE-PLACEHOLDER-KEY-NOT-REAL" in url
    assert "outputFormat=GTiff" in url


def test_opentopography_dem_source_requires_api_key():
    """Verified live (2026-09-02): OpenTopography's globaldem endpoint
    returns HTTP 401 with no key. Fail fast locally instead of making a
    request that's guaranteed to be rejected.
    """
    source = OpenTopographyDemSource()
    bbox = BoundingBox(min_lon=126.0, min_lat=37.0, max_lon=127.0, max_lat=38.0)
    with pytest.raises(ValueError):
        source.fetch(bbox, api_key="")


def test_opentopography_dem_source_validates_bbox_before_network():
    source = OpenTopographyDemSource()
    bad_bbox = BoundingBox(min_lon=127.0, min_lat=37.0, max_lon=126.0, max_lat=38.0)
    with pytest.raises(ValueError):
        # Should raise on bbox validation, not attempt a network call.
        source.fetch(bad_bbox, api_key="FAKE-PLACEHOLDER-KEY-NOT-REAL")


def test_build_sentinelhub_process_request():
    bbox = BoundingBox(min_lon=126.0, min_lat=37.0, max_lon=127.0, max_lat=38.0)
    body = build_sentinelhub_process_request(
        bbox=bbox,
        data_collection="S2L2A",
        time_from="2026-06-01T00:00:00Z",
        time_to="2026-06-30T00:00:00Z",
        width=512,
        height=512,
        evalscript=SentinelHubImagerySource.TRUE_COLOR_EVALSCRIPT,
    )
    assert body["input"]["bounds"]["bbox"] == [126.0, 37.0, 127.0, 38.0]
    assert body["input"]["data"][0]["type"] == "S2L2A"
    assert body["input"]["data"][0]["dataFilter"]["timeRange"] == {
        "from": "2026-06-01T00:00:00Z",
        "to": "2026-06-30T00:00:00Z",
    }
    assert body["output"]["width"] == 512
    assert body["output"]["height"] == 512
    assert body["output"]["responses"][0]["format"]["type"] == "image/tiff"
    assert "evaluatePixel" in body["evalscript"]


def test_sentinelhub_imagery_source_requires_credentials():
    """SentinelHubImagerySource needs BOTH client_id and client_secret
    (OAuth2 client-credentials) — verify the fast-fail happens before any
    network call, same discipline as
    test_opentopography_dem_source_requires_api_key.
    """
    source = SentinelHubImagerySource(client_id="", client_secret="")
    bbox = BoundingBox(min_lon=126.0, min_lat=37.0, max_lon=127.0, max_lat=38.0)
    with pytest.raises(ValueError):
        source.fetch(bbox)


def test_sentinelhub_imagery_source_validates_bbox_before_network():
    source = SentinelHubImagerySource(
        client_id="FAKE-CLIENT-ID-NOT-REAL", client_secret="FAKE-CLIENT-SECRET-NOT-REAL"
    )
    bad_bbox = BoundingBox(min_lon=127.0, min_lat=37.0, max_lon=126.0, max_lat=38.0)
    with pytest.raises(ValueError):
        # Should raise on bbox validation, not attempt a network call.
        source.fetch(bad_bbox)


def test_build_xyz_layer_uri():
    uri = build_xyz_layer_uri(
        "https://xdworld.vworld.kr/2d/Base/service/{z}/{x}/{y}.png", zmin=7, zmax=18
    )
    assert uri.startswith("type=xyz&url=")
    assert uri.endswith("&zmax=18&zmin=7")
    # {z}/{x}/{y} must survive percent-encoding intact (as %7Bz%7D etc.) —
    # QGIS's WMS provider expects the literal placeholder text encoded, not
    # substituted at URI-build time.
    assert "%7Bz%7D" in uri
    assert "%7Bx%7D" in uri
    assert "%7By%7D" in uri


def test_korea_basemap_source_vworld_styles():
    for style in ("street", "satellite", "gray"):
        uri = KoreaBasemapSource.vworld_layer_uri(style)
        assert uri.startswith("type=xyz&url=")
        assert "xdworld.vworld.kr" in uri


def test_korea_basemap_source_vworld_unknown_style():
    with pytest.raises(ValueError):
        KoreaBasemapSource.vworld_layer_uri("does_not_exist")


def test_korea_basemap_source_naver_styles():
    for style in ("street", "satellite", "terrain"):
        uri = KoreaBasemapSource.naver_layer_uri(style, version="1778232861")
        assert uri.startswith("type=xyz&url=")
        assert "map.pstatic.net" in uri
        assert "1778232861" in uri


def test_korea_basemap_source_naver_unknown_style():
    with pytest.raises(ValueError):
        KoreaBasemapSource.naver_layer_uri("does_not_exist", version="1778232861")


def test_probe_tile_reachable_true_on_http_200():
    """Mocks urlopen so this test doesn't depend on the network — the real
    live behavior (HTTP 200 for a good VWorld/Naver tile, HTTP 400 for a
    Naver tile with a bad version) was independently confirmed with real
    curl requests, 2026-09-03 (see probe_tile_reachable's docstring)."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__.return_value = mock_response
    with patch("datasource.urllib.request.urlopen", return_value=mock_response):
        assert probe_tile_reachable("https://example.com/{z}/{x}/{y}.png") is True


def test_probe_tile_reachable_false_on_http_error():
    with patch(
        "datasource.urllib.request.urlopen",
        side_effect=urllib.error.HTTPError("url", 400, "Bad Request", {}, None),
    ):
        assert probe_tile_reachable("https://example.com/{z}/{x}/{y}.png") is False


def test_probe_tile_reachable_false_on_timeout():
    with patch(
        "datasource.urllib.request.urlopen", side_effect=TimeoutError("timed out")
    ):
        assert probe_tile_reachable("https://example.com/{z}/{x}/{y}.png") is False


def test_korea_basemap_source_url_templates_have_placeholders():
    """The raw template accessors (used both for the QGIS layer URI and for
    probe_tile_reachable) must keep literal {z}/{x}/{y} — not pre-filled —
    since probe_tile_reachable() itself substitutes concrete coordinates.
    """
    vworld_template = KoreaBasemapSource.vworld_url_template("street")
    assert "{z}" in vworld_template and "{x}" in vworld_template and "{y}" in vworld_template

    naver_template = KoreaBasemapSource.naver_url_template("satellite", version="1787907321")
    assert "{z}" in naver_template and "{x}" in naver_template and "{y}" in naver_template
    assert "1787907321" in naver_template
