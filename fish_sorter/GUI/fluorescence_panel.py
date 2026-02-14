from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QMessageBox,
    QGridLayout,
)

from fish_sorter.GUI.widgets.camera_controls import CameraControlsWidget


class _TilePresets(QWidget):
    def __init__(self, title: str, presets: list[str], on_apply, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.title = title
        self.presets = [str(p) for p in (presets or [])]
        self.on_apply = on_apply
        self._last_cols = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.lbl = QLabel("")
        root.addWidget(self.lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll, stretch=1)

        self.host = QWidget()
        self.grid = QGridLayout(self.host)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)
        self.grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.scroll.setWidget(self.host)

        self._render(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render(force=False)

    def _cols_for_width(self) -> int:
        tile_w = 180
        w = max(1, self.scroll.viewport().width())
        cols = max(1, int(w // tile_w))
        return min(cols, 6)

    def _render(self, force: bool):
        cols = self._cols_for_width()
        if (not force) and (self._last_cols == cols):
            return
        self._last_cols = cols

        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        self.lbl.setText(f"{self.title}: {len(self.presets)} presets" if self.presets else f"{self.title}: (none)")

        for i, p in enumerate(self.presets):
            r = i // cols
            c = i % cols
            b = QToolButton()
            b.setText(p)
            b.setCheckable(False)
            b.setMinimumHeight(44)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setStyleSheet("QToolButton{padding:10px;border:1px solid #aaa;border-radius:8px;}")
            b.clicked.connect(lambda _=False, x=p: self.on_apply(x))
            self.grid.addWidget(b, r, c)

        self.grid.setRowStretch(r + 1, 1)
        self.grid.setColumnStretch(cols, 1)


class FluorescencePanel(QWidget):
    FILTER_GROUP_CANDIDATES = ["Filter cubes", "FilterCube", "Filter Cubes", "filter cubes", "Filter cube"]

    def __init__(self, core, viewer_model, repo_root: Path, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.core = core
        self.viewer_model = viewer_model
        self.repo_root = repo_root

        self.store_path = (repo_root / "qt_presets" / "fluorescence.json")
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        self.filter_group: Optional[str] = None
        self._current_filter: Optional[str] = None
        self.presets: list[dict] = []

        self._build_ui()
        self._load_store()
        self._discover_filter_group()
        self._populate_filter_tiles()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(QLabel("Fluorescence"))

        self.camera = CameraControlsWidget(self.core, self.viewer_model, title="Camera")
        root.addWidget(self.camera)

        filt_box = QGroupBox("Filter cube")
        fv = QVBoxLayout(filt_box)
        self.lbl_group = QLabel("Filter group: (detecting)")
        fv.addWidget(self.lbl_group)

        self.tiles_host = QWidget()
        self.tiles_layout = QVBoxLayout(self.tiles_host)
        self.tiles_layout.setContentsMargins(0, 0, 0, 0)
        fv.addWidget(self.tiles_host, stretch=1)

        root.addWidget(filt_box, stretch=1)

        presets_box = QGroupBox("Qt Presets")
        pb = QHBoxLayout(presets_box)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemSelectionChanged.connect(self._preset_selected)
        pb.addWidget(self.list, stretch=1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        self.btn_new = QPushButton("New")
        self.btn_new.clicked.connect(self._preset_new)
        rv.addWidget(self.btn_new)

        self.btn_save = QPushButton("Save current → selected")
        self.btn_save.clicked.connect(self._preset_save_current_into_selected)
        rv.addWidget(self.btn_save)

        self.btn_apply_preset = QPushButton("Apply selected")
        self.btn_apply_preset.clicked.connect(self._preset_apply_selected)
        rv.addWidget(self.btn_apply_preset)

        self.btn_delete = QPushButton("Delete selected")
        self.btn_delete.clicked.connect(self._preset_delete_selected)
        rv.addWidget(self.btn_delete)

        rv.addStretch(1)
        pb.addWidget(right)

        root.addWidget(presets_box, stretch=1)

        self.status = QLabel("Status: -")
        root.addWidget(self.status)

    def _discover_filter_group(self):
        try:
            groups = [str(g) for g in list(self.core.getAvailableConfigGroups())]
        except Exception:
            groups = []

        gl = {g.lower(): g for g in groups}
        for cand in self.FILTER_GROUP_CANDIDATES:
            if cand.lower() in gl:
                self.filter_group = gl[cand.lower()]
                break

        if self.filter_group is None and groups:
            for g in groups:
                if "filter" in g.lower():
                    self.filter_group = g
                    break

        self.lbl_group.setText(f"Filter group: {self.filter_group or '(none found)'}")

    def _populate_filter_tiles(self):
        while self.tiles_layout.count():
            item = self.tiles_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        if not self.filter_group:
            self.tiles_layout.addWidget(QLabel("No filter cube config group found. Use Micro-Manager (posterity)."))
            return

        try:
            presets = [str(p) for p in list(self.core.getAvailableConfigs(self.filter_group))]
        except Exception:
            presets = []

        def _apply(preset: str):
            try:
                self.core.setConfig(self.filter_group, preset)
                self._current_filter = preset
                self.status.setText(f"Status: filter={preset}")
            except Exception as e:
                self.status.setText(f"Status: setConfig failed: {e!r}")

        self.tiles_layout.addWidget(_TilePresets(title=self.filter_group, presets=presets, on_apply=_apply))

    # Presets CRUD + Scenes hook
    def _load_store(self):
        self.presets = []
        if self.store_path.exists():
            try:
                self.presets = json.loads(self.store_path.read_text(encoding="utf-8"))
            except Exception:
                self.presets = []
        self._refresh_list()

    def _save_store(self):
        try:
            self.store_path.write_text(json.dumps(self.presets, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", repr(e))

    def _refresh_list(self):
        self.list.clear()
        for p in self.presets:
            name = p.get("name", "(unnamed)")
            parts = []
            if "filter" in p and p.get("filter") is not None:
                parts.append(f"filter={p.get('filter')}")
            cam = p.get("camera", {})
            if isinstance(cam, dict):
                if "exposure_value" in cam and "exposure_unit" in cam:
                    parts.append(f"exp={cam.get('exposure_value')} {cam.get('exposure_unit')}")
                if "gain" in cam:
                    parts.append(f"gain={cam.get('gain')}")
                if "gamma" in cam:
                    parts.append(f"gamma={cam.get('gamma')}")
                if "binning" in cam:
                    parts.append(f"bin={cam.get('binning')}")
            label = name if not parts else (name + "  |  " + "  ".join(parts))
            self.list.addItem(QListWidgetItem(label))

    def _selected_index(self) -> Optional[int]:
        items = self.list.selectedIndexes()
        if not items:
            return None
        return int(items[0].row())

    def _preset_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        self.status.setText(f"Status: selected preset {self.presets[idx].get('name')}")

    def _preset_new(self):
        name, ok = QInputDialog.getText(self, "New preset", "Preset name:")
        if not ok or not name.strip():
            return
        self.presets.append(
            {
                "name": name.strip(),
                "filter": self._current_filter,
                "camera": self.camera.preset_payload(),
                "exposure_ms": self.camera.current_exposure_ms(),
            }
        )
        self._save_store()
        self._refresh_list()

    def _preset_save_current_into_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        p = self.presets[idx]
        p["filter"] = self._current_filter
        p["camera"] = self.camera.preset_payload()
        p["exposure_ms"] = self.camera.current_exposure_ms()
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: saved current into {p.get('name')}")

    def _preset_apply_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        self._apply_preset_obj(self.presets[idx])

    def _preset_delete_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        name = self.presets[idx].get("name", "(unnamed)")
        self.presets.pop(idx)
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: deleted {name}")

    def apply_named_preset(self, name: str):
        for p in self.presets:
            if str(p.get("name", "")).strip() == str(name).strip():
                self._apply_preset_obj(p)
                return
        self.status.setText(f"Status: preset not found: {name!r}")

    def _apply_preset_obj(self, p: dict):
        filt = p.get("filter", None)
        if self.filter_group and filt:
            try:
                self.core.setConfig(self.filter_group, str(filt))
                self._current_filter = str(filt)
            except Exception:
                pass

        cam = p.get("camera", None)
        if isinstance(cam, dict):
            try:
                self.camera.apply_payload(cam)
            except Exception:
                pass

        self.status.setText(f"Status: applied {p.get('name')} | filter={self._current_filter}")

