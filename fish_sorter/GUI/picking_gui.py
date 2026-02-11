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
    QComboBox, 
    QGridLayout,
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

    def __init__(self, picker=None, parent: QWidget | None=None):
        """Initialize Picker GUI

        :param picker: Pick class object to control picking
        :type picker: class instance
        """
        
        super().__init__(parent=parent)
        CMMCorePlus.instance()

        self.pick = picker
        self.pick_calib = False
        self.disp_calib = False
        
        self.calib_pick = PipettePickCalibWidget(self)
        self.pick_calib_status = QLabel('❌ Pick Not Calibrated')
        calib_disp = PipetteDispCalibWidget(self)
        self.disp_calib_status = QLabel('❌ Disp Not Calibrated')
        self.btn_move2pick = Pipette2PickWidget(self)
        self.btn_move2disp = Pipette2DispWidget(self)
        self.btn_move2clear = Pipette2ClearWidget(self)
        self.btn_move2swing = Pipette2SwingWidget(self)
        img = ImageWidget(self)
        home = HomeWidget(self)
        move_pipette = MovePipette(self)
        stage_pos = StagePositionsWidget(self)
        disp_plate_calib = DispensePlateCalibWidget(self)
        stage_box = QWidget()
        stage_box_layout = QVBoxLayout(stage_box)
        stage_box_layout.setContentsMargins(0, 0, 0, 0)

        stage_tabs = QTabWidget()
        stage_tabs.addTab(stage_pos, "Zabers")
        stage_tabs.addTab(disp_plate_calib, "Dispense Plate")
        stage_box_layout.addWidget(stage_tabs)
        self.pw = PickWidget(self)
        self.pw.setEnabled(False)
        self.pw.pause_button.setEnabled(False)
        self.pw.stop_button.setEnabled(False)
        self.new_expt = NewExptWidget(self)
        reset = ResetWidget(self)
        
        draw = PipetteDrawWidget(self)
        expel = PipetteExpelWidget(self)
        ppp = PipettePressureWidget(self)
        
        time = ChangeTimeWidget(self)
        self.single = SinglePickWidget(self)
        self.single.setEnabled(False)

        layout = QGridLayout(self)
        layout.addWidget(self.calib_pick, 1, 0)
        layout.addWidget(self.pick_calib_status, 1, 3)
        layout.addWidget(calib_disp, 1, 1)
        layout.addWidget(self.btn_move2swing, 1, 2)
        layout.addWidget(self.btn_move2pick, 2, 0)
        layout.addWidget(self.btn_move2disp, 2, 1)
        layout.addWidget(self.btn_move2clear, 2, 2)
        layout.addWidget(img, 3, 0)
        layout.addWidget(home, 3, 1)
        layout.addWidget(self.pick_calib_status, 4, 0)
        layout.addWidget(self.disp_calib_status, 4, 1)
        self._update_calib_status()
        
        layout.addWidget(move_pipette, 5, 0)
        layout.addWidget(stage_box, 5, 1, 1, 3)
        layout.addWidget(time, 6, 0)
        layout.addWidget(draw, 7, 0)
        layout.addWidget(expel, 7, 1)
        layout.addWidget(ppp, 7, 2)
        layout.addWidget(self.single, 8, 0)
        layout.addWidget(self.pw, 9, 0)
        layout.addWidget(self.pw.pause_button, 9, 1)
        layout.addWidget(self.pw.stop_button, 9, 2)
        layout.addWidget(self.new_expt, 10, 0)
        layout.addWidget(reset, 10, 1)

    def _update_calib_status(self):
        """Update the GUI that the pick and/or dispense positions are set."""

        def _fmt_mm(v):
            try:
                return f"{float(v):.3f} mm"
            except Exception:
                return str(v)

        if self.pick_calib:
            try:
                self.pick_calib_status.setText(f"Pick position set: {_fmt_mm(self.pick.phc.pick_h)}")
            except Exception:
                self.pick_calib_status.setText("Pick position set")
        else:
            self.pick_calib_status.setText("Pick position not set")

        if self.disp_calib:
            try:
                self.disp_calib_status.setText(f"Disp position set: {_fmt_mm(self.pick.phc.disp_h)}")
            except Exception:
                self.disp_calib_status.setText("Disp position set")
        else:
            self.disp_calib_status.setText("Disp position not set")

    def update_pick_widgets(self, status: bool=True):
        """Updates the widgets dependent on the Pick class
        """
        
        self.pw.setEnabled(status)
        self.single.setEnabled(status)
        self.pw.pause_button.setEnabled(status)
        self.pw.stop_button.setEnabled(status)

