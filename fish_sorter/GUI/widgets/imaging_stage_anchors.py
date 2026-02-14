from __future__ import annotations

from typing import Optional

from fish_sorter.GUI.widgets import imaging_stage_math
from fish_sorter.GUI.widgets.grid_ulbr import ULBRGrid


class ImagingStageAnchors:
    def __init__(self, panel):
        self.p = panel

    def default_requested_well(self, anchor_name: str) -> str:
        return imaging_stage_math.default_requested_well(
            str(anchor_name),
            int(self.p.rows.value()),
            int(self.p.cols.value()),
        )

    def neighbor_wells(self, well: str) -> list[str]:
        return imaging_stage_math.neighbor_wells(
            str(well),
            int(self.p.rows.value()),
            int(self.p.cols.value()),
        )

    def pack_well_vertex(self, well: str, vertex: str) -> str:
        return imaging_stage_math.pack_well_vertex(str(well), str(vertex))

    def unpack_well_vertex(self, s: str) -> tuple[str, str]:
        return imaging_stage_math.unpack_well_vertex(str(s))

    def rebuild_anchor_well_choices(self):
        rows = int(self.p.rows.value())
        cols = int(self.p.cols.value())
        if rows < 1 or cols < 1:
            return

        sel = self.p.presets.selected_grid()
        anchors = (sel or {}).get("anchors") if isinstance(sel, dict) else None
        anchors = anchors if isinstance(anchors, dict) else {}

        for nm in getattr(self.p, "_anchor_names", []):
            ui = self.p._anchors_ui.get(nm)
            if not isinstance(ui, dict):
                continue

            combo = ui.get("combo")
            sx = ui.get("x")
            sy = ui.get("y")
            if combo is None or sx is None or sy is None:
                continue

            try:
                combo.blockSignals(True)
                combo.clear()
            except Exception:
                pass

            saved = anchors.get(nm) if isinstance(anchors.get(nm), dict) else {}
            req_well = str(saved.get("well") or self.default_requested_well(nm))
            req_vertex = str(saved.get("vertex") or "C").upper()
            if req_vertex not in self.p.VERTEX_CHOICES:
                req_vertex = "C"

            try:
                for w in self.neighbor_wells(req_well):
                    for v in self.p.VERTEX_CHOICES:
                        combo.addItem(self.pack_well_vertex(w, v))

                want = self.pack_well_vertex(req_well, req_vertex)
                idx = combo.findText(want)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            except Exception:
                pass

            try:
                combo.blockSignals(False)
            except Exception:
                pass

            try:
                if "x_um" in saved:
                    sx.setValue(float(saved["x_um"]))
                if "y_um" in saved:
                    sy.setValue(float(saved["y_um"]))
            except Exception:
                pass

    def goto_anchor_requested(self, anchor_name: str):
        ui = self.p._anchors_ui.get(str(anchor_name))
        if not isinstance(ui, dict):
            return
        try:
            wv = str(ui["combo"].currentText())
        except Exception:
            return
        well, _vertex = self.unpack_well_vertex(wv)

        g = ULBRGrid(
            ul_x=float(self.p.presets.ul_x_from_selected()),
            ul_y=float(self.p.presets.ul_y_from_selected()),
            br_x=float(self.p.presets.br_x_from_selected()),
            br_y=float(self.p.presets.br_y_from_selected()),
            rows=int(self.p.rows.value()),
            cols=int(self.p.cols.value()),
        )
        xy = g.xy_for_well(str(well))
        if xy is None:
            try:
                self.p.status.setText(f"Status: cannot go-to {well} (need UL/BR + rows/cols)")
            except Exception:
                pass
            return

        x, y = xy
        ok = self.p.stageio.set_xy(float(x), float(y))
        try:
            self.p.status.setText(f"Status: go-to {anchor_name} {well} -> {'OK' if ok else 'FAIL'}")
        except Exception:
            pass
        self.p.stageio.refresh()

    def set_anchor_from_current(self, anchor_name: str):
        xy = self.p.stageio.get_xy()
        if xy is None:
            try:
                self.p.status.setText("Status: no XY stage")
            except Exception:
                pass
            return
        x, y = xy

        ui = self.p._anchors_ui.get(str(anchor_name))
        if not isinstance(ui, dict):
            return

        try:
            wv = str(ui["combo"].currentText())
        except Exception:
            return
        well, vertex = self.unpack_well_vertex(wv)

        try:
            ui["x"].setValue(float(x))
            ui["y"].setValue(float(y))
        except Exception:
            pass

        idx = self.p.presets.grid_idx()
        if idx is None:
            try:
                self.p.status.setText("Status: select a grid preset first")
            except Exception:
                pass
            return

        g = self.p.grid_presets[idx]
        if not isinstance(g, dict):
            return

        anchors = g.get("anchors") if isinstance(g.get("anchors"), dict) else {}
        anchors[str(anchor_name)] = {"well": str(well), "vertex": str(vertex), "x_um": float(x), "y_um": float(y)}
        g["anchors"] = anchors

        if str(anchor_name) == "UL":
            g["ul_x"] = float(x)
            g["ul_y"] = float(y)
        if str(anchor_name) == "BR":
            g["br_x"] = float(x)
            g["br_y"] = float(y)

        g["rows"] = int(self.p.rows.value())
        g["cols"] = int(self.p.cols.value())
        g["mode"] = "affine" if self.p.mode.currentIndex() == 1 else "ulbr"

        self.p.presets.save_grids()
        self.p.presets.refresh_grid_list()
        try:
            self.p.grid_list.setCurrentRow(int(idx))
        except Exception:
            pass

        try:
            self.p.status.setText(f"Status: set {anchor_name} from current XY (saved into selected preset)")
        except Exception:
            pass
