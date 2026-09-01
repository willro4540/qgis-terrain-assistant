"""Main plugin class.

Per the official PyQGIS plugin contract, only two methods are required to
exist: initGui() (called when the plugin loads) and unload() (called when
it unloads) — https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/plugins/plugins.html
"""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox

from .settings_dialog import ApiKeyDialog
from .map_export import export_map_png


class TerrainAssistantPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.menu = "&Terrain Assistant"

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        export_action = QAction(icon, "Export current map as PNG", self.iface.mainWindow())
        export_action.triggered.connect(self.run_export)
        self.iface.addToolBarIcon(export_action)
        self.iface.addPluginToMenu(self.menu, export_action)
        self.actions.append(export_action)

        settings_action = QAction("Set V-World API key…", self.iface.mainWindow())
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
