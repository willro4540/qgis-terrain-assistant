"""QGIS plugin entry point.

Every QGIS plugin's __init__.py must define classFactory(iface), which QGIS
core calls when loading the plugin, passing the QgisInterface instance.
Reference: https://docs.qgis.org/latest/en/docs/pyqgis_developer_cookbook/plugins/plugins.html
(pattern independently re-confirmed against this project's own
qgis-architecture-study/docs/04_plugin_system_and_pyqgis.md, which documents
the same classFactory(iface) convention from the locally-installed QGIS 4.2.1
bundled plugins).
"""


def classFactory(iface):
    from .terrain_assistant import TerrainAssistantPlugin
    return TerrainAssistantPlugin(iface)
