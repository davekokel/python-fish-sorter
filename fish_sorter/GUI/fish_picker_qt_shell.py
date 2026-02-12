from __future__ import annotations

import argparse
import sys

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from napari.components.viewer_model import ViewerModel
from napari.qt import QtViewer


class FishPickerQtShell(QMainWindow):
    """
    Qt-first application shell with embedded napari viewer.

    Qt owns:
      - navigation
      - panel composition
      - future state machine + safety gating

    Napari is treated as a viewer component (layers/overlays), not a dock framework.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FishPicker (Qt Shell)")

        root = QWidget()
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Left navigation
        nav = QWidget()
        nav_l = QVBoxLayout(nav)
        nav_l.setContentsMargins(0, 0, 0, 0)
        nav_l.setSpacing(8)

        self.btn_workflow = QPushButton("Workflow")
        self.btn_picking = QPushButton("Picking")
        self.btn_mda = QPushButton("MDA")
        self.btn_classify = QPushButton("Classify")

        for b in (self.btn_workflow, self.btn_picking, self.btn_mda, self.btn_classify):
            b.setMinimumWidth(200)
            nav_l.addWidget(b)

        nav_l.addStretch(1)
        layout.addWidget(nav)

        # Embedded napari viewer (ViewerModel + QtViewer)
        self.viewer_model = ViewerModel(title="Viewer")
        self.qt_viewer = QtViewer(self.viewer_model)
        layout.addWidget(self.qt_viewer, stretch=1)

        # Right panels owned by Qt
        self.panels = QStackedWidget()
        self.panels.setMinimumWidth(420)

        self.panel_workflow = QLabel("Workflow panel placeholder (Qt shell)")
        self.panel_workflow.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.panel_picking = QLabel("Picking panel placeholder (Qt shell)")
        self.panel_picking.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.panel_mda = QLabel("MDA panel placeholder (Qt shell)")
        self.panel_mda.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.panel_classify = QLabel("Classify panel placeholder (Qt shell)")
        self.panel_classify.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.panels.addWidget(self.panel_workflow)  # idx 0
        self.panels.addWidget(self.panel_picking)   # idx 1
        self.panels.addWidget(self.panel_mda)       # idx 2
        self.panels.addWidget(self.panel_classify)  # idx 3

        layout.addWidget(self.panels)

        # Wiring
        self.btn_workflow.clicked.connect(lambda: self.panels.setCurrentIndex(0))
        self.btn_picking.clicked.connect(lambda: self.panels.setCurrentIndex(1))
        self.btn_mda.clicked.connect(lambda: self.panels.setCurrentIndex(2))
        self.btn_classify.clicked.connect(lambda: self.panels.setCurrentIndex(3))

        self.panels.setCurrentIndex(0)


def main() -> None:
    _ = argparse.ArgumentParser().parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    win = FishPickerQtShell()
    win.resize(1600, 900)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
