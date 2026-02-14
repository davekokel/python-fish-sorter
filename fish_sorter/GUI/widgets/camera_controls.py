from __future__ import annotations

import re
from typing import Optional

import numpy as np
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class CameraControlsWidget(QGroupBox):
    """
    Reusable camera controls widget (MMCore-backed):

      - Live/Stop (snap loop)
      - Snap
      - Live rate control (timer interval)
      - Preview downsample (1x/2x/4x)
      - Exposure value + unit (ms/us)
      - Best-effort: Binning + other "nice" camera props when discoverable
      - Display controls for the napari 'preview' layer:
          - Auto contrast (percentile-based)
          - Lock contrast (keeps contrast_limits fixed)
          - Auto contrast on snap (optional)
          - Invert (gray_r)

      - Advanced camera properties (dynamic):
          - pick any camera property
          - view current value
          - set via allowed-values dropdown (if enum) or free text (if not)

    Writes images into viewer_model as 'preview' layer.

    Preset behavior:
      - preset_payload includes:
          live, live_rate_ms, preview_downsample
          exposure_value/unit, binning
          display: lock/auto_on_snap/p_lo/p_hi/invert/contrast_limits
      - apply_payload(payload, apply_live=False) will NOT change live state unless apply_live=True
    """

    LIVE_RATES = [
        ("Slow", 500),
        ("Normal", 250),
        ("Fast", 100),
    ]

    DOWNSAMPLE = [
        ("1x", 1),
        ("2x", 2),
        ("4x", 4),
    ]

    def __init__(self, core, viewer_model, title: str = "Camera", parent: QWidget | None = None):
        super().__init__(title, parent=parent)
        self.core = core
        self.viewer_model = viewer_model

        self._preview_layer = None
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(250)
        self._live_timer.timeout.connect(self._live_tick)

        self._in_flight = False

        self.camera_device: Optional[str] = None
        self.prop_binning: Optional[str] = None
        self.prop_exposure_us: Optional[str] = None

        self._build_ui()
        self._discover_camera()
        self._sync_from_core()

    # ---------------- UI ----------------
    def _build_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        # Row 0: Live / Snap / Live rate / Preview downsample
        self.btn_live = QPushButton("Start Live")
        self.btn_live.clicked.connect(self.toggle_live)
        layout.addWidget(self.btn_live, 0, 0)

        self.btn_snap = QPushButton("Snap")
        self.btn_snap.clicked.connect(self.snap)
        layout.addWidget(self.btn_snap, 0, 1)

        layout.addWidget(QLabel("Live rate"), 0, 2)
        self.live_rate = QComboBox()
        for name, ms in self.LIVE_RATES:
            self.live_rate.addItem(name, ms)
        self.live_rate.setCurrentIndex(1)  # Normal
        self.live_rate.currentIndexChanged.connect(self._set_live_rate_from_ui)
        layout.addWidget(self.live_rate, 0, 3)

        layout.addWidget(QLabel("Preview"), 0, 4)
        self.preview_ds = QComboBox()
        for name, k in self.DOWNSAMPLE:
            self.preview_ds.addItem(name, k)
        self.preview_ds.setCurrentIndex(0)  # 1x
        layout.addWidget(self.preview_ds, 0, 5)

        # Row 1: Exposure + Apply
        layout.addWidget(QLabel("Exposure"), 1, 0)
        self.exp_val = QDoubleSpinBox()
        self.exp_val.setDecimals(3)
        self.exp_val.setRange(0.001, 5000.0)
        self.exp_val.setValue(10.0)
        layout.addWidget(self.exp_val, 1, 1)

        self.exp_unit = QComboBox()
        self.exp_unit.addItems(["ms", "us"])
        layout.addWidget(self.exp_unit, 1, 2)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self.apply)
        layout.addWidget(self.btn_apply, 1, 3)

        # Optional: binning
        self.lbl_bin = QLabel("Binning")
        self.binning = QComboBox()
        layout.addWidget(self.lbl_bin, 1, 4)
        layout.addWidget(self.binning, 1, 5)

        # Row 2: Display controls (preview layer)
        disp = QGroupBox("Display (preview layer)")
        dh = QHBoxLayout(disp)
        dh.setContentsMargins(8, 8, 8, 8)
        dh.setSpacing(10)

        self.chk_lock_contrast = QCheckBox("Lock contrast")
        self.chk_lock_contrast.setChecked(True)
        self.chk_lock_contrast.stateChanged.connect(self._on_lock_changed)
        dh.addWidget(self.chk_lock_contrast)

        self.chk_auto_on_snap = QCheckBox("Auto on snap")
        self.chk_auto_on_snap.setChecked(False)
        dh.addWidget(self.chk_auto_on_snap)

        dh.addWidget(QLabel("p_lo"))
        self.p_lo = QDoubleSpinBox()
        self.p_lo.setDecimals(2)
        self.p_lo.setRange(0.0, 49.0)
        self.p_lo.setValue(1.0)
        dh.addWidget(self.p_lo)

        dh.addWidget(QLabel("p_hi"))
        self.p_hi = QDoubleSpinBox()
        self.p_hi.setDecimals(2)
        self.p_hi.setRange(51.0, 100.0)
        self.p_hi.setValue(99.0)
        dh.addWidget(self.p_hi)

        self.btn_auto = QPushButton("Auto now")
        self.btn_auto.clicked.connect(self.auto_contrast_now)
        dh.addWidget(self.btn_auto)

        self.chk_invert = QCheckBox("Invert")
        self.chk_invert.setChecked(False)
        self.chk_invert.stateChanged.connect(self._apply_invert_to_layer)
        dh.addWidget(self.chk_invert)

        layout.addWidget(disp, 2, 0, 1, 6)

        # Row 3: Advanced camera properties
        adv = QGroupBox("Advanced camera properties")
        ag = QGridLayout(adv)
        ag.setContentsMargins(8, 8, 8, 8)
        ag.setHorizontalSpacing(10)
        ag.setVerticalSpacing(8)

        self.btn_refresh_props = QPushButton("Refresh props")
        self.btn_refresh_props.clicked.connect(self._refresh_props_ui)
        ag.addWidget(self.btn_refresh_props, 0, 0)

        ag.addWidget(QLabel("Property"), 0, 1)
        self.prop_name = QComboBox()
        self.prop_name.currentIndexChanged.connect(self._prop_selected)
        ag.addWidget(self.prop_name, 0, 2, 1, 2)

        ag.addWidget(QLabel("Current"), 1, 0)
        self.prop_cur = QLabel("-")
        ag.addWidget(self.prop_cur, 1, 1, 1, 3)

        ag.addWidget(QLabel("Set"), 2, 0)
        self.prop_set_enum = QComboBox()
        ag.addWidget(self.prop_set_enum, 2, 1, 1, 2)

        self.prop_set_text = QLineEdit()
        ag.addWidget(self.prop_set_text, 2, 1, 1, 2)

        self.btn_prop_apply = QPushButton("Apply prop")
        self.btn_prop_apply.clicked.connect(self._apply_selected_property)
        ag.addWidget(self.btn_prop_apply, 2, 3)

        # default: hide set widgets until we know if enum/free
        self.prop_set_enum.hide()
        self.prop_set_text.hide()

        layout.addWidget(adv, 3, 0, 1, 6)

        # Row 4: Status
        self.status = QLabel("Status: -")
        layout.addWidget(self.status, 4, 0, 1, 6)

    # ---------------- Live loop perf ----------------
    def _set_live_rate_from_ui(self):
        try:
            ms = int(self.live_rate.currentData())
        except Exception:
            ms = 250
        self._live_timer.setInterval(max(50, ms))

    def is_live(self) -> bool:
        return bool(self._live_timer.isActive())

    def start_live(self):
        self._set_live_rate_from_ui()
        if not self._live_timer.isActive():
            self._live_timer.start()
            self.btn_live.setText("Stop Live")

    def stop_live(self):
        if self._live_timer.isActive():
            self._live_timer.stop()
            self.btn_live.setText("Start Live")

    # ---------------- Preview layer ----------------
    def _ensure_preview_layer(self, arr):
        if self._preview_layer is None:
            try:
                self._preview_layer = self.viewer_model.add_image(arr, name="preview")
            except Exception:
                self._preview_layer = None
                return

            # On creation: set invert colormap if requested
            self._apply_invert_to_layer()

            # On creation: establish contrast if lock is enabled
            if self.chk_lock_contrast.isChecked():
                self.auto_contrast_now()

    def _apply_invert_to_layer(self):
        if self._preview_layer is None:
            return
        try:
            self._preview_layer.colormap = "gray_r" if self.chk_invert.isChecked() else "gray"
        except Exception:
            pass

    def _downsample(self, arr: np.ndarray) -> np.ndarray:
        try:
            k = int(self.preview_ds.currentData())
        except Exception:
            k = 1
        if k <= 1:
            return arr
        return arr[::k, ::k]

    def _compute_contrast_limits(self, arr: np.ndarray) -> Optional[tuple[float, float]]:
        try:
            lo = float(self.p_lo.value())
            hi = float(self.p_hi.value())
            if not (0.0 <= lo < hi <= 100.0):
                return None
            a = np.asarray(arr)
            if a.size == 0:
                return None
            vmin = float(np.percentile(a, lo))
            vmax = float(np.percentile(a, hi))
            if vmax <= vmin:
                vmax = vmin + 1.0
            return vmin, vmax
        except Exception:
            return None

    def auto_contrast_now(self):
        if self._preview_layer is None:
            self.status.setText("Status: auto-contrast needs preview layer")
            return
        try:
            arr = self._preview_layer.data
        except Exception:
            return
        lim = self._compute_contrast_limits(arr)
        if lim is None:
            return
        try:
            self._preview_layer.contrast_limits = lim
        except Exception:
            pass

    def _on_lock_changed(self):
        # If locking was just enabled, establish limits now
        if self.chk_lock_contrast.isChecked():
            self.auto_contrast_now()

    # ---------------- Camera discovery + basic props ----------------
    def _discover_camera(self):
        dev = None
        try:
            dev = str(self.core.getCameraDevice() or "").strip()
        except Exception:
            dev = None

        if not dev:
            try:
                devs = [str(d) for d in list(self.core.getLoadedDevices())]
            except Exception:
                devs = []
            for d in devs:
                if "cam" in d.lower():
                    dev = d
                    break

        self.camera_device = dev if dev else None
        self.prop_binning = None
        self.prop_exposure_us = None

        if not self.camera_device:
            self.lbl_bin.hide()
            self.binning.hide()
            self.status.setText("Status: camera device not found")
            self._refresh_props_ui()
            return

        try:
            props = [str(p) for p in list(self.core.getDevicePropertyNames(self.camera_device))]
        except Exception:
            props = []

        for p in props:
            pl = p.lower()
            if "exposure" in pl and ("us" in pl or "µs" in pl):
                self.prop_exposure_us = p
                break

        for p in props:
            pl = p.lower()
            if self.prop_binning is None and "bin" in pl:
                self.prop_binning = p

        # Configure binning dropdown if possible
        if self.camera_device and self.prop_binning:
            self.binning.clear()
            allowed = []
            try:
                allowed = [str(v) for v in list(self.core.getAllowedPropertyValues(self.camera_device, self.prop_binning))]
            except Exception:
                allowed = []
            if allowed:
                self.binning.addItems(allowed)
                self.lbl_bin.show()
                self.binning.show()
            else:
                self.lbl_bin.hide()
                self.binning.hide()
        else:
            self.lbl_bin.hide()
            self.binning.hide()

        self._refresh_props_ui()

    def _sync_from_core(self):
        try:
            ms = float(self.core.getExposure())
            self.exp_val.setValue(ms)
            self.exp_unit.setCurrentText("ms")
        except Exception:
            pass

        if self.camera_device and self.prop_binning:
            try:
                v = str(self.core.getProperty(self.camera_device, self.prop_binning))
                idx = self.binning.findText(v)
                if idx >= 0:
                    self.binning.setCurrentIndex(idx)
            except Exception:
                pass

        self.status.setText(f"Status: camera={self.camera_device or '-'}")

    def current_exposure_ms(self) -> float:
        val = float(self.exp_val.value())
        unit = str(self.exp_unit.currentText())
        return (val / 1000.0) if unit == "us" else val

    def apply(self):
        # exposure
        try:
            ms = self.current_exposure_ms()
            self.core.setExposure(float(ms))
        except Exception:
            pass

        # optional direct us property (if exists)
        if self.camera_device and self.prop_exposure_us and str(self.exp_unit.currentText()) == "us":
            try:
                self.core.setProperty(self.camera_device, self.prop_exposure_us, str(float(self.exp_val.value())))
            except Exception:
                pass

        # binning
        if self.camera_device and self.prop_binning and self.binning.count() > 0:
            try:
                self.core.setProperty(self.camera_device, self.prop_binning, str(self.binning.currentText()))
            except Exception:
                pass

        self.status.setText(f"Status: applied (exposure={self.exp_val.value()} {self.exp_unit.currentText()})")

    # ---------------- Snapshot / live ----------------
    def snap(self):
        if self._in_flight:
            return
        self._in_flight = True
        try:
            self.core.snapImage()
            img = self.core.getImage()
            h = int(self.core.getImageHeight())
            w = int(self.core.getImageWidth())
            arr = np.asarray(img).reshape(h, w)
            arr = self._downsample(arr)
        except Exception as e:
            self.status.setText(f"Status: snap failed: {e!r}")
            self._in_flight = False
            return

        self._ensure_preview_layer(arr)

        # update layer data
        if self._preview_layer is not None:
            try:
                self._preview_layer.data = arr
            except Exception:
                pass

            # display behavior
            if self.chk_auto_on_snap.isChecked():
                self.auto_contrast_now()

        self._in_flight = False

    def toggle_live(self):
        if self._live_timer.isActive():
            self.stop_live()
            return
        self.start_live()

    def _live_tick(self):
        self.snap()

    # ---------------- Advanced camera properties ----------------
    def _refresh_props_ui(self):
        self.prop_name.clear()
        self.prop_cur.setText("-")
        self.prop_set_enum.clear()
        self.prop_set_text.setText("")

        if not self.camera_device:
            self.prop_name.addItem("(no camera)")
            self.prop_set_enum.hide()
            self.prop_set_text.hide()
            return

        try:
            props = [str(p) for p in list(self.core.getDevicePropertyNames(self.camera_device))]
        except Exception:
            props = []

        props = sorted(props)
        if not props:
            self.prop_name.addItem("(no properties)")
            self.prop_set_enum.hide()
            self.prop_set_text.hide()
            return

        self.prop_name.addItems(props)
        self._prop_selected()

    def _prop_selected(self):
        if not self.camera_device:
            return
        pname = str(self.prop_name.currentText())
        if not pname or pname.startswith("("):
            return

        try:
            cur = self.core.getProperty(self.camera_device, pname)
        except Exception as e:
            self.prop_cur.setText(f"getProperty failed: {e!r}")
            self.prop_set_enum.hide()
            self.prop_set_text.hide()
            return

        self.prop_cur.setText(str(cur))

        # allowed values?
        allowed = []
        try:
            allowed = [str(v) for v in list(self.core.getAllowedPropertyValues(self.camera_device, pname))]
        except Exception:
            allowed = []

        if allowed:
            self.prop_set_text.hide()
            self.prop_set_enum.show()
            self.prop_set_enum.clear()
            self.prop_set_enum.addItems(allowed)
            idx = self.prop_set_enum.findText(str(cur))
            if idx >= 0:
                self.prop_set_enum.setCurrentIndex(idx)
        else:
            self.prop_set_enum.hide()
            self.prop_set_text.show()
            self.prop_set_text.setText(str(cur))

    def _apply_selected_property(self):
        if not self.camera_device:
            return
        pname = str(self.prop_name.currentText())
        if not pname or pname.startswith("("):
            return

        if self.prop_set_enum.isVisible():
            val = str(self.prop_set_enum.currentText())
        else:
            val = str(self.prop_set_text.text())

        try:
            self.core.setProperty(self.camera_device, pname, val)
            self.status.setText(f"Status: set {pname}={val}")
        except Exception as e:
            self.status.setText(f"Status: setProperty failed: {e!r}")

        self._prop_selected()

    # ---------------- Presets ----------------
    def preset_payload(self) -> dict:
        payload = {
            "live": bool(self.is_live()),
            "live_rate_ms": int(self._live_timer.interval()),
            "preview_downsample": int(self.preview_ds.currentData()),
            "exposure_value": float(self.exp_val.value()),
            "exposure_unit": str(self.exp_unit.currentText()),
            "display": {
                "lock_contrast": bool(self.chk_lock_contrast.isChecked()),
                "auto_on_snap": bool(self.chk_auto_on_snap.isChecked()),
                "p_lo": float(self.p_lo.value()),
                "p_hi": float(self.p_hi.value()),
                "invert": bool(self.chk_invert.isChecked()),
            },
        }

        # include locked limits if present
        if self._preview_layer is not None:
            try:
                payload["display"]["contrast_limits"] = list(self._preview_layer.contrast_limits)
            except Exception:
                pass

        # binning if available
        if self.camera_device and self.prop_binning and self.binning.count() > 0:
            payload["binning"] = str(self.binning.currentText())

        return payload

    def apply_payload(self, payload: dict, apply_live: bool = False):
        if not isinstance(payload, dict):
            return

        # perf settings
        if "live_rate_ms" in payload:
            try:
                ms = int(payload["live_rate_ms"])
                if ms >= 50:
                    best = None
                    for i in range(self.live_rate.count()):
                        if int(self.live_rate.itemData(i)) == ms:
                            best = i
                            break
                    if best is not None:
                        self.live_rate.setCurrentIndex(best)
                    self._live_timer.setInterval(ms)
            except Exception:
                pass

        if "preview_downsample" in payload:
            try:
                k = int(payload["preview_downsample"])
                best = None
                for i in range(self.preview_ds.count()):
                    if int(self.preview_ds.itemData(i)) == k:
                        best = i
                        break
                if best is not None:
                    self.preview_ds.setCurrentIndex(best)
            except Exception:
                pass

        # exposure
        if "exposure_value" in payload and "exposure_unit" in payload:
            try:
                self.exp_val.setValue(float(payload["exposure_value"]))
                self.exp_unit.setCurrentText(str(payload["exposure_unit"]))
            except Exception:
                pass

        # binning
        if "binning" in payload and self.camera_device and self.prop_binning and self.binning.count() > 0:
            try:
                idx = self.binning.findText(str(payload["binning"]))
                if idx >= 0:
                    self.binning.setCurrentIndex(idx)
            except Exception:
                pass

        # display settings
        disp = payload.get("display", None)
        if isinstance(disp, dict):
            try:
                self.chk_lock_contrast.setChecked(bool(disp.get("lock_contrast", True)))
            except Exception:
                pass
            try:
                self.chk_auto_on_snap.setChecked(bool(disp.get("auto_on_snap", False)))
            except Exception:
                pass
            try:
                self.p_lo.setValue(float(disp.get("p_lo", 1.0)))
            except Exception:
                pass
            try:
                self.p_hi.setValue(float(disp.get("p_hi", 99.0)))
            except Exception:
                pass
            try:
                self.chk_invert.setChecked(bool(disp.get("invert", False)))
            except Exception:
                pass

            # if preview exists and lock is on, restore limits if present
            if self._preview_layer is not None and self.chk_lock_contrast.isChecked():
                cl = disp.get("contrast_limits", None)
                if isinstance(cl, (list, tuple)) and len(cl) == 2:
                    try:
                        self._preview_layer.contrast_limits = (float(cl[0]), float(cl[1]))
                    except Exception:
                        pass

        self.apply()

        # live operational; only if explicitly requested
        if apply_live and ("live" in payload):
            try:
                want = bool(payload.get("live"))
                if want:
                    self.start_live()
                else:
                    self.stop_live()
            except Exception:
                pass
