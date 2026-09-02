"""API key storage using QgsSettings — QGIS's standard persistent-settings
mechanism (a thin wrapper over QSettings), so the key is never hardcoded
into plugin source and survives across QGIS sessions.
Reference: https://qgis.org/pyqgis/master/core/QgsSettings.html
"""

from qgis.core import QgsSettings
from qgis.PyQt.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox

SETTINGS_KEY = "TerrainAssistant/opentopography_api_key"
SENTINELHUB_CLIENT_ID_KEY = "TerrainAssistant/sentinelhub_client_id"
SENTINELHUB_CLIENT_SECRET_KEY = "TerrainAssistant/sentinelhub_client_secret"


def get_api_key() -> str:
    return QgsSettings().value(SETTINGS_KEY, "", type=str)


def set_api_key(key: str) -> None:
    QgsSettings().setValue(SETTINGS_KEY, key)


def get_sentinelhub_credentials() -> tuple[str, str]:
    """Returns (client_id, client_secret) — Sentinel Hub uses an OAuth2
    client-id/secret pair, not a single API key (see
    datasource.SentinelHubImagerySource's docstring for why this is a
    genuinely different shape from get_api_key()'s single string)."""
    settings = QgsSettings()
    return (
        settings.value(SENTINELHUB_CLIENT_ID_KEY, "", type=str),
        settings.value(SENTINELHUB_CLIENT_SECRET_KEY, "", type=str),
    )


def set_sentinelhub_credentials(client_id: str, client_secret: str) -> None:
    settings = QgsSettings()
    settings.setValue(SENTINELHUB_CLIENT_ID_KEY, client_id)
    settings.setValue(SENTINELHUB_CLIENT_SECRET_KEY, client_secret)


class ApiKeyDialog(QDialog):
    """Settings dialog: OpenTopography's single API key, plus Sentinel
    Hub's OAuth2 client_id/client_secret pair (kept in one dialog so the
    user has a single "Terrain Assistant settings" entry point, even
    though the two providers' credential shapes are genuinely different).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Terrain Assistant — API Keys")
        layout = QFormLayout(self)

        self.key_edit = QLineEdit(self)
        self.key_edit.setText(get_api_key())
        self.key_edit.setPlaceholderText("OpenTopography portal API key")
        layout.addRow("OpenTopography API key:", self.key_edit)

        sh_client_id, sh_client_secret = get_sentinelhub_credentials()

        self.sh_client_id_edit = QLineEdit(self)
        self.sh_client_id_edit.setText(sh_client_id)
        self.sh_client_id_edit.setPlaceholderText("Sentinel Hub OAuth client ID")
        layout.addRow("Sentinel Hub client ID:", self.sh_client_id_edit)

        self.sh_client_secret_edit = QLineEdit(self)
        self.sh_client_secret_edit.setText(sh_client_secret)
        self.sh_client_secret_edit.setPlaceholderText("Sentinel Hub OAuth client secret")
        self.sh_client_secret_edit.setEchoMode(QLineEdit.Password)
        layout.addRow("Sentinel Hub client secret:", self.sh_client_secret_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def save(self) -> None:
        set_api_key(self.key_edit.text().strip())
        set_sentinelhub_credentials(
            self.sh_client_id_edit.text().strip(),
            self.sh_client_secret_edit.text().strip(),
        )
