import logging
from qtpy.QtWidgets import QGridLayout, QLabel, QPushButton, QWidget

class StagePositionsWidget(QWidget):
    """Operator-friendly readout of current Zaber positions (x/y/p)."""

    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.picking = picking
        self._create_gui()

    def _create_gui(self):
        layout = QGridLayout(self)
        layout.addWidget(QLabel("Zabers (x/y plate, p pipette)"), 0, 0, 1, 4)

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

