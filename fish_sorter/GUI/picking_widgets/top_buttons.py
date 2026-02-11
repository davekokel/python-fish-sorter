import logging

from pymmcore_plus import CMMCorePlus
from PyQt6.QtCore import pyqtSignal
from qtpy.QtWidgets import QPushButton, QSizePolicy, QWidget

class PipettePickCalibWidget(QPushButton):
    save_pick_h = pyqtSignal()

    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Set Pick Position")
        self.clicked.connect(self._pick_calib)

    def _pick_calib(self)->None:
        logging.info("Calibrate pick height into array")
        self.picking.pick.set_calib(pick=True)
        self.picking.pick_calib = True
        self.picking._update_calib_status()
        self.save_pick_h.emit()


class PipetteDispCalibWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Set Dispense Position")
        self.clicked.connect(self._disp_calib)

    def _disp_calib(self)->None:
        logging.info("Calibrate dispense height into destination plate")
        self.picking.pick.set_calib(pick=False)
        self.picking.disp_calib = True
        self.picking._update_calib_status()


class Pipette2PickWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Move to Pick Position")
        self.clicked.connect(self._pick_pos)

    def _pick_pos(self)->None:
        self.picking.pick.move_calib(pick=True)
        self.picking.pick.phc.move_pipette(pos="pick")


class Pipette2DispWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Move to Dispense Position")
        self.clicked.connect(self._disp_pos)

    def _disp_pos(self)->None:
        self.picking.pick.move_calib(pick=False, well="A01")
        self.picking.pick.phc.move_pipette(pos="dispense")


class Pipette2ClearWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Move to Clearance Position")
        self.clicked.connect(self._clear_pos)

    def _clear_pos(self)->None:
        self.picking.pick.phc.move_pipette(pos="clearance")


class Pipette2SwingWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Move to Swing Position")
        self.clicked.connect(self._swing_pos)

    def _swing_pos(self)->None:
        self.picking.pick.phc.move_pipette(pos="pipette_swing")


class HomeWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Move Dispense Stages to Home")
        self.clicked.connect(self.picking.pick.phc.dest_home)


class ImageWidget(QPushButton):
    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        self.picking = picking
        self._mmc = CMMCorePlus.instance()
        self.setText("Move Stages to Image")
        self.clicked.connect(self.picking.pick.phc.move_fluor_img)
