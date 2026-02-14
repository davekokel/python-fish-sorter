from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable, Optional

from qtpy.QtCore import QTimer, Qt
from qtpy.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pymmcore_plus import CMMCorePlus


class StageControlPanel(QWidget):
    def __init__(self, core: CMMCorePlus, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.core = core

        root = QGridLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setHorizontalSpacing(10)
        root.setVerticalSpacing(8)

        self.lbl_dev = QLabel("XY stage: -")
        self.lbl_pos = QLabel("X: -    Y: -")
        root.addWidget(self.lbl_dev, 0, 0, 1, 3)
        root.addWidget(self.lbl_pos, 0, 3, 1, 3)

        root.addWidget(QLabel("Step (um)"), 1, 0)
        self.step_um = QDoubleSpinBox()
        self.step_um.setDecimals(1)
        self.step_um.setRange(0.1, 5000.0)
        self.step_um.setValue(50.0)
        root.addWidget(self.step_um, 1, 1)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        root.addWidget(self.btn_refresh, 1, 2)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.stop)
        root.addWidget(self.btn_stop, 1, 3)

        self.btn_home = QPushButton("Home")
        self.btn_home.clicked.connect(self.home)
        root.addWidget(self.btn_home, 1, 4)

        self.btn_xm = QPushButton("X -")
        self.btn_xp = QPushButton("X +")
        self.btn_ym = QPushButton("Y -")
        self.btn_yp = QPushButton("Y +")

        self.btn_xm.clicked.connect(lambda: self.jog(dx_um=-self.step_um.value(), dy_um=0.0))
        self.btn_xp.clicked.connect(lambda: self.jog(dx_um=+self.step_um.value(), dy_um=0.0))
        self.btn_ym.clicked.connect(lambda: self.jog(dx_um=0.0, dy_um=-self.step_um.value()))
        self.btn_yp.clicked.connect(lambda: self.jog(dx_um=0.0, dy_um=+self.step_um.value()))

        root.addWidget(self.btn_xm, 2, 0)
        root.addWidget(self.btn_xp, 2, 1)
        root.addWidget(self.btn_ym, 2, 2)
        root.addWidget(self.btn_yp, 2, 3)

        root.addWidget(QLabel("Go to X (um)"), 3, 0)
        self.goto_x = QDoubleSpinBox()
        self.goto_x.setDecimals(1)
        self.goto_x.setRange(-1e9, 1e9)
        root.addWidget(self.goto_x, 3, 1)

        root.addWidget(QLabel("Go to Y (um)"), 3, 2)
        self.goto_y = QDoubleSpinBox()
        self.goto_y.setDecimals(1)
        self.goto_y.setRange(-1e9, 1e9)
        root.addWidget(self.goto_y, 3, 3)

        self.btn_goto = QPushButton("Go")
        self.btn_goto.clicked.connect(self.goto)
        root.addWidget(self.btn_goto, 3, 4)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self.refresh()

    def _xy_dev(self) -> Optional[str]:
        try:
            dev = str(self.core.getXYStageDevice() or "").strip()
            return dev if dev else None
        except Exception:
            return None

    def _get_xy_um(self) -> Optional[tuple[float, float]]:
        dev = self._xy_dev()
        if not dev:
            return None
        try:
            x = float(self.core.getXPosition(dev))
            y = float(self.core.getYPosition(dev))
            return x, y
        except Exception:
            pass
        try:
            x, y = self.core.getXYPosition(dev)
            return float(x), float(y)
        except Exception:
            return None

    def _set_xy_um(self, x: float, y: float) -> bool:
        dev = self._xy_dev()
        if not dev:
            return False
        try:
            self.core.setXYPosition(dev, float(x), float(y))
            return True
        except Exception:
            return False

    def refresh(self):
        dev = self._xy_dev()
        self.lbl_dev.setText(f"XY stage: {dev or '(none)'}")
        xy = self._get_xy_um()
        if xy is None:
            self.lbl_pos.setText("X: -    Y: -")
            return
        x, y = xy
        self.lbl_pos.setText(f"X: {x:.1f}    Y: {y:.1f}")

    def jog(self, dx_um: float, dy_um: float):
        xy = self._get_xy_um()
        if xy is None:
            return
        x, y = xy
        self._set_xy_um(x + float(dx_um), y + float(dy_um))

    def goto(self):
        self._set_xy_um(self.goto_x.value(), self.goto_y.value())

    def stop(self):
        dev = self._xy_dev()
        if not dev:
            return
        try:
            self.core.stop(dev)
            return
        except Exception:
            pass
        try:
            self.core.stop()
        except Exception:
            pass

    def home(self):
        dev = self._xy_dev()
        if not dev:
            return
        try:
            self.core.home(dev)
        except Exception:
            pass


