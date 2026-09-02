"""MCP server exposing this plugin's existing, already-verified functions as
tools for an MCP client (Claude Code, Claude Desktop) to call directly.

Design decision — standalone headless process, not "inside the QGIS GUI
plugin" (per this session's explicit instruction to prefer this):
this script initializes QGIS's own API headlessly via QgsApplication +
QgsApplication.initQgis(), the official PyQGIS "Standalone Scripts" pattern
(confirmed real via direct introspection of the installed QGIS 4.2.1's
`qgis.core.QgsApplication` — it exposes `initQgis()`/`exitQgis()`/
`setPrefixPath()` as static methods, grade (a)). This means Claude Code can
call these tools whether or not the QGIS desktop application happens to be
open — it does not reuse the interactive `iface`/canvas at all, only
`QgsProject`/`QgsCoordinateTransform`/`QgsPrintLayout`, none of which
require an open GUI session (verified: map_export.py's functions never
reference `iface`).

MCP SDK — verified 2026-09-02 by installing the real `mcp` PyPI package
(version 2.1.1) and introspecting it directly, NOT guessed from
documentation that may be stale for this installed version:
    from mcp.server.mcpserver import MCPServer
is the real, current import path in this installed version. Earlier MCP
SDK versions (pre-2.0) used `from mcp.server.fastmcp import FastMCP` —
that name was renamed to `MCPServer` in the 2.x line (the old import
raises `ModuleNotFoundError` with an explicit message saying so). Pin
whichever `mcp` version you actually install and keep this import in sync;
don't assume `FastMCP` still exists without checking your installed
version first.

2D vs 3D tools — kept as separate, explicit tools, not one blended tool,
per this session's explicit instruction. Every tool takes explicit
parameters from the caller (bounding box, paths, format) rather than
autonomously deciding what area/data to use, per this session's explicit
instruction ("데이터는 내가 가져오겠지만").

Running this server:
    Set QGIS_PREFIX_PATH to your QGIS install's "apps/qgis" directory
    (Windows example: "C:\\Program Files\\QGIS 4.2.1\\apps\\qgis"), make
    sure QGIS's own Python (the interpreter QGIS ships, e.g.
    "C:\\Program Files\\QGIS 4.2.1\\apps\\Python312\\python.exe") is used
    so `qgis.core`/`qgis._3d` are importable, then:
        python mcp_server.py
    This was NOT executed end-to-end in this session (no live QGIS
    environment with GPU context available here) — the tool-registration
    and parameter-handling logic below was exercised via
    tests/test_mcp_server.py instead (see that file for what was actually
    run and verified vs. what remains to be tried on a real machine).
"""

from __future__ import annotations

import os
import sys

from mcp.server.mcpserver import MCPServer

from datasource import BoundingBox, OpenTopographyDemSource, SentinelHubImagerySource

mcp = MCPServer("qgis-terrain-assistant")

_qgis_app = None  # populated by _init_qgis(), kept module-level so it isn't
                   # garbage-collected out from under a running QApplication


def _init_qgis() -> None:
    """Headless QGIS init, following the official PyQGIS Developer Cookbook
    "Standalone Scripts" pattern (QgsApplication + setPrefixPath +
    initQgis), using the real static methods confirmed on the installed
    QgsApplication class. Call once before using any qgis.core API.
    """
    global _qgis_app
    if _qgis_app is not None:
        return
    from qgis.core import QgsApplication

    prefix_path = os.environ.get("QGIS_PREFIX_PATH")
    if not prefix_path:
        raise RuntimeError(
            "Set QGIS_PREFIX_PATH to your QGIS install's 'apps/qgis' "
            "directory before running this server (see module docstring)."
        )
    _qgis_app = QgsApplication([], False)
    QgsApplication.setPrefixPath(prefix_path, True)
    QgsApplication.initQgis()


@mcp.tool()
def load_dem(
    south: float,
    north: float,
    west: float,
    east: float,
    api_key: str,
    demtype: str = "COP30",
    output_path: str = "dem_output.tif",
) -> str:
    """Fetch a DEM (elevation) GeoTIFF for the given lon/lat bounding box
    from OpenTopography's live Global DEM API and save it to output_path.

    All of south/north/west/east/demtype/output_path are explicit caller
    inputs — this tool never guesses an area of interest on its own.

    Returns the output_path on success. Raises the same exceptions
    datasource.OpenTopographyDemSource.fetch does (ValueError for a bad
    bbox/missing key, urllib.error.URLError for a live HTTP failure).
    """
    bbox = BoundingBox(min_lon=west, min_lat=south, max_lon=east, max_lat=north)
    source = OpenTopographyDemSource(demtype=demtype)
    data = source.fetch(bbox, api_key=api_key)
    with open(output_path, "wb") as f:
        f.write(data)
    return output_path


