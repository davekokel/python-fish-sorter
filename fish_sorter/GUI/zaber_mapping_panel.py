from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QInputDialog,
)

try:
    from serial.tools import list_ports
except Exception:
    list_ports = None


class _PortRow:
    def __init__(self, port: str):
        self.port = str(port)
        self.axis_combo: Optional[QComboBox] = None
        self.lbl_connected: Optional[QLabel] = None
        self.lbl_pos: Optional[QLabel] = None
        self.lbl_delta: Optional[QLabel] = None
        self.btn_connect: Optional[QPushButton] = None
        self.btn_read: Optional[QPushButton] = None
        self.btn_jog_m: Optional[QPushButton] = None
        self.btn_jog_p: Optional[QPushButton] = None

        self.connected: bool = False
        self.base_pos_mm: Optional[float] = None
        self.last_pos_mm: Optional[float] = None


class ZaberMappingPanel(QWidget):
    """
    Zaber Setup (Mapping Wizard) with presets as system truth.

    Busy-port fix:
      - If a live ZaberController (zc) is provided, this panel will NOT open COM ports.
      - Read/Jog uses zc.get_pos(axis) / zc.move_arm(axis, ...).

    Presets-as-truth:
      - Presets stored in qt_presets/zaber_mapping.json
      - Exactly one preset may be marked is_default=true
      - "Set selected as DEFAULT" writes zaber_config.json (compile step)

    zaber_config.json is treated as a compiled artifact used by the boot hardware layer.
    """

    AXES = ["", "x", "y", "p"]

    def __init__(self, repo_root: Path, zc=None, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.repo_root = repo_root
        self.zc = zc

        self.cfg_path = repo_root / "fish_sorter" / "configs" / "hardware" / "zaber_config.json"
        self.preset_path = repo_root / "qt_presets" / "zaber_mapping.json"
        self.preset_path.parent.mkdir(parents=True, exist_ok=True)

        self._det_zaber: list[tuple[str, str]] = []   # (port, desc)
        self._det_other: list[tuple[str, str]] = []   # (port, desc)

        self._rows: list[_PortRow] = []
        self._presets: list[dict] = []

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)

        self._build_ui()
        self.load_presets()
        self.load_compiled_config_into_rows()
        self.detect_ports()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(QLabel("Zaber Setup (Mapping Wizard)"))

        notes = QGroupBox("What to do here")
        nv = QVBoxLayout(notes)
        nv.setContentsMargins(8, 8, 8, 8)
        nv.addWidget(QLabel("Truth model: presets are the truth. One preset can be marked DEFAULT (system truth)."))
        nv.addWidget(QLabel("DEFAULT preset is compiled to zaber_config.json for controller startup."))
        nv.addWidget(QLabel("Busy-port note: in the running app, Zaber ports are already open. Jog/read uses the live controller."))
        root.addWidget(notes)
        # System compiled-config controls intentionally hidden (DEFAULT preset is system truth).
        det_box = QGroupBox("Detected ports")
        dv = QVBoxLayout(det_box)
        dv.setContentsMargins(8, 8, 8, 8)
        dv.setSpacing(8)

        self.chk_show_other = QCheckBox("Show non-Zaber ports")
        self.chk_show_other.setChecked(False)
        self.chk_show_other.stateChanged.connect(lambda *_: self._render_detect_lists())
        dv.addWidget(self.chk_show_other)

        btn_row = QWidget()
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(8)

        self.btn_detect = QPushButton("Detect Zaber ports")
        self.btn_detect.clicked.connect(self.detect_ports)
        bh.addWidget(self.btn_detect)

        bh.addStretch(1)
        dv.addWidget(btn_row)
        self.list_detect = QListWidget()
        self.list_detect.setSelectionMode(QAbstractItemView.ExtendedSelection)
        dv.addWidget(self.list_detect)

        self.lbl_ports = QLabel("Configured ports: -")
        dv.addWidget(self.lbl_ports)

        root.addWidget(det_box)

        mapper = QGroupBox("Value mapper (uses live controller; no COM re-open)")
        mv = QVBoxLayout(mapper)
        mv.setContentsMargins(8, 8, 8, 8)
        mv.setSpacing(8)

        top = QWidget()
        th = QHBoxLayout(top)
        th.setContentsMargins(0, 0, 0, 0)

        self.chk_enable_motion = QCheckBox("Enable motion tests (allows jog)")
        self.chk_enable_motion.setChecked(False)
        self.chk_enable_motion.stateChanged.connect(lambda *_: self._update_motion_enablement())
        th.addWidget(self.chk_enable_motion)

        th.addWidget(QLabel("Jog step (mm)"))
        self.step_mm = QDoubleSpinBox()
        self.step_mm.setDecimals(3)
        self.step_mm.setRange(0.001, 10.0)
        self.step_mm.setValue(0.250)
        th.addWidget(self.step_mm)

        self.btn_read_all = QPushButton("Read all")
        self.btn_read_all.clicked.connect(self._read_all)
        th.addWidget(self.btn_read_all)

        mv.addWidget(top)

        self.map_grid = QGridLayout()
        self.map_grid.setHorizontalSpacing(10)
        self.map_grid.setVerticalSpacing(8)

        self.map_grid.addWidget(QLabel("Port"), 0, 0)
        self.map_grid.addWidget(QLabel("Axis"), 0, 1)
        self.map_grid.addWidget(QLabel("Status"), 0, 2)
        self.map_grid.addWidget(QLabel("Pos (mm)"), 0, 3)
        self.map_grid.addWidget(QLabel("Δ (mm)"), 0, 4)
        self.map_grid.addWidget(QLabel("Actions"), 0, 5)

        mv.addLayout(self.map_grid)
        root.addWidget(mapper, stretch=1)

        presets = QGroupBox("Presets (SYSTEM TRUTH is the DEFAULT preset)")
        pv = QHBoxLayout(presets)
        pv.setContentsMargins(8, 8, 8, 8)

        self.preset_list = QListWidget()
        self.preset_list.setSelectionMode(QAbstractItemView.SingleSelection)
        pv.addWidget(self.preset_list, stretch=1)

        pr = QWidget()
        prv = QVBoxLayout(pr)
        prv.setContentsMargins(0, 0, 0, 0)
        prv.setSpacing(8)

        self.btn_preset_new = QPushButton("New")
        self.btn_preset_new.clicked.connect(self.preset_new)
        prv.addWidget(self.btn_preset_new)

        self.btn_preset_save = QPushButton("Save current → selected")
        self.btn_preset_save.clicked.connect(self.preset_save_current_into_selected)
        prv.addWidget(self.btn_preset_save)

        self.btn_preset_apply = QPushButton("Apply selected (to editor)")
        self.btn_preset_apply.clicked.connect(self.preset_apply_selected)
        prv.addWidget(self.btn_preset_apply)

        self.btn_preset_default = QPushButton("Set selected as DEFAULT")
        self.btn_preset_default.clicked.connect(self.preset_set_default)
        prv.addWidget(self.btn_preset_default)

        self.btn_preset_delete = QPushButton("Delete selected")
        self.btn_preset_delete.clicked.connect(self.preset_delete_selected)
        prv.addWidget(self.btn_preset_delete)

        prv.addStretch(1)
        pv.addWidget(pr)

        root.addWidget(presets)

        self.status = QLabel("Status: -")
        root.addWidget(self.status)

    # ---------------- Helpers: compiled config ----------------
    def _read_cfg(self) -> dict:
        if not self.cfg_path.exists():
            return {}
        try:
            return json.loads(self.cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_cfg(self, d: dict):
        try:
            self.cfg_path.write_text(json.dumps(d, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", repr(e))

    def load_compiled_config_into_rows(self):
        d = self._read_cfg()
        z = d.get("zaber_config", {}) if isinstance(d, dict) else {}
        ports = [str(p) for p in list(z.get("ports") or [])]
        p2a = z.get("port_to_axis") or {}
        if not isinstance(p2a, dict):
            p2a = {}
        self._set_configured_ports(ports, p2a=p2a)
        self.status.setText(f"Status: loaded compiled config ({len(ports)} port(s))")

    def compile_default_to_config(self):
        p = self._default_preset()
        if p is None:
            self.status.setText("Status: no DEFAULT preset set")
            return
        self._compile_preset_to_config(p)
        self.status.setText(f"Status: wrote compiled config from DEFAULT ({p.get('name')})")

    def _compile_preset_to_config(self, preset: dict):
        ports = [str(x) for x in (preset.get("ports") or [])]
        p2a = preset.get("port_to_axis") or {}
        if not isinstance(p2a, dict):
            p2a = {}
        d = self._read_cfg()
        if not isinstance(d, dict):
            d = {}
        if "zaber_config" not in d or not isinstance(d.get("zaber_config"), dict):
            d["zaber_config"] = {}
        z = d["zaber_config"]
        z["ports"] = ports
        z["port_to_axis"] = {str(k): str(v) for k, v in p2a.items()}
        self._write_cfg(d)
        self._set_configured_ports(ports, p2a=z["port_to_axis"])

    # ---------------- Detection ----------------
    def _configured_ports(self) -> list[str]:
        d = self._read_cfg()
        z = d.get("zaber_config", {}) if isinstance(d, dict) else {}
        return [str(p) for p in list(z.get("ports") or [])]

    def detect_ports(self):
        self._det_zaber = []
        self._det_other = []

        cfg_ports = set(self._configured_ports())

        ports = []
        if list_ports is not None:
            try:
                for p in list_ports.comports():
                    ports.append((str(p.device), str(getattr(p, "description", ""))))
            except Exception:
                ports = []

        for dev, desc in ports:
            if dev in cfg_ports:
                self._det_zaber.append((dev, desc + "  [CONFIGURED / IN-USE]"))
            else:
                self._det_other.append((dev, desc))

        self._render_detect_lists()
        self.status.setText(f"Status: detected {len(self._det_zaber)} configured Zaber port(s), {len(self._det_other)} other port(s)")

    def _render_detect_lists(self):
        self.list_detect.clear()

        for dev, desc in sorted(self._det_zaber, key=lambda x: x[0]):
            self.list_detect.addItem(QListWidgetItem(f"{dev}  |  {desc}"))

        if self.chk_show_other.isChecked():
            if self._det_other:
                self.list_detect.addItem(QListWidgetItem("---- non-Zaber ports ----"))
            for dev, desc in sorted(self._det_other, key=lambda x: x[0]):
                self.list_detect.addItem(QListWidgetItem(f"{dev}  |  {desc}"))

        self._refresh_ports_label()

    # ---------------- Rows / mapper ----------------
    def _clear_rows(self):
        while self.map_grid.count() > 6:
            item = self.map_grid.takeAt(6)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _set_configured_ports(self, ports: list[str], p2a: Optional[dict] = None):
        if p2a is None:
            p2a = {}
        self._rows = [_PortRow(p) for p in ports]
        self._render_rows(p2a=p2a)
        self._refresh_ports_label()
        self._timer.start()

    def _refresh_ports_label(self):
        ports = [r.port for r in self._rows]
        self.lbl_ports.setText("Configured ports: " + (", ".join(ports) if ports else "-"))

    def _render_rows(self, p2a: Optional[dict] = None):
        if p2a is None:
            p2a = {}
        self._clear_rows()

        for i, r in enumerate(self._rows, start=1):
            lbl_port = QLabel(r.port)

            combo = QComboBox()
            combo.addItems(self.AXES)
            cur = str(p2a.get(r.port, "") or "")
            idx = combo.findText(cur)
            if idx >= 0:
                combo.setCurrentIndex(idx)

            lbl_stat = QLabel("ready")
            lbl_pos = QLabel("-")
            lbl_dlt = QLabel("-")

            btn_read = QPushButton("Read")
            btn_jog_m = QPushButton("Jog -")
            btn_jog_p = QPushButton("Jog +")

            btn_read.clicked.connect(lambda _=None, rr=r: self._read_pos(rr))
            btn_jog_m.clicked.connect(lambda _=None, rr=r: self._jog(rr, -float(self.step_mm.value())))
            btn_jog_p.clicked.connect(lambda _=None, rr=r: self._jog(rr, +float(self.step_mm.value())))

            act = QWidget()
            ah = QHBoxLayout(act)
            ah.setContentsMargins(0, 0, 0, 0)
            ah.setSpacing(6)
            ah.addWidget(btn_read)
            ah.addWidget(btn_jog_m)
            ah.addWidget(btn_jog_p)

            self.map_grid.addWidget(lbl_port, i, 0)
            self.map_grid.addWidget(combo, i, 1)
            self.map_grid.addWidget(lbl_stat, i, 2)
            self.map_grid.addWidget(lbl_pos, i, 3)
            self.map_grid.addWidget(lbl_dlt, i, 4)
            self.map_grid.addWidget(act, i, 5)

            r.axis_combo = combo
            r.lbl_connected = lbl_stat
            r.lbl_pos = lbl_pos
            r.lbl_delta = lbl_dlt
            r.btn_read = btn_read
            r.btn_jog_m = btn_jog_m
            r.btn_jog_p = btn_jog_p

        self._update_motion_enablement()

    def _tick(self):
        self._update_motion_enablement()

    def _update_motion_enablement(self):
        enable_jog = bool(self.chk_enable_motion.isChecked())
        for r in self._rows:
            if r.btn_jog_m is not None:
                r.btn_jog_m.setEnabled(enable_jog)
            if r.btn_jog_p is not None:
                r.btn_jog_p.setEnabled(enable_jog)

    def _axis_for_row(self, r: _PortRow) -> Optional[str]:
        if r.axis_combo is None:
            return None
        a = str(r.axis_combo.currentText()).strip()
        return a if a else None

    def _read_pos(self, r: _PortRow):
        axis = self._axis_for_row(r)
        if not axis:
            self._set_row_status(r, "select axis", pos=None, delta=None)
            return
        if self.zc is None:
            self._set_row_status(r, "no live controller", pos=None, delta=None)
            return
        try:
            pos = float(self.zc.get_pos(axis))
            if r.base_pos_mm is None:
                r.base_pos_mm = pos
            r.last_pos_mm = pos
            dlt = pos - float(r.base_pos_mm)
            self._set_row_status(r, "OK", pos=pos, delta=dlt)
        except Exception as e:
            self._set_row_status(r, f"read failed: {e!r}", pos=None, delta=None)

    def _read_all(self):
        for r in self._rows:
            self._read_pos(r)
        self.status.setText("Status: read all attempted")

    def _jog(self, r: _PortRow, step_mm: float):
        if not self.chk_enable_motion.isChecked():
            self.status.setText("Status: motion tests disabled")
            return
        axis = self._axis_for_row(r)
        if not axis:
            self._set_row_status(r, "select axis", pos=None, delta=None)
            return
        if self.zc is None:
            self._set_row_status(r, "no live controller", pos=None, delta=None)
            return
        try:
            self.zc.move_arm(axis, float(step_mm), is_relative=True)
        except Exception as e:
            self._set_row_status(r, f"jog failed: {e!r}", pos=None, delta=None)
            return
        self._read_pos(r)

    def _set_row_status(self, r: _PortRow, msg: str, pos: Optional[float], delta: Optional[float]):
        if r.lbl_connected is not None:
            r.lbl_connected.setText(str(msg))
        if r.lbl_pos is not None:
            r.lbl_pos.setText("-" if pos is None else f"{pos:.3f}")
        if r.lbl_delta is not None:
            r.lbl_delta.setText("-" if delta is None else f"{delta:+.3f}")

    # ---------------- Presets as truth ----------------
    def load_presets(self):
        self._presets = []
        if self.preset_path.exists():
            try:
                self._presets = json.loads(self.preset_path.read_text(encoding="utf-8"))
            except Exception:
                self._presets = []

        if self._presets and not any(bool(p.get("is_default")) for p in self._presets):
            self._presets[0]["is_default"] = True
            self.save_presets()

        self._refresh_preset_list()

    def save_presets(self):
        try:
            self.preset_path.write_text(json.dumps(self._presets, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Preset save failed", repr(e))

    def _refresh_preset_list(self):
        self.preset_list.clear()
        for p in self._presets:
            name = str(p.get("name", "(unnamed)"))
            ports = [str(x) for x in (p.get("ports") or [])]
            p2a = p.get("port_to_axis") or {}
            if not isinstance(p2a, dict):
                p2a = {}
            is_def = bool(p.get("is_default", False))

            parts = []
            for port in ports:
                ax = str(p2a.get(port, "") or "")
                if ax:
                    parts.append(f"{port}->{ax}")
            mapping_str = " ".join(parts) if parts else "(no mapping)"
            label = ("[DEFAULT] " if is_def else "") + f"{name}  |  {mapping_str}"
            self.preset_list.addItem(QListWidgetItem(label))

    def _preset_selected_index(self) -> Optional[int]:
        items = self.preset_list.selectedIndexes()
        if not items:
            return None
        return int(items[0].row())

    def _snapshot_mapping(self) -> dict:
        ports = [r.port for r in self._rows]
        p2a = {}
        for r in self._rows:
            if r.axis_combo is not None:
                p2a[r.port] = str(r.axis_combo.currentText())
        return {"ports": ports, "port_to_axis": p2a}

    def _default_preset(self) -> Optional[dict]:
        for p in self._presets:
            if bool(p.get("is_default", False)):
                return p
        return self._presets[0] if self._presets else None

    def preset_new(self):
        name, ok = QInputDialog.getText(self, "New Zaber mapping preset", "Preset name:")
        if not ok or not name.strip():
            return
        snap = self._snapshot_mapping()
        self._presets.append({"name": name.strip(), "is_default": False, **snap})
        self.save_presets()
        self._refresh_preset_list()
        self.status.setText(f"Status: created preset {name.strip()}")

    def preset_save_current_into_selected(self):
        idx = self._preset_selected_index()
        if idx is None:
            return
        snap = self._snapshot_mapping()
        self._presets[idx]["ports"] = snap["ports"]
        self._presets[idx]["port_to_axis"] = snap["port_to_axis"]
        self.save_presets()
        self._refresh_preset_list()
        self.status.setText(f"Status: saved current into {self._presets[idx].get('name')}")

    def preset_apply_selected(self):
        idx = self._preset_selected_index()
        if idx is None:
            return
        p = self._presets[idx]
        ports = [str(x) for x in (p.get("ports") or [])]
        p2a = p.get("port_to_axis") or {}
        if not isinstance(p2a, dict):
            p2a = {}
        self._set_configured_ports(ports, p2a=p2a)
        self.status.setText(f"Status: applied preset to editor ({p.get('name')})")

    def preset_set_default(self):
        idx = self._preset_selected_index()
        if idx is None:
            return
        for p in self._presets:
            p["is_default"] = False
        self._presets[idx]["is_default"] = True
        self.save_presets()
        self._refresh_preset_list()

        self._compile_preset_to_config(self._presets[idx])
        self.status.setText(f"Status: set DEFAULT = {self._presets[idx].get('name')} and wrote compiled config (restart to apply)")

    def preset_delete_selected(self):
        idx = self._preset_selected_index()
        if idx is None:
            return
        was_default = bool(self._presets[idx].get("is_default", False))
        name = self._presets[idx].get("name", "(unnamed)")
        self._presets.pop(idx)

        if was_default and self._presets:
            self._presets[0]["is_default"] = True

        self.save_presets()
        self._refresh_preset_list()
        self.status.setText(f"Status: deleted preset {name}")

