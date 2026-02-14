from __future__ import annotations

from typing import Optional

from qtpy.QtCore import QTimer, Qt
from qtpy.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class FocusControlsWidget(QGroupBox):
    """
    Reusable focus controls widget:
      - Status: device + current Z
      - Controls: step + up/down jog
      - Absolute: slider + field + apply
    """

    def __init__(self, core, title: str = "Focus", parent: QWidget | None = None):
        super().__init__(title, parent=parent)
        self.core = core
        self.dev: Optional[str] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.lbl_dev = QLabel("Device: -")
        self.lbl_pos = QLabel("Z: -")
        root.addWidget(self.lbl_dev)
        root.addWidget(self.lbl_pos)

        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)

        g.addWidget(QLabel("Step (um)"), 0, 0)
        self.step_um = QDoubleSpinBox()
        self.step_um.setDecimals(2)
        self.step_um.setRange(0.01, 20000.0)
        self.step_um.setValue(10.0)
        g.addWidget(self.step_um, 0, 1)

        self.btn_down = QPushButton("Down")
        self.btn_up = QPushButton("Up")
        self.btn_down.clicked.connect(lambda: self.jog(-float(self.step_um.value())))
        self.btn_up.clicked.connect(lambda: self.jog(+float(self.step_um.value())))
        g.addWidget(self.btn_down, 0, 2)
        g.addWidget(self.btn_up, 0, 3)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        g.addWidget(self.btn_refresh, 0, 4)

        g.addWidget(QLabel("Z slider"), 1, 0)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(-20000, 20000)
        self.slider.valueChanged.connect(self._slider_changed)
        g.addWidget(self.slider, 1, 1, 1, 4)

        g.addWidget(QLabel("Z (um)"), 2, 0)
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(2)
        self.spin.setRange(-20000.0, 20000.0)
        self.spin.valueChanged.connect(self._spin_changed)
        g.addWidget(self.spin, 2, 1)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self.apply)
        g.addWidget(self.btn_apply, 2, 2)

        root.addLayout(g)

        self.status = QLabel("Status: -")
        root.addWidget(self.status)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self._discover_device()
        self.refresh()

    def _discover_device(self):
        dev = None
        try:
            dev = str(self.core.getFocusDevice() or "").strip()
        except Exception:
            dev = None

        if not dev:
            try:
                devs = list(self.core.getLoadedDevices())
            except Exception:
                devs = []
            if "ManualFocus" in devs:
                dev = "ManualFocus"

        self.dev = dev if dev else None
        self.lbl_dev.setText(f"Device: {self.dev or '(none)'}")

    def _get_z(self) -> Optional[float]:
        if not self.dev:
            return None
        try:
            return float(self.core.getPosition(self.dev))
        except Exception:
            return None

    def _set_z(self, z: float) -> bool:
        if not self.dev:
            return False
        try:
            self.core.setPosition(self.dev, float(z))
            return True
        except Exception:
            return False

    def refresh(self):
        if not self.dev:
            self._discover_device()
        z = self._get_z()
        if z is None:
            self.lbl_pos.setText("Z: -")
            return
        self.lbl_pos.setText(f"Z: {z:.2f}")

        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(z)
        self.slider.setValue(int(round(z)))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)

    def jog(self, dz: float):
        z = self._get_z()
        if z is None:
            self.status.setText("Status: no focus device")
            return
        ok = self._set_z(float(z) + float(dz))
        self.status.setText(f"Status: jog dz={dz:+.2f} -> {'OK' if ok else 'FAIL'}")
        self.refresh()

    def _slider_changed(self, v: int):
        self.spin.blockSignals(True)
        self.spin.setValue(float(v))
        self.spin.blockSignals(False)

    def _spin_changed(self, v: float):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(float(v))))
        self.slider.blockSignals(False)

    def apply(self):
        ok = self._set_z(float(self.spin.value()))
        self.status.setText(f"Status: apply -> {'OK' if ok else 'FAIL'}")
        self.refresh()
