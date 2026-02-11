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
    QVBoxLayout, 
    QWidget
)

from fish_sorter.GUI.picking import Pick

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
        move2pick = Pipette2PickWidget(self)
        move2disp = Pipette2DispWidget(self)
        move2clear = Pipette2ClearWidget(self)
        move2swing = Pipette2SwingWidget(self)
        img = ImageWidget(self)
        home = HomeWidget(self)
        move_pipette = MovePipette(self)
        stage_pos = StagePositionsWidget(self)
        disp_plate_calib = DispensePlateCalibWidget(self)
        stage_box = QWidget()
        stage_box_layout = QVBoxLayout(stage_box)
        stage_box_layout.setContentsMargins(0, 0, 0, 0)
        stage_box_layout.addWidget(stage_pos)
        stage_box_layout.addWidget(disp_plate_calib)
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
        layout.addWidget(move2swing, 1, 2)
        layout.addWidget(move2pick, 2, 0)
        layout.addWidget(move2disp, 2, 1)
        layout.addWidget(move2clear, 2, 2)
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

class PipettePickCalibWidget(QPushButton):
    """A push button widget to calibrate the pick position for the pipette
    """
    
    save_pick_h = pyqtSignal()

    def __init__(self, picking, parent: QWidget | None=None):
        
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )

        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_button()

    def _create_button(self)->None:
        
        self.setText("Set Pick Position")
        self.clicked.connect(self._pick_calib)

    def _pick_calib(self)->None:
        
        logging.info('Calibrate pick height into array')
        self.picking.pick.set_calib(pick=True)
        self.picking.pick_calib = True
        self.picking._update_calib_status()
        self.save_pick_h.emit()


class PipetteDispCalibWidget(QPushButton):
    """A push button widget to calibrate the dispense position for the pipette
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
        
        self.setText("Set Dispense Position")
        self.clicked.connect(self._disp_calib)

    def _disp_calib(self)->None:

        logging.info('Calibrate dispense height into destination plate')
        self.picking.pick.set_calib(pick=False)
        self.picking.disp_calib = True         
        self.picking._update_calib_status()     


class Pipette2PickWidget(QPushButton):
    """A push button widget to connect to the pipette widget move the pipette to the pick position 

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
        
        self.setText("Move to Pick Position")
        self.clicked.connect(self._pick_pos)

    def _pick_pos(self)->None:
        
        self.picking.pick.move_calib(pick=True)
        self.picking.pick.phc.move_pipette(pos='pick')


class Pipette2DispWidget(QPushButton):
    """A push button widget to connect to the pipette widget move the pipette to the dispense position 

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
        
        self.setText("Move to Dispense Position")
        self.clicked.connect(self._disp_pos)

    def _disp_pos(self)->None:
        self.picking.pick.move_calib(pick=False, well='A01')
        self.picking.pick.phc.move_pipette(pos='dispense')


class Pipette2ClearWidget(QPushButton):
    """A push button widget to connect to the pipette widget move the pipette to the clearance position 

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
        
        self.setText("Move to Clearance Position")
        self.clicked.connect(self._clear_pos)

    def _clear_pos(self)->None:
        
        self.picking.pick.phc.move_pipette(pos='clearance')


