import json
import logging
from pathlib import Path
from typing import Optional

from qtpy.QtWidgets import QGridLayout, QLabel, QPushButton, QWidget

class DispensePlateCalibWidget(QWidget):
    """UI calibration for dispense plate corners stored in picker_config.json.

    Writes:
      dispense_plate.TL_corner.x/y
      dispense_plate.BR_corner.x/y

    NOTE: config stores um; Zaber reports mm. We write (mm * 1000).
    """

    def __init__(self, picking, parent: QWidget | None=None):
        super().__init__(parent=parent)
        self.picking = picking
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
        except Exception as e:
            logging.warning(f"DispensePlateCalibWidget: failed to read cfg: {e!r}")
            return None

    def _write_cfg(self, d: dict) -> bool:
        p = self._cfg_path()
        if not p:
            return False
        try:
            with open(p, "w") as f:
                json.dump(d, f, indent=4, separators=(",", ": "))
            return True
        except Exception as e:
            logging.warning(f"DispensePlateCalibWidget: failed to write cfg: {e!r}")
            return False

    def _fmt_corner_mm(self, c: dict) -> str:
        try:
            x_mm = float(c.get("x", 0.0)) / 1000.0
            y_mm = float(c.get("y", 0.0)) / 1000.0
            return f"x={x_mm:.3f} mm, y={y_mm:.3f} mm"
        except Exception:
            return "x=?, y=?"

    def _create_gui(self):
        layout = QGridLayout(self)
        layout.addWidget(QLabel("Dispense Plate Corners"), 0, 0, 1, 4)

        self.tl_label = QLabel("TL: —")
        self.br_label = QLabel("BR: —")
        layout.addWidget(self.tl_label, 1, 0, 1, 4)
        layout.addWidget(self.br_label, 2, 0, 1, 4)

        self.btn_set_tl = QPushButton("Set TL (A01) from current XY")
        self.btn_set_br = QPushButton("Set BR (B03) from current XY")
        self.btn_move_tl = QPushButton("Move to TL (A01)")
        self.btn_move_br = QPushButton("Move to BR (B03)")
        self.btn_refresh = QPushButton("Refresh corners")

        self.btn_set_tl.clicked.connect(lambda: self._set_corner("TL_corner"))
        self.btn_set_br.clicked.connect(lambda: self._set_corner("BR_corner"))
        self.btn_move_tl.clicked.connect(lambda: self._move_to_well("A01"))
        self.btn_move_br.clicked.connect(lambda: self._move_to_well("B03"))
        self.btn_refresh.clicked.connect(self.refresh)

        layout.addWidget(self.btn_set_tl, 3, 0, 1, 2)
        layout.addWidget(self.btn_set_br, 3, 2, 1, 2)
        layout.addWidget(self.btn_move_tl, 4, 0, 1, 2)
        layout.addWidget(self.btn_move_br, 4, 2, 1, 2)
        layout.addWidget(self.btn_refresh, 5, 0, 1, 4)

    def refresh(self):
        d = self._read_cfg()
        if not d:
            self.tl_label.setText("TL: (no cfg)")
            self.br_label.setText("BR: (no cfg)")
            return
        dp = d.get("dispense_plate", {})
        tl = dp.get("TL_corner", {})
        br = dp.get("BR_corner", {})
        self.tl_label.setText(f"TL: {self._fmt_corner_mm(tl)}")
        self.br_label.setText(f"BR: {self._fmt_corner_mm(br)}")

    def _set_corner(self, key: str):
        d = self._read_cfg()
        if not d:
            return

        try:
            zc = self.picking.pick.phc.zc
            x_mm = float(zc.get_pos("x"))
            y_mm = float(zc.get_pos("y"))
        except Exception as e:
            logging.warning(f"DispensePlateCalibWidget: failed to read current XY: {e!r}")
            return

        x_um = x_mm * 1000.0
        y_um = y_mm * 1000.0

        d.setdefault("dispense_plate", {})
        d["dispense_plate"].setdefault(key, {})
        d["dispense_plate"][key]["x"] = float(x_um)
        d["dispense_plate"][key]["y"] = float(y_um)

        if not self._write_cfg(d):
            return

        # Best-effort live reload (only works if a dispense plate has been defined)
        try:
            phc = self.picking.pick.phc
            if hasattr(phc, "current_dp") and hasattr(phc, "pixel_size_um"):
                phc.define_dp(phc.current_dp, phc.pixel_size_um)
        except Exception as e:
            logging.warning(f"DispensePlateCalibWidget: reload failed (restart may be needed): {e!r}")

        self.refresh()

    def _move_to_well(self, well: str):
        try:
            phc = self.picking.pick.phc
            if not hasattr(phc, "dplate") or phc.dplate is None:
                logging.warning("DispensePlateCalibWidget: dispense plate not initialized yet (run Setup first).")
                return
            phc.dplate.go_to_well(well)
        except Exception as e:
            logging.warning(f"DispensePlateCalibWidget: move_to_well({well!r}) failed: {e!r}")
