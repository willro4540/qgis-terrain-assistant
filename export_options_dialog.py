"""Pre-export options dialog for DEM heightmap export.

Advanced/optional settings collapsed behind a checkable group box by
default — per explicit request ("메뉴항이 만아지면 임의설정란을 열고닫을
수 있게... 현직에서도 쓰니깐"): a collapsible "Advanced" section is a
standard desktop-app pattern for infrequently-touched settings, not
something invented for this project. Both settings default OFF, so a
user who never opens this dialog's advanced group gets exactly today's
already-verified export behavior — nothing about the default path changes.
"""

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)


class HeightmapExportOptionsDialog(QDialog):
    """Lets the user opt into GDAL upsampling and/or (beta) smoothing
    before exporting a DEM as a heightmap — added after the user found
    visible grid/facet artifacts in Twinmotion from a low-pixel-count
    source DEM (2026-09-03).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Terrain Assistant — 하이트맵 내보내기 옵션")
        layout = QVBoxLayout(self)

        info_label = QLabel(
            "Twinmotion에서 지형에 격자/각진 무늬가 보이면 아래 옵션으로 완화할 수 "
            "있습니다. 기본값(꺼짐)은 지금까지 검증된 동작 그대로입니다."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.advanced_group = QGroupBox("고급 설정 (선택, 기본 꺼짐)", self)
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        form = QFormLayout(self.advanced_group)

        self.upsample_spin = QSpinBox(self.advanced_group)
        self.upsample_spin.setRange(1, 16)
        self.upsample_spin.setValue(4)
        self.upsample_spin.setSuffix(" 배")
        self.upsample_spin.setToolTip(
            "GDAL의 cubic-spline 보간(gdal.Warp)으로 픽셀 수를 늘립니다. "
            "실제 측량 디테일을 새로 만들어내는 게 아니라, 기존 샘플 사이를 "
            "매끄럽게 보간하는 것입니다."
        )
        form.addRow("업샘플링:", self.upsample_spin)

        self.smoothing_check = QCheckBox("스무딩 적용 (베타)", self.advanced_group)
        self.smoothing_check.setToolTip(
            "scipy.ndimage.gaussian_filter로 고도값을 한 번 더 부드럽게 처리합니다. "
            "업샘플링만으로 부족할 때 추가로 켜보는 용도 — 이 세션에서 실제 QGIS "
            "환경 실행 테스트는 안 된 베타 기능입니다."
        )
        form.addRow("", self.smoothing_check)

        layout.addWidget(self.advanced_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def upsample_factor(self) -> int:
        """1 (no-op) unless the advanced group is checked — so cancelling
        or ignoring the advanced section always yields today's original
        behavior, never a surprise default upsample."""
        return self.upsample_spin.value() if self.advanced_group.isChecked() else 1

    @property
    def apply_smoothing(self) -> bool:
        return self.advanced_group.isChecked() and self.smoothing_check.isChecked()
