from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from qtpy.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from napari.components.viewer_model import ViewerModel
from napari.qt import QtViewer

from pymmcore_plus import CMMCorePlus

from fish_sorter.GUI.picking_gui import PickGUI
from fish_sorter.GUI.picking_widgets.workflow_panel import WorkflowPanel
from fish_sorter.GUI.picking import Pick
from fish_sorter.hardware.picking_pipette import PickingPipette
from fish_sorter.GUI.mm_panel import MicroManagerPanel
from fish_sorter.GUI.transmitted_light_panel import TransmittedLightPanel
from fish_sorter.GUI.fluorescence_panel import FluorescencePanel
from fish_sorter.GUI.focus_panel import FocusPanel
from fish_sorter.GUI.pipette_panel import PipettePanel
from fish_sorter.GUI.scenes_panel import ScenesPanel
from fish_sorter.GUI.imaging_stage_panel import ImagingStagePanel
from fish_sorter.GUI.collection_plate_panel import CollectionPlatePanel
from fish_sorter.GUI.zaber_mapping_panel import ZaberMappingPanel


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_site_cfg() -> dict:
    cfg = _repo_root() / "fish_sorter.local.toml"
    if not cfg.exists():
        return {}
    return tomllib.loads(cfg.read_text(encoding="utf-8"))


class PickingContainer(QWidget):
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
        self.show_picking()

        if step == 1:
            self.pick_gui.focus_tab(self.pick_gui.TAB_PLATE)
            self.pick_gui.focus_stage_subtab("Dispense Plate")
            return

        if step in (2, 3):
            self.pick_gui.focus_tab(self.pick_gui.TAB_PIPETTE)
            return

        if step == 4:
            self.router.go_to_panel("Micro-Manager")
            return

        self.pick_gui.focus_tab(self.pick_gui.TAB_RUN)


class QtShellRouter:
    def __init__(self, shell: "FishPickerQtShell"):
        self.shell = shell

    def has_panel(self, name: str) -> bool:
        return name in self.shell.panel_index

    def go_to_panel(self, name: str) -> None:
        self.shell.show_panel(name)

    def go_to_step(self, step: int) -> None:
        self.shell.go_to_step(step)


class FishPickerQtShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FishPicker (Qt Shell)")

        self.repo_root = _repo_root()
        self.site_cfg = _load_site_cfg()

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

        # 1) Hardware COM mapping
        nav_l.addWidget(QLabel("Hardware COM mapping"))

        self.btn_zaber_map = QPushButton("Zaber COM mapping")
        self.btn_valve_map = QPushButton("Valve mapping")
        self.btn_olympus = QPushButton("Olympus")

        nav_l.addWidget(self.btn_zaber_map)
        nav_l.addWidget(self.btn_valve_map)
        nav_l.addWidget(self.btn_olympus)

        nav_l.addSpacing(10)

        # 2) Hardware setting presets
        nav_l.addWidget(QLabel("Hardware setting presets"))

        nav_l.addWidget(QLabel("Scope"))
        self.btn_tl = QPushButton("Camera + transmitted light")
        self.btn_focus = QPushButton("Focus")
        self.btn_fl = QPushButton("Camera + fluorescent light")
        nav_l.addWidget(self.btn_tl)
        nav_l.addWidget(self.btn_focus)
        nav_l.addWidget(self.btn_fl)

        nav_l.addWidget(QLabel("Stages"))
        self.btn_imaging_stage = QPushButton("Imaging stage (scope)")
        self.btn_collection_plate = QPushButton("Collection stage (zaber)")
        nav_l.addWidget(self.btn_imaging_stage)
        nav_l.addWidget(self.btn_collection_plate)

        self.btn_pipette = QPushButton("Pipette")
        nav_l.addWidget(self.btn_pipette)

        self.btn_valves = QPushButton("Valves")
        nav_l.addWidget(self.btn_valves)

        nav_l.addSpacing(10)

        # 3) Select hardware presets for next experiment
        nav_l.addWidget(QLabel("Select hardware presets for next experiment"))
        self.btn_scenes = QPushButton("Select presets")
        nav_l.addWidget(self.btn_scenes)

        nav_l.addSpacing(10)

        # 4) MDA setup
        nav_l.addWidget(QLabel("MDA setup"))
        self.btn_mda = QPushButton("MDA")
        nav_l.addWidget(self.btn_mda)

        nav_l.addSpacing(10)

        # 5) Run it
        nav_l.addWidget(QLabel("Run it"))
        self.btn_run = QPushButton("Run")
        nav_l.addWidget(self.btn_run)

        # spacer so Tools stays pinned at bottom
        nav_l.addStretch(1)

        # 6) Tools (bottom)
        nav_l.addWidget(QLabel("Tools"))
        self.btn_picking = QPushButton("Picking")
        self.btn_mm = QPushButton("Micro-Manager (posterity)")
        nav_l.addWidget(self.btn_picking)
        nav_l.addWidget(self.btn_mm)

        layout.addWidget(nav)
        # Embedded napari viewer
        self.viewer_model = ViewerModel(title="Viewer")
        self.qt_viewer = QtViewer(self.viewer_model)
        layout.addWidget(self.qt_viewer, stretch=1)

        # Right panel stack
        self.panels = QStackedWidget()
        self.panels.setMinimumWidth(520)
        layout.addWidget(self.panels)

        # Shared MM core
        self.core = CMMCorePlus.instance()
        self._load_mm_config_best_effort()

        # Picking backend (sim bring-up)
        cfg_dir = self.repo_root / "fish_sorter" / "configs"
        self.phc = PickingPipette(cfg_dir, sim=True)
        self.pick = Pick(self.phc)

        self.router = QtShellRouter(self)

        # Panels
        self.pick_gui = PickGUI(self.pick)
        self.picking_container = PickingContainer(self.pick_gui, router=self.router)

        self.tl_panel = TransmittedLightPanel(self.core, self.viewer_model, repo_root=self.repo_root)
        self.fl_panel = FluorescencePanel(self.core, self.viewer_model, repo_root=self.repo_root)
        self.focus_panel = FocusPanel(self.core)
        self.pipette_panel = PipettePanel(self.pick, self.repo_root)

        self.imaging_stage_panel = ImagingStagePanel(self.core, viewer_model=self.viewer_model, repo_root=self.repo_root)
        self.collection_plate_panel = CollectionPlatePanel(self.pick, repo_root=self.repo_root)
        self.zaber_map_panel = ZaberMappingPanel(self.repo_root, zc=self.phc.zc)
        self.valve_map_panel = QLabel("Valve mapping: placeholder (define valve channel mapping here)")
        self.olympus_panel = QLabel("Olympus: placeholder (scope-specific settings/presets go here)")
        self.valves_panel = QLabel("Valves: placeholder (valve presets/sequences go here)")
        self.run_panel = QLabel("Run: shortcut to Picking panel (use Tools -> Picking for now)")

        self.mm_panel = MicroManagerPanel(self.viewer_model, site_cfg=self.site_cfg)

        self.scenes_panel = ScenesPanel(
            repo_root=self.repo_root,
            core=self.core,
            tl_panel=self.tl_panel,
            camera_panel=None,
        )

        self.panel_index = {}
        self._add_panel("Transmitted Light", self.tl_panel)
        self._add_panel("Fluorescence", self.fl_panel)
        self._add_panel("Focus", self.focus_panel)
        self._add_panel("Pipette", self.pipette_panel)
        self._add_panel("Imaging Stage / Plate", self.imaging_stage_panel)
        self._add_panel("Collection Stage / Plate", self.collection_plate_panel)
        self._add_panel("Zaber Mapping", self.zaber_map_panel)
        self._add_panel("Valve mapping", self.valve_map_panel)
        self._add_panel("Olympus", self.olympus_panel)
        self._add_panel("Valves", self.valves_panel)
        self._add_panel("Run", self.run_panel)
        self.mda_panel = QLabel("MDA: placeholder — wire to MM MDA widget later")
        self._add_panel("MDA", self.mda_panel)
        self._add_panel("Picking", self.picking_container)
        self._add_panel("Micro-Manager", self.mm_panel)
        self._add_panel("Scenes", self.scenes_panel)

        # Wiring
        self.btn_tl.clicked.connect(lambda: self.show_panel("Transmitted Light"))
        self.btn_fl.clicked.connect(lambda: self.show_panel("Fluorescence"))
        self.btn_focus.clicked.connect(lambda: self.show_panel("Focus"))
        self.btn_pipette.clicked.connect(lambda: self.show_panel("Pipette"))
        self.btn_imaging_stage.clicked.connect(lambda: self.show_panel("Imaging Stage / Plate"))
        self.btn_collection_plate.clicked.connect(lambda: self.show_panel("Collection Stage / Plate"))
        self.btn_mda.clicked.connect(lambda: self.show_panel("MDA"))
        self.btn_zaber_map.clicked.connect(lambda: self.show_panel("Zaber Mapping"))
        self.btn_valve_map.clicked.connect(lambda: self.show_panel("Valve mapping"))
        self.btn_olympus.clicked.connect(lambda: self.show_panel("Olympus"))
        self.btn_valves.clicked.connect(lambda: self.show_panel("Valves"))
        self.btn_run.clicked.connect(lambda: self.show_panel("Picking"))
        self.btn_picking.clicked.connect(lambda: self.show_panel("Picking"))
        self.btn_mm.clicked.connect(lambda: self.show_panel("Micro-Manager"))
        self.btn_scenes.clicked.connect(lambda: self.show_panel("Scenes"))

        self.show_panel("Transmitted Light")

    def _load_mm_config_best_effort(self):
        mm = self.site_cfg.get("micromanager", {}) if isinstance(self.site_cfg, dict) else {}
        mm_cfg = (mm.get("mm_config_path") or "").strip()
        if not mm_cfg:
            return
        cfg_path = Path(mm_cfg)
        if not cfg_path.exists():
            return
        try:
            self.core.loadSystemConfiguration(str(cfg_path))
        except Exception:
            return

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












