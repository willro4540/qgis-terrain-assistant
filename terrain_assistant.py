"""Main plugin class.

Per the official PyQGIS plugin contract, only two methods are required to
exist: initGui() (called when the plugin loads) and unload() (called when
it unloads) — https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/plugins/plugins.html
"""

import os
import tempfile

from qgis.core import QgsProject, QgsRasterLayer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox

from .settings_dialog import ApiKeyDialog, get_api_key
from .map_export import export_map_png, refine_crs
from .datasource import BoundingBox, OpenTopographyDemSource


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

        export_action = QAction(icon, "Export current map as PNG", self.iface.mainWindow())
        export_action.triggered.connect(self.run_export)
        self.iface.addToolBarIcon(export_action)
        self.iface.addPluginToMenu(self.menu, export_action)
        self.actions.append(export_action)

        settings_action = QAction("Set OpenTopography API key…", self.iface.mainWindow())
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
