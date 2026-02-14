from __future__ import annotations

from typing import Optional


class ImagingStageStageIO:
    def __init__(self, panel):
        self.p = panel

    def xy_dev(self) -> Optional[str]:
        try:
            dev = str(self.p.core.getXYStageDevice() or "").strip()
        except Exception:
            dev = ""
        return dev or None

    def get_xy(self) -> Optional[tuple[float, float]]:
        dev = self.xy_dev()
        if not dev:
            return None
        try:
            x, y = self.p.core.getXYPosition(dev)
            return float(x), float(y)
        except Exception:
            try:
                x = float(self.p.core.getXPosition(dev))
                y = float(self.p.core.getYPosition(dev))
                return float(x), float(y)
            except Exception:
                return None

    def set_xy(self, x: float, y: float) -> bool:
        dev = self.xy_dev()
        if not dev:
            return False
        try:
            self.p.core.setXYPosition(dev, float(x), float(y))
            return True
        except Exception:
            return False

    def refresh(self):
        dev = self.xy_dev()
        try:
            self.p.lbl_dev.setText(f"XY stage: {dev or '(none)'}")
        except Exception:
            pass

        xy = self.get_xy()
        if xy is None:
            try:
                self.p.lbl_xy.setText("X: -    Y: -")
                self.p.status.setText("Status: no XY stage")
            except Exception:
                pass
            return

        x, y = xy
        try:
            self.p.lbl_xy.setText(f"X: {x:.1f}    Y: {y:.1f}")
        except Exception:
            pass

    def jog(self, dx_um: float, dy_um: float):
        xy = self.get_xy()
        if xy is None:
            return
        x, y = xy
        ok = self.set_xy(x + float(dx_um), y + float(dy_um))
        try:
            self.p.status.setText(f"Status: jog -> {'OK' if ok else 'FAIL'}")
        except Exception:
            pass
        self.refresh()

    def goto(self):
        try:
            x = float(self.p.goto_x.value())
            y = float(self.p.goto_y.value())
        except Exception:
            return
        ok = self.set_xy(x, y)
        try:
            self.p.status.setText(f"Status: goto -> {'OK' if ok else 'FAIL'}")
        except Exception:
            pass
        self.refresh()
