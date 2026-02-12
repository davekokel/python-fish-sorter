import json
from pathlib import Path
from typing import Optional

from qtpy.QtWidgets import QGridLayout, QLabel, QPushButton, QWidget


class WorkflowPanel(QWidget):
    """Operator checklist + next-step guidance.

    This is intentionally simple: it reflects state we can *actually* read
    from the running app + config files.
    """

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

        # Checklist rows
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

        # Small hint footer
        self.lbl_hint = QLabel("Tip: use the Picking buttons + Dispense Plate tab, then Refresh.")
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
        st = {
            "zabers": False,
            "plate": False,
            "pick": False,
            "disp": False,
        }

        # Zabers connected
        try:
            zc = self.picking.pick.phc.zc
            _ = zc.get_pos("x")
            _ = zc.get_pos("y")
            _ = zc.get_pos("p")
            st["zabers"] = True
        except Exception:
            st["zabers"] = False

        # Plate TL/BR set (from picker_config.json)
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

        # Pick/disp positions: rely on GUI flags (set by Set Pick/Dispense buttons)
        st["pick"] = bool(getattr(self.picking, "pick_calib", False))
        st["disp"] = bool(getattr(self.picking, "disp_calib", False))

        return st

    def refresh(self):
        st = self._status_map()

        # render statuses
        for key, lbl in self.rows:
            lbl.setText("OK" if st.get(key) else "MISSING")

        # compute next step
        if not st["zabers"]:
            nxt = "Connect Zabers"
        elif not st["plate"]:
            nxt = "Set dispense plate TL/BR (Dispense Plate tab)"
        elif not st["pick"]:
            nxt = "Set pick position"
        elif not st["disp"]:
            nxt = "Set dispense position"
        else:
            nxt = "Ready (define grid/channels in MDA, then Run)"

        self.lbl_next.setText(f"Next: {nxt}")
    def go_to_next_step(self):
        """Navigate operator to the UI area needed for the current Next step."""
        st = self._status_map()

        # If we can't even read Zabers, go to Picking (operator will see connection errors)
        if not st.get("zabers", False):
            try:
                fp = getattr(self.picking, "fishpicker", None)
                if fp is not None:
                    dw = fp.v.window._dock_widgets.get("Picking")
                if dw is not None:
                    dw.show()
            except Exception:
                pass
            return

        # Need TL/BR -> go to Picking -> Dispense Plate tab
        if not st.get("plate", False):
            try:
                fp = getattr(self.picking, "fishpicker", None)
                if fp is not None:
                    dw = fp.v.window._dock_widgets.get("Picking")
                if dw is not None:
                    dw.show()
                # PickGUI keeps stage_tabs; if present switch to Dispense Plate
                tabs = getattr(self.picking, "stage_tabs", None)
                if tabs is not None:
                    for i in range(tabs.count()):
                        if tabs.tabText(i) == "Dispense Plate":
                            tabs.setCurrentIndex(i)
                            break
            except Exception:
                pass
            return

        # Need pick/disp positions -> go to Picking tab
        if (not st.get("pick", False)) or (not st.get("disp", False)):
            try:
                fp = getattr(self.picking, "fishpicker", None)
                if fp is not None:
                    dw = fp.v.window._dock_widgets.get("Picking")
                if dw is not None:
                    dw.show()
            except Exception:
                pass
            return

        # Otherwise: go to MDA
        try:
            fp = getattr(self.picking, "fishpicker", None)
            if fp is not None and hasattr(fp, "main_window"):
                fp.main_window._show_dock_widget("MDA")
        except Exception:
            pass

