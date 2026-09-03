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
from .map_export import export_map_png, refine_crs
from .datasource import (
    BoundingBox,
    OpenTopographyDemSource,
    SentinelHubImagerySource,
    KoreaBasemapSource,
    fetch_naver_tile_version,
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

        load_korea_basemap_action = QAction(
            icon, "Load Korea basemap (VWorld/Naver)…", self.iface.mainWindow()
        )
        load_korea_basemap_action.triggered.connect(self.run_load_korea_basemap)
        self.iface.addToolBarIcon(load_korea_basemap_action)
        self.iface.addPluginToMenu(self.menu, load_korea_basemap_action)
        self.actions.append(load_korea_basemap_action)

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
        if dialog.exec_():
            dialog.save()

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

        canvas = self.iface.mapCanvas()
        canvas_crs = canvas.mapSettings().destinationCrs()
        canvas_epsg = canvas_crs.postgisSrid()  # numeric EPSG code, e.g. 4326, 3857, 5186

        try:
            if canvas_epsg == 4326:
                extent_4326 = canvas.extent()
            else:
                extent_4326 = refine_crs(canvas.extent(), canvas_epsg, 4326)

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

        canvas = self.iface.mapCanvas()
        canvas_crs = canvas.mapSettings().destinationCrs()
        canvas_epsg = canvas_crs.postgisSrid()

        try:
            if canvas_epsg == 4326:
                extent_4326 = canvas.extent()
            else:
                extent_4326 = refine_crs(canvas.extent(), canvas_epsg, 4326)

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
                        f"fallback version ({version}). Tiles may fail to "
                        "load if Naver has rotated the token since this "
                        "fallback was last verified.",
                    )
                uri = KoreaBasemapSource.naver_layer_uri(style, version)
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
