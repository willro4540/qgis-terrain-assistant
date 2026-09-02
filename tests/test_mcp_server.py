"""Tests for mcp_server.py that run with plain pytest, no QGIS install
needed.

What this actually verifies (grade (a), directly run in this session):
- The module imports cleanly without qgis.core being installed at all —
  this confirms the design goal that refine_crs/export_map_png/
  export_3d_scene defer their `qgis`/`map_export` imports until the tool
  body actually runs, so the MCP server process doesn't hard-require a
  QGIS Python environment just to start up and register its tools.
- The three tools registered with @mcp.tool() are visible on the MCPServer
  instance with the expected names.
- load_dem (the one tool with zero qgis.core dependency) actually runs its
  real validation path (calls datasource.OpenTopographyDemSource.fetch,
  which validates the bbox and requires an api_key) using a fake,
  clearly-marked placeholder key — never a real one.

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


def test_all_four_tools_registered():
    names = _tool_names()
    assert names == {"load_dem", "refine_crs", "export_map_png", "export_3d_scene"}


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
