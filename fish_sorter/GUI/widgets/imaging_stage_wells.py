from __future__ import annotations

from fish_sorter.GUI.widgets.grid_ulbr import all_wells
from fish_sorter.GUI.widgets.well_tile_picker import WellTilePickerDialog


class ImagingStageWells:
    def __init__(self, panel):
        self.p = panel

    def update_well_list(self):
        wells = all_wells(int(self.p.rows.value()), int(self.p.cols.value()))
        cur = ""
        try:
            cur = str(self.p.well.currentText())
        except Exception:
            cur = ""

        try:
            self.p.well.blockSignals(True)
        except Exception:
            pass

        try:
            self.p.well.clear()
            self.p.well.addItems(wells)
            if cur:
                idx = self.p.well.findText(cur)
                if idx >= 0:
                    self.p.well.setCurrentIndex(idx)
        except Exception:
            pass

        try:
            self.p.well.blockSignals(False)
        except Exception:
            pass

        try:
            self.p.anchors.rebuild_anchor_well_choices()
        except Exception:
            pass

    def open_well_tiles(self):
        wells = all_wells(int(self.p.rows.value()), int(self.p.cols.value()))
        dlg = WellTilePickerDialog(wells=wells, columns=int(self.p.cols.value()), title="Pick a well", parent=self.p)
        if dlg.exec_():
            if dlg.selected:
                try:
                    idx = self.p.well.findText(str(dlg.selected))
                    if idx >= 0:
                        self.p.well.setCurrentIndex(idx)
                except Exception:
                    pass
                try:
                    self.goto_selected_well()
                except Exception:
                    pass

    def goto_selected_well(self):
        try:
            well = str(self.p.well.currentText())
        except Exception:
            return
        xy = None
        try:
            xy = self.p.mapping.xy_for_well_center(well)
        except Exception:
            xy = None
        if xy is None:
            return
        x, y = xy
        ok = self.p.stageio.set_xy(float(x), float(y))
        try:
            self.p.status.setText(f"Status: goto well {well} -> {'OK' if ok else 'FAIL'}")
        except Exception:
            pass
        self.p.stageio.refresh()
