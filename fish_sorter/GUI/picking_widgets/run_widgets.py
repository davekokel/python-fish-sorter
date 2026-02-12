import logging

from pymmcore_plus import CMMCorePlus
from PyQt6.QtCore import pyqtSignal, QMutex, QThread, QWaitCondition
from qtpy.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QWidget,
)

class PickerThread(QThread):
    """Thread picking so that live preview stays on during full picking."""
    status_update = pyqtSignal(str)
    picking_done = pyqtSignal()

    def __init__(self, picking, parent=None):
        super().__init__(parent=parent)
        self.picking = picking
        self._pause = False
        self._stop = False
        self._mutex = QMutex()
        self._wait_cond = QWaitCondition()

    def run(self):
        try:
            self.status_update.emit("Start Picking Thread")
            self._check_state()
            self.picking.pick.get_classified()
            self.status_update.emit("Matching to pick parameters")
            self._check_state()
            self.picking.pick.match_pick()
            self.status_update.emit("Start of picking")

            for checkpoint, log_me in self.picking.pick.pick_me():
                self._check_state()
                if log_me:
                    self.status_update.emit(checkpoint)

            self.status_update.emit("Picking complete!")
        except Exception as e:
            self.status_update.emit(f"Exception {str(e)}")
        finally:
            self.picking_done.emit()

    def _check_state(self):
        self._mutex.lock()
        while self._pause:
            logging.info("Picking Thread Paused")
            self._wait_cond.wait(self._mutex)
        if self._stop:
            self._mutex.unlock()
            logging.info("Picking Thread Stopped")
            raise Exception("Stopped Picking")
        self._mutex.unlock()

    def pause(self):
        self._mutex.lock()
        self._pause = True
        self._mutex.unlock()

    def resume(self):
        self._mutex.lock()
        self._pause = False
        self._wait_cond.wakeAll()
        self._mutex.unlock()

    def stop(self):
        self._mutex.lock()
        self._stop = True
        self._wait_cond.wakeAll()
        self._mutex.unlock()


class PickWidget(QPushButton):
    """A push button widget to start full picking."""
    state_changed = pyqtSignal(str)

    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)

        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.setText("Full Pick!")

        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.clicked.connect(self._start_full_picking)

        self.fp_thread = None
        self.paused = False

        self.pause_button = QPushButton("Pause Picking")
        self.pause_button.clicked.connect(self._pause_picking)
        self.pause_button.setEnabled(False)

        self.stop_button = QPushButton("Stop Picking")
        self.stop_button.clicked.connect(self._stop_picking)
        self.stop_button.setEnabled(False)

    def _start_full_picking(self):
        self._mmc.live_mode = True

        if self.picking.pick_calib and self.picking.disp_calib:
            self.fp_thread = PickerThread(self.picking)
            self.fp_thread.status_update.connect(self._update_status)
            self.fp_thread.picking_done.connect(self._picking_finished)

            self.paused = False
            self.pause_button.setText("Pause Picking")
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)

            self.state_changed.emit("PICKING")
            self.fp_thread.start()
        else:
            logging.info("Pipette not calibrated")
            self.state_changed.emit("CALIBRATION")
            QMessageBox.information(self, "Calibration Needed", "Please set pick + dispense positions before picking")

    def _update_status(self, msg):
        logging.info(f"{msg}")
        if isinstance(msg, str) and msg.startswith("Exception "):
            self.state_changed.emit("ERROR")

    def _picking_finished(self):
        logging.info("Picker thread finished")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.pause_button.setText("Pause Picking")
        self.paused = False
        self.state_changed.emit("READY")
        QMessageBox.information(self, "Complete", "Picking Finished!")

    def _pause_picking(self):
        if self.fp_thread and self.fp_thread.isRunning():
            if not self.paused:
                self.fp_thread.pause()
                self.pause_button.setText("Resume Picking")
                self.paused = True
                logging.info("Paused picking")
                self.state_changed.emit("PAUSED")
            else:
                self.fp_thread.resume()
                self.pause_button.setText("Pause Picking")
                self.paused = False
                logging.info("Resumed Picking")
                self.state_changed.emit("PICKING")

    def _stop_picking(self):
        if self.fp_thread and self.fp_thread.isRunning():
            self.fp_thread.stop()
            logging.info("Stop picking requested")
            self.state_changed.emit("STOPPING")


class NewExptWidget(QPushButton):
    """A push button widget to start a new experiment."""
    new_exp_req = pyqtSignal()

    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("New Experiment")
        self.clicked.connect(self._new)

    def _new(self):
        logging.info("Start new experiment")
        self.picking.update_pick_widgets(False)
        self.new_exp_req.emit()


class ResetWidget(QPushButton):
    """A push button widget to reset the hardware connection."""

    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Reset Hardware")
        self.clicked.connect(self.picking.pick.reset_hardware)


class SinglePickThread(QThread):
    """Thread picking so that live preview stays on during a single pick."""

    status_update = pyqtSignal(str)
    picking_done = pyqtSignal()

    def __init__(self, picking, parent=None):
        super().__init__(parent=parent)
        self.picking = picking
        self.dtime = 1.0

    def run(self):
        try:
            self.status_update.emit("Start Single Pick Thread")
            self.picking.pick.single_pick(self.dtime)
            self.status_update.emit("Single Pick Complete!")
        except Exception as e:
            self.status_update.emit(f"Exception {str(e)}")
        finally:
            self.status_update.emit("Finished single pick")


class SinglePickWidget(QWidget):
    """A widget to pick once with the automation at the current stage position."""

    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self._create_gui()

    def _create_gui(self):
        layout = QGridLayout(self)
        layout.addWidget(QLabel("Single Pick"), 0, 0)
        layout.addWidget(QLabel("Delay Time"), 1, 0)

        self.delay_time_spinbox = QDoubleSpinBox()
        self.delay_time_spinbox.setRange(0.00, 10.00)
        self.delay_time_spinbox.setSingleStep(0.05)
        self.delay_time_spinbox.setValue(1.00)
        layout.addWidget(self.delay_time_spinbox, 2, 0)
        layout.addWidget(QLabel("s"), 2, 1)

        self.single_pick_btn = QPushButton("Single Pick")
        self.single_pick_btn.clicked.connect(self._start_pick)
        layout.addWidget(self.single_pick_btn, 3, 0)

    def _start_pick(self):
        self._mmc.live_mode = True

        if self.picking.pick_calib and self.picking.disp_calib:
            self.sp_thread = SinglePickThread(picking=self.picking)
            self.sp_thread.dtime = float(self.delay_time_spinbox.value())
            logging.info(f"Delay time set to {self.sp_thread.dtime} s")
            self.sp_thread.status_update.connect(self._update_status)
            self.sp_thread.start()
        else:
            logging.info("Pipette not calibrated")

    def _update_status(self, msg):
        logging.info(f"{msg}")
