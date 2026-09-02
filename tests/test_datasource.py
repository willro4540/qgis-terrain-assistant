"""Unit tests for datasource.py — no QGIS import needed, runs with plain pytest.

Run with:
    cd qgis-terrain-assistant
    python -m pytest tests/ -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datasource import (
    BoundingBox,
    VWorldDemSource,
    DataSourceUnavailableError,
    build_vworld_request_url,
    OpenTopographyDemSource,
    build_opentopography_request_url,
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
