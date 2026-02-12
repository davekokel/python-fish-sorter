import logging
import json
import sys
from json import load
from pathlib import Path
from time import sleep
from typing import List, Optional, Union

from pymmcore_plus import CMMCorePlus
from qtpy.QtCore import (
    QSize,
    Qt
)
from PyQt6.QtCore import (
    pyqtSignal,
    QMutex,
    QThread,
    QWaitCondition
)
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QDoubleSpinBox,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget
)

from fish_sorter.GUI.picking import Pick

from fish_sorter.GUI.picking_widgets.stage_widgets import StagePositionsWidget
from fish_sorter.GUI.picking_widgets.dispense_plate import DispensePlateCalibWidget
from fish_sorter.GUI.picking_widgets.top_buttons import (
    PipettePickCalibWidget, PipetteDispCalibWidget,
    Pipette2PickWidget, Pipette2DispWidget, Pipette2ClearWidget, Pipette2SwingWidget,
    HomeWidget, ImageWidget,
)

from fish_sorter.GUI.picking_widgets.run_widgets import (
    PickWidget, NewExptWidget, ResetWidget,
    SinglePickWidget,
)

COLOR_TYPES = Union[
    QColor,
    int,
    str,
    Qt.GlobalColor,
    "tuple[int, int, int, int]",
    "tuple[int, int, int]"
]


