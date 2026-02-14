from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QWidget

from fish_sorter.GUI.widgets.imaging_stage_crosshairs import render_crosshairs
from fish_sorter.GUI.widgets.imaging_stage_stageio import ImagingStageStageIO
from fish_sorter.GUI.widgets.imaging_stage_presets import ImagingStagePresets
from fish_sorter.GUI.widgets.imaging_stage_anchors import ImagingStageAnchors
from fish_sorter.GUI.widgets.imaging_stage_mapping import ImagingStageMapping
from fish_sorter.GUI.widgets.imaging_stage_wells import ImagingStageWells
from fish_sorter.GUI.widgets.imaging_stage_ui import build_imaging_stage_ui
from fish_sorter.GUI.widgets import imaging_stage_math


@dataclass
class Anchor:
    name: str
    well: str
    vertex: str
    x_um: float
    y_um: float


class ImagingStagePanel(QWidget):
    VERTEX_CHOICES = imaging_stage_math.VERTEX_CHOICES

    def __init__(self, core, viewer_model=None, repo_root: Path | None = None, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.core = core
        self.viewer_model = viewer_model

        if repo_root is None:
            repo_root = Path(__file__).resolve().parents[2]
        self.repo_root = repo_root

        self.store_grids = (repo_root / "qt_presets" / "imaging_stage_grid.json")
        self.store_grids.parent.mkdir(parents=True, exist_ok=True)

        self.grid_presets: list[dict] = []
        self._crosshairs_on = False

        self.stageio = ImagingStageStageIO(self)
        self.presets = ImagingStagePresets(self)
        self.anchors = ImagingStageAnchors(self)
        self.mapping = ImagingStageMapping(self)
        self.wells = ImagingStageWells(self)

        build_imaging_stage_ui(self)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.stageio.refresh)

        self.presets.load_grids()
        self._timer.start()
        self.stageio.refresh()

    def toggle_crosshairs(self):
        self._crosshairs_on = not self._crosshairs_on
        self._render_crosshairs()

    def _render_crosshairs(self):
        on, msg = render_crosshairs(self.viewer_model, bool(self._crosshairs_on))
        self._crosshairs_on = bool(on)
        if msg:
            try:
                self.status.setText(str(msg))
            except Exception:
                pass