@mcp.tool()
def load_sentinel_imagery(
    south: float,
    north: float,
    west: float,
    east: float,
    client_id: str,
    client_secret: str,
    time_from: str = "2026-06-01T00:00:00Z",
    time_to: str = "2026-06-30T00:00:00Z",
    output_path: str = "sentinel_output.tif",
) -> str:
    """Fetch a Sentinel-2 L2A true-color GeoTIFF for the given lon/lat
    bounding box from Sentinel Hub's Process API and save it to
    output_path.

    All of south/north/west/east/client_id/client_secret/time_from/
    time_to/output_path are explicit caller inputs — this tool never
    guesses an area, time range, or credentials on its own.

    NOTE: unlike load_dem, this requires an OAuth client_id AND
    client_secret pair (Sentinel Hub's real auth shape — see
    datasource.SentinelHubImagerySource's docstring), and Sentinel Hub is
    NOT a permanently-free service like OpenTopography — see that same
    docstring for the honest trial/pricing caveat.

    Returns the output_path on success.
    """
    bbox = BoundingBox(min_lon=west, min_lat=south, max_lon=east, max_lat=north)
    source = SentinelHubImagerySource(client_id=client_id, client_secret=client_secret)
    data = source.fetch(bbox, time_from=time_from, time_to=time_to)
    with open(output_path, "wb") as f:
        f.write(data)
    return output_path


@mcp.tool()
def refine_crs(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    source_epsg: int,
    target_epsg: int,
) -> dict:
    """Reproject an explicit bounding box from source_epsg to target_epsg
    using QGIS's own PROJ-backed QgsCoordinateTransform (wraps
    map_export.refine_crs — same function the plugin's toolbar uses).

    Returns {"min_x", "min_y", "max_x", "max_y"} in target_epsg.
    """
    _init_qgis()
    from qgis.core import QgsRectangle
    import map_export

    extent = QgsRectangle(min_x, min_y, max_x, max_y)
    result = map_export.refine_crs(extent, source_epsg, target_epsg)
    return {
        "min_x": result.xMinimum(),
        "min_y": result.yMinimum(),
        "max_x": result.xMaximum(),
        "max_y": result.yMaximum(),
    }


@mcp.tool()
def export_map_png(
    output_path: str,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    title: str,
    dpi: int = 300,
) -> str:
    """Export a title+map+scale-bar+legend PNG for the given explicit map
    extent, from whatever layers are already loaded in the current QGIS
    project (wraps map_export.export_map_png — the 2D export tool).

    Returns output_path on success.
    """
    _init_qgis()
    from qgis.core import QgsRectangle
    import map_export

    extent = QgsRectangle(min_x, min_y, max_x, max_y)
    map_export.export_map_png(output_path, extent, title, dpi=dpi)
    return output_path


@mcp.tool()
def export_3d_scene(
    output_folder: str,
    scene_name: str,
    export_format: str = "Obj",
    terrain_resolution: int = 128,
    export_textures: bool = True,
) -> bool:
    """Export the current 3D map view's scene to a mesh file (.obj or
    .stl) — the 3D counterpart to export_map_png, kept as a SEPARATE tool
    per this session's explicit instruction.

    HONESTY NOTE (see map_export_3d.py's module docstring for the full,
    graded explanation): the export API this wraps
    (Qgs3DMapScene.exportScene/Qgs3DMapExportSettings) is real and directly
    confirmed against the installed QGIS's type stubs, but a
    Qgs3DMapCanvas is a real GPU-backed window (QtGui.QWindow subclass),
    so this could not be execution-tested end-to-end in this session (no
    live GPU-backed QGIS session was available here). Try it on a real
    QGIS installation and report back if scene setup needs adjustment —
    the exportScene/Qgs3DMapExportSettings call shape itself is the
    verified part.
    """
    _init_qgis()
    import map_export_3d

    return map_export_3d.export_3d_scene(
        output_folder, scene_name, export_format, terrain_resolution, export_textures
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
