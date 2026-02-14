from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)


SCENE_COMPONENTS = [
    "magnification",
    "imaging_plate_position",
    "collection_plate_position",
    "pipette_position",
    "transmitted_light_preset",
    "fluorescence_preset",
    "camera_preset",
]


class ScenesPanel(QWidget):
    """
    Scenes = coordinated macros that reference component presets.

    Storage: qt_presets/scenes.json
    Default behavior: dry-run log (no motion) unless 'Enable execution' is checked.

    Execution (initial):
      - magnification: best-effort via MM config group 'objectives' or 'Objective'
      - transmitted_light_preset: delegates to TL panel if it exposes apply-by-name
      - camera_preset: delegates to Camera panel if it exposes apply-by-name
      - everything else: logged as TODO (wiring pending)
    """

    def __init__(self, repo_root: Path, core=None, tl_panel=None, camera_panel=None, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.repo_root = repo_root
        self.core = core
        self.tl_panel = tl_panel
        self.camera_panel = camera_panel

        self.store_path = (repo_root / "qt_presets" / "scenes.json")
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        self.scenes = []
        self._build_ui()
        self._load_store()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(QLabel("Scenes"))

        # Components schema
        comp_box = QGroupBox("Components controlled by a Scene")
        cv = QVBoxLayout(comp_box)
        cv.setContentsMargins(8, 8, 8, 8)
        cv.addWidget(QLabel("1) magnification"))
        cv.addWidget(QLabel("2) imaging plate position"))
        cv.addWidget(QLabel("3) collection plate position"))
        cv.addWidget(QLabel("4) pipette position"))
        cv.addWidget(QLabel("5) transmitted light preset nickname"))
        cv.addWidget(QLabel("6) fluorescence preset nickname"))
        cv.addWidget(QLabel("7) camera preset nickname"))
        root.addWidget(comp_box)

        # CRUD + apply
        box = QGroupBox("Scenes")
        bl = QHBoxLayout(box)
        bl.setContentsMargins(8, 8, 8, 8)

        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._scene_selected)
        bl.addWidget(self.list, stretch=1)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        self.exec_enable = QCheckBox("Enable execution (dangerous)")
        self.exec_enable.setChecked(False)
        rv.addWidget(self.exec_enable)

        self.btn_new = QPushButton("New")
        self.btn_new.clicked.connect(self._new)
        rv.addWidget(self.btn_new)

        self.btn_edit = QPushButton("Edit selected")
        self.btn_edit.clicked.connect(self._edit_selected)
        rv.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("Delete selected")
        self.btn_delete.clicked.connect(self._delete_selected)
        rv.addWidget(self.btn_delete)

        self.btn_apply = QPushButton("Apply selected")
        self.btn_apply.clicked.connect(self._apply_selected)
        rv.addWidget(self.btn_apply)

        rv.addStretch(1)
        bl.addWidget(right)

        root.addWidget(box, stretch=1)

        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log, stretch=1)

    def _load_store(self):
        self.scenes = []
        if self.store_path.exists():
            try:
                self.scenes = json.loads(self.store_path.read_text(encoding="utf-8"))
            except Exception:
                self.scenes = []
        self._refresh_list()

    def _save_store(self):
        try:
            self.store_path.write_text(json.dumps(self.scenes, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", repr(e))

    def _refresh_list(self):
        self.list.clear()
        for i, s in enumerate(self.scenes):
            name = s.get("name", f"(scene {i})")
            summary = self._scene_summary(s)
            item = QListWidgetItem(f"{name}  |  {summary}")
            item.setData(Qt.UserRole, i)
            self.list.addItem(item)

    def _selected_index(self) -> Optional[int]:
        items = self.list.selectedItems()
        if not items:
            return None
        idx = items[0].data(Qt.UserRole)
        return int(idx) if idx is not None else None

    def _scene_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        s = self.scenes[idx]
        self._log(f"Selected scene: {s.get('name')}\n{json.dumps(s, indent=2)}")

    def _scene_summary(self, s: dict) -> str:
        c = s.get("components", {})
        parts = []
        for k in SCENE_COMPONENTS:
            v = c.get(k, None)
            if v:
                parts.append(f"{k}={v}")
        return ", ".join(parts) if parts else "(empty)"

    def _new(self):
        name, ok = QInputDialog.getText(self, "New scene", "Scene name:")
        if not ok or not name.strip():
            return
        scene = {
            "name": name.strip(),
            "components": {k: None for k in SCENE_COMPONENTS},
        }
        self.scenes.append(scene)
        self._save_store()
        self._refresh_list()

    def _edit_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        s = self.scenes[idx]
        comps = s.get("components", {})

        # crude but effective: edit as JSON text
        txt = json.dumps(s, indent=2)
        new_txt, ok = QInputDialog.getMultiLineText(self, "Edit scene JSON", "Edit:", txt)
        if not ok:
            return
        try:
            new_obj = json.loads(new_txt)
        except Exception as e:
            QMessageBox.warning(self, "Invalid JSON", repr(e))
            return

        # minimal validation
        if "name" not in new_obj or "components" not in new_obj:
            QMessageBox.warning(self, "Invalid scene", "Scene must have keys: name, components")
            return

        self.scenes[idx] = new_obj
        self._save_store()
        self._refresh_list()

    def _delete_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        name = self.scenes[idx].get("name", "(unnamed)")
        self.scenes.pop(idx)
        self._save_store()
        self._refresh_list()
        self._log(f"Deleted scene: {name}")

    def _apply_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        s = self.scenes[idx]
        dry = not bool(self.exec_enable.isChecked())
        self.apply_scene(s, dry_run=dry)

    def apply_scene(self, s: dict, dry_run: bool = True):
        c = (s or {}).get("components", {}) or {}
        name = s.get("name", "(unnamed)")

        lines = []
        lines.append(f"APPLY SCENE: {name}")
        lines.append(f"MODE: {'DRY-RUN' if dry_run else 'EXECUTE'}")

        # 1) magnification
        mag = c.get("magnification")
        if mag:
            lines.append(f"- magnification -> {mag}")
            if (not dry_run) and self.core is not None:
                self._apply_magnification(mag, lines)
        else:
            lines.append("- magnification -> (none)")

        # 2) imaging plate position
        ipos = c.get("imaging_plate_position")
        lines.append(f"- imaging_plate_position -> {ipos or '(none)'} (TODO: wire to XYStage presets/coords)")

        # 3) collection plate position
        cpos = c.get("collection_plate_position")
        lines.append(f"- collection_plate_position -> {cpos or '(none)'} (TODO: wire to collection plate actuator)")

        # 4) pipette position
        ppos = c.get("pipette_position")
        lines.append(f"- pipette_position -> {ppos or '(none)'} (TODO: wire to pipette controller)")

        # 5) transmitted light preset nickname
        tl = c.get("transmitted_light_preset")
        if tl:
            lines.append(f"- transmitted_light_preset -> {tl}")
            if (not dry_run) and self.tl_panel is not None and hasattr(self.tl_panel, "apply_named_preset"):
                try:
                    self.tl_panel.apply_named_preset(tl)
                except Exception as e:
                    lines.append(f"  ERROR applying TL preset: {e!r}")
        else:
            lines.append("- transmitted_light_preset -> (none)")

        # 6) fluorescence preset nickname
        fl = c.get("fluorescence_preset")
        lines.append(f"- fluorescence_preset -> {fl or '(none)'} (TODO: implement fluorescence Qt presets)")

        # 7) camera preset nickname
        cam = c.get("camera_preset")
        if cam:
            lines.append(f"- camera_preset -> {cam}")
            if (not dry_run) and self.camera_panel is not None and hasattr(self.camera_panel, "apply_named_preset"):
                try:
                    self.camera_panel.apply_named_preset(cam)
                except Exception as e:
                    lines.append(f"  ERROR applying camera preset: {e!r}")
        else:
            lines.append("- camera_preset -> (none)")

        self._log("\n".join(lines))

    def _apply_magnification(self, mag: str, lines: list[str]):
        # Best-effort: try common group names
        group_candidates = ["objectives", "Objective", "Objectives"]
        for g in group_candidates:
            try:
                self.core.setConfig(g, str(mag))
                lines.append(f"  OK setConfig({g},{mag})")
                return
            except Exception:
                pass
        lines.append("  ERROR: could not apply magnification via setConfig (no matching group/preset)")

    def _log(self, msg: str):
        self.log.setPlainText(msg)
