"""Main plugin class.

Per the official PyQGIS plugin contract, only two methods are required to
exist: initGui() (called when the plugin loads) and unload() (called when
it unloads) — https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/plugins/plugins.html
"""

import os
import tempfile

import urllib.error

from qgis.core import QgsProject, QgsRasterLayer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QInputDialog, QMessageBox

from .settings_dialog import ApiKeyDialog, get_api_key, get_sentinelhub_credentials
from .scale_dialog import HeightmapScaleDialog
from .map_export import (
    export_map_png,
    export_dem_heightmap_png,
    export_dem_heightmap_r16,
    refine_crs,
    TWINMOTION_MAX_AMPLITUDE_M,
    TWINMOTION_MAX_LARGEST_DIMENSION_M,
)
from .datasource import (
    BoundingBox,
    OpenTopographyDemSource,
    SentinelHubImagerySource,
    KoreaBasemapSource,
    fetch_naver_tile_version,
    probe_tile_reachable,
)


class TerrainAssistantPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.menu = "&Terrain Assistant"

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        load_dem_action = QAction(icon, "Load DEM from OpenTopography…", self.iface.mainWindow())
        load_dem_action.triggered.connect(self.run_load_dem)
        self.iface.addToolBarIcon(load_dem_action)
        self.iface.addPluginToMenu(self.menu, load_dem_action)
        self.actions.append(load_dem_action)

        load_imagery_action = QAction(
            icon, "Load Sentinel-2 imagery…", self.iface.mainWindow()
        )
        load_imagery_action.triggered.connect(self.run_load_sentinel_imagery)
        self.iface.addToolBarIcon(load_imagery_action)
        self.iface.addPluginToMenu(self.menu, load_imagery_action)
        self.actions.append(load_imagery_action)

        load_imagery_fullband_action = QAction(
            icon, "Load Sentinel-2 imagery (12-band, full spectrum)…", self.iface.mainWindow()
        )
        load_imagery_fullband_action.triggered.connect(
            self.run_load_sentinel_imagery_full_bands
        )
        self.iface.addToolBarIcon(load_imagery_fullband_action)
        self.iface.addPluginToMenu(self.menu, load_imagery_fullband_action)
        self.actions.append(load_imagery_fullband_action)

        load_korea_basemap_action = QAction(
            icon, "Load Korea basemap (VWorld/Naver)…", self.iface.mainWindow()
        )
        load_korea_basemap_action.triggered.connect(self.run_load_korea_basemap)
        self.iface.addToolBarIcon(load_korea_basemap_action)
        self.iface.addPluginToMenu(self.menu, load_korea_basemap_action)
        self.actions.append(load_korea_basemap_action)

        export_heightmap_r16_action = QAction(
            icon, "Export DEM as heightmap (.r16, for Twinmotion)…", self.iface.mainWindow()
        )
        export_heightmap_r16_action.triggered.connect(self.run_export_heightmap_r16)
        self.iface.addToolBarIcon(export_heightmap_r16_action)
        self.iface.addPluginToMenu(self.menu, export_heightmap_r16_action)
        self.actions.append(export_heightmap_r16_action)

        export_heightmap_png_action = QAction(
            icon, "Export DEM as heightmap (.png, 16-bit preview)…", self.iface.mainWindow()
        )
        export_heightmap_png_action.triggered.connect(self.run_export_heightmap_png)
        self.iface.addToolBarIcon(export_heightmap_png_action)
        self.iface.addPluginToMenu(self.menu, export_heightmap_png_action)
        self.actions.append(export_heightmap_png_action)

        export_action = QAction(icon, "Export current map as PNG", self.iface.mainWindow())
        export_action.triggered.connect(self.run_export)
        self.iface.addToolBarIcon(export_action)
        self.iface.addPluginToMenu(self.menu, export_action)
        self.actions.append(export_action)

        settings_action = QAction("Set API keys…", self.iface.mainWindow())
        settings_action.triggered.connect(self.run_settings)
        self.iface.addPluginToMenu(self.menu, settings_action)
        self.actions.append(settings_action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []

    def run_settings(self):
        dialog = ApiKeyDialog(self.iface.mainWindow())
        if dialog.exec():
            dialog.save()

    def _canvas_extent_4326(self):
        """Return the current map canvas extent reprojected to EPSG:4326
        (lon/lat degrees) — the shape every bbox-based data source in this
        plugin (OpenTopography, Sentinel Hub) requires. Uses refine_crs()
        (QGIS's own PROJ transform, already used by the PNG-export path).
        Factored out of run_load_dem()/run_load_sentinel_imagery() since a
        third caller (run_load_sentinel_imagery_full_bands) needs the same
        four lines.
        """
        canvas = self.iface.mapCanvas()
        canvas_crs = canvas.mapSettings().destinationCrs()
        canvas_epsg = canvas_crs.postgisSrid()  # numeric EPSG code, e.g. 4326, 3857, 5186
        if canvas_epsg == 4326:
            return canvas.extent()
        return refine_crs(canvas.extent(), canvas_epsg, 4326)

    def run_load_dem(self):
        """Fetch a Copernicus GLO-30 DEM covering the current map canvas
        extent from OpenTopography and add it to the project as a raster
        layer. Uses refine_crs() (QGIS's own PROJ transform, already used
        by the PNG-export path) to convert the canvas extent to EPSG:4326,
        since OpenTopography's globaldem API takes south/north/west/east
        in geographic (lon/lat) degrees — verified live, see
        datasource.OpenTopographyDemSource's docstring.
        """
        api_key = get_api_key()
        if not api_key:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Terrain Assistant",
                "No OpenTopography API key set. Use "
                "'Set OpenTopography API key…' first — get a free one at "
                "https://portal.opentopography.org/requestService?service=api",
            )
            return

        try:
            extent_4326 = self._canvas_extent_4326()
            bbox = BoundingBox(
                min_lon=extent_4326.xMinimum(),
                min_lat=extent_4326.yMinimum(),
                max_lon=extent_4326.xMaximum(),
                max_lat=extent_4326.yMaximum(),
            )
            dem_bytes = OpenTopographyDemSource().fetch(bbox, api_key=api_key)
        except Exception as exc:  # noqa: BLE001 — surface any fetch failure to the user
            QMessageBox.critical(
                self.iface.mainWindow(), "Terrain Assistant — DEM load failed", str(exc)
            )
            return

        tif_path = tempfile.NamedTemporaryFile(
            prefix="terrain_assistant_dem_", suffix=".tif", delete=False
        ).name
        with open(tif_path, "wb") as f:
            f.write(dem_bytes)

        layer = QgsRasterLayer(tif_path, "OpenTopography DEM (COP30)")
        if not layer.isValid():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Terrain Assistant",
                f"OpenTopography response could not be loaded as a raster layer "
                f"(saved to {tif_path} for inspection).",
            )
            return

        QgsProject.instance().addMapLayer(layer)
        QMessageBox.information(
            self.iface.mainWindow(), "Terrain Assistant", "DEM layer added to the project."
        )

    def run_load_sentinel_imagery(self):
        """Fetch a Sentinel-2 L2A true-color image covering the current map
        canvas extent from Sentinel Hub and add it to the project as a
        raster layer. Same CRS-refinement approach as run_load_dem() (the
        Process API's bbox is in EPSG:4326 lon/lat degrees — verified,
        see datasource.SentinelHubImagerySource's docstring).

        Requires a Sentinel Hub OAuth client_id/client_secret pair (NOT a
        single API key) — genuinely different credential shape from
        OpenTopography, see settings_dialog.py and the datasource
        docstring for why.
        """
        client_id, client_secret = get_sentinelhub_credentials()
        if not client_id or not client_secret:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Terrain Assistant",
                "No Sentinel Hub credentials set. Use 'Set API keys…' first "
                "— register a free OAuth client at "
                "https://apps.sentinel-hub.com/dashboard/#/account/settings",
            )
            return

        try:
            extent_4326 = self._canvas_extent_4326()
            bbox = BoundingBox(
                min_lon=extent_4326.xMinimum(),
                min_lat=extent_4326.yMinimum(),
                max_lon=extent_4326.xMaximum(),
                max_lat=extent_4326.yMaximum(),
            )
            source = SentinelHubImagerySource(
                client_id=client_id, client_secret=client_secret
            )
            image_bytes = source.fetch(bbox)
        except Exception as exc:  # noqa: BLE001 — surface any fetch failure to the user
            QMessageBox.critical(
                self.iface.mainWindow(), "Terrain Assistant — imagery load failed", str(exc)
            )
            return

        tif_path = tempfile.NamedTemporaryFile(
            prefix="terrain_assistant_sentinel_", suffix=".tif", delete=False
        ).name
        with open(tif_path, "wb") as f:
            f.write(image_bytes)

        layer = QgsRasterLayer(tif_path, "Sentinel-2 L2A imagery")
        if not layer.isValid():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Terrain Assistant",
                f"Sentinel Hub response could not be loaded as a raster layer "
                f"(saved to {tif_path} for inspection).",
            )
            return

        QgsProject.instance().addMapLayer(layer)
        QMessageBox.information(
            self.iface.mainWindow(), "Terrain Assistant", "Imagery layer added to the project."
        )

    def run_load_sentinel_imagery_full_bands(self):
        """Fetch all 12 Sentinel-2 L2A optical bands (FLOAT32 reflectance,
        not a true-color visualization) covering the current map canvas
        extent, and add it as a raster layer.

        Same credentials/CRS-refinement path as run_load_sentinel_imagery()
        — the only difference is the evalscript
        (SentinelHubImagerySource.ALL_BANDS_EVALSCRIPT instead of the
        default TRUE_COLOR_EVALSCRIPT), so the resulting GeoTIFF has 12
        bands instead of 3 and is meant for analysis (e.g. NDVI, or as
        input to a model expecting full-spectrum Sentinel-2 data) rather
        than direct viewing. See datasource.py's ALL_BANDS_EVALSCRIPT
        docstring for why this specific 12-band combination was chosen —
        it's the prerequisite for docs/future_integration_candidates.md
        §3's Prithvi-EO-2.0 landslide-detection candidate, not that
        integration itself.
        """
        client_id, client_secret = get_sentinelhub_credentials()
        if not client_id or not client_secret:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Terrain Assistant",
                "No Sentinel Hub credentials set. Use 'Set API keys…' first "
                "— register a free OAuth client at "
                "https://apps.sentinel-hub.com/dashboard/#/account/settings",
            )
            return

        try:
            extent_4326 = self._canvas_extent_4326()
            bbox = BoundingBox(
                min_lon=extent_4326.xMinimum(),
                min_lat=extent_4326.yMinimum(),
                max_lon=extent_4326.xMaximum(),
                max_lat=extent_4326.yMaximum(),
            )
            source = SentinelHubImagerySource(
                client_id=client_id,
                client_secret=client_secret,
                evalscript=SentinelHubImagerySource.ALL_BANDS_EVALSCRIPT,
            )
            image_bytes = source.fetch(bbox)
        except Exception as exc:  # noqa: BLE001 — surface any fetch failure to the user
            QMessageBox.critical(
                self.iface.mainWindow(), "Terrain Assistant — imagery load failed", str(exc)
            )
            return

        tif_path = tempfile.NamedTemporaryFile(
            prefix="terrain_assistant_sentinel_12band_", suffix=".tif", delete=False
        ).name
        with open(tif_path, "wb") as f:
            f.write(image_bytes)

        layer = QgsRasterLayer(tif_path, "Sentinel-2 L2A imagery (12-band)")
        if not layer.isValid():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Terrain Assistant",
                f"Sentinel Hub response could not be loaded as a raster layer "
                f"(saved to {tif_path} for inspection).",
            )
            return

        QgsProject.instance().addMapLayer(layer)
        QMessageBox.information(
            self.iface.mainWindow(),
            "Terrain Assistant",
            "12-band Sentinel-2 layer added to the project.",
        )

    def run_load_korea_basemap(self):
        """Add a Korea-focused XYZ basemap tile layer (VWorld or Naver Maps
        v5) to the project — no API key needed for either provider (see
        datasource.KoreaBasemapSource's docstring, verified against
        mangosystem/qgis-tmsforkorea-plugin's source, 2026-09-03).

        Unlike run_load_dem()/run_load_sentinel_imagery(), this does not
        need the current map canvas extent at all — tiles load lazily as
        the user pans/zooms, so this only needs a provider+style choice.
        """
        options = []
        for style, info in KoreaBasemapSource.VWORLD_STYLES.items():
            options.append(("vworld", style, info["display_name"]))
        for style, info in KoreaBasemapSource.NAVER_STYLES.items():
            options.append(("naver", style, info["display_name"]))

        labels = [display_name for _, _, display_name in options]
        chosen_label, ok = QInputDialog.getItem(
            self.iface.mainWindow(),
            "Terrain Assistant",
            "Korea basemap:",
            labels,
            0,
            False,
        )
        if not ok or not chosen_label:
            return

        provider, style, display_name = next(
            (p, s, d) for p, s, d in options if d == chosen_label
        )

        try:
            if provider == "vworld":
                uri = KoreaBasemapSource.vworld_layer_uri(style)
            else:
                try:
                    version = fetch_naver_tile_version(style)
                except (urllib.error.URLError, urllib.error.HTTPError, ValueError, KeyError):
                    version = KoreaBasemapSource.NAVER_FALLBACK_VERSION
                    QMessageBox.warning(
                        self.iface.mainWindow(),
                        "Terrain Assistant",
                        "Could not fetch Naver's live tile version — using a "
                        f"fallback version ({version}). Checking it still "
                        "works before loading it…",
                    )

                naver_template = KoreaBasemapSource.naver_url_template(style, version)
                if probe_tile_reachable(naver_template):
                    uri = KoreaBasemapSource.naver_layer_uri(style, version)
                else:
                    # Safe mode: both the live version lookup AND the
                    # hardcoded fallback failed to serve a real tile — don't
                    # add a layer that would silently show as "valid" but
                    # render blank. Fall back to VWorld street instead,
                    # which needs no version token at all and is this
                    # plugin's most reliable basemap path.
                    QMessageBox.warning(
                        self.iface.mainWindow(),
                        "Terrain Assistant — safe mode",
                        "Naver tiles are unreachable right now (both the live "
                        "version lookup and the fallback version failed a "
                        "real tile check) — loading VWorld street basemap "
                        "instead as a safe fallback. Try Naver again later.",
                    )
                    provider, style = "vworld", "street"
                    display_name = KoreaBasemapSource.VWORLD_STYLES["street"]["display_name"]
                    uri = KoreaBasemapSource.vworld_layer_uri(style)
        except Exception as exc:  # noqa: BLE001 — surface any failure to the user
            QMessageBox.critical(
                self.iface.mainWindow(), "Terrain Assistant — basemap load failed", str(exc)
            )
            return

        layer = QgsRasterLayer(uri, display_name, "wms")
        if not layer.isValid():
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Terrain Assistant",
                f"'{display_name}' could not be loaded as a raster layer (URI: {uri}).",
            )
            return

        QgsProject.instance().addMapLayer(layer)
        QMessageBox.information(
            self.iface.mainWindow(), "Terrain Assistant", f"'{display_name}' layer added."
        )

    def _active_dem_layer_source(self):
        """Return the file path of the currently selected DEM raster layer
        in the Layers panel, or None with a warning shown if there isn't
        one. Shared by run_export_heightmap_r16()/run_export_heightmap_png().

        Design: operates on iface.activeLayer() (the user selects their
        already-loaded DEM in the Layers panel first) rather than
        re-fetching from OpenTopography — matches run_export()'s existing
        pattern of working on whatever's already loaded, not doing its own
        network fetch. Use "Load DEM from OpenTopography…" first to get a
        DEM layer to select.
        """
        layer = self.iface.activeLayer()
        if layer is None or not hasattr(layer, "source"):
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Terrain Assistant",
                "Select a DEM raster layer in the Layers panel first — e.g. "
                "one loaded via 'Load DEM from OpenTopography…'.",
            )
            return None
        return layer.source()

    def run_export_heightmap_r16(self):
        """Convert the selected DEM layer to Twinmotion's native `.r16`
        heightmap format (see map_export.export_dem_heightmap_r16's
        docstring — verified 2026-09-03 against Twinmotion 2026.2's own
        Import file-type dropdown, screenshot-confirmed).

        Twinmotion's Landscape import dialog has no pixel-resolution
        field at all — only "Largest dimension" and "Amplitude", both in
        real-world meters (screenshot-confirmed same session). This shows
        both, auto-computed, so the user doesn't have to hand-compute
        latitude-corrected degree-to-meter conversions themselves (which
        is exactly what happened the first time this was used).
        """
        dem_path = self._active_dem_layer_source()
        if dem_path is None:
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Export heightmap for Twinmotion",
            "",
            "Raw 16-bit heightmap (*.r16)",
        )
        if not output_path:
            return

        try:
            info = export_dem_heightmap_r16(dem_path, output_path)
        except Exception as exc:  # noqa: BLE001 — surface any conversion failure to the user
            QMessageBox.critical(
                self.iface.mainWindow(), "Terrain Assistant — heightmap export failed", str(exc)
            )
            return

        if info.largest_dimension_m is not None:
            # Let the user pick the scale ratio themselves (per their own
            # request for a "proper tool", not just one auto-computed
            # answer) — opens pre-filled with the largest ratio that fits
            # both of Twinmotion's real dialog caps.
            scale_dialog = HeightmapScaleDialog(
                info.largest_dimension_m, info.amplitude_m, self.iface.mainWindow()
            )
            if scale_dialog.exec():
                dimension_m = scale_dialog.chosen_dimension_m
                amplitude_m = scale_dialog.chosen_amplitude_m
            else:
                # User cancelled the scale picker — fall back to the
                # cap-fit recommendation rather than losing the export.
                dimension_m, amplitude_m, _ = info.twinmotion_recommended_values()

            twinmotion_hint = (
                f"In Twinmotion's Import ▸ Landscape dialog, set:\n"
                f"  Largest dimension: {dimension_m:.0f} m\n"
                f"  Amplitude: {amplitude_m:.0f} m"
            )
            if (
                dimension_m > TWINMOTION_MAX_LARGEST_DIMENSION_M
                or amplitude_m > TWINMOTION_MAX_AMPLITUDE_M
            ):
                twinmotion_hint += (
                    "\n\n⚠ This still exceeds Twinmotion's actual dialog limits "
                    f"(Largest dimension max {TWINMOTION_MAX_LARGEST_DIMENSION_M:.0f} m, "
                    f"Amplitude max {TWINMOTION_MAX_AMPLITUDE_M:.0f} m) — Twinmotion will "
                    "cap whatever you enter."
                )
        else:
            twinmotion_hint = (
                "Could not auto-compute real-world size (source CRS is neither "
                "geographic nor projected-in-meters) — check QGIS layer "
                "Properties ▸ Information for the extent, and set Twinmotion's "
                f"Amplitude to {info.amplitude_m:.0f} m."
            )

        QMessageBox.information(
            self.iface.mainWindow(),
            "Terrain Assistant",
            f"Exported {info.width_px}x{info.height_px} heightmap to {output_path}.\n\n"
            f"{twinmotion_hint}",
        )

    def run_export_heightmap_png(self):
        """Convert the selected DEM layer to a 16-bit grayscale heightmap
        PNG (see map_export.export_dem_heightmap_png's docstring). Useful
        for a quick visual preview outside Twinmotion — prefer
        run_export_heightmap_r16() when feeding Twinmotion directly, since
        `.r16`'s bit depth is unambiguous by format definition.
        """
        dem_path = self._active_dem_layer_source()
        if dem_path is None:
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Export heightmap preview",
            "",
            "PNG image (*.png)",
        )
        if not output_path:
            return

        try:
            export_dem_heightmap_png(dem_path, output_path)
        except Exception as exc:  # noqa: BLE001 — surface any conversion failure to the user
            QMessageBox.critical(
                self.iface.mainWindow(), "Terrain Assistant — heightmap export failed", str(exc)
            )
            return

        QMessageBox.information(
            self.iface.mainWindow(), "Terrain Assistant", f"Exported heightmap preview to {output_path}."
        )

    def run_export(self):
        canvas = self.iface.mapCanvas()
        if canvas.layerCount() == 0:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Terrain Assistant",
                "No layers loaded — load at least one layer before exporting.",
            )
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Export map as PNG",
            "",
            "PNG image (*.png)",
        )
        if not output_path:
            return

        try:
            export_map_png(
                output_path=output_path,
                map_extent=canvas.extent(),
                title="Terrain Assistant export",
            )
        except Exception as exc:  # noqa: BLE001 — surface any export failure to the user
            QMessageBox.critical(
                self.iface.mainWindow(), "Terrain Assistant — export failed", str(exc)
            )
            return

        QMessageBox.information(
            self.iface.mainWindow(), "Terrain Assistant", f"Exported to {output_path}"
        )