class MovePipette(QWidget):
    """A widget to move the pipette a user-defined distance"""

    def __init__(self, picking, parent: QWidget | None=None):
        
        super().__init__(parent=parent)

        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_gui()

    def _create_gui(self):

        layout = QGridLayout(self)
        label = QLabel('Move Pipette')
        layout.addWidget(label, 0, 0)

        self.distance_spinbox = QDoubleSpinBox()
        self.distance_spinbox.setRange(0.00, 1000.00)
        self.distance_spinbox.setSingleStep(0.05)
        self.distance_spinbox.setDecimals(2)
        self.distance_spinbox.setSuffix(" ")
        layout.addWidget(self.distance_spinbox, 1, 0)

        self.units_dropdown = QComboBox()
        self.units_dropdown.addItems(['mm', 'um'])
        layout.addWidget(self.units_dropdown, 1, 1)

        self.move_up_button = QPushButton('Pipette Up')
        self.move_up_button.clicked.connect(self._move_pipette_up)
        layout.addWidget(self.move_up_button, 1, 2)

        self.move_down_button = QPushButton('Pipette Down')
        self.move_down_button.clicked.connect(self._move_pipette_down)
        layout.addWidget(self.move_down_button, 1, 3)

    def _move_pipette_up(self):

        dist = -self.distance_spinbox.value()
        units = self.units_dropdown.currentText()
        unit_bool = units == 'mm'

        logging.info(f'Moving pipette by {dist} {units}')
        self.picking.pick.phc.move_pipette_increment(dist, unit_bool)

    def _move_pipette_down(self):

        dist = self.distance_spinbox.value()
        units = self.units_dropdown.currentText()
        unit_bool = units == 'mm'

        logging.info(f'Moving pipette by {dist} {units}')
        self.picking.pick.phc.move_pipette_increment(dist, unit_bool)


class ChangeTimeWidget(QWidget):
    """A widget to change the draw and expel times"""

    def __init__(self, picking, parent: QWidget | None=None):
        
        super().__init__(parent=parent)

        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_gui()

    def _create_gui(self):

        layout = QGridLayout(self)
        label = QLabel('Change Time')
        layout.addWidget(label, 0, 0)

        self.time_spinbox = QSpinBox()
        self.time_spinbox.setRange(0, 1000)
        layout.addWidget(self.time_spinbox, 1, 0)
        unit_label = QLabel('ms')
        layout.addWidget(unit_label, 1, 1)

        self.change_draw_button = QPushButton('Change Draw Time')
        self.change_draw_button.clicked.connect(self._change_draw)
        layout.addWidget(self.change_draw_button, 1, 2)

        self.change_expel_button = QPushButton('Change Expel Time')
        self.change_expel_button.clicked.connect(self._change_expel)
        layout.addWidget(self.change_expel_button, 1, 3)

    def _change_draw(self):

        time = self.time_spinbox.value()
        logging.info(f'Change Draw time to {time} ms')
        self.picking.pick.phc.draw_time(time)

    def _change_expel(self):

        time = self.time_spinbox.value()
        logging.info(f'Change Expel time to {time} ms')
        self.picking.pick.phc.expel_time(time)


class PipetteDrawWidget(QPushButton):
    """A push button widget to connect to the valve controller to actuate the draw function

    This is linked to the [hardware][picking_pipette] method
    """
    
    def __init__(self, picking, parent: QWidget | None=None):
        
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )

        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_button()

    def _create_button(self)->None:
        
        self.setText("Pipette Draw")
        self.clicked.connect(self._draw)

    def _draw(self)->None:
        
        self.picking.pick.phc.draw()


class PipetteExpelWidget(QPushButton):
    """A push button widget to connect to the valve controller to actuate the expel function

    This is linked to the [hardware][picking_pipette] method
    """
    
    def __init__(self, picking, parent: QWidget | None=None):
        
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )

        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_button()

    def _create_button(self)->None:
        
        self.setText("Pipette Expel")
        self.clicked.connect(self._expel)

    def _expel(self)->None:
        
        self.picking.pick.phc.expel()


class PipettePressureWidget(QPushButton):
    """A push button widget to connect to the valve controller to toggle the pressure

    This is linked to the [hardware][picking_pipette] method
    """
    
    def __init__(self, picking, parent: QWidget | None=None):
        
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )

        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_button()
        self.pressure_state = False

    def _create_button(self)->None:
        
        self.setText("Toggle Pressure Valve")
        self.clicked.connect(self._pressure)

    def _pressure(self)->None:
        
        self.pressure_state = not self.pressure_state
        self.picking.pick.phc.pressure(self.pressure_state)






