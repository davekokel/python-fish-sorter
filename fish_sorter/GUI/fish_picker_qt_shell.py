from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from qtpy.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from napari.components.viewer_model import ViewerModel
from napari.qt import QtViewer

from fish_sorter.GUI.picking_gui import PickGUI
from fish_sorter.GUI.picking_widgets.workflow_panel import WorkflowPanel
from fish_sorter.GUI.picking import Pick
from fish_sorter.hardware.picking_pipette import PickingPipette
from fish_sorter.GUI.mm_panel import MicroManagerPanel


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_site_cfg() -> dict:
    cfg = _repo_root() / "fish_sorter.local.toml"
    if not cfg.exists():
        return {}
    return tomllib.loads(cfg.read_text(encoding="utf-8"))


class PickingContainer(QWidget):
    """
    Picking super-panel.

    This is the core UX fix:
    - Wizard is not a separate "place" anymore.
    - It is a tab inside Picking.
    """

    TAB_WIZARD = 0
    TAB_PICKING = 1

    def __init__(self, pick_gui: PickGUI, router, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.pick_gui = pick_gui
        self.router = router

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        self.workflow_panel = WorkflowPanel(self.pick_gui, router=self.router)
        self.tabs.addTab(self.workflow_panel, "Wizard")
        self.tabs.addTab(self.pick_gui, "Picking")

        self.tabs.setCurrentIndex(self.TAB_WIZARD)

    def show_wizard(self):
        self.tabs.setCurrentIndex(self.TAB_WIZARD)

    def show_picking(self):
        self.tabs.setCurrentIndex(self.TAB_PICKING)

    def go_to_step(self, step: int):
        # Always route into the Picking tab for actions
        self.show_picking()

        if step == 1:
            self.pick_gui.focus_tab(self.pick_gui.TAB_PLATE)
            self.pick_gui.focus_stage_subtab("Dispense Plate")
            return

        if step in (2, 3):
            self.pick_gui.focus_tab(self.pick_gui.TAB_PIPETTE)
            return

        if step == 4:
            # MDA not yet ported as a Qt panel; route to Micro-Manager for now.
            self.router.go_to_panel("Micro-Manager")
            return

        self.pick_gui.focus_tab(self.pick_gui.TAB_RUN)


class QtShellRouter:
    """
    Router used by WorkflowPanel.
    Keeps the WorkflowPanel decoupled from napari docks.
    """

    def __init__(self, shell: "FishPickerQtShell"):
        self.shell = shell

    def has_panel(self, name: str) -> bool:
        return name in self.shell.panel_index

    def go_to_panel(self, name: str) -> None:
        self.shell.show_panel(name)

    def go_to_step(self, step: int) -> None:
        self.shell.go_to_step(step)


class FishPickerQtShell(QMainWindow):
    """
    Qt-first shell with embedded napari viewer.

    Left nav only selects the two real destinations:
      - Picking (which contains Wizard + Picking)
      - Micro-Manager
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FishPicker (Qt Shell)")

        self.site_cfg = _load_site_cfg()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Left navigation (ONLY real destinations)
        nav = QWidget()
        nav_l = QVBoxLayout(nav)
        nav_l.setContentsMargins(0, 0, 0, 0)
        nav_l.setSpacing(8)

        self.btn_picking = QPushButton("Picking")
        self.btn_mm = QPushButton("Micro-Manager")

        nav_l.addWidget(self.btn_picking)
        nav_l.addWidget(self.btn_mm)
        nav_l.addStretch(1)

        layout.addWidget(nav)

        # Embedded napari viewer
        self.viewer_model = ViewerModel(title="Viewer")
        self.qt_viewer = QtViewer(self.viewer_model)
        layout.addWidget(self.qt_viewer, stretch=1)

        # Right panel stack (ONLY real destinations)
        self.panels = QStackedWidget()
        self.panels.setMinimumWidth(520)
        layout.addWidget(self.panels)

        # Initialize picking backend (sim bring-up)
        cfg_dir = _repo_root() / "fish_sorter" / "configs"
        self.phc = PickingPipette(cfg_dir, sim=True)
        self.pick = Pick(self.phc)

        # Panels
        self.router = QtShellRouter(self)

        self.pick_gui = PickGUI(self.pick)
        self.picking_container = PickingContainer(self.pick_gui, router=self.router)

        self.mm_panel = MicroManagerPanel(self.viewer_model, site_cfg=self.site_cfg)

        # Stack order (stable names)
        self.panel_index = {}
        self._add_panel("Picking", self.picking_container)
        self._add_panel("Micro-Manager", self.mm_panel)

        # Wiring
        self.btn_picking.clicked.connect(lambda: self.show_panel("Picking"))
        self.btn_mm.clicked.connect(lambda: self.show_panel("Micro-Manager"))

        self.show_panel("Picking")
        self.picking_container.show_wizard()

    def _add_panel(self, name: str, w: QWidget) -> None:
        idx = self.panels.count()
        self.panels.addWidget(w)
        self.panel_index[name] = idx

    def show_panel(self, name: str) -> None:
        idx = self.panel_index.get(name)
        if idx is None:
            return
        self.panels.setCurrentIndex(idx)

    def go_to_step(self, step: int) -> None:
        # Delegate to PickingContainer for in-picking steps
        self.show_panel("Picking")
        self.picking_container.go_to_step(step)


def main() -> None:
    _ = argparse.ArgumentParser().parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    win = FishPickerQtShell()
    win.resize(1800, 1000)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
