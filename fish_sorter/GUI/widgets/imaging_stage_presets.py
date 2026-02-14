from __future__ import annotations

from pathlib import Path
from typing import Optional

from qtpy.QtWidgets import QListWidgetItem, QMessageBox, QInputDialog

from fish_sorter.GUI.widgets.imaging_stage_store import read_grids, write_grids


class ImagingStagePresets:
    def __init__(self, panel):
        self.p = panel

    def read_grids(self) -> list[dict]:
        return read_grids(self.p.store_grids)

    def write_grids(self, grids: list[dict]):
        try:
            write_grids(self.p.store_grids, grids)
        except Exception as e:
            QMessageBox.warning(self.p, "Save failed", repr(e))

    def load_grids(self):
        self.p.grid_presets = self.read_grids()
        self.refresh_grid_list()
        try:
            self.p.anchors.rebuild_anchor_well_choices()
        except Exception:
            pass

    def save_grids(self):
        self.write_grids(self.p.grid_presets)

    def grid_idx(self) -> Optional[int]:
        try:
            items = self.p.grid_list.selectedIndexes()
        except Exception:
            return None
        if not items:
            return None
        try:
            return int(items[0].row())
        except Exception:
            return None

    def selected_grid(self) -> Optional[dict]:
        idx = self.grid_idx()
        if idx is None:
            return None
        if idx < 0 or idx >= len(self.p.grid_presets):
            return None
        g = self.p.grid_presets[idx]
        return g if isinstance(g, dict) else None

    def refresh_grid_list(self):
        cur = self.grid_idx()
        try:
            self.p.grid_list.clear()
        except Exception:
            return

        for g in self.p.grid_presets:
            if not isinstance(g, dict):
                continue
            name = str(g.get("name", "(unnamed)"))
            ulx = g.get("ul_x"); uly = g.get("ul_y")
            brx = g.get("br_x"); bry = g.get("br_y")
            rows = g.get("rows"); cols = g.get("cols")
            mode = g.get("mode", "ulbr")
            try:
                self.p.grid_list.addItem(QListWidgetItem(
                    f"{name}  |  mode={mode}  UL=({ulx},{uly}) BR=({brx},{bry}) rows={rows} cols={cols}"
                ))
            except Exception:
                pass

        if cur is not None and 0 <= cur < self.p.grid_list.count():
            try:
                self.p.grid_list.setCurrentRow(cur)
            except Exception:
                pass

    def ul_x_from_selected(self) -> float:
        try:
            return float(self.p._anchors_ui["UL"]["x"].value())
        except Exception:
            return 0.0

    def ul_y_from_selected(self) -> float:
        try:
            return float(self.p._anchors_ui["UL"]["y"].value())
        except Exception:
            return 0.0

    def br_x_from_selected(self) -> float:
        try:
            return float(self.p._anchors_ui["BR"]["x"].value())
        except Exception:
            return 0.0

    def br_y_from_selected(self) -> float:
        try:
            return float(self.p._anchors_ui["BR"]["y"].value())
        except Exception:
            return 0.0

    def grid_snapshot(self) -> dict:
        sel = self.selected_grid() or {}
        anchors = sel.get("anchors") if isinstance(sel.get("anchors"), dict) else {}
        mode = sel.get("mode") or ("affine" if self.p.mode.currentIndex() == 1 else "ulbr")
        return {
            "ul_x": float(self.ul_x_from_selected()),
            "ul_y": float(self.ul_y_from_selected()),
            "br_x": float(self.br_x_from_selected()),
            "br_y": float(self.br_y_from_selected()),
            "rows": int(self.p.rows.value()),
            "cols": int(self.p.cols.value()),
            "mode": str(mode),
            "anchors": anchors,
        }

    def grid_preset_new(self):
        name, ok = QInputDialog.getText(self.p, "New grid preset", "Grid preset name:")
        if not ok or not str(name).strip():
            return
        d = {"name": str(name).strip(), **self.grid_snapshot()}
        self.p.grid_presets.append(d)
        self.save_grids()
        self.refresh_grid_list()
        try:
            self.p.status.setText("Status: created new grid preset")
        except Exception:
            pass

    def grid_preset_save_selected(self):
        idx = self.grid_idx()
        if idx is None:
            try:
                self.p.status.setText("Status: select a grid preset first")
            except Exception:
                pass
            return
        self.p.grid_presets[idx].update(self.grid_snapshot())
        self.save_grids()
        self.refresh_grid_list()
        try:
            self.p.grid_list.setCurrentRow(idx)
        except Exception:
            pass
        try:
            self.p.status.setText("Status: saved current → selected")
        except Exception:
            pass

    def grid_preset_apply_selected(self):
        idx = self.grid_idx()
        if idx is None:
            return
        g = self.p.grid_presets[idx]
        if not isinstance(g, dict):
            return

        try:
            self.p.rows.setValue(int(g.get("rows", 1)))
        except Exception:
            pass
        try:
            self.p.cols.setValue(int(g.get("cols", 1)))
        except Exception:
            pass

        mode = str(g.get("mode", "ulbr"))
        try:
            self.p.mode.setCurrentIndex(1 if mode == "affine" else 0)
        except Exception:
            pass

        anchors = g.get("anchors") if isinstance(g.get("anchors"), dict) else {}

        if "UL" not in anchors:
            anchors["UL"] = {
                "well": "A1",
                "vertex": "C",
                "x_um": float(g.get("ul_x", 0.0)),
                "y_um": float(g.get("ul_y", 0.0)),
            }
        if "BR" not in anchors:
            anchors["BR"] = {
                "well": self.p.anchors.default_requested_well("BR"),
                "vertex": "C",
                "x_um": float(g.get("br_x", 0.0)),
                "y_um": float(g.get("br_y", 0.0)),
            }

        g["anchors"] = anchors

        for nm in ["UL", "BR", "RowRef", "ColRef"]:
            ui = self.p._anchors_ui.get(nm)
            if not isinstance(ui, dict):
                continue
            a = anchors.get(nm) if isinstance(anchors.get(nm), dict) else {}
            try:
                if "x_um" in a:
                    ui["x"].setValue(float(a["x_um"]))
                if "y_um" in a:
                    ui["y"].setValue(float(a["y_um"]))
            except Exception:
                pass

        self.p.wells.update_well_list()
        try:
            self.p.status.setText("Status: loaded selected grid")
        except Exception:
            pass

    def grid_preset_delete_selected(self):
        idx = self.grid_idx()
        if idx is None:
            return
        try:
            name = str(self.p.grid_presets[idx].get("name", "(unnamed)"))
        except Exception:
            name = "(unnamed)"
        try:
            self.p.grid_presets.pop(idx)
        except Exception:
            return
        self.save_grids()
        self.refresh_grid_list()
        try:
            self.p.status.setText(f"Status: deleted grid {name}")
        except Exception:
            pass

    def grid_preset_rename_selected(self):
        idx = self.grid_idx()
        if idx is None:
            return
        cur = "(unnamed)"
        try:
            cur = str(self.p.grid_presets[idx].get("name", "(unnamed)"))
        except Exception:
            pass
        name, ok = QInputDialog.getText(self.p, "Rename grid preset", "New name:", text=cur)
        if not ok or not str(name).strip():
            return
        self.p.grid_presets[idx]["name"] = str(name).strip()
        self.save_grids()
        self.refresh_grid_list()
        try:
            self.p.grid_list.setCurrentRow(idx)
        except Exception:
            pass
        try:
            self.p.status.setText("Status: renamed grid preset")
        except Exception:
            pass
