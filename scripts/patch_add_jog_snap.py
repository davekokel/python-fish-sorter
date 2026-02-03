from __future__ import annotations

import re
from pathlib import Path

path = Path("fish_sorter/GUI/fish_picker.py")
txt = path.read_text(encoding="utf-8")

# 1) Ensure qtpy widgets include what we need
if "QPushButton" not in txt or "QDoubleSpinBox" not in txt or "QLabel" not in txt:
    txt = re.sub(
        r"from qtpy\.QtWidgets import \(\s*([\s\S]*?)\s*\)\s*",
        lambda m: "from qtpy.QtWidgets import (\n"
                  "    QGroupBox,\n"
                  "    QHBoxLayout,\n"
                  "    QTabWidget,\n"
                  "    QVBoxLayout,\n"
                  "    QWidget,\n"
                  "    QPushButton,\n"
                  "    QDoubleSpinBox,\n"
                  "    QLabel,\n"
                  ")\n",
        txt,
        count=1,
        flags=re.M,
    )

# 2) Ensure datetime import (for timestamped layer names)
if "from datetime import datetime" not in txt:
    # insert after other stdlib imports if possible
    if "import os" in txt:
        txt = txt.replace("import os", "import os\nfrom datetime import datetime", 1)
    else:
        txt = "from datetime import datetime\n" + txt

# 3) Insert JogSnapWidget class once (before FishPicker class)
if "class JogSnapWidget" not in txt:
    marker = re.search(r"^class FishPicker:", txt, flags=re.M)
    if not marker:
        raise SystemExit("Could not find 'class FishPicker:' in fish_picker.py")

    widget_src = r'''
class JogSnapWidget(QWidget):
    def __init__(self, fp: "FishPicker"):
        super().__init__()
        self.fp = fp

        root = QVBoxLayout()
        self.setLayout(root)

        self.status = QLabel("")
        root.addWidget(self.status)

        # Step controls
        steps_box = QGroupBox("Step sizes (mm)")
        steps_layout = QHBoxLayout()
        steps_box.setLayout(steps_layout)

        self.step_xy = QDoubleSpinBox()
        self.step_xy.setDecimals(3)
        self.step_xy.setRange(0.001, 50.0)
        self.step_xy.setSingleStep(0.1)
        self.step_xy.setValue(0.5)

        self.step_p = QDoubleSpinBox()
        self.step_p.setDecimals(3)
        self.step_p.setRange(0.001, 50.0)
        self.step_p.setSingleStep(0.1)
        self.step_p.setValue(0.2)

        steps_layout.addWidget(QLabel("XY"))
        steps_layout.addWidget(self.step_xy)
        steps_layout.addWidget(QLabel("P"))
        steps_layout.addWidget(self.step_p)

        root.addWidget(steps_box)

        # Jog buttons
        jog_box = QGroupBox("Jog (Zaber)")
        jog_layout = QVBoxLayout()
        jog_box.setLayout(jog_layout)

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        row3 = QHBoxLayout()

        self.btn_xm = QPushButton("X -")
        self.btn_xp = QPushButton("X +")
        self.btn_ym = QPushButton("Y -")
        self.btn_yp = QPushButton("Y +")
        self.btn_pm = QPushButton("P -")
        self.btn_pp = QPushButton("P +")

        row1.addWidget(self.btn_xm)
        row1.addWidget(self.btn_xp)
        row2.addWidget(self.btn_ym)
        row2.addWidget(self.btn_yp)
        row3.addWidget(self.btn_pm)
        row3.addWidget(self.btn_pp)

        jog_layout.addLayout(row1)
        jog_layout.addLayout(row2)
        jog_layout.addLayout(row3)

        root.addWidget(jog_box)

        # Snap button
        snap_box = QGroupBox("Camera")
        snap_layout = QHBoxLayout()
        snap_box.setLayout(snap_layout)

        self.btn_snap = QPushButton("Snap → new layer")
        snap_layout.addWidget(self.btn_snap)
        root.addWidget(snap_box)

        # Wiring
        self.btn_xm.clicked.connect(lambda: self._jog("x", -self.step_xy.value()))
        self.btn_xp.clicked.connect(lambda: self._jog("x", +self.step_xy.value()))
        self.btn_ym.clicked.connect(lambda: self._jog("y", -self.step_xy.value()))
        self.btn_yp.clicked.connect(lambda: self._jog("y", +self.step_xy.value()))
        self.btn_pm.clicked.connect(lambda: self._jog("p", -self.step_p.value()))
        self.btn_pp.clicked.connect(lambda: self._jog("p", +self.step_p.value()))
        self.btn_snap.clicked.connect(self._snap)

    def _set_status(self, msg: str) -> None:
        self.status.setText(msg)

    def _jog(self, axis: str, delta_mm: float) -> None:
        try:
            zc = self.fp.phc.zc
            zc.move_arm(axis, float(delta_mm), is_relative=True)
            self._set_status(f"Jog {axis} {delta_mm:+.3f} mm")
        except Exception as e:
            self._set_status(f"Jog failed: {e!r}")

    def _snap(self) -> None:
        try:
            core = self.fp.core
            v = self.fp.v

            core.snapImage()
            img = core.getImage()
            h = core.getImageHeight()
            w = core.getImageWidth()

            import numpy as _np
            arr = _np.asarray(img).reshape(int(h), int(w))

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            name = f"snap_{ts}"
            v.add_image(arr, name=name)
            self._set_status(f"Snapped {name} (min={int(arr.min())}, max={int(arr.max())})")
        except Exception as e:
            self._set_status(f"Snap failed: {e!r}")
'''.lstrip("\n")

    txt = txt[: marker.start()] + widget_src + "\n\n" + txt[marker.start():]

# 4) Wire widget into assign_widgets (once)
if "JogSnapWidget(" not in txt:
    # Insert near end of assign_widgets after pick_gui is added
    m = re.search(r"(self\.v\.window\.add_dock_widget\(\s*self\.pick_gui[\s\S]*?\)\s*)", txt)
    if not m:
        raise SystemExit("Could not find where pick_gui is added; cannot insert JogSnapWidget")

    insert = m.group(1) + "\n        # Jog + Snap controls\n        self.jog_snap = JogSnapWidget(self)\n        self.v.window.add_dock_widget(self.jog_snap, name='Jog + Snap', area='right', tabify=True)\n"
    txt = txt[: m.start(1)] + insert + txt[m.end(1):]

path.write_text(txt, encoding="utf-8")
print("OK: patched fish_sorter/GUI/fish_picker.py (added Jog + Snap dock)")
