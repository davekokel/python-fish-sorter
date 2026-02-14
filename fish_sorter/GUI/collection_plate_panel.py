from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from fish_sorter.GUI.widgets.grid_ulbr import all_wells


class CollectionPlatePanel(QWidget):
    """
    Collection stage / plate component.

    Tab 1: Motion
      - IN/AWAY controls
      - motion presets stored in qt_presets/collection_plate_motion.json
      - Motion safety: requires pipette clearance. If zaber 'p' is unmapped, we refuse motion.

    Tab 2: Grid
      - UL/BR + rows/cols
      - grid presets stored in qt_presets/collection_plate_grids.json
      - reads/writes napari-compatible pipettor_cfg keys:
          dispense_plate.TL_corner.{x,y}
          dispense_plate.BR_corner.{x,y}
          dispense_plate.rows
          dispense_plate.cols
      - Capture sources:
          MM XYStage (preferred, works today)
          Zaber XY (disabled until mapping exists)
    """

    def __init__(self, pick, repo_root: Path | None = None, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.pick = pick

        if repo_root is None:
            repo_root = Path(__file__).resolve().parents[2]
        self.repo_root = repo_root

        self.motion_store = (repo_root / "qt_presets" / "collection_plate_motion.json")
        self.motion_store.parent.mkdir(parents=True, exist_ok=True)

        self.grid_store = (repo_root / "qt_presets" / "collection_plate_grids.json")

        self.motion_presets: list[dict] = []
        self.grid_presets: list[dict] = []

        self._build_ui()
        self._load_motion_store()
        self._load_grid_store()
        self._load_grid_from_cfg()

        self._update_mapping_status()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(QLabel("Collection Stage / Plate"))

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        self.tab_motion = QWidget()
        self.tab_grid = QWidget()
        self.tabs.addTab(self.tab_motion, "Motion (IN/AWAY)")
        self.tabs.addTab(self.tab_grid, "Grid (UL/BR)")

        self._build_motion_tab()
        self._build_grid_tab()

        self.status = QLabel("Status: -")
        root.addWidget(self.status)

    def _build_motion_tab(self):
        root = QVBoxLayout(self.tab_motion)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.map_box = QGroupBox("Safety / Mapping")
        mg = QGridLayout(self.map_box)
        mg.setContentsMargins(8, 8, 8, 8)
        mg.setHorizontalSpacing(10)
        mg.setVerticalSpacing(8)

        self.lbl_pipette = QLabel("Pipette axis (p): -")
        self.lbl_stage = QLabel("Stage axes (x/y): -")
        mg.addWidget(self.lbl_pipette, 0, 0, 1, 2)
        mg.addWidget(self.lbl_stage, 1, 0, 1, 2)

        root.addWidget(self.map_box)

        box = QGroupBox("Controls")
        h = QHBoxLayout(box)
        h.setContentsMargins(8, 8, 8, 8)
        h.setSpacing(10)

        self.btn_away = QPushButton("AWAY (for picking)")
        self.btn_in = QPushButton("IN (for collecting)")
        self.btn_away.clicked.connect(self.away)
        self.btn_in.clicked.connect(self.into)

        h.addWidget(self.btn_away)
        h.addWidget(self.btn_in)
        root.addWidget(box)

        presets_box = QGroupBox("Qt Presets (motion)")
        pb = QHBoxLayout(presets_box)
        pb.setContentsMargins(8, 8, 8, 8)

        self.motion_list = QListWidget()
        pb.addWidget(self.motion_list, stretch=1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        self.btn_motion_new = QPushButton("New")
        self.btn_motion_new.clicked.connect(self._motion_new)
        rv.addWidget(self.btn_motion_new)

        self.btn_motion_set_in = QPushButton("Set selected = IN")
        self.btn_motion_set_in.clicked.connect(lambda: self._motion_set_selected("IN"))
        rv.addWidget(self.btn_motion_set_in)

        self.btn_motion_set_away = QPushButton("Set selected = AWAY")
        self.btn_motion_set_away.clicked.connect(lambda: self._motion_set_selected("AWAY"))
        rv.addWidget(self.btn_motion_set_away)

        self.btn_motion_apply = QPushButton("Apply selected")
        self.btn_motion_apply.clicked.connect(self._motion_apply_selected)
        rv.addWidget(self.btn_motion_apply)

        self.btn_motion_delete = QPushButton("Delete selected")
        self.btn_motion_delete.clicked.connect(self._motion_delete_selected)
        rv.addWidget(self.btn_motion_delete)

        rv.addStretch(1)
        pb.addWidget(right)

        root.addWidget(presets_box, stretch=1)

    def _build_grid_tab(self):
        root = QVBoxLayout(self.tab_grid)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        grid_box = QGroupBox("Dispense/Collection plate grid (UL/BR)")
        gg = QGridLayout(grid_box)
        gg.setContentsMargins(8, 8, 8, 8)
        gg.setHorizontalSpacing(10)
        gg.setVerticalSpacing(8)

        self.ul_x = QDoubleSpinBox(); self.ul_x.setDecimals(1); self.ul_x.setRange(-1e9, 1e9)
        self.ul_y = QDoubleSpinBox(); self.ul_y.setDecimals(1); self.ul_y.setRange(-1e9, 1e9)
        self.br_x = QDoubleSpinBox(); self.br_x.setDecimals(1); self.br_x.setRange(-1e9, 1e9)
        self.br_y = QDoubleSpinBox(); self.br_y.setDecimals(1); self.br_y.setRange(-1e9, 1e9)

        self.rows = QSpinBox(); self.rows.setRange(1, 26); self.rows.setValue(8)
        self.cols = QSpinBox(); self.cols.setRange(1, 99); self.cols.setValue(12)

        self.btn_set_ul_mm = QPushButton("Set UL = current (MM XYStage)")
        self.btn_set_br_mm = QPushButton("Set BR = current (MM XYStage)")
        self.btn_set_ul_zaber = QPushButton("Set UL = current (Zaber XY)")
        self.btn_set_br_zaber = QPushButton("Set BR = current (Zaber XY)")

        self.btn_set_ul_mm.clicked.connect(lambda: self._capture_ul(source="mm"))
        self.btn_set_br_mm.clicked.connect(lambda: self._capture_br(source="mm"))
        self.btn_set_ul_zaber.clicked.connect(lambda: self._capture_ul(source="zaber"))
        self.btn_set_br_zaber.clicked.connect(lambda: self._capture_br(source="zaber"))

        gg.addWidget(QLabel("UL X"), 0, 0); gg.addWidget(self.ul_x, 0, 1)
        gg.addWidget(QLabel("UL Y"), 0, 2); gg.addWidget(self.ul_y, 0, 3)
        gg.addWidget(self.btn_set_ul_mm, 0, 4); gg.addWidget(self.btn_set_ul_zaber, 0, 5)

        gg.addWidget(QLabel("BR X"), 1, 0); gg.addWidget(self.br_x, 1, 1)
        gg.addWidget(QLabel("BR Y"), 1, 2); gg.addWidget(self.br_y, 1, 3)
        gg.addWidget(self.btn_set_br_mm, 1, 4); gg.addWidget(self.btn_set_br_zaber, 1, 5)

        gg.addWidget(QLabel("Rows"), 2, 0); gg.addWidget(self.rows, 2, 1)
        gg.addWidget(QLabel("Cols"), 2, 2); gg.addWidget(self.cols, 2, 3)

        gg.addWidget(QLabel("Well"), 3, 0)
        self.well = QComboBox()
        gg.addWidget(self.well, 3, 1)

        self.btn_update_wells = QPushButton("Update wells")
        self.btn_update_wells.clicked.connect(self._update_well_list)
        gg.addWidget(self.btn_update_wells, 3, 2)

        self.btn_save_cfg = QPushButton("Save grid → pipettor_cfg")
        self.btn_save_cfg.clicked.connect(self._save_grid_to_cfg)
        gg.addWidget(self.btn_save_cfg, 3, 3)

        self.btn_reload_cfg = QPushButton("Reload from pipettor_cfg")
        self.btn_reload_cfg.clicked.connect(self._load_grid_from_cfg)
        gg.addWidget(self.btn_reload_cfg, 3, 4)

        root.addWidget(grid_box)

        presets_box = QGroupBox("Qt Presets (grid formats)")
        pb = QHBoxLayout(presets_box)
        pb.setContentsMargins(8, 8, 8, 8)

        self.grid_list = QListWidget()
        pb.addWidget(self.grid_list, stretch=1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        self.btn_grid_new = QPushButton("New")
        self.btn_grid_new.clicked.connect(self._grid_new)
        rv.addWidget(self.btn_grid_new)

        self.btn_grid_save = QPushButton("Save current → selected")
        self.btn_grid_save.clicked.connect(self._grid_save_selected)
        rv.addWidget(self.btn_grid_save)

        self.btn_grid_load = QPushButton("Load selected")
        self.btn_grid_load.clicked.connect(self._grid_apply_selected)
        rv.addWidget(self.btn_grid_load)

        self.btn_grid_delete = QPushButton("Delete selected")
        self.btn_grid_delete.clicked.connect(self._grid_delete_selected)
        rv.addWidget(self.btn_grid_delete)

        rv.addStretch(1)
        pb.addWidget(right)

        root.addWidget(presets_box, stretch=1)

        self._update_well_list()

    # ---------------- mapping status ----------------
    def _phc(self):
        try:
            return getattr(self.pick, "phc", None)
        except Exception:
            return None

    def _has_zaber_arm(self, arm: str) -> bool:
        phc = self._phc()
        if phc is None:
            return False
        zc = getattr(phc, "zc", None)
        if zc is None:
            return False
        try:
            _ = zc.get_pos(str(arm))
            return True
        except Exception:
            return False

    def _update_mapping_status(self):
        has_p = self._has_zaber_arm("p")
        has_x = self._has_zaber_arm("x")
        has_y = self._has_zaber_arm("y")

        self.lbl_pipette.setText(f"Pipette axis (p): {'OK' if has_p else 'MISSING'}")
        self.lbl_stage.setText(f"Stage axes (x/y): {'OK' if (has_x and has_y) else 'MISSING'}")

        # disable zaber capture buttons if unmapped
        self.btn_set_ul_zaber.setEnabled(bool(has_x and has_y))
        self.btn_set_br_zaber.setEnabled(bool(has_x and has_y))

    # ---------------- motion (IN/AWAY) ----------------
    def _require_pipette_clearance(self) -> bool:
        # If p is unmapped, we refuse motion.
        if not self._has_zaber_arm("p"):
            self.status.setText("Status: cannot move plate (pipette axis 'p' unmapped). Set pipette height mapping first.")
            return False

        # best-effort: raise pipette to clearance before moving plate
        phc = self._phc()
        if phc is None:
            self.status.setText("Status: no phc")
            return False

        try:
            # choose a conservative clearance position
            phc.move_pipette(pos="clearance")
            return True
        except Exception as e:
            self.status.setText(f"Status: pipette clearance failed: {e!r}")
            return False

    def away(self):
        if not self._require_pipette_clearance():
            return
        phc = self._phc()
        try:
            phc.dest_home()
            self.status.setText("Status: moved AWAY")
        except Exception as e:
            self.status.setText(f"Status: AWAY failed: {e!r}")

    def into(self):
        if not self._require_pipette_clearance():
            return
        phc = self._phc()
        try:
            phc.move_fluor_img()
            self.status.setText("Status: moved IN")
        except Exception as e:
            self.status.setText(f"Status: IN failed: {e!r}")

    def _load_motion_store(self):
        self.motion_presets = []
        if self.motion_store.exists():
            try:
                self.motion_presets = json.loads(self.motion_store.read_text(encoding="utf-8"))
            except Exception:
                self.motion_presets = []
        self._refresh_motion_list()

    def _save_motion_store(self):
        try:
            self.motion_store.write_text(json.dumps(self.motion_presets, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", repr(e))

    def _refresh_motion_list(self):
        self.motion_list.clear()
        for p in self.motion_presets:
            name = p.get("name", "(unnamed)")
            pos = p.get("position", None)
            pip = p.get("pipette_clearance_mode", None)
            label = f"{name}  |  position={pos}  pipette={pip}"
            self.motion_list.addItem(QListWidgetItem(label))

    def _motion_idx(self) -> Optional[int]:
        items = self.motion_list.selectedIndexes()
        if not items:
            return None
        return int(items[0].row())

    def _motion_new(self):
        name, ok = QInputDialog.getText(self, "New motion preset", "Preset name:")
        if not ok or not name.strip():
            return
        self.motion_presets.append(
            {
                "name": name.strip(),
                "position": "AWAY",
                "pipette_clearance_mode": "clearance",
            }
        )
        self._save_motion_store()
        self._refresh_motion_list()

    def _motion_set_selected(self, pos: str):
        idx = self._motion_idx()
        if idx is None:
            return
        self.motion_presets[idx]["position"] = str(pos)
        # we keep the implied safety requirement explicit
        self.motion_presets[idx]["pipette_clearance_mode"] = self.motion_presets[idx].get("pipette_clearance_mode") or "clearance"
        self._save_motion_store()
        self._refresh_motion_list()
        self.status.setText(f"Status: updated selected motion preset -> {pos}")

    def _motion_apply_selected(self):
        idx = self._motion_idx()
        if idx is None:
            return
        p = self.motion_presets[idx]
        pos = str(p.get("position", "")).upper()
        # (future) allow per-preset clearance mode; for now we use 'clearance'
        if pos == "IN":
            self.into()
        else:
            self.away()

    def _motion_delete_selected(self):
        idx = self._motion_idx()
        if idx is None:
            return
        name = self.motion_presets[idx].get("name", "(unnamed)")
        self.motion_presets.pop(idx)
        self._save_motion_store()
        self._refresh_motion_list()
        self.status.setText(f"Status: deleted {name}")

    # ---------------- grid ----------------
    def _update_well_list(self):
        wells = all_wells(int(self.rows.value()), int(self.cols.value()))
        cur = self.well.currentText()
        self.well.clear()
        self.well.addItems(wells)
        if cur:
            idx = self.well.findText(cur)
            if idx >= 0:
                self.well.setCurrentIndex(idx)

    def _cfg_path(self) -> Optional[Path]:
        phc = self._phc()
        if phc is None:
            return None
        try:
            return Path(phc.pipettor_cfg)
        except Exception:
            return None

    def _read_cfg(self) -> dict:
        p = self._cfg_path()
        if not p or not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_cfg(self, d: dict):
        p = self._cfg_path()
        if not p:
            self.status.setText("Status: pipettor_cfg not available")
            return
        try:
            p.write_text(json.dumps(d, indent=2), encoding="utf-8")
            self.status.setText(f"Status: wrote pipettor_cfg: {p}")
        except Exception as e:
            self.status.setText(f"Status: write cfg failed: {e!r}")

    def _load_grid_from_cfg(self):
        d = self._read_cfg()
        dp = (d or {}).get("dispense_plate", {}) or {}
        tl = dp.get("TL_corner", {}) or {}
        br = dp.get("BR_corner", {}) or {}

        if "x" in tl: self.ul_x.setValue(float(tl["x"]))
        if "y" in tl: self.ul_y.setValue(float(tl["y"]))
        if "x" in br: self.br_x.setValue(float(br["x"]))
        if "y" in br: self.br_y.setValue(float(br["y"]))

        if "rows" in dp:
            try: self.rows.setValue(int(dp["rows"]))
            except Exception: pass
        if "cols" in dp:
            try: self.cols.setValue(int(dp["cols"]))
            except Exception: pass

        self._update_well_list()
        self.status.setText("Status: loaded grid from pipettor_cfg")

    def _save_grid_to_cfg(self):
        d = self._read_cfg()
        if not isinstance(d, dict):
            d = {}
        if "dispense_plate" not in d or not isinstance(d.get("dispense_plate"), dict):
            d["dispense_plate"] = {}

        d["dispense_plate"]["TL_corner"] = {"x": float(self.ul_x.value()), "y": float(self.ul_y.value())}
        d["dispense_plate"]["BR_corner"] = {"x": float(self.br_x.value()), "y": float(self.br_y.value())}
        d["dispense_plate"]["rows"] = int(self.rows.value())
        d["dispense_plate"]["cols"] = int(self.cols.value())

        self._write_cfg(d)

    def _mm_xy(self) -> Optional[tuple[float, float]]:
        phc = self._phc()
        core = getattr(phc, "core", None) if phc is not None else None
        if core is None:
            return None
        try:
            dev = str(core.getXYStageDevice() or "").strip()
        except Exception:
            dev = ""
        if not dev:
            return None
        try:
            x, y = core.getXYPosition(dev)
            return float(x), float(y)
        except Exception:
            return None

    def _zaber_xy(self) -> Optional[tuple[float, float]]:
        phc = self._phc()
        if phc is None:
            return None
        zc = getattr(phc, "zc", None)
        if zc is None:
            return None
        try:
            x = float(zc.get_pos("x"))
            y = float(zc.get_pos("y"))
            return x, y
        except Exception:
            return None

    def _capture_ul(self, source: str):
        xy = self._mm_xy() if source == "mm" else self._zaber_xy()
        if xy is None:
            self.status.setText(f"Status: cannot capture UL (no {source.upper()} XY)")
            return
        x, y = xy
        self.ul_x.setValue(float(x))
        self.ul_y.setValue(float(y))
        self._update_well_list()
        self.status.setText(f"Status: captured UL=({x:.1f},{y:.1f}) via {source.upper()}")

    def _capture_br(self, source: str):
        xy = self._mm_xy() if source == "mm" else self._zaber_xy()
        if xy is None:
            self.status.setText(f"Status: cannot capture BR (no {source.upper()} XY)")
            return
        x, y = xy
        self.br_x.setValue(float(x))
        self.br_y.setValue(float(y))
        self._update_well_list()
        self.status.setText(f"Status: captured BR=({x:.1f},{y:.1f}) via {source.upper()}")

    def _grid_snapshot(self) -> dict:
        return {
            "ul_x": float(self.ul_x.value()),
            "ul_y": float(self.ul_y.value()),
            "br_x": float(self.br_x.value()),
            "br_y": float(self.br_y.value()),
            "rows": int(self.rows.value()),
            "cols": int(self.cols.value()),
        }

    def _load_grid_store(self):
        self.grid_presets = []
        if self.grid_store.exists():
            try:
                self.grid_presets = json.loads(self.grid_store.read_text(encoding="utf-8"))
            except Exception:
                self.grid_presets = []
        self._refresh_grid_list()

    def _save_grid_store(self):
        try:
            self.grid_store.write_text(json.dumps(self.grid_presets, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", repr(e))

    def _refresh_grid_list(self):
        self.grid_list.clear()
        for g in self.grid_presets:
            name = g.get("name", "(unnamed)")
            self.grid_list.addItem(QListWidgetItem(
                f"{name}  |  UL=({g.get('ul_x')},{g.get('ul_y')}) BR=({g.get('br_x')},{g.get('br_y')}) rows={g.get('rows')} cols={g.get('cols')}"
            ))

    def _grid_idx(self) -> Optional[int]:
        items = self.grid_list.selectedIndexes()
        if not items:
            return None
        return int(items[0].row())

    def _grid_new(self):
        name, ok = QInputDialog.getText(self, "New grid preset", "Grid preset name:")
        if not ok or not name.strip():
            return
        self.grid_presets.append({"name": name.strip(), **self._grid_snapshot()})
        self._save_grid_store()
        self._refresh_grid_list()

    def _grid_save_selected(self):
        idx = self._grid_idx()
        if idx is None:
            return
        self.grid_presets[idx].update(self._grid_snapshot())
        self._save_grid_store()
        self._refresh_grid_list()
        self.status.setText(f"Status: saved grid into {self.grid_presets[idx].get('name')}")

    def _grid_apply_selected(self):
        idx = self._grid_idx()
        if idx is None:
            return
        g = self.grid_presets[idx]
        self.ul_x.setValue(float(g.get("ul_x", 0.0)))
        self.ul_y.setValue(float(g.get("ul_y", 0.0)))
        self.br_x.setValue(float(g.get("br_x", 0.0)))
        self.br_y.setValue(float(g.get("br_y", 0.0)))
        self.rows.setValue(int(g.get("rows", 1)))
        self.cols.setValue(int(g.get("cols", 1)))
        self._update_well_list()
        self.status.setText(f"Status: loaded grid {g.get('name')}")

    def _grid_delete_selected(self):
        idx = self._grid_idx()
        if idx is None:
            return
        name = self.grid_presets[idx].get("name", "(unnamed)")
        self.grid_presets.pop(idx)
        self._save_grid_store()
        self._refresh_grid_list()
        self.status.setText(f"Status: deleted {name}")
