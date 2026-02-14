from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from qtpy.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QMessageBox,
)

from fish_sorter.GUI.widgets.focus_controls import FocusControlsWidget


class FocusPanel(QWidget):
    """
    Focus component + Qt presets.

    Presets stored in: qt_presets/focus.json
      - name
      - z_um
    """

    def __init__(self, core, repo_root: Path | None = None, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.core = core

        if repo_root is None:
            repo_root = Path(__file__).resolve().parents[2]
        self.repo_root = repo_root
        self.store_path = repo_root / "qt_presets" / "focus.json"
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        self.presets: list[dict] = []

        self._build_ui()
        self._load_store()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(QLabel("Focus"))

        self.controls = FocusControlsWidget(self.core, title="Focus")
        root.addWidget(self.controls)

        presets_box = QGroupBox("Qt Presets")
        pb = QHBoxLayout(presets_box)
        pb.setContentsMargins(8, 8, 8, 8)
        pb.setSpacing(10)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
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

        self.btn_apply = QPushButton("Apply selected")
        self.btn_apply.clicked.connect(self._preset_apply_selected)
        rv.addWidget(self.btn_apply)

        self.btn_delete = QPushButton("Delete selected")
        self.btn_delete.clicked.connect(self._preset_delete_selected)
        rv.addWidget(self.btn_delete)

        rv.addStretch(1)
        pb.addWidget(right)

        root.addWidget(presets_box, stretch=1)

        self.status = QLabel("Status: -")
        root.addWidget(self.status)

    # ---- focus helpers
    def _current_z(self) -> Optional[float]:
        try:
            return float(self.controls._get_z())
        except Exception:
            return None

    def _set_z(self, z: float) -> bool:
        try:
            return bool(self.controls._set_z(float(z)))
        except Exception:
            return False

    # ---- presets
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
            z = p.get("z_um", None)
            label = f"{name}  |  z_um={z}"
            self.list.addItem(QListWidgetItem(label))

    def _selected_index(self) -> Optional[int]:
        items = self.list.selectedIndexes()
        if not items:
            return None
        return int(items[0].row())

    def _preset_new(self):
        z = self._current_z()
        if z is None:
            self.status.setText("Status: cannot read focus")
            return
        name, ok = QInputDialog.getText(self, "New focus preset", "Preset name:")
        if not ok or not name.strip():
            return
        self.presets.append({"name": name.strip(), "z_um": float(z)})
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: created preset {name.strip()} (z={z:.2f})")

    def _preset_save_current_into_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        z = self._current_z()
        if z is None:
            self.status.setText("Status: cannot read focus")
            return
        self.presets[idx]["z_um"] = float(z)
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: saved current into {self.presets[idx].get('name')} (z={z:.2f})")

    def _preset_apply_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        p = self.presets[idx]
        z = p.get("z_um", None)
        if z is None:
            return
        ok = self._set_z(float(z))
        self.controls.refresh()
        self.status.setText(f"Status: apply -> {'OK' if ok else 'FAIL'} (z={float(z):.2f})")

    def _preset_delete_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        name = self.presets[idx].get("name", "(unnamed)")
        self.presets.pop(idx)
        self._save_store()
        self._refresh_list()
        self.status.setText(f"Status: deleted {name}")

    # scenes hook
    def apply_named_preset(self, name: str):
        for p in self.presets:
            if str(p.get("name", "")).strip() == str(name).strip():
                z = p.get("z_um", None)
                if z is None:
                    return
                ok = self._set_z(float(z))
                self.controls.refresh()
                self.status.setText(f"Status: apply_named_preset -> {'OK' if ok else 'FAIL'} ({name})")
                return
        self.status.setText(f"Status: preset not found: {name!r}")