class TileGrid(QWidget):
    def __init__(
        self,
        title: str,
        options: list[str],
        on_apply: Callable[[str], None],
        get_current: Optional[Callable[[], Optional[str]]] = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self.title = title
        self.options = [str(o) for o in (options or [])]
        self.on_apply = on_apply
        self.get_current = get_current

        self._buttons: dict[str, QToolButton] = {}
        self._last_cols: Optional[int] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.lbl = QLabel("")
        self.lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
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

    def refresh_selected(self):
        cur = None
        if self.get_current is not None:
            try:
                cur = self.get_current()
            except Exception:
                cur = None
        if cur is None:
            return
        cur = str(cur)
        b = self._buttons.get(cur)
        if b is not None:
            b.setChecked(True)

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
        self._buttons.clear()

        if not self.options:
            self.lbl.setText(f"{self.title}: (no presets)")
            return

        self.lbl.setText(f"{self.title}: {len(self.options)} presets")

        for i, opt in enumerate(self.options):
            r = i // cols
            c = i % cols
            b = QToolButton()
            b.setText(opt)
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setMinimumHeight(44)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)

            b.setStyleSheet(
                "QToolButton{padding:10px;border:1px solid #aaa;border-radius:8px;}"
                "QToolButton:checked{border:2px solid #2a7fff;font-weight:bold;}"
            )

            b.clicked.connect(lambda _=False, o=opt: self.on_apply(o))
            self.grid.addWidget(b, r, c)
            self._buttons[opt] = b

        self.grid.setRowStretch(r + 1, 1)
        self.grid.setColumnStretch(cols, 1)

        self.refresh_selected()


class TransmittedLightCombined(QWidget):
    """
    Combined tab:
      - Light path presets
      - Transmitted light presets
      - Voltage control (slider if numeric-ish, else tiles)
    """

    def __init__(self, core: CMMCorePlus, groups: dict[str, list[str]], apply_fn: Callable[[str, str], None], parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.core = core
        self.groups = groups
        self.apply_fn = apply_fn

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(QLabel("Transmitted Light (combined)"))

        if "light path" in groups:
            root.addWidget(self._section_tiles("Light path", groups["light path"]))

        if "transmitted light" in groups:
            root.addWidget(self._section_tiles("Transmitted light", groups["transmitted light"]))

        if "transmitted light voltage" in groups:
            root.addWidget(self._section_voltage("Transmitted light voltage", groups["transmitted light voltage"]))

        root.addStretch(1)

    def _section_tiles(self, label: str, presets: list[str]) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        v.addWidget(QLabel(label))

        def _apply(p, g=label):
            self.apply_fn(g, p)

        def _get_current(g=label):
            try:
                return str(self.core.getCurrentConfig(g))
            except Exception:
                return None

        v.addWidget(TileGrid(title=label, options=presets, on_apply=_apply, get_current=lambda g=label: _get_current(g)))
        return box

    def _try_parse_voltage(self, s: str) -> Optional[float]:
        # pulls first float from a string like "250", "250 mV", "on 4", etc.
        m = re.search(r"([-+]?\d+(\.\d+)?)", str(s))
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def _section_voltage(self, label: str, presets: list[str]) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        v.addWidget(QLabel(label))

        vals = [(p, self._try_parse_voltage(p)) for p in presets]
        numeric = [x for x in vals if x[1] is not None]

        # If we can parse >=3 numeric presets, show slider; otherwise fall back to tiles.
        if len(numeric) < 3:
            v.addWidget(self._section_tiles(label, presets))
            return box

        numeric.sort(key=lambda t: t[1])
        min_v = numeric[0][1]
        max_v = numeric[-1][1]

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)

        self.vol_label = QLabel("")
        h.addWidget(self.vol_label)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(int(min_v))
        self.slider.setMaximum(int(max_v))
        self.slider.setValue(int(min_v))
        self.slider.valueChanged.connect(lambda x: self.vol_label.setText(f"{label}: {x}"))
        h.addWidget(self.slider, stretch=1)

        btn_apply = QPushButton("Apply")
        h.addWidget(btn_apply)
        v.addWidget(row)

        def _closest_preset(x: float) -> str:
            best = None
            bestd = 1e18
            for p, val in numeric:
                d = abs(val - x)
                if d < bestd:
                    bestd = d
                    best = p
            return best if best is not None else numeric[0][0]

        def _apply_voltage():
            target = float(self.slider.value())
            preset = _closest_preset(target)
            self.apply_fn(label, preset)

        btn_apply.clicked.connect(_apply_voltage)
        self.vol_label.setText(f"{label}: {self.slider.value()}")

        return box


