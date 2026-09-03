"""Tests for mcp_server.py that run with plain pytest, no QGIS install
needed.

What this actually verifies (grade (a), directly run in this session):
- The module imports cleanly without qgis.core being installed at all —
  this confirms the design goal that refine_crs/export_map_png/
  export_3d_scene defer their `qgis`/`map_export` imports until the tool
  body actually runs, so the MCP server process doesn't hard-require a
  QGIS Python environment just to start up and register its tools.
- The five tools registered with @mcp.tool() are visible on the MCPServer
  instance with the expected names.
- load_dem and load_sentinel_imagery (the two tools with zero qgis.core
  dependency) actually run their real validation paths (calling
  datasource.OpenTopographyDemSource.fetch / SentinelHubImagerySource.fetch,
  which validate the bbox and require real credentials) using fake,
  clearly-marked placeholder values — never real ones.

What this does NOT verify (left for a real QGIS environment, same honesty
convention as tests/test_datasource.py): refine_crs/export_map_png/
export_3d_scene's actual QGIS-dependent bodies, since qgis.core is not
importable in this test environment.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import mcp_server


def test_module_imports_without_qgis():
    # If mcp_server.py imported qgis.core at module level, this test file
    # itself would already have failed to import above. Getting this far
    # is the actual assertion; this test body just makes that explicit.
    assert mcp_server.mcp is not None


def _tool_names():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    return {t.name for t in tools}


def test_all_six_tools_registered():
    names = _tool_names()
    assert names == {
        "load_dem",
        "load_sentinel_imagery",
        "load_sentinel_imagery_full_bands",
        "refine_crs",
        "export_map_png",
        "export_3d_scene",
    }


def test_load_dem_requires_api_key():
    with pytest.raises(ValueError):
        mcp_server.load_dem(
            south=37.0, north=38.0, west=126.0, east=127.0,
            api_key="",  # deliberately empty, not a real key
        )


def test_load_dem_rejects_invalid_bbox():
    with pytest.raises(ValueError):
        mcp_server.load_dem(
            south=38.0, north=37.0, west=126.0, east=127.0,  # south > north
            api_key="FAKE-PLACEHOLDER-KEY-NOT-REAL",
        )


def test_load_sentinel_imagery_requires_credentials():
    with pytest.raises(ValueError):
        mcp_server.load_sentinel_imagery(
            south=37.0, north=38.0, west=126.0, east=127.0,
            client_id="", client_secret="",  # deliberately empty, not real
        )


def test_load_sentinel_imagery_rejects_invalid_bbox():
    with pytest.raises(ValueError):
        mcp_server.load_sentinel_imagery(
            south=38.0, north=37.0, west=126.0, east=127.0,  # south > north
            client_id="FAKE-CLIENT-ID-NOT-REAL",
            client_secret="FAKE-CLIENT-SECRET-NOT-REAL",
        )


def test_load_sentinel_imagery_full_bands_requires_credentials():
    with pytest.raises(ValueError):
        mcp_server.load_sentinel_imagery_full_bands(
            south=37.0, north=38.0, west=126.0, east=127.0,
            client_id="", client_secret="",  # deliberately empty, not real
        )


def test_load_sentinel_imagery_full_bands_rejects_invalid_bbox():
    with pytest.raises(ValueError):
        mcp_server.load_sentinel_imagery_full_bands(
            south=38.0, north=37.0, west=126.0, east=127.0,  # south > north
            client_id="FAKE-CLIENT-ID-NOT-REAL",
            client_secret="FAKE-CLIENT-SECRET-NOT-REAL",
        )
