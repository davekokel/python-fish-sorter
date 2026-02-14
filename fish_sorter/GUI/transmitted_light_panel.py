from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QDial,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QMessageBox,
    QToolButton,
    QGridLayout,
)

from fish_sorter.GUI.widgets.camera_controls import CameraControlsWidget


class _TileRow(QWidget):
    def __init__(self, title: str, options: list[str], on_apply, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.options = [str(o) for o in (options or [])]
        self.on_apply = on_apply

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        root.addWidget(QLabel(title))

        host = QWidget()
        g = QGridLayout(host)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(8)
        g.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        cols = 6
        for i, opt in enumerate(self.options):
            r = i // cols
            c = i % cols
            b = QToolButton()
            b.setText(opt)
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setMinimumHeight(38)
            b.setStyleSheet(
                "QToolButton{padding:8px;border:1px solid #aaa;border-radius:8px;}"
                "QToolButton:checked{border:2px solid #2a7fff;font-weight:bold;}"
            )
            b.clicked.connect(lambda _=False, x=opt: self.on_apply(x))
            g.addWidget(b, r, c)

        g.setRowStretch(r + 1, 1)
        g.setColumnStretch(cols, 1)

        root.addWidget(host)


class TransmittedLightPanel(QWidget):
    """
    Transmitted Light component:
      - CameraControlsWidget (ms/us exposure + gain/gamma/binning + optional live flag in payload)
      - TransmittedLamp.State tiles (if discoverable) with highlight sync
      - TL voltage float-aware slider/dial (0.1 steps) + spinbox
      - Presets store focus + camera + TL settings
    """

    def __init__(self, core, viewer_model, repo_root: Path, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.core = core

        self.store_path = (repo_root / "qt_presets" / "transmitted_light.json")
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        self.vol_device: Optional[str] = None
        self.vol_prop: Optional[str] = None
        self.vol_min: Optional[float] = None
        self.vol_max: Optional[float] = None

        self.state_device: Optional[str] = None
        self.state_prop: Optional[str] = None
        self.state_values: list[str] = []
        self._current_state: Optional[str] = None

        self.presets: list[dict] = []

        self._build_ui(core, viewer_model)
        self._load_store()
        self._discover_state_property()
        self._discover_voltage_property()
        self._sync_state_from_core()
        self._sync_voltage_widgets_from_core()

    # ---- focus helpers
    def _focus_device(self) -> Optional[str]:
        try:
            dev = str(self.core.getFocusDevice() or "").strip()
        except Exception:
            dev = ""
        if dev:
            return dev
        try:
            devs = list(self.core.getLoadedDevices())
        except Exception:
            devs = []
        if "ManualFocus" in devs:
            return "ManualFocus"
        return None

    def _get_focus_z(self) -> Optional[float]:
        dev = self._focus_device()
        if not dev:
            return None
        try:
            return float(self.core.getPosition(dev))
        except Exception:
            return None

    def _set_focus_z(self, z: float) -> bool:
        dev = self._focus_device()
        if not dev:
            return False
        try:
            self.core.setPosition(dev, float(z))
            return True
        except Exception:
            return False

    def _build_ui(self, core, viewer_model):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(QLabel("Transmitted Light"))

        self.camera = CameraControlsWidget(core, viewer_model, title="Camera")
        root.addWidget(self.camera)

        # Lamp state
        self.state_box = QGroupBox("Lamp State")
        sv = QVBoxLayout(self.state_box)
        self.lbl_state_detect = QLabel("Detecting state control...")
        sv.addWidget(self.lbl_state_detect)

        self.state_tiles_host = QWidget()
        self.state_tiles_layout = QVBoxLayout(self.state_tiles_host)
        self.state_tiles_layout.setContentsMargins(0, 0, 0, 0)
        sv.addWidget(self.state_tiles_host)
        root.addWidget(self.state_box)

        # Voltage
        vol_box = QGroupBox("Voltage / Intensity")
        v = QVBoxLayout(vol_box)

        self.lbl_detect = QLabel("Detecting voltage control...")
        v.addWidget(self.lbl_detect)

        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)

        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(1)
        self.spin.setRange(0.0, 5000.0)
        self.spin.valueChanged.connect(self._spin_changed)
        rl.addWidget(self.spin)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 50000)
        self.slider.valueChanged.connect(self._slider_changed)
        rl.addWidget(self.slider, stretch=1)

        self.dial = QDial()
        self.dial.setRange(0, 50000)
        self.dial.valueChanged.connect(self._dial_changed)
        rl.addWidget(self.dial)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self.apply_voltage)
        rl.addWidget(self.btn_apply)

        v.addWidget(row)
        root.addWidget(vol_box)

        # Presets
        presets_box = QGroupBox("Qt Presets")
        pb = QHBoxLayout(presets_box)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemSelectionChanged.connect(self._preset_selected)
        pb.addWidget(self.list, stretch=1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        self.btn_new = QPushButton("New")
        self.btn_new.clicked.connect(self._preset_new)
        rv.addWidget(self.btn_new)

        self.btn_save = QPushButton("Save current → selected")
        self.btn_save.clicked.connect(self._preset_save_current_into_selected)
        rv.addWidget(self.btn_save)

        self.btn_apply_preset = QPushButton("Apply selected")
        self.btn_apply_preset.clicked.connect(self._preset_apply_selected)
        rv.addWidget(self.btn_apply_preset)

        self.btn_delete = QPushButton("Delete selected")
        self.btn_delete.clicked.connect(self._preset_delete_selected)
        rv.addWidget(self.btn_delete)

        self.chk_apply_live = QCheckBox("Apply live state")
        self.chk_apply_live.setChecked(False)
        rv.addWidget(self.chk_apply_live)

        rv.addStretch(1)
        pb.addWidget(right)

        root.addWidget(presets_box, stretch=1)

        self.status = QLabel("Status: -")
        root.addWidget(self.status)

    # ----------------
    # State
    # ----------------
    def _discover_state_property(self):
        dev = "TransmittedLamp"
        try:
            devs = list(self.core.getLoadedDevices())
        except Exception:
            devs = []

        if dev not in devs:
            self.lbl_state_detect.setText("State control: TransmittedLamp not loaded")
            return

        try:
            props = [str(p) for p in list(self.core.getDevicePropertyNames(dev))]
        except Exception:
            props = []

        candidates = []
        for p in props:
            if p.lower() == "state":
                candidates = [p]
                break
        if not candidates:
            candidates = [p for p in props if "state" in p.lower()]

        for p in candidates:
            try:
                allowed = [str(x) for x in list(self.core.getAllowedPropertyValues(dev, p))]
            except Exception:
                allowed = []
            if allowed:
                self.state_device = dev
                self.state_prop = p
                self.state_values = allowed
                self.lbl_state_detect.setText(f"State control: {dev}.{p}")
                self._render_state_tiles()
                return

        self.lbl_state_detect.setText("State control: not found (no allowed values)")
        self.state_device = None
        self.state_prop = None
        self.state_values = []

    def _render_state_tiles(self):
        while self.state_tiles_layout.count():
            item = self.state_tiles_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        if not (self.state_device and self.state_prop and self.state_values):
            self.state_tiles_layout.addWidget(QLabel("No state values available"))
            return

        self.state_tiles_layout.addWidget(
            _TileRow("TransmittedLamp state", self.state_values, lambda val: self.apply_state(val))
        )

    def _set_state_tile_checked(self, val: str | None):
        if val is None:
            return
        target = str(val).strip()
        try:
            buttons = self.state_tiles_host.findChildren(QToolButton)
        except Exception:
            return
        for b in buttons:
            try:
                if str(b.text()).strip() == target:
                    b.setChecked(True)
                    return
            except Exception:
                pass

    def _sync_state_from_core(self):
        if not (self.state_device and self.state_prop):
            return
        try:
            cur = str(self.core.getProperty(self.state_device, self.state_prop))
        except Exception:
            cur = None
        self._current_state = cur
        self._set_state_tile_checked(cur)

    def apply_state(self, val: str):
        if not (self.state_device and self.state_prop):
            self.status.setText("Status: no state property found")
            return
        try:
            self.core.setProperty(self.state_device, self.state_prop, str(val))
            self._current_state = str(val)
            self._set_state_tile_checked(val)
            self.status.setText(f"Status: state={val}")
        except Exception as e:
            self.status.setText(f"Status: set state failed: {e!r}")

    # ----------------
    # Voltage
    # ----------------
    def _discover_voltage_property(self):
        try:
            devs = list(self.core.getLoadedDevices())
        except Exception:
            devs = []

        candidates = []
        if "TransmittedLamp" in devs:
            candidates.append("TransmittedLamp")
        candidates.extend([d for d in devs if d not in candidates])

        for dev in candidates:
            try:
                props = list(self.core.getDevicePropertyNames(dev))
            except Exception:
                continue

            for p in props:
                pl = str(p).lower()
                if ("volt" in pl) or ("intens" in pl) or ("level" in pl) or ("power" in pl):
                    try:
                        cur = self.core.getProperty(dev, p)
                    except Exception:
                        continue
                    m = re.search(r"([-+]?\d+(\.\d+)?)", str(cur))
                    if not m:
                        continue

                    lo = None
                    hi = None
                    try:
                        if bool(self.core.hasPropertyLimits(dev, p)):
                            lo = float(self.core.getPropertyLowerLimit(dev, p))
                            hi = float(self.core.getPropertyUpperLimit(dev, p))
                    except Exception:
                        lo = None
                        hi = None

                    self.vol_device = str(dev)
                    self.vol_prop = str(p)
                    self.vol_min = lo
                    self.vol_max = hi
                    self._configure_voltage_widgets()
                    self.lbl_detect.setText(f"Voltage control: {self.vol_device}.{self.vol_prop} (range: {self.vol_min}..{self.vol_max})")
                    return

        self.lbl_detect.setText("Voltage control: not found (will not apply voltage)")
        self.vol_device = None
        self.vol_prop = None
        self.vol_min = None
        self.vol_max = None

    def _configure_voltage_widgets(self):
        lo = self.vol_min if self.vol_min is not None else 0.0
        hi = self.vol_max if self.vol_max is not None else 5000.0
        if hi <= lo:
            hi = lo + 1.0

        self.spin.blockSignals(True)
        self.spin.setRange(lo, hi)
        self.spin.blockSignals(False)

        self.slider.blockSignals(True)
        self.slider.setRange(int(round(lo * 10)), int(round(hi * 10)))
        self.slider.blockSignals(False)

        self.dial.blockSignals(True)
        self.dial.setRange(int(round(lo * 10)), int(round(hi * 10)))
        self.dial.blockSignals(False)

    def _read_voltage_from_core(self) -> Optional[float]:
        if not self.vol_device or not self.vol_prop:
            return None
        try:
            cur = self.core.getProperty(self.vol_device, self.vol_prop)
        except Exception:
            return None
        m = re.search(r"([-+]?\d+(\.\d+)?)", str(cur))
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def _sync_voltage_widgets_from_core(self):
        v = self._read_voltage_from_core()
        if v is None:
            return
        self._set_voltage_widgets(v)

    def _set_voltage_widgets(self, v: float):
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.dial.blockSignals(True)

        self.spin.setValue(float(v))
        self.slider.setValue(int(round(float(v) * 10)))
        self.dial.setValue(int(round(float(v) * 10)))

        self.spin.blockSignals(False)
        self.slider.blockSignals(False)
        self.dial.blockSignals(False)

        self.status.setText(f"Status: state={self._current_state or '-'}, voltage={float(v):.1f}")

    def _spin_changed(self, v: float):
        self._set_voltage_widgets(v)

    def _slider_changed(self, v: int):
        self._set_voltage_widgets(float(v) / 10.0)

    def _dial_changed(self, v: int):
        self._set_voltage_widgets(float(v) / 10.0)

    def apply_voltage(self):
        if not self.vol_device or not self.vol_prop:
            self.status.setText("Status: no voltage property found")
            return
        v = float(self.spin.value())
        try:
            self.core.setProperty(self.vol_device, self.vol_prop, str(v))
            self.status.setText(f"Status: set {self.vol_device}.{self.vol_prop}={v:.1f}")
        except Exception as e:
            self.status.setText(f"Status: setProperty failed: {e!r}")

    # ----------------
    # Presets
    # ----------------
    def _load_store(self):
        self.presets = []
        if self.store_path.exists():
            try:
                self.presets = json.loads(self.store_path.read_text(encoding="utf-8"))
            except Exception:
                self.presets = []
        self._refresh_list()

    def _save_store(self):
        try:
            self.store_path.write_text(json.dumps(self.presets, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", repr(e))

    def _refresh_list(self):
        self.list.clear()
        for p in self.presets:
            name = p.get("name", "(unnamed)")
            parts = []
            if p.get("focus_z") is not None:
                parts.append(f"focus_z={p.get('focus_z')}")
            if p.get("state") is not None:
                parts.append(f"state={p.get('state')}")
            if "voltage" in p:
                parts.append(f"voltage={p.get('voltage')}")
            cam = p.get("camera", {})
            if isinstance(cam, dict):
                if "exposure_value" in cam and "exposure_unit" in cam:
                    parts.append(f"exp={cam.get('exposure_value')} {cam.get('exposure_unit')}")
                if "binning" in cam:
                    parts.append(f"bin={cam.get('binning')}")
                if "gain" in cam:
                    parts.append(f"gain={cam.get('gain')}")
                if "gamma" in cam:
                    parts.append(f"gamma={cam.get('gamma')}")
                if "live" in cam:
                    parts.append(f"live={cam.get('live')}")
                if "live_rate_ms" in cam:
                    parts.append(f"rate_ms={cam.get('live_rate_ms')}")
                if "preview_downsample" in cam:
                    parts.append(f"preview={cam.get('preview_downsample')}x")
            label = name if not parts else (name + "  |  " + "  ".join(parts))
            self.list.addItem(QListWidgetItem(label))

    def _selected_index(self) -> Optional[int]:
        items = self.list.selectedIndexes()
        if not items:
            return None
        return int(items[0].row())

    def _preset_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        self.status.setText(f"Status: selected preset {self.presets[idx].get('name')}")

    def _preset_new(self):
        name, ok = QInputDialog.getText(self, "New preset", "Preset name:")
        if not ok or not name.strip():
            return
        self.presets.append(
            {
                "name": name.strip(),
                "focus_z": self._get_focus_z(),
                "state": self._current_state,
                "voltage": float(self.spin.value()),
                "camera": self.camera.preset_payload(),
            }
        )
        self._save_store()
        self._refresh_list()

    def _preset_save_current_into_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        p = self.presets[idx]
        p["focus_z"] = self._get_focus_z()
        p["state"] = self._current_state
        p["voltage"] = float(self.spin.value())
        p["camera"] = self.camera.preset_payload()
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: saved current into {p.get('name')}")

    def _preset_apply_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        self._apply_preset_obj(self.presets[idx])

    def _preset_delete_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        name = self.presets[idx].get("name", "(unnamed)")
        self.presets.pop(idx)
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: deleted {name}")

    def apply_named_preset(self, name: str):
        for p in self.presets:
            if str(p.get("name", "")).strip() == str(name).strip():
                self._apply_preset_obj(p)
                return
        self.status.setText(f"Status: preset not found: {name!r}")

    def _apply_preset_obj(self, p: dict):
        fz = p.get("focus_z", None)
        if fz is not None:
            try:
                self._set_focus_z(float(fz))
            except Exception:
                pass

        st = p.get("state", None)
        if st is not None:
            try:
                self.apply_state(str(st))
            except Exception:
                pass

        v = p.get("voltage", None)
        if v is not None:
            try:
                self._set_voltage_widgets(float(v))
                self.apply_voltage()
            except Exception:
                pass

        cam = p.get("camera", None)
        if isinstance(cam, dict):
            try:
                self.camera.apply_payload(cam, apply_live=bool(self.chk_apply_live.isChecked()))
            except Exception:
                pass

