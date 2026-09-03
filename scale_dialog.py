"""Interactive scale calculator for Twinmotion Landscape import values.

Separate from settings_dialog.py (credentials) — this dialog is pure
UI-driven arithmetic, no QgsSettings persistence. Follows this project's
existing dialog pattern (QDialog + QFormLayout + QDialogButtonBox, PyQt6
scoped enums — see settings_dialog.py's own 2026-09-03 PyQt6 fixes).

Design: map_export.HeightmapExportInfo.twinmotion_recommended_values()
already computes ONE automatic answer (the largest ratio that fits both
of Twinmotion's real dialog caps, TWINMOTION_MAX_LARGEST_DIMENSION_M /
TWINMOTION_MAX_AMPLITUDE_M — see map_export.py for how those two
empirical limits were found). This dialog exists because the user
explicitly asked for a "proper tool" to CHOOSE a scale ratio themselves,
not just accept the one auto-fit answer — e.g. to deliberately go
smaller than the cap-fit size for a cleaner round number, or to preview
what a partial scale looks like before committing.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .map_export import TWINMOTION_MAX_AMPLITUDE_M, TWINMOTION_MAX_LARGEST_DIMENSION_M


class HeightmapScaleDialog(QDialog):
    """Lets the user pick a scale percentage (1-100%) and see the
    resulting Twinmotion "Largest dimension"/"Amplitude" values update
    live, with a clear warning whenever the current percentage would
    still exceed Twinmotion's real dialog caps.

    Both fields are scaled by the SAME percentage always (never
    independently) — see HeightmapExportInfo.twinmotion_recommended_values()'s
    docstring for why: scaling only one axis distorts the true
    horizontal:vertical relief ratio.
    """

    def __init__(self, real_dimension_m: float, real_amplitude_m: float, parent=None):
        super().__init__(parent)
        self.real_dimension_m = real_dimension_m
        self.real_amplitude_m = real_amplitude_m
        self.chosen_dimension_m = real_dimension_m
        self.chosen_amplitude_m = real_amplitude_m

        self.setWindowTitle("Terrain Assistant — Twinmotion 축척 계산기")
        layout = QVBoxLayout(self)

        form = QFormLayout()
        real_label = QLabel(
            f"{real_dimension_m:,.0f} m  ×  Amplitude {real_amplitude_m:,.0f} m"
        )
        real_label.setStyleSheet("color: gray;")
        form.addRow("실제 크기(100%):", real_label)

        # Default to the largest percentage that fits BOTH Twinmotion caps
        # (mirrors HeightmapExportInfo.twinmotion_recommended_values()'s own
        # scale_factor formula) so the dialog opens on a value that's
        # already valid, not on 100% when 100% is known to be rejected.
        fit_factor = min(
            TWINMOTION_MAX_LARGEST_DIMENSION_M / real_dimension_m if real_dimension_m else 1.0,
            TWINMOTION_MAX_AMPLITUDE_M / real_amplitude_m if real_amplitude_m else 1.0,
            1.0,
        )
        default_percent = round(fit_factor * 100, 1)

        # Quick-preset buttons — round 1:N ratios (the standard surveying/
        # cartography scale notation this dialog already displays, see
        # _recompute()'s ratio_label) plus the one non-round but practical
        # preset, "Twinmotion 맞춤" (fit-to-cap, same value the dialog
        # opens on by default). Each just sets percent_spin — the existing
        # valueChanged signal chain (_on_percent_spin_changed -> slider +
        # _recompute) handles the rest, no separate logic needed here.
        preset_row = QHBoxLayout()
        presets = [
            ("1:1 (실제크기)", 100.0),
            ("1:2", 50.0),
            ("1:4", 25.0),
            ("1:10", 10.0),
            ("Twinmotion 맞춤", default_percent),
        ]
        for label, percent_value in presets:
            button = QPushButton(label, self)
            button.clicked.connect(
                lambda checked=False, p=percent_value: self.percent_spin.setValue(p)
            )
            preset_row.addWidget(button)
        form.addRow("빠른 선택:", preset_row)

        self.percent_spin = QDoubleSpinBox(self)
        self.percent_spin.setRange(1.0, 100.0)
        self.percent_spin.setSuffix(" %")
        self.percent_spin.setDecimals(1)
        self.percent_spin.setValue(default_percent)
        form.addRow("축척 비율:", self.percent_spin)

        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setRange(10, 1000)  # 1.0%–100.0%, in 0.1% steps
        self.slider.setValue(int(default_percent * 10))
        form.addRow("", self.slider)

        self.result_label = QLabel(self)
        self.result_label.setStyleSheet("font-weight: 600;")
        form.addRow("Twinmotion에 입력할 값:", self.result_label)

        self.ratio_label = QLabel(self)
        self.ratio_label.setStyleSheet("color: gray;")
        form.addRow("축척(표준 표기):", self.ratio_label)

        self.warning_label = QLabel(self)
        self.warning_label.setWordWrap(True)
        form.addRow("", self.warning_label)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.percent_spin.valueChanged.connect(self._on_percent_spin_changed)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self._recompute(default_percent)

    def _on_percent_spin_changed(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(value * 10)))
        self.slider.blockSignals(False)
        self._recompute(value)

    def _on_slider_changed(self, value: int) -> None:
        percent = value / 10.0
        self.percent_spin.blockSignals(True)
        self.percent_spin.setValue(percent)
        self.percent_spin.blockSignals(False)
        self._recompute(percent)

    def _recompute(self, percent: float) -> None:
        factor = percent / 100.0
        self.chosen_dimension_m = self.real_dimension_m * factor
        self.chosen_amplitude_m = self.real_amplitude_m * factor

        self.result_label.setText(
            f"Largest dimension: {self.chosen_dimension_m:,.0f} m   ·   "
            f"Amplitude: {self.chosen_amplitude_m:,.0f} m"
        )

        # 국토지리정보원 등 국내 측량/지도 표준 표기(1:N, "N분의 1") — 실제
        # 크기를 N으로 나눈 값을 표시한다는 뜻. percent=100%(축척 없음)이면
        # "1:1"(실제 크기 그대로)로 표시.
        if percent >= 100.0:
            self.ratio_label.setText("1:1 (실제 크기 그대로)")
        else:
            n = 100.0 / percent
            self.ratio_label.setText(f"1:{n:,.1f}  ({n:,.1f}분의 1로 축소)")

        over_dimension = self.chosen_dimension_m > TWINMOTION_MAX_LARGEST_DIMENSION_M
        over_amplitude = self.chosen_amplitude_m > TWINMOTION_MAX_AMPLITUDE_M
        if over_dimension or over_amplitude:
            parts = []
            if over_dimension:
                parts.append(f"Largest dimension이 Twinmotion 상한({TWINMOTION_MAX_LARGEST_DIMENSION_M:,.0f}m)을 초과")
            if over_amplitude:
                parts.append(f"Amplitude가 Twinmotion 상한({TWINMOTION_MAX_AMPLITUDE_M:,.0f}m)을 초과")
            self.warning_label.setText("⚠ " + " / ".join(parts) + " — 비율을 더 낮추세요.")
            self.warning_label.setStyleSheet("color: #a0522d;")
        else:
            self.warning_label.setText("✓ Twinmotion 다이얼로그에 그대로 입력 가능한 값입니다.")
            self.warning_label.setStyleSheet("color: #3d6b57;")