class Pipette2SwingWidget(QPushButton):
    """A push button widget to connect to the pipette widget move the pipette to the swing position 

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
        
        self.setText("Move to Swing Position")
        self.clicked.connect(self._swing_pos)

    def _swing_pos(self)->None:
        
        self.picking.pick.phc.move_pipette(pos='pipette_swing')


class DispensePlateCalibWidget(QWidget):
    """UI calibration for dispense plate corners stored in picker_config.json.

    Writes:
      dispense_plate.TL_corner.x/y
      dispense_plate.BR_corner.x/y

    NOTE: config stores um; Zaber reports mm. We write (mm * 1000).
    """

    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.picking = picking
        self._create_gui()
        self.refresh()

    def _cfg_path(self) -> Optional[Path]:
        try:
            return Path(self.picking.pick.phc.pipettor_cfg)
        except Exception:
            return None

    def _read_cfg(self) -> Optional[dict]:
        p = self._cfg_path()
        if not p or not p.exists():
            return None
        try:
            with open(p, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"DispensePlateCalibWidget: failed to read cfg: {e!r}")
            return None

    def _write_cfg(self, d: dict) -> bool:
        p = self._cfg_path()
        if not p:
            return False
        try:
            with open(p, "w") as f:
                json.dump(d, f, indent=4, separators=(",", ": "))
            return True
        except Exception as e:
            logging.warning(f"DispensePlateCalibWidget: failed to write cfg: {e!r}")
            return False

    def _fmt_corner_mm(self, c: dict) -> str:
        try:
            x_mm = float(c.get("x", 0.0)) / 1000.0
            y_mm = float(c.get("y", 0.0)) / 1000.0
            return f"x={x_mm:.3f} mm, y={y_mm:.3f} mm"
        except Exception:
            return "x=?, y=?"

    def _create_gui(self):
        layout = QGridLayout(self)
        layout.addWidget(QLabel("Dispense Plate Corners"), 0, 0, 1, 4)

        self.tl_label = QLabel("TL: —")
        self.br_label = QLabel("BR: —")
        layout.addWidget(self.tl_label, 1, 0, 1, 4)
        layout.addWidget(self.br_label, 2, 0, 1, 4)

        self.btn_set_tl = QPushButton("Set TL (A01) from current XY")
        self.btn_set_br = QPushButton("Set BR (B03) from current XY")
        self.btn_refresh = QPushButton("Refresh corners")

        self.btn_set_tl.clicked.connect(lambda: self._set_corner("TL_corner"))
        self.btn_set_br.clicked.connect(lambda: self._set_corner("BR_corner"))
        self.btn_refresh.clicked.connect(self.refresh)

        layout.addWidget(self.btn_set_tl, 3, 0, 1, 2)
        layout.addWidget(self.btn_set_br, 3, 2, 1, 2)
        layout.addWidget(self.btn_refresh, 4, 0, 1, 4)

    def refresh(self):
        d = self._read_cfg()
        if not d:
            self.tl_label.setText("TL: (no cfg)")
            self.br_label.setText("BR: (no cfg)")
            return
        dp = d.get("dispense_plate", {})
        tl = dp.get("TL_corner", {})
        br = dp.get("BR_corner", {})
        self.tl_label.setText(f"TL: {self._fmt_corner_mm(tl)}")
        self.br_label.setText(f"BR: {self._fmt_corner_mm(br)}")

    def _set_corner(self, key: str):
        d = self._read_cfg()
        if not d:
            return

        try:
            zc = self.picking.pick.phc.zc
            x_mm = float(zc.get_pos("x"))
            y_mm = float(zc.get_pos("y"))
        except Exception as e:
            logging.warning(f"DispensePlateCalibWidget: failed to read current XY: {e!r}")
            return

        x_um = x_mm * 1000.0
        y_um = y_mm * 1000.0

        d.setdefault("dispense_plate", {})
        d["dispense_plate"].setdefault(key, {})
        d["dispense_plate"][key]["x"] = float(x_um)
        d["dispense_plate"][key]["y"] = float(y_um)

        if not self._write_cfg(d):
            return

        # Best-effort live reload (only works if a dispense plate has been defined)
        try:
            phc = self.picking.pick.phc
            if hasattr(phc, "current_dp") and hasattr(phc, "pixel_size_um"):
                phc.define_dp(phc.current_dp, phc.pixel_size_um)
        except Exception as e:
            logging.warning(f"DispensePlateCalibWidget: reload failed (restart may be needed): {e!r}")

        self.refresh()

class StagePositionsWidget(QWidget):
    """Operator-friendly readout of current Zaber positions (x/y/p)."""

    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.picking = picking
        self._create_gui()

    def _create_gui(self):
        layout = QGridLayout(self)
        layout.addWidget(QLabel("Stage Positions (Zaber)"), 0, 0, 1, 4)

        layout.addWidget(QLabel("x"), 1, 0)
        self.x_label = QLabel("—")
        layout.addWidget(self.x_label, 1, 1)

        layout.addWidget(QLabel("y"), 1, 2)
        self.y_label = QLabel("—")
        layout.addWidget(self.y_label, 1, 3)

        layout.addWidget(QLabel("p"), 2, 0)
        self.p_label = QLabel("—")
        layout.addWidget(self.p_label, 2, 1)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        layout.addWidget(self.btn_refresh, 2, 2, 1, 2)

        self.refresh()

    def refresh(self):
        try:
            zc = self.picking.pick.phc.zc
            self.x_label.setText(str(zc.get_pos("x")))
            self.y_label.setText(str(zc.get_pos("y")))
            self.p_label.setText(str(zc.get_pos("p")))
        except Exception as e:
            self.x_label.setText("ERR")
            self.y_label.setText("ERR")
            self.p_label.setText("ERR")
            logging.warning(f"StagePositionsWidget refresh failed: {e!r}")
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


class PickerThread(QThread):
    """Thread picking so that live preview stay on during full picking
    """

    status_update = pyqtSignal(str)
    picking_done = pyqtSignal()

    def __init__(self, picking, parent = None):
        super().__init__(parent=parent)
        self.picking = picking
        self._pause = False
        self._stop = False
        self._mutex = QMutex()
        self._wait_cond = QWaitCondition()
    
    def run(self):

        try:
            self.status_update.emit('Start Picking Thread')
            self._check_state()
            self.picking.pick.get_classified()
            self.status_update.emit('Matching to pick parameters')
            self._check_state()
            self.picking.pick.match_pick()
            self.status_update.emit('Start of picking')

            for checkpoint, log_me in self.picking.pick.pick_me():
                self._check_state()
                if log_me:
                    self.status_update.emit(checkpoint)
            self.status_update.emit('Picking complete!')
        except Exception as e:
            self.status_update.emit(f'Exception {str(e)}')
        finally:
            self.picking_done.emit()

    def _check_state(self):
        """Check function for whether pause/resume, or stop have been 
        pressed
        """

        self._mutex.lock()
        while self._pause:
            logging.info('Picking Thread Paused')
            self._wait_cond.wait(self._mutex)
        if self._stop:
            self._mutex.unlock()
            logging.info('Picking Thread Stopped')
            raise Exception('Stopped Picking')
        self._mutex.unlock()

    def pause(self):
        """Pause function to pause picking
        """

        self._mutex.lock()
        self._pause = True
        self._mutex.unlock()

    def resume(self):
        """Function to resume picking
        """

        self._mutex.lock()
        self._pause = False
        self._wait_cond.wakeAll()
        self._mutex.unlock()

    def stop(self):
        """Function to stop picking
        """

        self._mutex.lock()
        self._stop = True
        self._wait_cond.wakeAll()
        self._mutex.unlock()

class PickWidget(QPushButton):
    """A push button widget to start picking
    """
    
    def __init__(self, picking, parent: QWidget | None=None):
        
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )
        self.setText("Full Pick!")

        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.clicked.connect(self._start_full_picking) 

        self.fp_thread = None
        self.paused = False

        self.pause_button = QPushButton('Pause Picking')
        self.pause_button.clicked.connect(self._pause_picking)
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton('Stop Picking')
        self.stop_button.clicked.connect(self._stop_picking)
        self.stop_button.setEnabled(False)
    
    def _start_full_picking(self):

        self._mmc.live_mode = True
        
        if self.picking.pick_calib and self.picking.disp_calib:
            self.fp_thread = PickerThread(self.picking)
            self.fp_thread.status_update.connect(self._update_status)
            self.fp_thread.picking_done.connect(self._picking_finished)
            self.fp_thread.start()
        else:
            logging.info('Pipette not calibrated')
            QMessageBox.information(self, 'Calibration Needed', f'Please calibrate the pipette before picking')

    def _update_status(self, msg):
        """Helper to update logging
        """

        logging.info(f'{msg}')

    def _picking_finished(self):
        """Helper to update logging on thread
        """

        logging.info('Picker thread finished')
        QMessageBox.information(self, 'Complete', f'Picking Finished!')

    def _pause_picking(self):
        """Callback to pause picking
        """

        if self.fp_thread and self.fp_thread.isRunning():
            if not self.paused:
                self.fp_thread.pause()
                self.pause_button.setText('Resume Picking')
                self.paused = True
                logging.info('Paused picking')
            else:
                self.fp_thread.resume()
                self.pause_button.setText('Pause Picking')
                self.paused = False
                logging.info('Resumed Picking')
            

    def _stop_picking(self):
        """Calback to stop picking
        """

        if self.fp_thread and self.fp_thread.isRunning():
            self.fp_thread.stop()
            logging.info('Stop picking requested')


class NewExptWidget(QPushButton):
    """A push button widget to start a new experiment
    """
    
    new_exp_req = pyqtSignal()

    def __init__(self, picking, parent: QWidget | None=None):
        
        super().__init__(parent=parent)

        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        )

        self.picking = picking
        self._mmc = CMMCorePlus.instance()

        self._create_button()

    def _create_button(self)->None:
        
        self.setText("New Experiment")
        self.clicked.connect(self._new)

    def _new(self):
        logging.info('Start new experiment')

        self.picking.update_pick_widgets(False)
        self.new_exp_req.emit()


class ResetWidget(QPushButton):
    """A push button widget to reset the hardware connection
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
        
        self.setText("Reset Hardware")
        self.clicked.connect(self.picking.pick.reset_hardware) 


