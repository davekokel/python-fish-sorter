import json
from pathlib import Path
from typing import Optional

from qtpy.QtWidgets import QGridLayout, QLabel, QPushButton, QWidget


class WorkflowPanel(QWidget):
    def __init__(self, picking, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.picking = picking
        self._create_gui()
        self.refresh()

    def _create_gui(self):
        layout = QGridLayout(self)

        layout.addWidget(QLabel("Workflow"), 0, 0, 1, 3)

        self.lbl_next = QLabel("Next: —")
        layout.addWidget(self.lbl_next, 1, 0, 1, 2)

        self.btn_refresh = QPushButton("Update checklist")
        self.btn_refresh.clicked.connect(self.refresh)
        layout.addWidget(self.btn_refresh, 1, 2, 1, 1)

        self.btn_go = QPushButton("Go to next step")
        self.btn_go.clicked.connect(self.go_to_next_step)
        layout.addWidget(self.btn_go, 2, 2, 1, 1)

        self.rows = []
        items = [
            ("Zabers connected", "zabers"),
            ("Dispense plate TL/BR set", "plate"),
            ("Pick position set", "pick"),
            ("Dispense position set", "disp"),
        ]

        r0 = 2
        for i, (label, key) in enumerate(items):
            lbl = QLabel(label)
            st = QLabel("—")
            layout.addWidget(lbl, r0 + i, 0, 1, 2)
            layout.addWidget(st, r0 + i, 2, 1, 1)
            self.rows.append((key, st))

        self.lbl_hint = QLabel("Tip: use the Picking buttons + Dispense Plate tab, then Update checklist.")
        layout.addWidget(self.lbl_hint, r0 + len(items) + 1, 0, 1, 3)

    def _cfg_path(self) -> Optional[Path]:
        try:
            return Path(self.picking.pick.phc.pipettor_cfg)
        except Exception:
            return None

    def _read_picker_cfg(self) -> Optional[dict]:
        p = self._cfg_path()
        if not p or not p.exists():
            return None
        try:
            with open(p, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _status_map(self) -> dict:
        st = {"zabers": False, "plate": False, "pick": False, "disp": False}

        try:
            zc = self.picking.pick.phc.zc
            _ = zc.get_pos("x")
            _ = zc.get_pos("y")
            _ = zc.get_pos("p")
            st["zabers"] = True
        except Exception:
            st["zabers"] = False

        d = self._read_picker_cfg()
        if d:
            dp = d.get("dispense_plate", {})
            tl = dp.get("TL_corner", {})
            br = dp.get("BR_corner", {})
            try:
                tl_ok = ("x" in tl) and ("y" in tl)
                br_ok = ("x" in br) and ("y" in br)
                st["plate"] = bool(tl_ok and br_ok)
            except Exception:
                st["plate"] = False

        st["pick"] = bool(getattr(self.picking, "pick_calib", False))
        st["disp"] = bool(getattr(self.picking, "disp_calib", False))

        return st

    def refresh(self):
        st = self._status_map()

        for key, lbl in self.rows:
            lbl.setText("OK" if st.get(key) else "MISSING")

        if not st["zabers"]:
            nxt = "Connect Zabers"
            go = "Go to Picking tab"
        elif not st["plate"]:
            nxt = "Set dispense plate TL/BR (Dispense Plate tab)"
            go = "Go to Dispense Plate tab"
        elif not st["pick"]:
            nxt = "Set pick position"
            go = "Go to Picking tab"
        elif not st["disp"]:
            nxt = "Set dispense position"
            go = "Go to Picking tab"
        else:
            nxt = "Ready (define grid/channels in MDA, then Run)"
            go = "Go to MDA tab"

        self.lbl_next.setText(f"Next: {nxt}")
        try:
            self.btn_go.setText(go)
        except Exception:
            pass

    def go_to_next_step(self):
        st = self._status_map()
        fp = getattr(self.picking, "fishpicker", None)
        if fp is None:
            return

        if not st.get("zabers", False):
            fp.show_right_panel("Picking")
            return

        if not st.get("plate", False):
            fp.show_right_panel("Picking")
            try:
                tabs = getattr(self.picking, "stage_tabs", None)
                if tabs is not None:
                    for i in range(tabs.count()):
                        if tabs.tabText(i) == "Dispense Plate":
                            tabs.setCurrentIndex(i)
                            break
            except Exception:
                pass
            return

        if (not st.get("pick", False)) or (not st.get("disp", False)):
            fp.show_right_panel("Picking")
            return

        fp.show_right_panel("MDA")
