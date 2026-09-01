# Terrain Assistant (QGIS plugin, v0.1.0)

A QGIS plugin that refines coordinate reference systems using QGIS's own
PROJ-based reprojection, and exports a print-quality PNG map (title, scale
bar, legend) — a "산출물 you can hand to a third party" workflow.

Built following the official QGIS plugin structure documented in the
[PyQGIS Developer Cookbook — Plugins](https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/plugins/plugins.html)
and cross-checked against this repo's own [`qgis-architecture-study`](https://github.com/willro4540/qgis-architecture-study)
research (`docs/04_plugin_system_and_pyqgis.md` for the `classFactory`
convention, `docs/06_crs_coordinate_systems.md` for the CRS/PROJ approach).

## What works right now (v0.1.0)

- **CRS refinement** (`map_export.refine_crs`) — reproject any extent
  between two EPSG codes using `QgsCoordinateTransform`, QGIS's built-in
  on-the-fly reprojection engine. No custom coordinate math.
- **PNG export** (`map_export.export_map_png`) — composes a
  `QgsPrintLayout` (map + title + scale bar + legend) from whatever layers
  are currently loaded in your QGIS project, and exports it via
  `QgsLayoutExporter`. Works with any layer source — you don't need a
  V-World API key to use this part.
- Toolbar/menu integration (`initGui`/`unload`), a settings dialog for
  storing an API key via `QgsSettings` (not hardcoded).

## ⚠️ Known limitation — V-World DEM is NOT implemented (and can't be, right now)

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
to a made-up endpoint. **This needs a decision before v1's "load terrain
data automatically" feature can actually work**: either V-World adds
elevation data back, or a different, currently-live elevation provider is
picked (candidates worth checking: a global open DEM like Copernicus
GLO-30 / OpenTopography, or Korea's National Geographic Information
Institute's own distribution channel for DEM data — neither has been
verified yet, don't assume either works without checking first).

Until then, use the plugin by loading any terrain/raster layer into QGIS
yourself (e.g. a DEM file you already have, or any other layer) — the CRS
refinement and PNG export both work on whatever is loaded, independent of
where it came from.

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
in this session: 5/5 pass). `map_export.py` and `terrain_assistant.py`
import `qgis.core`/`qgis.PyQt`, which only exist inside a running QGIS
Python environment — they have **not** been executed end-to-end in this
session (there's no way to run the QGIS desktop application headlessly in
this environment). Their code follows the official PyQGIS Cookbook pattern
exactly (see the module docstrings for the exact source), but treat them as
"correct per official docs, not yet execution-tested" until you load the
plugin into a real QGIS session and try the toolbar button.

## License

MIT — see [LICENSE](./LICENSE).
