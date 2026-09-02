# Terrain Assistant (QGIS plugin, v0.2.0)

A QGIS plugin that refines coordinate reference systems using QGIS's own
PROJ-based reprojection, and exports a print-quality PNG map (title, scale
bar, legend) — a "산출물 you can hand to a third party" workflow.

Built following the official QGIS plugin structure documented in the
[PyQGIS Developer Cookbook — Plugins](https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/plugins/plugins.html)
and cross-checked against this repo's own [`qgis-architecture-study`](https://github.com/willro4540/qgis-architecture-study)
research (`docs/04_plugin_system_and_pyqgis.md` for the `classFactory`
convention, `docs/06_crs_coordinate_systems.md` for the CRS/PROJ approach).

## What works right now (v0.2.0)

- **DEM loading via OpenTopography** (`datasource.OpenTopographyDemSource`,
  wired into the toolbar as "Load DEM from OpenTopography…") — fetches real
  elevation data (Copernicus GLO-30 by default, ~30m resolution, global
  coverage including Korea) for the current map canvas extent, and adds it
  to the project as a raster layer. Requires a free API key (see below).
  The canvas extent is converted to the lon/lat degrees OpenTopography's
  API expects using `map_export.refine_crs` (QGIS's own PROJ transform) —
  same reprojection code path the PNG export already uses.
- **CRS refinement** (`map_export.refine_crs`) — reproject any extent
  between two EPSG codes using `QgsCoordinateTransform`, QGIS's built-in
  on-the-fly reprojection engine. No custom coordinate math.
- **PNG export** (`map_export.export_map_png`) — composes a
  `QgsPrintLayout` (map + title + scale bar + legend) from whatever layers
  are currently loaded in your QGIS project, and exports it via
  `QgsLayoutExporter`. Works with any layer source, not just OpenTopography
  DEMs.
- Toolbar/menu integration (`initGui`/`unload`), a settings dialog for
  storing an API key via `QgsSettings` (not hardcoded).

## Getting an OpenTopography API key (needed for DEM loading)

1. Sign up for a free account at https://portal.opentopography.org
2. Request an API key at https://portal.opentopography.org/requestService?service=api
3. Open this plugin's menu → "Set OpenTopography API key…" and paste it in
   — stored via `QgsSettings`, never in this repo.
4. Free-tier limits (per OpenTopography's own developer page, not
   independently load-tested): 200 requests/24h for academic accounts,
   50/24h otherwise. Each DEM area is also capped (450,000 km² for 30m
   datasets like COP30/SRTMGL1) — plenty for a single map export.

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

## Installing this plugin into QGIS

1. Copy this folder into your QGIS profile's plugin directory:
   `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\qgis-terrain-assistant\`
   (create the `plugins` folder if it doesn't exist yet — it's created the
   first time QGIS runs with a profile, and this environment hadn't run one
   yet as of writing this).
2. Restart QGIS, then enable it in **Plugins → Manage and Install
   Plugins → Installed**.
3. A "Terrain Assistant" entry appears in the Plugins menu and toolbar.

## Running the tests

```
cd qgis-terrain-assistant
python -m pip install pytest
python -m pytest tests/ -v
```

`tests/test_datasource.py` covers `datasource.py` only — it has no QGIS
import, so it runs with plain Python outside the QGIS application (verified
in this session: 8/8 pass, including the new OpenTopography URL-building
and validation tests). Note what's *not* covered: `OpenTopographyDemSource.fetch()`'s
actual network call was not executed end-to-end with a real API key in
this session (no key was obtained here) — what *was* directly verified is
the live endpoint's behavior itself (base URL, parameter names, and the
XML error format) via real `curl` requests against
`https://portal.opentopography.org/API/globaldem`, so the request-building
code is based on observed reality, not guessed docs. `map_export.py` and
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
