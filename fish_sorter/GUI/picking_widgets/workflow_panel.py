import json
from pathlib import Path
from typing import Optional

from qtpy.QtWidgets import QGridLayout, QLabel, QPushButton, QWidget


class WorkflowPanel(QWidget):
    """
    Wizard Mode checklist with Go-to buttons.

    Key design:
    - This panel must NOT assume napari docks.
    - Navigation is via an injected router (Qt shell), with a backwards-compatible fallback
      to the legacy napari-as-shell fishpicker object if present.
    """

    def __init__(self, picking, router=None, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.picking = picking
        self.router = router
        self._create_gui()
        self.refresh()

    def _cfg_path(self) -> Optional[Path]:
        try:
            return Path(self.picking.pick.phc.pipettor_cfg)
        except Exception:
            return None

    def _read_cfg(self) -> Optional[dict]:
        p = self._cfg_path()
        if not p or not p.exists():
            return None
        try:
            with open(p, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _dp_corners_ok(self, d: dict) -> bool:
        try:
            dp = (d or {}).get("dispense_plate", {})
            tl = dp.get("TL_corner", {})
            br = dp.get("BR_corner", {})
            return ("x" in tl and "y" in tl and "x" in br and "y" in br)
        except Exception:
            return False

    def _zabers_ok(self) -> bool:
        try:
            zc = self.picking.pick.phc.zc
            _ = zc.get_pos("x")
            _ = zc.get_pos("y")
            _ = zc.get_pos("p")
            return True
        except Exception:
            return False

    def _pick_ok(self) -> bool:
        return bool(getattr(self.picking, "pick_calib", False))

    def _disp_ok(self) -> bool:
        return bool(getattr(self.picking, "disp_calib", False))

    def _panel_exists(self, name: str) -> bool:
        # Preferred: Qt shell router
        if self.router is not None and hasattr(self.router, "has_panel"):
            try:
                return bool(self.router.has_panel(name))
            except Exception:
                pass

        # Legacy fallback: napari docks
        fp = getattr(self.picking, "fishpicker", None)
        if fp is None:
            return False
        try:
            return fp.v.window._dock_widgets.get(name) is not None
        except Exception:
            return False

    def _create_gui(self):
        layout = QGridLayout(self)

        layout.addWidget(QLabel("Workflow (Wizard Mode)"), 0, 0, 1, 2)

        self.btn_refresh = QPushButton("Update checklist")
        self.btn_refresh.clicked.connect(self.refresh)
        layout.addWidget(self.btn_refresh, 1, 1, 1, 1)

        layout.addWidget(QLabel("Step / Tool"), 2, 0, 1, 1)
        layout.addWidget(QLabel("Status"), 2, 1, 1, 1)

        self.btn_step1 = QPushButton("Step 1 - Dispense plate corners (TL/BR)")
        self.lbl_step1 = QLabel("-")
        self.btn_step1.clicked.connect(lambda: self.go_to_step(1))
        layout.addWidget(self.btn_step1, 3, 0, 1, 1)
        layout.addWidget(self.lbl_step1, 3, 1, 1, 1)

        self.btn_step2 = QPushButton("Step 2 - Pipette pick height")
        self.lbl_step2 = QLabel("-")
        self.btn_step2.clicked.connect(lambda: self.go_to_step(2))
        layout.addWidget(self.btn_step2, 4, 0, 1, 1)
        layout.addWidget(self.lbl_step2, 4, 1, 1, 1)

        self.btn_step3 = QPushButton("Step 3 - Pipette dispense height")
        self.lbl_step3 = QLabel("-")
        self.btn_step3.clicked.connect(lambda: self.go_to_step(3))
        layout.addWidget(self.btn_step3, 5, 0, 1, 1)
        layout.addWidget(self.lbl_step3, 5, 1, 1, 1)

        self.btn_step4 = QPushButton("Step 4 - Define grid/channels in MDA")
        self.lbl_step4 = QLabel("-")
        self.btn_step4.clicked.connect(lambda: self.go_to_step(4))
        layout.addWidget(self.btn_step4, 6, 0, 1, 1)
        layout.addWidget(self.lbl_step4, 6, 1, 1, 1)

        # Micro-Manager panel (Qt shell)
        self.btn_mm = QPushButton("Micro-Manager")
        self.lbl_mm = QLabel("-")
        self.btn_mm.clicked.connect(lambda: self.go_to_panel("Micro-Manager"))
        layout.addWidget(self.btn_mm, 7, 0, 1, 1)
        layout.addWidget(self.lbl_mm, 7, 1, 1, 1)

        self.lbl_hint = QLabel("Tip: Use Go-to buttons, do the step, then click Update checklist.")
        layout.addWidget(self.lbl_hint, 8, 0, 1, 2)

    def refresh(self):
        d = self._read_cfg() or {}

        zab_ok = self._zabers_ok()
        plate_ok = self._dp_corners_ok(d)
        pick_ok = self._pick_ok()
        disp_ok = self._disp_ok()

        step1_ok = bool(zab_ok and plate_ok)
        step2_ok = bool(pick_ok)
        step3_ok = bool(disp_ok)
        step4_ok = bool(step1_ok and step2_ok and step3_ok)

        self.lbl_step1.setText("OK" if step1_ok else "MISSING")
        self.lbl_step2.setText("OK" if step2_ok else "MISSING")
        self.lbl_step3.setText("OK" if step3_ok else "MISSING")
        self.lbl_step4.setText("OK" if step4_ok else "MISSING")

        self.lbl_mm.setText("OK" if self._panel_exists("Micro-Manager") else "MISSING")

    def go_to_panel(self, name: str):
        # Preferred: Qt shell router
        if self.router is not None and hasattr(self.router, "go_to_panel"):
            try:
                self.router.go_to_panel(name)
                return
            except Exception:
                pass

        # Legacy fallback
        fp = getattr(self.picking, "fishpicker", None)
        if fp is None:
            return
        fp.show_right_panel(name)

    def go_to_step(self, step: int):
        # Preferred: Qt shell router
        if self.router is not None and hasattr(self.router, "go_to_step"):
            try:
                self.router.go_to_step(step)
                return
            except Exception:
                pass

        # Legacy fallback (napari-as-shell)
        fp = getattr(self.picking, "fishpicker", None)
        if fp is None:
            return

        if step in (1, 2, 3):
            fp.show_right_panel("Picking")

            pg = getattr(fp, "pick_gui", None)
            if pg is None:
                return

            if step == 1:
                try:
                    pg.focus_tab(getattr(pg, "TAB_PLATE", 0))
                    pg.focus_stage_subtab("Dispense Plate")
                except Exception:
                    pass
                return

            if step in (2, 3):
                try:
                    pg.focus_tab(getattr(pg, "TAB_PIPETTE", 1))
                except Exception:
                    pass
                return

        if step == 4:
            fp.show_right_panel("MDA")
            return