class PickGUI(QWidget):
    """
    Picking UI organized by superfunction.

    Tabs:
      1) Run Experiment
      2) Pipette
      3) Dispense Plate / Collection Plate
      4) Valve Calibration

    Workflow panel buttons should route to these tabs (not dump the user into a generic place).
    """

    TAB_PLATE = 0
    TAB_PIPETTE = 1
    TAB_VALVE = 2
    TAB_RUN = 3

    def __init__(self, picker=None, parent: QWidget | None = None):
        super().__init__(parent=parent)
        CMMCorePlus.instance()

        self.pick = picker
        self.pick_calib = False
        self.disp_calib = False

        # ---- state banner ----
        self._ui_state = "IDLE"
        self.state_banner = QLabel("")
        self.state_banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._set_state("IDLE")

        # ---- global manual gating ----
        self.manual_enable = QCheckBox("Enable Manual Overrides")
        self.manual_enable.stateChanged.connect(self._apply_manual_gating)

        # ---- pipette calibration widgets ----
        self.calib_pick = PipettePickCalibWidget(self)
        self.calib_disp = PipetteDispCalibWidget(self)
        self.pick_calib_status = QLabel("not set")
        self.disp_calib_status = QLabel("not set")

        self.btn_move2pick = Pipette2PickWidget(self)
        self.btn_move2disp = Pipette2DispWidget(self)
        self.btn_move2clear = Pipette2ClearWidget(self)
        self.btn_move2swing = Pipette2SwingWidget(self)

        # ---- plate widgets ----
        self.stage_pos = StagePositionsWidget(self)
        self.disp_plate_calib = DispensePlateCalibWidget(self)
        self.stage_tabs = QTabWidget()
        self.stage_tabs.addTab(self.stage_pos, "Zabers")
        self.stage_tabs.addTab(self.disp_plate_calib, "Dispense Plate")

        # plate motion (these were mislabeled Image/Home historically)
        self.btn_plate_in = ImageWidget(self)   # "Move collection plate IN for collecting"
        self.btn_plate_away = HomeWidget(self)  # "Move collection plate AWAY for picking"

        # ---- manual pipette widget ----
        self.move_pipette = MovePipette(self)

        # ---- valve widgets ----
        self.draw = PipetteDrawWidget(self)
        self.expel = PipetteExpelWidget(self)
        self.ppp = PipettePressureWidget(self)
        self.time = ChangeTimeWidget(self)

        # ---- run widgets ----
        self.pw = PickWidget(self)
        self.pw.setEnabled(False)
        self.pw.pause_button.setEnabled(False)
        self.pw.stop_button.setEnabled(False)
        self.pw.state_changed.connect(self._on_state_changed)

        self.single = SinglePickWidget(self)
        self.single.setEnabled(False)

        self.new_expt = NewExptWidget(self)
        self.reset = ResetWidget(self)

        # ---- compose ----
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        status_box = self._group("STATUS")
        s = QGridLayout(status_box)
        s.addWidget(self.state_banner, 0, 0, 1, 2)
        s.addWidget(QLabel("Pick height:"), 1, 0)
        s.addWidget(self.pick_calib_status, 1, 1)
        s.addWidget(QLabel("Disp height:"), 2, 0)
        s.addWidget(self.disp_calib_status, 2, 1)
        root.addWidget(status_box)

        self.main_tabs = QTabWidget()
        self.main_tabs.addTab(self._tab_plate(), "Dispense Plate / Collection Plate")
        self.main_tabs.addTab(self._tab_pipette(), "Pipette")
        self.main_tabs.addTab(self._tab_valve(), "Valve Calibration")
        self.main_tabs.addTab(self._tab_run(), "Run Experiment")
        root.addWidget(self.main_tabs)

        # initial status/gating
        self._update_calib_status()
        self._apply_manual_gating()
        self._apply_tab_gating(self._infer_state())

    # --------------------------
    # Tab builders
    # --------------------------

    def _tab_run(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        box = self._group("RUN EXPERIMENT")
        g = QGridLayout(box)
        g.addWidget(self.single, 0, 0, 1, 2)
        g.addWidget(self.pw, 1, 0, 1, 2)
        g.addWidget(self.pw.pause_button, 2, 0)
        g.addWidget(self.pw.stop_button, 2, 1)
        g.addWidget(self.new_expt, 3, 0)
        g.addWidget(self.reset, 3, 1)

        layout.addWidget(box)
        layout.addStretch(1)
        return w

    def _tab_pipette(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._manual_gate_box())

        calib = self._group("PIPETTE POSITIONS (CALIBRATION)")
        g = QGridLayout(calib)
        g.addWidget(self.calib_pick, 0, 0)
        g.addWidget(self.calib_disp, 0, 1)
        g.addWidget(self.btn_move2swing, 0, 2)
        g.addWidget(self.btn_move2pick, 1, 0)
        g.addWidget(self.btn_move2disp, 1, 1)
        g.addWidget(self.btn_move2clear, 1, 2)
        layout.addWidget(calib)

        manual = self._group("MANUAL PIPETTE MOVEMENT (OVERRIDE)")
        ml = QVBoxLayout(manual)
        ml.setContentsMargins(8, 8, 8, 8)
        self.manual_pipette_container = QWidget()
        c = QVBoxLayout(self.manual_pipette_container)
        c.setContentsMargins(0, 0, 0, 0)
        c.addWidget(self.move_pipette)
        ml.addWidget(self.manual_pipette_container)
        layout.addWidget(manual)

        layout.addStretch(1)
        return w

    def _tab_plate(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._manual_gate_box())

        corners = self._group("DISPENSE PLATE CORNERS (TL/BR) + STAGE")
        cl = QVBoxLayout(corners)
        cl.setContentsMargins(8, 8, 8, 8)
        cl.addWidget(self.stage_tabs)
        layout.addWidget(corners)

        motion = self._group("COLLECTION PLATE MOTION (OVERRIDE)")
        ml = QHBoxLayout(motion)
        ml.setContentsMargins(8, 8, 8, 8)
        self.manual_plate_container = QWidget()
        row = QHBoxLayout(self.manual_plate_container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.btn_plate_away)
        row.addWidget(self.btn_plate_in)
        row.addStretch(1)
        ml.addWidget(self.manual_plate_container)
        layout.addWidget(motion)

        layout.addStretch(1)
        return w

    def _tab_valve(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._manual_gate_box())

        prim = self._group("VALVE PRIMITIVES (OVERRIDE)")
        pl = QHBoxLayout(prim)
        pl.setContentsMargins(8, 8, 8, 8)
        self.manual_valve_container = QWidget()
        row = QHBoxLayout(self.manual_valve_container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.draw)
        row.addWidget(self.expel)
        row.addWidget(self.ppp)
        row.addStretch(1)
        pl.addWidget(self.manual_valve_container)
        layout.addWidget(prim)

        timing = self._group("VALVE TIMING")
        tl = QVBoxLayout(timing)
        tl.setContentsMargins(8, 8, 8, 8)
        tl.addWidget(self.time)
        layout.addWidget(timing)

        layout.addStretch(1)
        return w

    def _manual_gate_box(self) -> QGroupBox:
        gb = self._group("SAFETY")
        l = QHBoxLayout(gb)
        l.setContentsMargins(8, 8, 8, 8)
        l.addWidget(self.manual_enable)
        l.addStretch(1)
        return gb

    # --------------------------
    # External navigation API (used by workflow_panel)
    # --------------------------

    def focus_tab(self, tab_index: int) -> None:
        try:
            self.main_tabs.setCurrentIndex(int(tab_index))
        except Exception:
            pass

    def focus_stage_subtab(self, name: str) -> None:
        try:
            tabs = self.stage_tabs
            for i in range(tabs.count()):
                if tabs.tabText(i) == name:
                    tabs.setCurrentIndex(i)
                    break
        except Exception:
            pass

    # --------------------------
    # State + gating
    # --------------------------

    def _group(self, title: str) -> QGroupBox:
        return QGroupBox(title)

    def _set_state(self, state: str) -> None:
        self._ui_state = state
        self.state_banner.setText(f"STATE: {state}")

    def _infer_state(self) -> str:
        if not (self.pick_calib and self.disp_calib):
            return "CALIBRATION"
        if self.pw.isEnabled():
            return "READY"
        return "IDLE"

    def _apply_tab_gating(self, state: str) -> None:
        s = (state or "").strip().upper()
        locked = s in ("PICKING", "PAUSED", "STOPPING", "ERROR")
        try:
            # keep Run enabled; lock everything else while picking/paused/stopping/error
            self.main_tabs.setTabEnabled(self.TAB_RUN, True)
            self.main_tabs.setTabEnabled(self.TAB_PIPETTE, not locked)
            self.main_tabs.setTabEnabled(self.TAB_PLATE, not locked)
            self.main_tabs.setTabEnabled(self.TAB_VALVE, not locked)
        except Exception:
            pass

    def _on_state_changed(self, state: str) -> None:
        if not isinstance(state, str):
            return
        s = state.strip().upper()

        if s == "READY":
            self._set_state(self._infer_state())
            self._apply_tab_gating(self._ui_state)
            return

        if s in ("CALIBRATION", "STOPPING", "PICKING", "PAUSED", "ERROR"):
            self._set_state(s)
            self._apply_tab_gating(s)
            return

        self._set_state(self._infer_state())
        self._apply_tab_gating(self._ui_state)

    def _apply_manual_gating(self) -> None:
        enabled = bool(self.manual_enable.isChecked())
        for attr in ("manual_pipette_container", "manual_plate_container", "manual_valve_container"):
            w = getattr(self, attr, None)
            if w is not None:
                w.setEnabled(enabled)

    def _update_calib_status(self) -> None:
        def _fmt_mm(v):
            try:
                return f"{float(v):.3f} mm"
            except Exception:
                return str(v)

        if self.pick_calib:
            try:
                self.pick_calib_status.setText(f"set ({_fmt_mm(self.pick.phc.pick_h)})")
            except Exception:
                self.pick_calib_status.setText("set")
        else:
            self.pick_calib_status.setText("not set")

        if self.disp_calib:
            try:
                self.disp_calib_status.setText(f"set ({_fmt_mm(self.pick.phc.disp_h)})")
            except Exception:
                self.disp_calib_status.setText("set")
        else:
            self.disp_calib_status.setText("not set")

        self._set_state(self._infer_state())
        self._apply_tab_gating(self._ui_state)

    def update_pick_widgets(self, status: bool = True):
        self.pw.setEnabled(status)
        self.single.setEnabled(status)
        self.pw.pause_button.setEnabled(status)
        self.pw.stop_button.setEnabled(status)
        self._set_state(self._infer_state())
        self._apply_tab_gating(self._ui_state)


class MovePipette(QWidget):
    """Move pipette by a user-defined increment."""

    def __init__(self, picking, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_gui()

    def _create_gui(self):
        layout = QGridLayout(self)
        layout.addWidget(QLabel("Move Pipette"), 0, 0)

        self.distance_spinbox = QDoubleSpinBox()
        self.distance_spinbox.setRange(0.00, 1000.00)
        self.distance_spinbox.setSingleStep(0.05)
        self.distance_spinbox.setDecimals(2)
        self.distance_spinbox.setSuffix(" ")
        layout.addWidget(self.distance_spinbox, 1, 0)

        self.units_dropdown = QComboBox()
        self.units_dropdown.addItems(["mm", "um"])
        layout.addWidget(self.units_dropdown, 1, 1)

        self.move_up_button = QPushButton("Pipette Up")
        self.move_up_button.clicked.connect(self._move_pipette_up)
        layout.addWidget(self.move_up_button, 1, 2)

        self.move_down_button = QPushButton("Pipette Down")
        self.move_down_button.clicked.connect(self._move_pipette_down)
        layout.addWidget(self.move_down_button, 1, 3)

    def _move_pipette_up(self):
        dist = -self.distance_spinbox.value()
        units = self.units_dropdown.currentText()
        unit_bool = units == "mm"
        logging.info(f"Moving pipette by {dist} {units}")
        self.picking.pick.phc.move_pipette_increment(dist, unit_bool)

    def _move_pipette_down(self):
        dist = self.distance_spinbox.value()
        units = self.units_dropdown.currentText()
        unit_bool = units == "mm"
        logging.info(f"Moving pipette by {dist} {units}")
        self.picking.pick.phc.move_pipette_increment(dist, unit_bool)


class ChangeTimeWidget(QWidget):
    """Change draw/expel times (ms)."""

    def __init__(self, picking, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_gui()

    def _create_gui(self):
        layout = QGridLayout(self)
        layout.addWidget(QLabel("Change Time"), 0, 0)

        self.time_spinbox = QSpinBox()
        self.time_spinbox.setRange(0, 1000)
        layout.addWidget(self.time_spinbox, 1, 0)
        layout.addWidget(QLabel("ms"), 1, 1)

        self.change_draw_button = QPushButton("Change Draw Time")
        self.change_draw_button.clicked.connect(self._change_draw)
        layout.addWidget(self.change_draw_button, 1, 2)

        self.change_expel_button = QPushButton("Change Expel Time")
        self.change_expel_button.clicked.connect(self._change_expel)
        layout.addWidget(self.change_expel_button, 1, 3)

    def _change_draw(self):
        t = self.time_spinbox.value()
        logging.info(f"Change Draw time to {t} ms")
        self.picking.pick.phc.draw_time(t)

    def _change_expel(self):
        t = self.time_spinbox.value()
        logging.info(f"Change Expel time to {t} ms")
        self.picking.pick.phc.expel_time(t)


class PipetteDrawWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Pipette Draw")
        self.clicked.connect(self._draw)

    def _draw(self) -> None:
        self.picking.pick.phc.draw()


class PipetteExpelWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Pipette Expel")
        self.clicked.connect(self._expel)

    def _expel(self) -> None:
        self.picking.pick.phc.expel()


class PipettePressureWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.pressure_state = False
        self.setText("Toggle Pressure Valve")
        self.clicked.connect(self._pressure)

    def _pressure(self) -> None:
        self.pressure_state = not self.pressure_state
        self.picking.pick.phc.pressure(self.pressure_state)

