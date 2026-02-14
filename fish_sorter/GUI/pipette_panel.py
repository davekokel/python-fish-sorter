from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QMessageBox,
)


class PipettePanel(QWidget):
    """
    Pipette (Zaber 'p') component with Qt presets.

    Presets stored in: qt_presets/pipette_positions.json
    Keys:
      - name
      - swing_mm
      - clearance_mm
      - pick_mm
      - dispense_mm
      - pre_pick_mm
      - pre_dispense_mm
    """

    def __init__(self, pick, repo_root: Path, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.pick = pick
        self.repo_root = repo_root
        self.store_path = repo_root / "qt_presets" / "pipette_positions.json"
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        self.presets: list[dict] = []

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.refresh)

        self._build_ui()
        self._load_store()

        self._timer.start()
        self.refresh()

    def _phc(self):
        try:
            return getattr(self.pick, "phc", None)
        except Exception:
            return None

    def _zc(self):
        phc = self._phc()
        return getattr(phc, "zc", None) if phc is not None else None

    def _get_p(self) -> Optional[float]:
        zc = self._zc()
        if zc is None:
            return None
        try:
            return float(zc.get_pos("p"))
        except Exception:
            return None

    def _move_p_abs_mm(self, p_mm: float) -> bool:
        zc = self._zc()
        if zc is None:
            return False
        try:
            zc.move_arm("p", float(p_mm), is_relative=False)
            return True
        except Exception as e:
            self.status.setText(f"Status: move failed: {e!r}")
            return False

    def _move_p_rel_mm(self, dp_mm: float) -> bool:
        zc = self._zc()
        if zc is None:
            return False
        try:
            zc.move_arm("p", float(dp_mm), is_relative=True)
            return True
        except Exception as e:
            self.status.setText(f"Status: jog failed: {e!r}")
            return False

    def refresh(self):
        p = self._get_p()
        ok = p is not None
        self.lbl_p.setText("P (mm): -" if p is None else f"P (mm): {p:.3f}")

        # enable/disable motion widgets if unmapped
        for w in (
            self.btn_refresh,
            self.btn_step_down,
            self.btn_step_up,
            self.btn_jog_m,
            self.btn_jog_p,
            self.btn_apply_go,
            self.btn_move_swing,
            self.btn_move_clear,
            self.btn_move_pick,
            self.btn_move_disp,
            self.btn_move_pre_pick,
            self.btn_move_pre_disp,
            self.btn_set_swing,
            self.btn_set_clear,
            self.btn_set_pick,
            self.btn_set_disp,
        ):
            try:
                w.setEnabled(bool(ok))
            except Exception:
                pass

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(QLabel("Pipette (Zaber P axis)"))

        status_box = QGroupBox("Status")
        sh = QHBoxLayout(status_box)
        sh.setContentsMargins(8, 8, 8, 8)
        sh.setSpacing(10)

        self.lbl_p = QLabel("P (mm): -")
        sh.addWidget(self.lbl_p)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        sh.addWidget(self.btn_refresh)

        root.addWidget(status_box)

        # Jog controls
        jog_box = QGroupBox("Jog / Direct control")
        jg = QGridLayout(jog_box)
        jg.setContentsMargins(8, 8, 8, 8)
        jg.setHorizontalSpacing(10)
        jg.setVerticalSpacing(8)

        jg.addWidget(QLabel("Step (mm)"), 0, 0)
        self.step_mm = QDoubleSpinBox()
        self.step_mm.setDecimals(3)
        self.step_mm.setRange(0.001, 50.0)
        self.step_mm.setValue(1.000)
        jg.addWidget(self.step_mm, 0, 1)

        self.btn_step_down = QPushButton("Down")
        self.btn_step_up = QPushButton("Up")
        self.btn_step_down.clicked.connect(lambda: self._jog(-float(self.step_mm.value())))
        self.btn_step_up.clicked.connect(lambda: self._jog(+float(self.step_mm.value())))
        jg.addWidget(self.btn_step_down, 0, 2)
        jg.addWidget(self.btn_step_up, 0, 3)

        jg.addWidget(QLabel("Jog by (mm)"), 1, 0)
        self.jog_mm = QDoubleSpinBox()
        self.jog_mm.setDecimals(3)
        self.jog_mm.setRange(0.001, 50.0)
        self.jog_mm.setValue(0.250)
        jg.addWidget(self.jog_mm, 1, 1)

        self.btn_jog_m = QPushButton("Jog -")
        self.btn_jog_p = QPushButton("Jog +")
        self.btn_jog_m.clicked.connect(lambda: self._jog(-float(self.jog_mm.value())))
        self.btn_jog_p.clicked.connect(lambda: self._jog(+float(self.jog_mm.value())))
        jg.addWidget(self.btn_jog_m, 1, 2)
        jg.addWidget(self.btn_jog_p, 1, 3)

        jg.addWidget(QLabel("Go to P (mm)"), 2, 0)
        self.go_p = QDoubleSpinBox()
        self.go_p.setDecimals(3)
        self.go_p.setRange(-1e6, 1e6)
        self.go_p.setValue(0.0)
        jg.addWidget(self.go_p, 2, 1)

        self.btn_apply_go = QPushButton("Go")
        self.btn_apply_go.clicked.connect(self._go_absolute)
        jg.addWidget(self.btn_apply_go, 2, 2)

        root.addWidget(jog_box)

        # Named positions
        pos_box = QGroupBox("Named positions (mm)")
        g = QGridLayout(pos_box)
        g.setContentsMargins(8, 8, 8, 8)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)

        self.swing = QDoubleSpinBox(); self.swing.setDecimals(3); self.swing.setRange(-1e6, 1e6)
        self.clearance = QDoubleSpinBox(); self.clearance.setDecimals(3); self.clearance.setRange(-1e6, 1e6)
        self.pick_mm = QDoubleSpinBox(); self.pick_mm.setDecimals(3); self.pick_mm.setRange(-1e6, 1e6)
        self.disp_mm = QDoubleSpinBox(); self.disp_mm.setDecimals(3); self.disp_mm.setRange(-1e6, 1e6)
        self.pre_pick = QDoubleSpinBox(); self.pre_pick.setDecimals(3); self.pre_pick.setRange(-1e6, 1e6)
        self.pre_disp = QDoubleSpinBox(); self.pre_disp.setDecimals(3); self.pre_disp.setRange(-1e6, 1e6)

        g.addWidget(QLabel("Swing"), 0, 0); g.addWidget(self.swing, 0, 1)
        g.addWidget(QLabel("Clearance"), 0, 2); g.addWidget(self.clearance, 0, 3)

        g.addWidget(QLabel("Pick"), 1, 0); g.addWidget(self.pick_mm, 1, 1)
        g.addWidget(QLabel("Dispense"), 1, 2); g.addWidget(self.disp_mm, 1, 3)

        g.addWidget(QLabel("Pre-pick"), 2, 0); g.addWidget(self.pre_pick, 2, 1)
        g.addWidget(QLabel("Pre-dispense"), 2, 2); g.addWidget(self.pre_disp, 2, 3)

        self.btn_move_swing = QPushButton("Move swing")
        self.btn_move_clear = QPushButton("Move clearance")
        self.btn_move_pick = QPushButton("Move pick")
        self.btn_move_disp = QPushButton("Move dispense")
        self.btn_move_pre_pick = QPushButton("Move pre-pick")
        self.btn_move_pre_disp = QPushButton("Move pre-dispense")

        self.btn_move_swing.clicked.connect(lambda: self._move_named("swing"))
        self.btn_move_clear.clicked.connect(lambda: self._move_named("clearance"))
        self.btn_move_pick.clicked.connect(lambda: self._move_named("pick"))
        self.btn_move_disp.clicked.connect(lambda: self._move_named("dispense"))
        self.btn_move_pre_pick.clicked.connect(lambda: self._move_named("pre_pick"))
        self.btn_move_pre_disp.clicked.connect(lambda: self._move_named("pre_dispense"))

        g.addWidget(self.btn_move_swing, 0, 4)
        g.addWidget(self.btn_move_clear, 0, 5)
        g.addWidget(self.btn_move_pick, 1, 4)
        g.addWidget(self.btn_move_disp, 1, 5)
        g.addWidget(self.btn_move_pre_pick, 2, 4)
        g.addWidget(self.btn_move_pre_disp, 2, 5)

        self.btn_set_swing = QPushButton("Set swing = current")
        self.btn_set_clear = QPushButton("Set clearance = current")
        self.btn_set_pick = QPushButton("Set pick = current")
        self.btn_set_disp = QPushButton("Set dispense = current")

        self.btn_set_swing.clicked.connect(lambda: self._set_from_current(self.swing, "swing"))
        self.btn_set_clear.clicked.connect(lambda: self._set_from_current(self.clearance, "clearance"))
        self.btn_set_pick.clicked.connect(lambda: self._set_from_current(self.pick_mm, "pick"))
        self.btn_set_disp.clicked.connect(lambda: self._set_from_current(self.disp_mm, "dispense"))

        g.addWidget(self.btn_set_swing, 3, 0, 1, 2)
        g.addWidget(self.btn_set_clear, 3, 2, 1, 2)
        g.addWidget(self.btn_set_pick, 4, 0, 1, 2)
        g.addWidget(self.btn_set_disp, 4, 2, 1, 2)

        self.btn_calc_pre = QPushButton("Compute pre-* from pick/dispense + offsets")
        self.btn_calc_pre.clicked.connect(self._calc_pre_positions)
        g.addWidget(self.btn_calc_pre, 4, 4, 1, 2)

        root.addWidget(pos_box)

        # Presets
        presets_box = QGroupBox("Qt Presets")
        pb = QHBoxLayout(presets_box)
        pb.setContentsMargins(8, 8, 8, 8)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
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

        self.btn_apply = QPushButton("Apply selected")
        self.btn_apply.clicked.connect(self._preset_apply_selected)
        rv.addWidget(self.btn_apply)

        self.btn_delete = QPushButton("Delete selected")
        self.btn_delete.clicked.connect(self._preset_delete_selected)
        rv.addWidget(self.btn_delete)

        rv.addStretch(1)
        pb.addWidget(right)

        root.addWidget(presets_box, stretch=1)

        self.status = QLabel("Status: -")
        root.addWidget(self.status)

    # ---- jog/go
    def _jog(self, dp_mm: float):
        if self._get_p() is None:
            self.status.setText("Status: cannot read p (unmapped?)")
            return
        ok = self._move_p_rel_mm(dp_mm)
        self.status.setText(f"Status: jog {dp_mm:+.3f} mm -> {'OK' if ok else 'FAIL'}")
        self.refresh()

    def _go_absolute(self):
        if self._get_p() is None:
            self.status.setText("Status: cannot read p (unmapped?)")
            return
        target = float(self.go_p.value())
        ok = self._move_p_abs_mm(target)
        self.status.setText(f"Status: go {target:.3f} mm -> {'OK' if ok else 'FAIL'}")
        self.refresh()

    # ---- helpers
    def _set_from_current(self, spin: QDoubleSpinBox, label: str):
        p = self._get_p()
        if p is None:
            self.status.setText("Status: cannot read p (unmapped?)")
            return
        spin.setValue(float(p))
        self.status.setText(f"Status: set {label}={p:.3f} from current")

    def _calc_pre_positions(self):
        self.pre_pick.setValue(float(self.pick_mm.value()) + 2.0)
        self.pre_disp.setValue(float(self.disp_mm.value()) + 2.0)
        self.status.setText("Status: computed pre_pick/pre_dispense = +2.0mm")

    def _move_named(self, name: str):
        target = None
        if name == "swing":
            target = float(self.swing.value())
        elif name == "clearance":
            target = float(self.clearance.value())
        elif name == "pick":
            target = float(self.pick_mm.value())
        elif name == "dispense":
            target = float(self.disp_mm.value())
        elif name == "pre_pick":
            target = float(self.pre_pick.value())
        elif name == "pre_dispense":
            target = float(self.pre_disp.value())

        if target is None:
            return

        ok = self._move_p_abs_mm(target)
        self.status.setText(f"Status: move {name} -> {'OK' if ok else 'FAIL'} ({target:.3f} mm)")
        self.refresh()

    # ---- presets
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
            label = (
                f"{name}  |  swing={p.get('swing_mm')} clear={p.get('clearance_mm')} "
                f"pick={p.get('pick_mm')} disp={p.get('dispense_mm')} "
                f"pre_pick={p.get('pre_pick_mm')} pre_disp={p.get('pre_dispense_mm')}"
            )
            self.list.addItem(QListWidgetItem(label))

    def _selected_index(self) -> Optional[int]:
        items = self.list.selectedIndexes()
        if not items:
            return None
        return int(items[0].row())

    def _snapshot(self) -> dict:
        return {
            "swing_mm": float(self.swing.value()),
            "clearance_mm": float(self.clearance.value()),
            "pick_mm": float(self.pick_mm.value()),
            "dispense_mm": float(self.disp_mm.value()),
            "pre_pick_mm": float(self.pre_pick.value()),
            "pre_dispense_mm": float(self.pre_disp.value()),
        }

    def _apply_snapshot(self, d: dict):
        self.swing.setValue(float(d.get("swing_mm", self.swing.value())))
        self.clearance.setValue(float(d.get("clearance_mm", self.clearance.value())))
        self.pick_mm.setValue(float(d.get("pick_mm", self.pick_mm.value())))
        self.disp_mm.setValue(float(d.get("dispense_mm", self.disp_mm.value())))
        self.pre_pick.setValue(float(d.get("pre_pick_mm", self.pre_pick.value())))
        self.pre_disp.setValue(float(d.get("pre_dispense_mm", self.pre_disp.value())))

    def _preset_new(self):
        name, ok = QInputDialog.getText(self, "New pipette preset", "Preset name:")
        if not ok or not name.strip():
            return
        self.presets.append({"name": name.strip(), **self._snapshot()})
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: created preset {name.strip()}")

    def _preset_save_current_into_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        self.presets[idx].update(self._snapshot())
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: saved current into {self.presets[idx].get('name')}")

    def _preset_apply_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        p = self.presets[idx]
        self._apply_snapshot(p)
        self.status.setText(f"Status: loaded preset {p.get('name')}")
        self.refresh()

    def _preset_delete_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        name = self.presets[idx].get("name", "(unnamed)")
        self.presets.pop(idx)
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: deleted {name}")
