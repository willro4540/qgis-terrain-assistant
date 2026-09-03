"""Interactive scale calculator for Twinmotion Landscape import values.

Separate from settings_dialog.py (credentials) — this dialog is pure
UI-driven arithmetic, no QgsSettings persistence. Follows this project's
existing dialog pattern (QDialog + QFormLayout + QDialogButtonBox, PyQt6
scoped enums — see settings_dialog.py's own 2026-09-03 PyQt6 fixes).

Design: map_export.HeightmapExportInfo.twinmotion_recommended_values()
already computes ONE automatic answer (the largest ratio that fits both
of Twinmotion's real dialog caps, TWINMOTION_MAX_LARGEST_DIMENSION_M /
TWINMOTION_MAX_AMPLITUDE_M — see datasource.py for how those two
empirical limits were found). This dialog exists because the user
explicitly asked for a "proper tool" to CHOOSE a scale ratio themselves,
not just accept the one auto-fit answer.

INPUT MODEL — the "N" in "1:N", not a percentage (changed 2026-09-03):
a percent-based control (1-100%) cannot represent the standard map-scale
presets the user asked to add (1:5,000 up to 1:250,000 — five orders of
magnitude below 1%), so the denominator N is the primary control instead;
percent is only ever a derived display value now.

PRESET SCALES — supplied directly by the user (an architecture/landscape
professional), not independently re-verified against an external source
this session (unlike this project's usual practice of verifying before
using) — treated as domain-expert-provided ground truth for their own
field's conventions:
  건축·조경 도면(architecture/landscape drawings): 1:20, 30, 50, 100, 200,
    500, 1,000 — the scales those professions actually draw at.
  모형·스케일 모델(scale models): 1:18, 24, 35, 48, 72, 87, 144 — standard
    die-cast/hobby model scales (1:87 is HO gauge, 1:24 is common
    architectural model scale, etc.).
  지도(maps): 1:5,000, 10,000, 25,000, 50,000, 100,000, 250,000 — Korea's
    standard topographic map series (1:5,000/1:25,000 are NGII's own
    nationwide products, cross-referenced against
    qgis-architecture-study's earlier CRS research).
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from .map_export import TWINMOTION_MAX_AMPLITUDE_M, TWINMOTION_MAX_LARGEST_DIMENSION_M

#: (category label, [N, N, ...]) — see module docstring for source/meaning.
SCALE_PRESET_CATEGORIES = [
    ("건축·조경 도면", [20, 30, 50, 100, 200, 500, 1000]),
    ("모형·스케일 모델", [18, 24, 35, 48, 72, 87, 144]),
    ("지도", [5000, 10000, 25000, 50000, 100000, 250000]),
]

#: Sentinel stored as Qt.ItemDataRole.UserRole data on the combo box's
#: special (non-1:N) entries, so _on_combo_changed can tell them apart
#: from a real preset N value without string-parsing the visible label.
_COMBO_TRUE_SIZE = "true_size"
_COMBO_TWINMOTION_FIT = "twinmotion_fit"
_COMBO_CUSTOM = "custom"

#: Range for the continuous custom-adjustment slider — 1:1 through
#: 1:500 covers the practical hand-drag zone (true size down through the
#: architecture/model preset range); reaching a map-scale N (thousands+)
#: is done by typing it into the N spinbox directly, not by dragging,
#: same as picking any other preset.
_CUSTOM_SLIDER_MIN_N = 1
_CUSTOM_SLIDER_MAX_N = 500


class HeightmapScaleDialog(QDialog):
    """Lets the user pick a scale ratio 1:N and see the resulting
    Twinmotion "Largest dimension"/"Amplitude" values update live, with a
    clear warning whenever the current ratio would still exceed
    Twinmotion's real dialog caps.

    Both fields are always scaled by the SAME factor (1/N) — see
    HeightmapExportInfo.twinmotion_recommended_values()'s docstring for
    why: scaling only one axis distorts the true horizontal:vertical
    relief ratio.
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
        form.addRow("실제 크기(1:1):", real_label)

        # Largest N (smallest scale) that still fits BOTH Twinmotion caps —
        # mirrors HeightmapExportInfo.twinmotion_recommended_values()'s own
        # scale_factor, expressed as an N denominator instead of a ratio.
        fit_n = 1.0
        if real_dimension_m and real_dimension_m > TWINMOTION_MAX_LARGEST_DIMENSION_M:
            fit_n = max(fit_n, real_dimension_m / TWINMOTION_MAX_LARGEST_DIMENSION_M)
        if real_amplitude_m and real_amplitude_m > TWINMOTION_MAX_AMPLITUDE_M:
            fit_n = max(fit_n, real_amplitude_m / TWINMOTION_MAX_AMPLITUDE_M)
        self._fit_n = fit_n

        self.combo = QComboBox(self)
        self._populate_combo()
        form.addRow("표준 축척 선택:", self.combo)

        self.n_spin = QSpinBox(self)
        self.n_spin.setRange(1, 1_000_000)
        self.n_spin.setPrefix("1 : ")
        self.n_spin.setValue(max(1, round(fit_n)))
        form.addRow("직접 입력(N):", self.n_spin)

        self.custom_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.custom_slider.setRange(_CUSTOM_SLIDER_MIN_N, _CUSTOM_SLIDER_MAX_N)
        self.custom_slider.setValue(min(max(round(fit_n), _CUSTOM_SLIDER_MIN_N), _CUSTOM_SLIDER_MAX_N))
        self.custom_slider.setVisible(False)  # only shown in "사용자 지정" mode
        form.addRow("연속 조절:", self.custom_slider)

        self.result_label = QLabel(self)
        self.result_label.setStyleSheet("font-weight: 600;")
        form.addRow("Twinmotion에 입력할 값:", self.result_label)

        self.percent_label = QLabel(self)
        self.percent_label.setStyleSheet("color: gray;")
        form.addRow("(참고) 실제 크기 대비:", self.percent_label)

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

        self.combo.activated.connect(self._on_combo_changed)
        self.n_spin.valueChanged.connect(self._on_n_spin_changed)
        self.custom_slider.valueChanged.connect(self._on_custom_slider_changed)
        self._set_custom_mode(False)
        self._recompute(self.n_spin.value())

    def _populate_combo(self) -> None:
        model = QStandardItemModel(self)

        true_size_item = QStandardItem("1 : 1 (실제 크기)")
        true_size_item.setData(_COMBO_TRUE_SIZE)
        model.appendRow(true_size_item)

        fit_label = f"Twinmotion 맞춤 (1 : {self._fit_n:,.2f})"
        fit_item = QStandardItem(fit_label)
        fit_item.setData(_COMBO_TWINMOTION_FIT)
        model.appendRow(fit_item)

        for category, values in SCALE_PRESET_CATEGORIES:
            header_item = QStandardItem(f"── {category} ──")
            # Convenience setters (not a manual flags() bit-twiddle) —
            # QStandardItem.setSelectable/setEnabled already toggle the
            # right Qt.ItemFlag bits internally, so this greys the row out
            # and makes it unpickable without hand-computing a flag mask.
            header_item.setSelectable(False)
            header_item.setEnabled(False)
            model.appendRow(header_item)
            for n in values:
                item = QStandardItem(f"1 : {n:,}")
                item.setData(n)  # int N — a real preset, not a sentinel string
                model.appendRow(item)

        custom_item = QStandardItem("사용자 지정 (직접 조절)")
        custom_item.setData(_COMBO_CUSTOM)
        model.appendRow(custom_item)

        self.combo.setModel(model)

    def _on_combo_changed(self, index: int) -> None:
        data = self.combo.itemData(index)
        if data == _COMBO_CUSTOM:
            self._set_custom_mode(True)
            return
        self._set_custom_mode(False)
        if data == _COMBO_TRUE_SIZE:
            self.n_spin.setValue(1)
        elif data == _COMBO_TWINMOTION_FIT:
            self.n_spin.setValue(max(1, round(self._fit_n)))
        elif isinstance(data, int):
            self.n_spin.setValue(data)
        # Header rows are disabled/unselectable, so a real activation here
        # never lands on one — no branch needed for that case.

    def _set_custom_mode(self, enabled: bool) -> None:
        """상단 프리셋을 고르면 그 값만 바로 보여주고(N 직접입력 비활성화),
        "사용자 지정"을 고르면 이전 버전처럼 슬라이더로 자유롭게 조절할 수
        있게 전환한다 — 두 모드를 하나의 다이얼로그에 같이 둠(사용자 요청)."""
        self.n_spin.setEnabled(enabled)
        self.custom_slider.setVisible(enabled)
        if enabled:
            self.custom_slider.setValue(
                min(max(self.n_spin.value(), _CUSTOM_SLIDER_MIN_N), _CUSTOM_SLIDER_MAX_N)
            )

    def _on_n_spin_changed(self, value: int) -> None:
        if self.custom_slider.isVisible():
            self.custom_slider.blockSignals(True)
            self.custom_slider.setValue(min(max(value, _CUSTOM_SLIDER_MIN_N), _CUSTOM_SLIDER_MAX_N))
            self.custom_slider.blockSignals(False)
        self._recompute(value)

    def _on_custom_slider_changed(self, value: int) -> None:
        self.n_spin.blockSignals(True)
        self.n_spin.setValue(value)
        self.n_spin.blockSignals(False)
        self._recompute(value)

    def _recompute(self, n: int) -> None:
        factor = 1.0 / n
        self.chosen_dimension_m = self.real_dimension_m * factor
        self.chosen_amplitude_m = self.real_amplitude_m * factor

        self.result_label.setText(
            f"Largest dimension: {self.chosen_dimension_m:,.2f} m   ·   "
            f"Amplitude: {self.chosen_amplitude_m:,.2f} m"
        )
        self.percent_label.setText(f"1 : {n:,}  ( {factor * 100:.4g} % )")

        over_dimension = self.chosen_dimension_m > TWINMOTION_MAX_LARGEST_DIMENSION_M
        over_amplitude = self.chosen_amplitude_m > TWINMOTION_MAX_AMPLITUDE_M
        if over_dimension or over_amplitude:
            parts = []
            if over_dimension:
                parts.append(
                    f"Largest dimension({self.chosen_dimension_m:,.0f}m)이 실측 확인된 "
                    f"상한({TWINMOTION_MAX_LARGEST_DIMENSION_M:,.0f}m)을 넘음"
                )
            if over_amplitude:
                parts.append(
                    f"Amplitude({self.chosen_amplitude_m:,.0f}m)가 실측 확인된 "
                    f"상한({TWINMOTION_MAX_AMPLITUDE_M:,.0f}m)을 넘음"
                )
            self.warning_label.setText(
                "⚠ " + " / ".join(parts) + ". 이 상한은 Twinmotion 공식 문서가 아니라 "
                "직접 입력해서 확인한 값이라, 지금 표시된 수치는 \"여기까지는 확인됨\"인 "
                "최대치일 뿐 — 이보다 크면 Twinmotion이 어떻게 반응할지(거부/자동조정 등) "
                "지원 여부가 확실하지 않습니다. N을 더 크게(비율을 더 작게) 조정하세요."
            )
            self.warning_label.setStyleSheet("color: #a0522d;")
        else:
            self.warning_label.setText("✓ 지금까지 실측 확인된 Twinmotion 입력 범위 안입니다.")
            self.warning_label.setStyleSheet("color: #3d6b57;")
