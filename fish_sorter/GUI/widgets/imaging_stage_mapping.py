from __future__ import annotations

from typing import Optional

from fish_sorter.GUI.widgets.grid_ulbr import ULBRGrid
from fish_sorter.GUI.widgets import imaging_stage_math


class ImagingStageMapping:
    def __init__(self, panel):
        self.p = panel

    def xy_for_well_center(self, well: str) -> Optional[tuple[float, float]]:
        rows = int(self.p.rows.value())
        cols = int(self.p.cols.value())
        if rows < 1 or cols < 1:
            return None

        sel = self.p.presets.selected_grid()
        mode = "ulbr"
        if isinstance(sel, dict):
            mode = str(sel.get("mode") or ("affine" if self.p.mode.currentIndex() == 1 else "ulbr"))

        if mode == "affine":
            xy = self.xy_affine(str(well))
            if xy is not None:
                return xy

        g = ULBRGrid(
            ul_x=float(self.p.presets.ul_x_from_selected()),
            ul_y=float(self.p.presets.ul_y_from_selected()),
            br_x=float(self.p.presets.br_x_from_selected()),
            br_y=float(self.p.presets.br_y_from_selected()),
            rows=rows,
            cols=cols,
        )
        return g.xy_for_well(str(well))

    def xy_affine(self, well: str) -> Optional[tuple[float, float]]:
        sel = self.p.presets.selected_grid()
        if not isinstance(sel, dict):
            return None
        anchors = sel.get("anchors")
        if not isinstance(anchors, dict):
            return None
        return imaging_stage_math.xy_affine(str(well), anchors)
