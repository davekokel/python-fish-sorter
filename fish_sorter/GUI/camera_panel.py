from __future__ import annotations

from typing import Optional

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

import numpy as np


class CameraPanel(QWidget):
    """
    Camera control panel:
      - Load MM config (optional if already loaded)
      - Exposure (ms)
      - Snap
      - Live (snap loop)
    Writes frames to a napari ViewerModel as a 'preview' image layer.
    """

    def __init__(self, core, viewer_model, load_mm_config_cb=None, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.core = core
        self.viewer_model = viewer_model
        self.load_mm_config_cb = load_mm_config_cb

        self._preview_layer = None
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._tick)

        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        self.lbl = QLabel("Camera")
        layout.addWidget(self.lbl, 0, 0, 1, 4)

        self.btn_load = QPushButton("Load MM Config")
        self.btn_load.clicked.connect(self._load_mm)
        layout.addWidget(self.btn_load, 1, 0)

        self.btn_live = QPushButton("Start Live")
        self.btn_live.clicked.connect(self._toggle_live)
        layout.addWidget(self.btn_live, 1, 1)

        self.btn_snap = QPushButton("Snap")
        self.btn_snap.clicked.connect(self.snap)
        layout.addWidget(self.btn_snap, 1, 2)

        self.exp_ms = QSpinBox()
        self.exp_ms.setRange(1, 5000)
        self.exp_ms.setValue(10)
        self.exp_ms.valueChanged.connect(self._set_exposure)
        layout.addWidget(QLabel("Exposure (ms)"), 2, 0)
        layout.addWidget(self.exp_ms, 2, 1)

        self.status = QLabel("Status: -")
        layout.addWidget(self.status, 3, 0, 1, 4)

        self.refresh_status()

    def _load_mm(self):
        if self.load_mm_config_cb is not None:
            try:
                self.load_mm_config_cb()
            except Exception as e:
                self.status.setText(f"Status: load failed: {e!r}")
                return
        self.refresh_status()

    def refresh_status(self):
        try:
            devs = list(self.core.getLoadedDevices())
        except Exception:
            devs = []
        self.status.setText(f"Status: {len(devs)} device(s) loaded")
        try:
            self.exp_ms.setValue(int(round(float(self.core.getExposure()))))
        except Exception:
            pass

    def _set_exposure(self):
        try:
            self.core.setExposure(float(self.exp_ms.value()))
        except Exception:
            pass

    def _ensure_preview_layer(self, arr):
        if self._preview_layer is None:
            try:
                self._preview_layer = self.viewer_model.add_image(arr, name="preview")
            except Exception:
                self._preview_layer = None

    def snap(self):
        try:
            self.core.snapImage()
            img = self.core.getImage()
            h = int(self.core.getImageHeight())
            w = int(self.core.getImageWidth())
            arr = np.asarray(img).reshape(h, w)
        except Exception as e:
            self.status.setText(f"Status: snap failed: {e!r}")
            return

        self._ensure_preview_layer(arr)
        if self._preview_layer is not None:
            try:
                self._preview_layer.data = arr
            except Exception:
                pass

    def _toggle_live(self):
        if self._timer.isActive():
            self._timer.stop()
            self.btn_live.setText("Start Live")
            return
        self._timer.start()
        self.btn_live.setText("Stop Live")

    def _tick(self):
        self.snap()