class HomeWidget(QPushButton):
    """A push button widget to move the dispense stages to the home position
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
        
        self.setText("Move Dispense Stages to Home")
        self.clicked.connect(self.picking.pick.phc.dest_home)  


class ImageWidget(QPushButton):
    """A push button widget to move the stages for fluorescence imaging
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
        
        self.setText("Move Stages to Image")
        self.clicked.connect(self.picking.pick.phc.move_fluor_img)


class SinglePickThread(QThread):
    """Thread picking so that live preview stay on during a single pick
    """

    status_update = pyqtSignal(str)
    picking_done = pyqtSignal()

    def __init__(self, picking, parent = None):
        """Thread for single picking

        :param picking: picking gui class
        :type picking: pick gui class instance
        """

        super().__init__(parent=parent)
        self.picking = picking
    
    def run(self):
        """Run the single pick thread
        """

        try:
            self.status_update.emit('Start Single Pick Thread')
            self.picking.pick.single_pick(self.dtime)
            self.status_update.emit('Single Pick Complete!')
        except Exception as e:
            self.status_update.emit(f'Exception {str(e)}')
        finally:
            self.status_update.emit('Finished single pick')


class SinglePickWidget(QWidget):
    """A widget to pick once with the automation at the current stage
    position
    """

    def __init__(self, picking, parent: QWidget | None=None):
        
        super().__init__(parent=parent)

        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_gui()

    def _create_gui(self):

        layout = QGridLayout(self)
        label = QLabel('Single Pick')
        layout.addWidget(label, 0, 0)
        delay_label = QLabel('Delay Time')
        layout.addWidget(delay_label, 1, 0)

        self.delay_time_spinbox = QDoubleSpinBox()
        self.delay_time_spinbox.setRange(0.00, 10.00)
        self.delay_time_spinbox.setSingleStep(0.05)
        self.delay_time_spinbox.setValue(1.00)
        layout.addWidget(self.delay_time_spinbox, 2, 0)
        unit_label = QLabel('s')
        layout.addWidget(unit_label, 2, 1)

        self.single_pick_btn = QPushButton('Single Pick')
        self.single_pick_btn.clicked.connect(self._start_pick)
        layout.addWidget(self.single_pick_btn, 3, 0)

    def _start_pick(self):
        """Runs the single pick thread
        """

        self._mmc.live_mode = True

        if self.picking.pick_calib and self.picking.disp_calib:
            self.sp_thread = SinglePickThread(picking = self.picking)
            self.sp_thread.dtime = self.delay_time_spinbox.value()
            logging.info(f'Delay time set to {self.sp_thread.dtime} s')
            self.sp_thread.status_update.connect(self._update_status)
            self.sp_thread.start()
        else:
            logging.info('Pipette not calibrated')

    def _update_status(self, msg):
        """Helper to update logging
        """

        logging.info(f'{msg}')






