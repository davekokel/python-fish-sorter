from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QGridLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QMessageBox,
)

from fish_sorter.GUI.widgets.grid_ulbr import ULBRGrid, all_wells, well_to_rc
from fish_sorter.GUI.widgets.well_tile_picker import WellTilePickerDialog
from fish_sorter.GUI.widgets.imaging_stage_crosshairs import render_crosshairs
from fish_sorter.GUI.widgets.imaging_stage_store import read_grids, write_grids
from fish_sorter.GUI.widgets import imaging_stage_math


@dataclass
class Anchor:
    name: str
    well: str
    vertex: str  # "C" (center legacy) or "UL"/"UR"/"LL"/"LR"
    x_um: float
    y_um: float


class ImagingStagePanel(QWidget):
    """
    Imaging stage / plate component (MMCore XYStage) + Qt grid presets.

    Truth model:
      - Grid presets are truth (qt_presets/imaging_stage_grid.json)
      - UL/BR provides coarse navigation.
      - Optional: RowRef + ColRef enables affine mapping (more accurate mid-grid).

    Grid preset schema (backward compatible):
      {name, ul_x, ul_y, br_x, br_y, rows, cols,
       mode: "ulbr" | "affine",
       anchors: {UL:{well,vertex,x_um,y_um}, BR:{...}, RowRef:{...}, ColRef:{...}} }
    """

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

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.refresh)

        self._build_ui()
        self._load_grids()
        self._timer.start()
        self.refresh()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(QLabel("Imaging Stage / Plate"))

        # Status
        status = QGroupBox("Status")
        sg = QGridLayout(status)
        sg.setContentsMargins(8, 8, 8, 8)
        sg.setHorizontalSpacing(10)
        sg.setVerticalSpacing(8)

        self.lbl_dev = QLabel("XY stage: -")
        self.lbl_xy = QLabel("X: -    Y: -")
        sg.addWidget(self.lbl_dev, 0, 0, 1, 3)
        sg.addWidget(self.lbl_xy, 0, 3, 1, 3)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        sg.addWidget(self.btn_refresh, 1, 0)

        root.addWidget(status)

        # Controls (jog + goto)
        ctrl = QGroupBox("Controls")
        cg = QGridLayout(ctrl)
        cg.setContentsMargins(8, 8, 8, 8)
        cg.setHorizontalSpacing(10)
        cg.setVerticalSpacing(8)

        cg.addWidget(QLabel("Step (um)"), 0, 0)
        self.step_um = QDoubleSpinBox()
        self.step_um.setDecimals(1)
        self.step_um.setRange(0.1, 50000.0)
        self.step_um.setValue(100.0)
        cg.addWidget(self.step_um, 0, 1)

        self.btn_xm = QPushButton("X -")
        self.btn_xp = QPushButton("X +")
        self.btn_ym = QPushButton("Y -")
        self.btn_yp = QPushButton("Y +")

        self.btn_xm.clicked.connect(lambda: self.jog(-self.step_um.value(), 0.0))
        self.btn_xp.clicked.connect(lambda: self.jog(+self.step_um.value(), 0.0))
        self.btn_ym.clicked.connect(lambda: self.jog(0.0, -self.step_um.value()))
        self.btn_yp.clicked.connect(lambda: self.jog(0.0, +self.step_um.value()))

        cg.addWidget(self.btn_xm, 1, 0)
        cg.addWidget(self.btn_xp, 1, 1)
        cg.addWidget(self.btn_ym, 1, 2)
        cg.addWidget(self.btn_yp, 1, 3)

        cg.addWidget(QLabel("Go to X (um)"), 2, 0)
        self.goto_x = QDoubleSpinBox()
        self.goto_x.setDecimals(1)
        self.goto_x.setRange(-1e9, 1e9)
        cg.addWidget(self.goto_x, 2, 1)

        cg.addWidget(QLabel("Go to Y (um)"), 2, 2)
        self.goto_y = QDoubleSpinBox()
        self.goto_y.setDecimals(1)
        self.goto_y.setRange(-1e9, 1e9)
        cg.addWidget(self.goto_y, 2, 3)

        self.btn_goto = QPushButton("Go")
        self.btn_goto.clicked.connect(self.goto)
        cg.addWidget(self.btn_goto, 2, 4)

        root.addWidget(ctrl)

        # Grid calibration
        calib = QGroupBox("Grid calibration (vertex-based)")
        gg = QGridLayout(calib)
        gg.setContentsMargins(8, 8, 8, 8)
        gg.setHorizontalSpacing(10)
        gg.setVerticalSpacing(8)

        self.mode = QComboBox()
        self.mode.addItems(["ulbr (2-point)", "affine (UL+RowRef+ColRef)"])
        gg.addWidget(QLabel("Mode"), 0, 0)
        gg.addWidget(self.mode, 0, 1, 1, 2)

        self.btn_crosshairs = QPushButton("Toggle crosshairs")
        self.btn_crosshairs.clicked.connect(self.toggle_crosshairs)
        gg.addWidget(self.btn_crosshairs, 0, 4)

        self.rows = QSpinBox(); self.rows.setRange(1, 99); self.rows.setValue(8)
        self.cols = QSpinBox(); self.cols.setRange(1, 99); self.cols.setValue(12)
        self.rows.valueChanged.connect(self._update_well_list)
        self.cols.valueChanged.connect(self._update_well_list)

        gg.addWidget(QLabel("Rows"), 1, 0)
        gg.addWidget(self.rows, 1, 1)
        gg.addWidget(QLabel("Cols"), 1, 2)
        gg.addWidget(self.cols, 1, 3)

        # 5-column calibration table header
        gg.addWidget(QLabel("Label"), 2, 0)
        gg.addWidget(QLabel("Well / vertex"), 2, 1)
        gg.addWidget(QLabel("X (um)"), 2, 2)
        gg.addWidget(QLabel("Y (um)"), 2, 3)
        gg.addWidget(QLabel("Actions"), 2, 4)

        # Anchor rows
        self._anchor_names = ["UL", "BR", "RowRef", "ColRef"]
        self._anchors_ui: dict[str, dict] = {}

        r0 = 3
        for i, nm in enumerate(self._anchor_names):
            rr = r0 + i
            gg.addWidget(QLabel(nm), rr, 0)

            combo = QComboBox()
            combo.setEditable(False)
            gg.addWidget(combo, rr, 1)

            sx = QDoubleSpinBox(); sx.setDecimals(1); sx.setRange(-1e9, 1e9)
            sy = QDoubleSpinBox(); sy.setDecimals(1); sy.setRange(-1e9, 1e9)
            gg.addWidget(sx, rr, 2)
            gg.addWidget(sy, rr, 3)

            btns = QWidget()
            bgl = QGridLayout(btns)
            bgl.setContentsMargins(0, 0, 0, 0)
            bgl.setHorizontalSpacing(6)
            bgl.setVerticalSpacing(4)

            btn_goto = QPushButton("Go to")
            btn_set = QPushButton("Set = current XY")

            bgl.addWidget(btn_goto, 0, 0)
            bgl.addWidget(btn_set, 0, 1)

            gg.addWidget(btns, rr, 4)

            self._anchors_ui[nm] = {
                "combo": combo,
                "x": sx,
                "y": sy,
                "btn_goto": btn_goto,
                "btn_set": btn_set,
            }

            btn_goto.clicked.connect(lambda _=False, nn=nm: self._goto_anchor_requested(nn))
            btn_set.clicked.connect(lambda _=False, nn=nm: self._set_anchor_from_current(nn))

        # Well navigation widgets (kept, but tiles are primary)
        gg.addWidget(QLabel("Well"), 7, 0)
        self.well = QComboBox()
        gg.addWidget(self.well, 7, 1)

        self.btn_refresh_wells = QPushButton("Update wells")
        self.btn_refresh_wells.clicked.connect(self._update_well_list)
        gg.addWidget(self.btn_refresh_wells, 7, 2)

        self.btn_goto_well = QPushButton("Go to well")
        self.btn_goto_well.clicked.connect(self.goto_selected_well)
        gg.addWidget(self.btn_goto_well, 7, 3)

        self.btn_well_tiles = QPushButton("Well tiles…")
        self.btn_well_tiles.clicked.connect(self.open_well_tiles)
        gg.addWidget(self.btn_well_tiles, 7, 4)

        root.addWidget(calib)

        # Grid presets (own frame)
        presets = QGroupBox("Grid presets (truth)")
        pg = QGridLayout(presets)
        pg.setContentsMargins(8, 8, 8, 8)
        pg.setHorizontalSpacing(10)
        pg.setVerticalSpacing(8)

        self.grid_list = QListWidget()
        pg.addWidget(self.grid_list, 0, 0, 6, 4)

        self.btn_grid_new = QPushButton("New")
        self.btn_grid_new.clicked.connect(self._grid_preset_new)
        pg.addWidget(self.btn_grid_new, 0, 4)

        self.btn_grid_save = QPushButton("Save current → selected")
        self.btn_grid_save.clicked.connect(self._grid_preset_save_selected)
        pg.addWidget(self.btn_grid_save, 1, 4)

        self.btn_grid_apply = QPushButton("Load selected")
        self.btn_grid_apply.clicked.connect(self._grid_preset_apply_selected)
        pg.addWidget(self.btn_grid_apply, 2, 4)

        self.btn_grid_delete = QPushButton("Delete selected")
        self.btn_grid_delete.clicked.connect(self._grid_preset_delete_selected)
        pg.addWidget(self.btn_grid_delete, 3, 4)

        self.btn_grid_rename = QPushButton("Rename selected")
        self.btn_grid_rename.clicked.connect(self._grid_preset_rename_selected)
        pg.addWidget(self.btn_grid_rename, 4, 4)

        root.addWidget(presets, stretch=1)

        self.status = QLabel("Status: -")
        root.addWidget(self.status)

        self._update_well_list()

    # ---------------- Crosshairs ----------------
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
    # ---------------- Grid store IO (thin wrappers) ----------------
    def _read_grids(self) -> list[dict]:
        return read_grids(self.store_grids)

    def _write_grids(self, grids: list[dict]):
        try:
            write_grids(self.store_grids, grids)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", repr(e))

    def _load_grids(self):
        self.grid_presets = self._read_grids()
        self._refresh_grid_list()
        self._rebuild_anchor_well_choices()

    def _save_grids(self):
        self._write_grids(self.grid_presets)

    # ---------------- XY stage helpers (restored) ----------------
    def _xy_dev(self) -> Optional[str]:
        try:
            dev = str(self.core.getXYStageDevice() or "").strip()
        except Exception:
            dev = ""
        return dev or None

    def _get_xy(self) -> Optional[tuple[float, float]]:
        dev = self._xy_dev()
        if not dev:
            return None
        try:
            x, y = self.core.getXYPosition(dev)
            return float(x), float(y)
        except Exception:
            try:
                x = float(self.core.getXPosition(dev))
                y = float(self.core.getYPosition(dev))
                return float(x), float(y)
            except Exception:
                return None

    def _set_xy(self, x: float, y: float) -> bool:
        dev = self._xy_dev()
        if not dev:
            return False
        try:
            self.core.setXYPosition(dev, float(x), float(y))
            return True
        except Exception:
            return False

    def refresh(self):
        dev = self._xy_dev()
        try:
            self.lbl_dev.setText(f"XY stage: {dev or '(none)'}")
        except Exception:
            pass

        xy = self._get_xy()
        if xy is None:
            try:
                self.lbl_xy.setText("X: -    Y: -")
                self.status.setText("Status: no XY stage")
            except Exception:
                pass
            return

        x, y = xy
        try:
            self.lbl_xy.setText(f"X: {x:.1f}    Y: {y:.1f}")
        except Exception:
            pass

    def jog(self, dx_um: float, dy_um: float):
        xy = self._get_xy()
        if xy is None:
            return
        x, y = xy
        ok = self._set_xy(x + float(dx_um), y + float(dy_um))
        try:
            self.status.setText(f"Status: jog -> {'OK' if ok else 'FAIL'}")
        except Exception:
            pass
        self.refresh()

    def goto(self):
        try:
            x = float(self.goto_x.value())
            y = float(self.goto_y.value())
        except Exception:
            return
        ok = self._set_xy(x, y)
        try:
            self.status.setText(f"Status: goto -> {'OK' if ok else 'FAIL'}")
        except Exception:
            pass
        self.refresh()

    # ---------------- Wells + anchor choices (restored) ----------------
    def _update_well_list(self):
        wells = all_wells(int(self.rows.value()), int(self.cols.value()))
        cur = ""
        try:
            cur = str(self.well.currentText())
        except Exception:
            cur = ""

        try:
            self.well.blockSignals(True)
        except Exception:
            pass

        try:
            self.well.clear()
            self.well.addItems(wells)
            if cur:
                idx = self.well.findText(cur)
                if idx >= 0:
                    self.well.setCurrentIndex(idx)
        except Exception:
            pass

        try:
            self.well.blockSignals(False)
        except Exception:
            pass

        try:
            self._rebuild_anchor_well_choices()
        except Exception:
            pass

    def open_well_tiles(self):
        wells = all_wells(int(self.rows.value()), int(self.cols.value()))
        dlg = WellTilePickerDialog(wells=wells, columns=int(self.cols.value()), title="Pick a well", parent=self)
        if dlg.exec_():
            if dlg.selected:
                try:
                    idx = self.well.findText(str(dlg.selected))
                    if idx >= 0:
                        self.well.setCurrentIndex(idx)
                except Exception:
                    pass
                try:
                    self.goto_selected_well()
                except Exception:
                    pass

    def goto_selected_well(self):
        try:
            well = str(self.well.currentText())
        except Exception:
            return
        xy = None
        try:
            xy = self._xy_for_well_center(well)
        except Exception:
            xy = None
        if xy is None:
            return
        x, y = xy
        ok = self._set_xy(float(x), float(y))
        try:
            self.status.setText(f"Status: goto well {well} -> {'OK' if ok else 'FAIL'}")
        except Exception:
            pass
        self.refresh()

    # ---- anchor dropdown population (uses imaging_stage_math helpers) ----
    def _default_requested_well(self, anchor_name: str) -> str:
        return imaging_stage_math.default_requested_well(
            str(anchor_name),
            int(self.rows.value()),
            int(self.cols.value()),
        )

    def _neighbor_wells(self, well: str) -> list[str]:
        return imaging_stage_math.neighbor_wells(
            str(well),
            int(self.rows.value()),
            int(self.cols.value()),
        )

    def _pack_well_vertex(self, well: str, vertex: str) -> str:
        return imaging_stage_math.pack_well_vertex(str(well), str(vertex))

    def _unpack_well_vertex(self, s: str) -> tuple[str, str]:
        return imaging_stage_math.unpack_well_vertex(str(s))

    def _rebuild_anchor_well_choices(self):
        rows = int(self.rows.value())
        cols = int(self.cols.value())
        if rows < 1 or cols < 1:
            return

        sel = self._selected_grid()
        anchors = (sel or {}).get("anchors") if isinstance(sel, dict) else None
        anchors = anchors if isinstance(anchors, dict) else {}

        for nm in getattr(self, "_anchor_names", []):
            ui = self._anchors_ui.get(nm)
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
            req_well = str(saved.get("well") or self._default_requested_well(nm))
            req_vertex = str(saved.get("vertex") or "C").upper()
            if req_vertex not in self.VERTEX_CHOICES:
                req_vertex = "C"

            try:
                for w in self._neighbor_wells(req_well):
                    for v in self.VERTEX_CHOICES:
                        combo.addItem(self._pack_well_vertex(w, v))

                want = self._pack_well_vertex(req_well, req_vertex)
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

    # ---------------- Mapping (restored) ----------------
    def _xy_for_well_center(self, well: str) -> Optional[tuple[float, float]]:
        rows = int(self.rows.value())
        cols = int(self.cols.value())
        if rows < 1 or cols < 1:
            return None

        sel = self._selected_grid()
        mode = "ulbr"
        if isinstance(sel, dict):
            mode = str(sel.get("mode") or ("affine" if self.mode.currentIndex() == 1 else "ulbr"))

        if mode == "affine":
            xy = self._xy_affine(str(well))
            if xy is not None:
                return xy

        g = ULBRGrid(
            ul_x=float(self.ul_x_from_selected()),
            ul_y=float(self.ul_y_from_selected()),
            br_x=float(self.br_x_from_selected()),
            br_y=float(self.br_y_from_selected()),
            rows=rows,
            cols=cols,
        )
        return g.xy_for_well(str(well))

    def _xy_affine(self, well: str) -> Optional[tuple[float, float]]:
        sel = self._selected_grid()
        if not isinstance(sel, dict):
            return None
        anchors = sel.get("anchors")
        if not isinstance(anchors, dict):
            return None
        return imaging_stage_math.xy_affine(str(well), anchors)

    # ---------------- Anchor actions (restored) ----------------
    def _goto_anchor_requested(self, anchor_name: str):
        ui = self._anchors_ui.get(str(anchor_name))
        if not isinstance(ui, dict):
            return
        try:
            wv = str(ui["combo"].currentText())
        except Exception:
            return
        well, _vertex = self._unpack_well_vertex(wv)

        g = ULBRGrid(
            ul_x=float(self.ul_x_from_selected()),
            ul_y=float(self.ul_y_from_selected()),
            br_x=float(self.br_x_from_selected()),
            br_y=float(self.br_y_from_selected()),
            rows=int(self.rows.value()),
            cols=int(self.cols.value()),
        )
        xy = g.xy_for_well(str(well))
        if xy is None:
            try:
                self.status.setText(f"Status: cannot go-to {well} (need UL/BR + rows/cols)")
            except Exception:
                pass
            return

        x, y = xy
        ok = self._set_xy(float(x), float(y))
        try:
            self.status.setText(f"Status: go-to {anchor_name} {well} -> {'OK' if ok else 'FAIL'}")
        except Exception:
            pass
        self.refresh()

    def _set_anchor_from_current(self, anchor_name: str):
        xy = self._get_xy()
        if xy is None:
            try:
                self.status.setText("Status: no XY stage")
            except Exception:
                pass
            return
        x, y = xy

        ui = self._anchors_ui.get(str(anchor_name))
        if not isinstance(ui, dict):
            return

        try:
            wv = str(ui["combo"].currentText())
        except Exception:
            return
        well, vertex = self._unpack_well_vertex(wv)

        try:
            ui["x"].setValue(float(x))
            ui["y"].setValue(float(y))
        except Exception:
            pass

        idx = self._grid_idx()
        if idx is None:
            try:
                self.status.setText("Status: select a grid preset first")
            except Exception:
                pass
            return

        g = self.grid_presets[idx]
        if not isinstance(g, dict):
            return

        anchors = g.get("anchors") if isinstance(g.get("anchors"), dict) else {}
        anchors[str(anchor_name)] = {"well": str(well), "vertex": str(vertex), "x_um": float(x), "y_um": float(y)}
        g["anchors"] = anchors

        # keep legacy UL/BR fields in sync
        if str(anchor_name) == "UL":
            g["ul_x"] = float(x)
            g["ul_y"] = float(y)
        if str(anchor_name) == "BR":
            g["br_x"] = float(x)
            g["br_y"] = float(y)

        g["rows"] = int(self.rows.value())
        g["cols"] = int(self.cols.value())
        g["mode"] = "affine" if self.mode.currentIndex() == 1 else "ulbr"

        self._save_grids()
        self._refresh_grid_list()
        try:
            self.grid_list.setCurrentRow(int(idx))
        except Exception:
            pass

        try:
            self.status.setText(f"Status: set {anchor_name} from current XY (saved into selected preset)")
        except Exception:
            pass

    # ---------------- Grid store IO (restored) ----------------
    def _read_grids(self) -> list[dict]:
        return read_grids(self.store_grids)

    def _write_grids(self, grids: list[dict]):
        try:
            write_grids(self.store_grids, grids)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", repr(e))

    def _load_grids(self):
        self.grid_presets = self._read_grids()
        self._refresh_grid_list()
        try:
            self._rebuild_anchor_well_choices()
        except Exception:
            pass

    def _save_grids(self):
        self._write_grids(self.grid_presets)

    # ---------------- Grid preset selection/list (restored) ----------------
    def _grid_idx(self) -> Optional[int]:
        try:
            items = self.grid_list.selectedIndexes()
        except Exception:
            return None
        if not items:
            return None
        try:
            return int(items[0].row())
        except Exception:
            return None

    def _selected_grid(self) -> Optional[dict]:
        idx = self._grid_idx()
        if idx is None:
            return None
        if idx < 0 or idx >= len(self.grid_presets):
            return None
        g = self.grid_presets[idx]
        return g if isinstance(g, dict) else None

    def _refresh_grid_list(self):
        cur = self._grid_idx()
        try:
            self.grid_list.clear()
        except Exception:
            return

        for g in self.grid_presets:
            if not isinstance(g, dict):
                continue
            name = str(g.get("name", "(unnamed)"))
            ulx = g.get("ul_x"); uly = g.get("ul_y")
            brx = g.get("br_x"); bry = g.get("br_y")
            rows = g.get("rows"); cols = g.get("cols")
            mode = g.get("mode", "ulbr")
            try:
                self.grid_list.addItem(QListWidgetItem(
                    f"{name}  |  mode={mode}  UL=({ulx},{uly}) BR=({brx},{bry}) rows={rows} cols={cols}"
                ))
            except Exception:
                pass

        if cur is not None and 0 <= cur < self.grid_list.count():
            try:
                self.grid_list.setCurrentRow(cur)
            except Exception:
                pass

    # ---------------- Grid snapshot + helpers (restored) ----------------
    def ul_x_from_selected(self) -> float:
        try:
            return float(self._anchors_ui["UL"]["x"].value())
        except Exception:
            return 0.0

    def ul_y_from_selected(self) -> float:
        try:
            return float(self._anchors_ui["UL"]["y"].value())
        except Exception:
            return 0.0

    def br_x_from_selected(self) -> float:
        try:
            return float(self._anchors_ui["BR"]["x"].value())
        except Exception:
            return 0.0

    def br_y_from_selected(self) -> float:
        try:
            return float(self._anchors_ui["BR"]["y"].value())
        except Exception:
            return 0.0

    def _grid_snapshot(self) -> dict:
        sel = self._selected_grid() or {}
        anchors = sel.get("anchors") if isinstance(sel.get("anchors"), dict) else {}
        mode = sel.get("mode") or ("affine" if self.mode.currentIndex() == 1 else "ulbr")
        return {
            "ul_x": float(self.ul_x_from_selected()),
            "ul_y": float(self.ul_y_from_selected()),
            "br_x": float(self.br_x_from_selected()),
            "br_y": float(self.br_y_from_selected()),
            "rows": int(self.rows.value()),
            "cols": int(self.cols.value()),
            "mode": str(mode),
            "anchors": anchors,
        }

    # ---------------- Grid preset CRUD (restored) ----------------
    def _grid_preset_new(self):
        name, ok = QInputDialog.getText(self, "New grid preset", "Grid preset name:")
        if not ok or not str(name).strip():
            return
        d = {"name": str(name).strip(), **self._grid_snapshot()}
        self.grid_presets.append(d)
        self._save_grids()
        self._refresh_grid_list()
        try:
            self.status.setText("Status: created new grid preset")
        except Exception:
            pass

    def _grid_preset_save_selected(self):
        idx = self._grid_idx()
        if idx is None:
            try:
                self.status.setText("Status: select a grid preset first")
            except Exception:
                pass
            return
        self.grid_presets[idx].update(self._grid_snapshot())
        self._save_grids()
        self._refresh_grid_list()
        try:
            self.grid_list.setCurrentRow(idx)
        except Exception:
            pass
        try:
            self.status.setText("Status: saved current → selected")
        except Exception:
            pass

    def _grid_preset_apply_selected(self):
        idx = self._grid_idx()
        if idx is None:
            return
        g = self.grid_presets[idx]
        if not isinstance(g, dict):
            return

        try:
            self.rows.setValue(int(g.get("rows", 1)))
        except Exception:
            pass
        try:
            self.cols.setValue(int(g.get("cols", 1)))
        except Exception:
            pass

        mode = str(g.get("mode", "ulbr"))
        try:
            self.mode.setCurrentIndex(1 if mode == "affine" else 0)
        except Exception:
            pass

        anchors = g.get("anchors") if isinstance(g.get("anchors"), dict) else {}

        # backfill UL/BR anchor dicts if missing (keeps backward compatibility)
        if "UL" not in anchors:
            anchors["UL"] = {
                "well": "A1",
                "vertex": "C",
                "x_um": float(g.get("ul_x", 0.0)),
                "y_um": float(g.get("ul_y", 0.0)),
            }
        if "BR" not in anchors:
            anchors["BR"] = {
                "well": self._default_requested_well("BR"),
                "vertex": "C",
                "x_um": float(g.get("br_x", 0.0)),
                "y_um": float(g.get("br_y", 0.0)),
            }

        g["anchors"] = anchors

        # push anchor coords into UI fields
        for nm in ["UL", "BR", "RowRef", "ColRef"]:
            ui = self._anchors_ui.get(nm)
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

        self._update_well_list()
        try:
            self.status.setText("Status: loaded selected grid")
        except Exception:
            pass

    def _grid_preset_delete_selected(self):
        idx = self._grid_idx()
        if idx is None:
            return
        try:
            name = str(self.grid_presets[idx].get("name", "(unnamed)"))
        except Exception:
            name = "(unnamed)"
        try:
            self.grid_presets.pop(idx)
        except Exception:
            return
        self._save_grids()
        self._refresh_grid_list()
        try:
            self.status.setText(f"Status: deleted grid {name}")
        except Exception:
            pass

    def _grid_preset_rename_selected(self):
        idx = self._grid_idx()
        if idx is None:
            return
        cur = "(unnamed)"
        try:
            cur = str(self.grid_presets[idx].get("name", "(unnamed)"))
        except Exception:
            pass
        name, ok = QInputDialog.getText(self, "Rename grid preset", "New name:", text=cur)
        if not ok or not str(name).strip():
            return
        self.grid_presets[idx]["name"] = str(name).strip()
        self._save_grids()
        self._refresh_grid_list()
        try:
            self.grid_list.setCurrentRow(idx)
        except Exception:
            pass
        try:
            self.status.setText("Status: renamed grid preset")
        except Exception:
            pass