class MicroManagerPanel(QWidget):
    def __init__(self, viewer_model, site_cfg: Optional[dict] = None, parent: QWidget | None = None):
        super().__init__(parent=parent)
        self.viewer_model = viewer_model
        self.site_cfg = site_cfg or {}

        self.core = CMMCorePlus.instance()
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(150)
        self._live_timer.timeout.connect(self._live_tick)

        self._preview_layer = None
        self._last_error: Optional[str] = None

        self._build_ui()
        QTimer.singleShot(0, self._auto_load_if_possible)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(QLabel("Micro-Manager"))
        hl.addStretch(1)
        root.addWidget(header)

        controls = QWidget()
        g = QGridLayout(controls)
        g.setContentsMargins(0, 0, 0, 0)

        self.btn_load = QPushButton("Load MM Config")
        self.btn_load.clicked.connect(self._load_mm_config)
        g.addWidget(self.btn_load, 0, 0)

        self.btn_live = QPushButton("Start Live")
        self.btn_live.clicked.connect(self._toggle_live)
        g.addWidget(self.btn_live, 0, 1)

        self.btn_snap = QPushButton("Snap")
        self.btn_snap.clicked.connect(self._snap_once)
        g.addWidget(self.btn_snap, 0, 2)

        self.exp_ms = QSpinBox()
        self.exp_ms.setRange(1, 5000)
        self.exp_ms.setValue(10)
        self.exp_ms.valueChanged.connect(self._set_exposure)
        g.addWidget(QLabel("Exposure (ms)"), 1, 0)
        g.addWidget(self.exp_ms, 1, 1)

        self.lbl_status = QLabel("Status: -")
        g.addWidget(self.lbl_status, 2, 0, 1, 3)

        root.addWidget(controls)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        self.groups_tabs = QTabWidget()
        self.tabs.addTab(self.groups_tabs, "Config Groups")

        self.props_container = QWidget()
        self.props_layout = QVBoxLayout(self.props_container)
        self.props_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs.addTab(self.props_container, "Device Properties")

    def _mm_cfg_path_from_site_cfg(self) -> str:
        mm = self.site_cfg.get("micromanager", {}) if isinstance(self.site_cfg, dict) else {}
        return (mm.get("mm_config_path") or "").strip()

    def _set_error(self, msg: str):
        self._last_error = msg
        self._update_status_line()

    def _clear_error(self):
        self._last_error = None
        self._update_status_line()

    def _update_status_line(self):
        try:
            devs = list(self.core.getLoadedDevices())
        except Exception as e:
            self.lbl_status.setText(f"Status: getLoadedDevices failed: {e!r}")
            return

        head = ", ".join(devs[:8])
        tail = "" if len(devs) <= 8 else f" (+{len(devs)-8} more)"
        base = f"{len(devs)} device(s) loaded: {head}{tail}"
        if self._last_error:
            self.lbl_status.setText(f"Status: {base} | ERROR: {self._last_error}")
        else:
            self.lbl_status.setText(f"Status: {base}")

    def _auto_load_if_possible(self):
        mm_cfg = self._mm_cfg_path_from_site_cfg()
        if not mm_cfg:
            self._set_error("mm_config_path missing in fish_sorter.local.toml (manual load)")
            return
        self._load_mm_config()

    def _load_mm_config(self):
        self._clear_error()

        mm_cfg = self._mm_cfg_path_from_site_cfg()
        if not mm_cfg:
            self._set_error("mm_config_path missing in fish_sorter.local.toml")
            return

        cfg_path = Path(mm_cfg)
        if not cfg_path.exists():
            self._set_error(f"config not found: {cfg_path}")
            return

        try:
            self.core.loadSystemConfiguration(str(cfg_path))
        except Exception as e:
            self._set_error(f"load config failed: {e!r}")
            return

        try:
            self.exp_ms.setValue(int(round(float(self.core.getExposure()))))
        except Exception:
            pass

        self._compile_config_groups()
        self._populate_properties()
        self._update_status_line()

    def _compile_config_groups(self):
        while self.groups_tabs.count():
            self.groups_tabs.removeTab(0)

        try:
            raw_groups = [str(g) for g in list(self.core.getAvailableConfigGroups())]
        except Exception as e:
            self._set_error(f"getAvailableConfigGroups failed: {e!r}")
            return

        if not raw_groups:
            msg = QLabel("No config groups found in this MM config.\nUse Device Properties tab or define groups in MM Studio.")
            msg.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.groups_tabs.addTab(msg, "(none)")
            return

        # Build map: lowercase -> canonical group name
        canon = {g.lower(): g for g in raw_groups}

        # Merge transmitted light groups into one synthetic tab (if present)
        tl_keys = ["light path", "transmitted light", "transmitted light voltage"]
        tl_present = [k for k in tl_keys if k in canon]

        if tl_present:
            groups_for_tab = {}
            for k in tl_present:
                g = canon[k]
                try:
                    presets = [str(p) for p in list(self.core.getAvailableConfigs(g))]
                except Exception:
                    presets = []
                groups_for_tab[g.lower()] = presets

            def _apply(group_label: str, preset: str):
                try:
                    self.core.setConfig(group_label, preset)
                except Exception as e:
                    self._set_error(f"setConfig({group_label!r},{preset!r}) failed: {e!r}")
                    return
                self._clear_error()

            combined = TransmittedLightCombined(
                core=self.core,
                groups={canon.get(k, k): groups_for_tab.get(canon.get(k, k).lower(), []) for k in tl_present},
                apply_fn=_apply,
            )
            self.groups_tabs.addTab(combined, "Transmitted Light")

        # Compile remaining groups (excluding merged ones)
        remaining = [g for g in raw_groups if g.lower() not in tl_present]
        remaining.sort(key=lambda x: x.lower())

        for g in remaining:
            try:
                presets = [str(p) for p in list(self.core.getAvailableConfigs(g))]
            except Exception as e:
                presets = []
                self._set_error(f"getAvailableConfigs({g!r}) failed: {e!r}")

            def _apply(preset: str, group=g):
                try:
                    self.core.setConfig(group, preset)
                except Exception as e:
                    self._set_error(f"setConfig({group!r},{preset!r}) failed: {e!r}")
                    return
                self._clear_error()
                w = self.groups_tabs.currentWidget()
                if hasattr(w, "refresh_selected"):
                    try:
                        w.refresh_selected()
                    except Exception:
                        pass

            def _get_current(group=g) -> Optional[str]:
                try:
                    return str(self.core.getCurrentConfig(group))
                except Exception:
                    return None

            if "stage" in g.lower():
                container = QWidget()
                v = QVBoxLayout(container)
                v.setContentsMargins(0, 0, 0, 0)
                v.setSpacing(8)

                v.addWidget(StageControlPanel(self.core))

                tiles = TileGrid(title=g, options=presets, on_apply=_apply, get_current=lambda group=g: _get_current(group))
                v.addWidget(tiles, stretch=1)

                def _rs():
                    tiles.refresh_selected()
                container.refresh_selected = _rs  # type: ignore[attr-defined]

                self.groups_tabs.addTab(container, g)
            else:
                tiles = TileGrid(title=g, options=presets, on_apply=_apply, get_current=lambda group=g: _get_current(group))
                self.groups_tabs.addTab(tiles, g)

    def _populate_properties(self):
        while self.props_layout.count():
            item = self.props_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        try:
            from pymmcore_widgets.device_properties import PropertyBrowser
        except Exception as e:
            self._set_error(f"PropertyBrowser unavailable: {e!r}")
            return

        try:
            w = PropertyBrowser(mmcore=self.core)
            self.props_layout.addWidget(w, stretch=1)
        except Exception as e:
            self._set_error(f"PropertyBrowser init failed: {e!r}")

    def _set_exposure(self):
        try:
            self.core.setExposure(float(self.exp_ms.value()))
        except Exception:
            pass

    def _ensure_preview_layer(self, arr):
        if self._preview_layer is None:
            try:
                self._preview_layer = self.viewer_model.add_image(arr, name="preview")
            except Exception:
                self._preview_layer = None

    def _snap_once(self):
        try:
            self.core.snapImage()
            img = self.core.getImage()
            h = int(self.core.getImageHeight())
            w = int(self.core.getImageWidth())
        except Exception as e:
            self._set_error(f"snap failed: {e!r}")
            return

        try:
            import numpy as np
            arr = np.asarray(img).reshape(h, w)
        except Exception as e:
            self._set_error(f"reshape failed: {e!r}")
            return

        self._ensure_preview_layer(arr)
        if self._preview_layer is not None:
            try:
                self._preview_layer.data = arr
            except Exception:
                pass

    def _toggle_live(self):
        if self._live_timer.isActive():
            self._live_timer.stop()
            self.btn_live.setText("Start Live")
            return
        self._live_timer.start()
        self.btn_live.setText("Stop Live")

    def _live_tick(self):
        self._snap_once()
