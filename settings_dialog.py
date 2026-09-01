"""API key storage using QgsSettings — QGIS's standard persistent-settings
mechanism (a thin wrapper over QSettings), so the key is never hardcoded
into plugin source and survives across QGIS sessions.
Reference: https://qgis.org/pyqgis/master/core/QgsSettings.html
"""

from qgis.core import QgsSettings
from qgis.PyQt.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox

SETTINGS_KEY = "TerrainAssistant/vworld_api_key"


def get_api_key() -> str:
    return QgsSettings().value(SETTINGS_KEY, "", type=str)


def set_api_key(key: str) -> None:
    QgsSettings().setValue(SETTINGS_KEY, key)


class ApiKeyDialog(QDialog):
    """Minimal settings dialog: one field, one OK/Cancel row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Terrain Assistant — API Key")
        layout = QFormLayout(self)

        self.key_edit = QLineEdit(self)
        self.key_edit.setText(get_api_key())
        self.key_edit.setPlaceholderText("V-World developer portal API key")
        layout.addRow("V-World API key:", self.key_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def save(self) -> None:
        set_api_key(self.key_edit.text().strip())
