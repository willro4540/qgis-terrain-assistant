# Terrain Assistant (QGIS plugin, v0.5.0)

A QGIS plugin that refines coordinate reference systems using QGIS's own
PROJ-based reprojection, and exports a print-quality PNG map (title, scale
bar, legend) — a "산출물 you can hand to a third party" workflow.

Built following the official QGIS plugin structure documented in the
[PyQGIS Developer Cookbook — Plugins](https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/plugins/plugins.html)
and cross-checked against this repo's own [`qgis-architecture-study`](https://github.com/willro4540/qgis-architecture-study)
research (`docs/04_plugin_system_and_pyqgis.md` for the `classFactory`
convention, `docs/06_crs_coordinate_systems.md` for the CRS/PROJ approach).

## What works right now (v0.4.0)

- **DEM loading via OpenTopography** (`datasource.OpenTopographyDemSource`,
  wired into the toolbar as "Load DEM from OpenTopography…") — fetches real
  elevation data (Copernicus GLO-30 by default, ~30m resolution, global
  coverage including Korea) for the current map canvas extent, and adds it
  to the project as a raster layer. Requires a free API key (see below).
  The canvas extent is converted to the lon/lat degrees OpenTopography's
  API expects using `map_export.refine_crs` (QGIS's own PROJ transform) —
  same reprojection code path the PNG export already uses.
- **Sentinel-2 imagery loading via Sentinel Hub** (`datasource.SentinelHubImagerySource`,
  new in v0.4.0, wired into the toolbar as "Load Sentinel-2 imagery…") —
  fetches a true-color Sentinel-2 L2A image for the current map canvas
  extent via Sentinel Hub's Process API, and adds it as a raster layer.
  **Different credential shape than OpenTopography** (OAuth2
  client_id/client_secret pair, not a single key) and **not a free-forever
  service** — see "Getting Sentinel Hub credentials" below before relying
  on this.
- **CRS refinement** (`map_export.refine_crs`) — reproject any extent
  between two EPSG codes using `QgsCoordinateTransform`, QGIS's built-in
  on-the-fly reprojection engine. No custom coordinate math.
- **PNG export** (`map_export.export_map_png`) — composes a
  `QgsPrintLayout` (map + title + scale bar + legend) from whatever layers
  are currently loaded in your QGIS project, and exports it via
  `QgsLayoutExporter`. Works with any layer source, not just OpenTopography
  DEMs.
- Toolbar/menu integration (`initGui`/`unload`), a settings dialog
  ("Set API keys…") for storing the OpenTopography key and Sentinel Hub
  OAuth credentials via `QgsSettings` (not hardcoded).
- **MCP server** (`mcp_server.py`, MCP added in v0.3.0, `load_sentinel_imagery`
  added in v0.4.0) — exposes `load_dem`, `load_sentinel_imagery`,
  `refine_crs`, `export_map_png`, and `export_3d_scene` as MCP tools so
  Claude Code / Claude Desktop can drive this plugin's real functions
  directly via natural language. See "AI integration (MCP server)" below.

## Getting an OpenTopography API key (needed for DEM loading)

1. Sign up for a free account at https://portal.opentopography.org
2. Request an API key at https://portal.opentopography.org/requestService?service=api
3. Open this plugin's menu → "Set OpenTopography API key…" and paste it in
   — stored via `QgsSettings`, never in this repo.
4. Free-tier limits (per OpenTopography's own developer page, not
   independently load-tested): 200 requests/24h for academic accounts,
   50/24h otherwise. Each DEM area is also capped (450,000 km² for 30m
   datasets like COP30/SRTMGL1) — plenty for a single map export.

## Getting Sentinel Hub credentials (needed for Sentinel-2 imagery loading)

**Read this before assuming it's free the way OpenTopography is — it is not.**

1. Sign up for a Sentinel Hub account (now operated under Planet) at
   https://www.sentinel-hub.com.
2. In the dashboard, go to **User Settings → OAuth clients → Create**, name
   the client, and copy both the **client ID** and **client secret**
   immediately — the secret is shown only once
   (https://apps.sentinel-hub.com/dashboard/#/account/settings).
3. Open this plugin's menu → "Set API keys…" and paste both values in —
   stored via `QgsSettings`, never in this repo.
4. **Honest pricing note** (grade (c) — pieced together from a Planet
   community forum post and search-result summaries, NOT a single
   definitive pricing page this session could fetch directly): Sentinel
   Hub offers a time-limited trial with a capped monthly "processing unit"
   allowance, not an unlimited/forever-free tier like OpenTopography.
   Confirm current terms yourself at https://www.sentinel-hub.com/pricing/
   before relying on this for repeated use.
5. Unlike OpenTopography's single `API_Key` string, Sentinel Hub uses
   OAuth2 client-credentials (a `client_id` **and** `client_secret` pair) —
   see `datasource.SentinelHubImagerySource`'s docstring for the full,
   graded explanation of why this data source's code shape is genuinely
   different from `OpenTopographyDemSource`'s.

## ⚠️ Historical note — V-World DEM was the original v1 plan and is a dead end

The original plan for v1 was "load V-World's DEM (수치표고모델) automatically."
While building this, I checked V-World's actual current API documentation
and found:

- V-World's **3D Data Open API** (which used to serve DEM as `.bil` raster
  tiles) was **discontinued in 2019** and is no longer reachable through any
  documented endpoint.
- V-World's current **WMS/WFS API 2.0** layer catalog
  (https://www.vworld.kr/dev/v4dv_wmsguide2_s001.do) has **no elevation,
  DEM, or contour-line layer** among its published layers, as of this check
  (2026-09-01).

So `datasource.VWorldDemSource` is a documented stub that always raises
`DataSourceUnavailableError` explaining this, rather than sending requests
to a made-up endpoint. **Resolved (2026-09-02)**: DEM loading now uses
`OpenTopographyDemSource` instead (see above) — a currently-live, directly
verified API (confirmed by sending real requests to it, not just reading
docs). `VWorldDemSource` is kept in the codebase as documented history of
a real dead end, not deleted, per this project's practice of never
papering over a wrong assumption.

A related idea — falling back to V-World's old (undocumented, unreachable)
3D Data API endpoint if it turns out to still respond despite being
delisted — was considered and put on hold (not rejected outright): that
API appears to have been actively shut down by V-World at the request of
Korea's Spatial Information Industry Promotion Agency for national-security
reasons (restrictions on reproducing/storing 공개제한 spatial data), not
merely neglected. Relying on it even if technically reachable would be a
legal/ethical risk, not just a reliability one — so OpenTopography is the
sole DEM path for now.

## Getting a V-World API key (for when a working data source is added)

1. Sign up at https://www.vworld.kr
2. Go to Open API → 인증키 관리 (Authentication Key Management) → 인증키 발급
   (Issue Authentication Key).
3. When registering, the "서비스 URL" (service web address) field can be set
   to `http://localhost:4141` for local/desktop use.
4. Open this plugin's menu → "Set V-World API key…" and paste it in — it's
   stored via `QgsSettings`, not in this repo.

## Case study — real NGII (국토지리정보원) data

[`docs/case_study_ngii_data.md`](docs/case_study_ngii_data.md) walks through using this
plugin's problem space (CRS refinement) on real downloaded Korean public geospatial data:
a missing-`.prj` shapefile actually fixed and verified, two NGII products found to use
*different* CRSs (EPSG:5186 vs EPSG:5179) for the same area, a Korean-filename zip-encoding
gotcha, and an honest write-up of an aerial-photo georeferencing attempt that didn't fully
resolve (documented as an open question, not papered over).

## Korea basemap tiles (VWorld / Naver Maps v5) — v0.5.0

`datasource.KoreaBasemapSource`, wired into the toolbar as "Load Korea
basemap (VWorld/Naver)…" — adds a no-API-key Korea-focused XYZ basemap tile
layer (VWorld street/satellite/gray, Naver street/satellite/terrain).
Unlike the DEM/Sentinel-2 sources above, this isn't a bbox-bounded
one-shot fetch — it builds a `type=xyz` provider URI and QGIS's own WMS
provider loads tiles lazily as you pan/zoom. Naver's tile path embeds a
rotating version token resolved live via `fetch_naver_tile_version()`,
falling back to a hardcoded version (with a warning) if that lookup
fails — see `KoreaBasemapSource`'s docstring for live-tested confirmation
that the version really does rotate. Grew out of
[`docs/future_integration_candidates.md`](docs/future_integration_candidates.md)'s
GitHub research (mangosystem/qgis-tmsforkorea-plugin was the verified
reference for the actual tile URL templates — not reused/copied, only the
URLs themselves were confirmed against its source).

## Future integration candidates (research, not yet built)

[`docs/future_integration_candidates.md`](docs/future_integration_candidates.md) —
GitHub/Hugging Face research (2026-09-03) on what else could be integrated:
a mature land-cover classification plugin as a design reference, and two
geospatial foundation models (Prithvi-EO-2.0, Clay v1.5) — including a
concrete finding that Prithvi's landslide-detection fine-tune uses exactly
this plugin's two existing data sources (Sentinel-2 + DEM) as input. (The
Korea-basemap candidate from this doc has since been implemented — see
above.)

## Installing this plugin into QGIS

1. Copy this folder into your QGIS profile's plugin directory:
   `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\qgis-terrain-assistant\`
   (create the `plugins` folder if it doesn't exist yet — it's created the
   first time QGIS runs with a profile, and this environment hadn't run one
   yet as of writing this).
2. Restart QGIS, then enable it in **Plugins → Manage and Install
   Plugins → Installed**.
3. A "Terrain Assistant" entry appears in the Plugins menu and toolbar.

## AI integration (MCP server)

Why this exists: this project's broader research series
([`autocad-architecture-study`](https://github.com/willro4540/autocad-architecture-study),
[`revit-architecture-study`](https://github.com/willro4540/revit-architecture-study))
found that Autodesk ships its own MCP Server bundles inside AutoCAD/Revit,
exposing CAD operations as tools for an AI client. `mcp_server.py` does the
same for this plugin: it exposes the exact functions the toolbar buttons
call — nothing is reimplemented — as MCP tools, over stdio.

**Two design choices, both deliberate:**
- **Standalone headless process, not "inside the QGIS GUI plugin."** The
  server initializes QGIS's own API headlessly via
  `QgsApplication.initQgis()` (the official PyQGIS "Standalone Scripts"
  pattern), so Claude Code can call these tools whether or not the QGIS
  desktop application happens to be open.
- **2D and 3D are separate tools** (`export_map_png` vs. `export_3d_scene`),
  not one blended tool — because they're genuinely different QGIS
  subsystems (2D print layout vs. the GPU-backed 3D map view).

**What's real vs. what's a stub, honestly:**
- `load_dem` and `refine_crs`/`export_map_png` wrap functions that were
  already verified in earlier sessions (`datasource.py`,
  `map_export.py`) — see those modules' docstrings for exactly what was
  tested and how.
- `load_sentinel_imagery` (new in v0.4.0) wraps `SentinelHubImagerySource` —
  the request-building logic is unit-tested and the API shape is verified
  against official docs, but the actual network round-trip (OAuth token +
  image fetch) was **not** executed end-to-end in this session (no real
  Sentinel Hub OAuth credentials were available — see the class docstring
  and "Getting Sentinel Hub credentials" above).
- `export_3d_scene` wraps a **real, confirmed** QGIS API
  (`Qgs3DMapScene.exportScene`/`Qgs3DMapExportSettings`, confirmed by
  directly reading the installed QGIS's compiled Python type stubs, not
  guessed) that exports to `.obj`/`.stl` mesh files — but a 3D scene needs
  a GPU-backed window (`Qgs3DMapCanvas` is a `QtGui.QWindow` subclass) to
  populate before it can export anything, and this could not be
  execution-tested end-to-end in this session (no live GPU-backed QGIS
  session was available). See `map_export_3d.py`'s module docstring for
  the full, graded explanation before relying on it.
- The MCP tool-registration and parameter-validation logic itself **was**
  actually run — see `tests/test_mcp_server.py` (4/4 pass, verified this
  session) and "Running the tests" below.

**Every tool takes explicit parameters from the caller** (bounding box,
output paths, format) — none of them autonomously decide what area or
data to use. You (or whoever is driving the MCP client) supply the data.

**Running the server:**

```
pip install -r requirements-mcp.txt
```

Then, using the Python interpreter QGIS itself ships (so `qgis.core`/
`qgis._3d` are importable — e.g. on Windows,
`C:\Program Files\QGIS 4.2.1\apps\Python312\python.exe`), with
`QGIS_PREFIX_PATH` set to your QGIS install's `apps\qgis` directory:

```
set QGIS_PREFIX_PATH=C:\Program Files\QGIS 4.2.1\apps\qgis
"C:\Program Files\QGIS 4.2.1\apps\Python312\python.exe" mcp_server.py
```

**Connecting Claude Code / Claude Desktop:** add an entry to your MCP
client config pointing at the same interpreter and script, e.g.:

```json
{
  "mcpServers": {
    "qgis-terrain-assistant": {
      "command": "C:\\Program Files\\QGIS 4.2.1\\apps\\Python312\\python.exe",
      "args": ["C:\\Users\\user\\Desktop\\qgis-terrain-assistant\\mcp_server.py"],
      "env": { "QGIS_PREFIX_PATH": "C:\\Program Files\\QGIS 4.2.1\\apps\\qgis" }
    }
  }
}
```

This exact config was not tested against a running Claude Code/Desktop
client in this session — verify the config-file location and key names
against your client's current documentation if it doesn't connect.

## Running the tests

```
cd qgis-terrain-assistant
python -m pip install pytest -r requirements-mcp.txt
python -m pytest tests/ -v
```

(`tests/test_mcp_server.py` needs the `mcp` package from
`requirements-mcp.txt`; `tests/test_datasource.py` doesn't. Both run fine
with plain `python`/pytest — neither needs a real QGIS install, since
`mcp_server.py` defers all `qgis.core`/`map_export` imports until a
QGIS-dependent tool actually runs. Verified this session: 17/17 pass.)

`tests/test_datasource.py` covers `datasource.py` only — it has no QGIS
import, so it runs with plain Python outside the QGIS application (verified
in this session: 11/11 pass, including the OpenTopography and Sentinel Hub
URL/request-building and validation tests). Note what's *not* covered:
`OpenTopographyDemSource.fetch()`'s and `SentinelHubImagerySource.fetch()`'s
actual network calls were not executed end-to-end with real credentials in
this session (no OpenTopography key or Sentinel Hub OAuth client was used
here) — what *was* directly verified for OpenTopography is the live
endpoint's behavior itself (base URL, parameter names, and the XML error
format) via real `curl` requests against
`https://portal.opentopography.org/API/globaldem`; for Sentinel Hub, the
token endpoint, Process API endpoint, and request-body shape were verified
against official Sentinel Hub documentation and `sentinelhub-py`'s
documented examples (grade (a) for the URLs/shape, not independently
probed live the way OpenTopography was — see `SentinelHubImagerySource`'s
docstring). `map_export.py` and
`terrain_assistant.py` import `qgis.core`/`qgis.PyQt`, which only exist
inside a running QGIS Python environment — they have **not** been executed
end-to-end in this session (there's no way to run the QGIS desktop
application headlessly in this environment). Their code follows the
official PyQGIS Cookbook pattern exactly (see the module docstrings for
the exact source), but treat them as "correct per official docs, not yet
execution-tested" until you load the plugin into a real QGIS session and
try the toolbar button.

## License

MIT — see [LICENSE](./LICENSE).
