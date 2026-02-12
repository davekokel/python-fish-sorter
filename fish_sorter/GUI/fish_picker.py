from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime
import tomllib
from pathlib import Path

import napari
import numpy as np
from napari.utils.colormaps import Colormap
from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout, QPushButton, QDoubleSpinBox, QApplication

from tifffile import imwrite
from useq import MDASequence, Channel

from fish_sorter.GUI.classify import Classify
from fish_sorter.GUI.image_gui import ImageWidget
from fish_sorter.GUI.picking import Pick
from fish_sorter.GUI.picking_gui import PickGUI
from fish_sorter.GUI.picking_widgets.workflow_panel import WorkflowPanel
from fish_sorter.GUI.selection_gui import SelectGUI
from fish_sorter.GUI.setup_gui import SetupWidget
from fish_sorter.hardware.imaging_plate import ImagingPlate
from fish_sorter.hardware.picking_pipette import PickingPipette
from fish_sorter.helpers.mosaic import Mosaic

try:
    from mda_simulator.mmcore import FakeDemoCamera
except ModuleNotFoundError:
    FakeDemoCamera = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_site_cfg() -> dict:
    cfg = _repo_root() / "fish_sorter.local.toml"
    if not cfg.exists():
        return {}
    return tomllib.loads(cfg.read_text(encoding="utf-8"))


class _SuppressKnownMmcorePlusNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "MMCorePlus callback 'imageSnapped'" in msg and "signal has 0 argument(s) but 1 provided" in msg:
            return False
        if "QCoreSignaler.imageSnapped" in msg and "signal has 0 argument(s) but 1 provided" in msg:
            return False
        return True


def _apply_log_filters() -> None:
    logging.getLogger("pymmcore-plus").addFilter(_SuppressKnownMmcorePlusNoise())
    logging.getLogger("pymmcore_plus").addFilter(_SuppressKnownMmcorePlusNoise())


def _ensure_active_camera(core) -> None:
    cam = core.getCameraDevice()
    if cam:
        return
    try:
        cams = list(core.getLoadedDevicesOfType(core.DeviceType.CameraDevice))
    except Exception:
        cams = []
    if cams:
        core.setCameraDevice(cams[0])
        try:
            core.initializeDevice(cams[0])
        except Exception:
            pass


def _mm_channel_group_and_presets(core, site_cfg: dict) -> tuple[str, list[str]]:
    mm = site_cfg.get("micromanager", {}) if isinstance(site_cfg, dict) else {}
    group = (mm.get("channel_group") or "").strip()
    presets = list(mm.get("default_presets") or [])
    if not group:
        try:
            group = (core.getChannelGroup() or "").strip()
        except Exception:
            group = ""
    if group:
        try:
            groups = list(core.getAvailableConfigGroups())
        except Exception:
            groups = []
        if group not in groups:
            group = ""
            presets = []
    return group, presets


class JogSnapWidget(QWidget):
    def __init__(self, fp: "FishPicker"):
        super().__init__()
        self.fp = fp

        root = QVBoxLayout()
        self.setLayout(root)

        self.status = QLabel("")
        root.addWidget(self.status)

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

        snap_box = QGroupBox("Camera")
        snap_layout = QHBoxLayout()
        snap_box.setLayout(snap_layout)

        self.btn_snap = QPushButton("Snap → new layer")
        snap_layout.addWidget(self.btn_snap)
        root.addWidget(snap_box)

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


class CrosshairsPanel(QWidget):
    def __init__(self, fp: "FishPicker"):
        super().__init__()
        self.fp = fp

        root = QVBoxLayout()
        self.setLayout(root)

        self.status = QLabel("Crosshairs: -")
        root.addWidget(self.status)

        self.btn = QPushButton("Toggle crosshairs")
        self.btn.clicked.connect(self._toggle)
        root.addWidget(self.btn)

        self.refresh()

    def refresh(self):
        try:
            on = ("crosshairs" in self.fp.v.layers)
            self.status.setText("Crosshairs: ON" if on else "Crosshairs: OFF")
        except Exception:
            self.status.setText("Crosshairs: -")

    def _toggle(self):
        try:
            self.fp.img_tools.toggle_crosshairs()
        except Exception:
            pass
        self.refresh()
class FishPicker:

    def _right_dock_names(self) -> list[str]:
        return [
            "Workflow",
            "Picking",
            "Setup",
            "MDA",
            "MM Presets",
            "MM Properties",
            "Pick Selection",
            "Crosshairs",
        ]

    def _apply_right_dock_width(self, frac: float = 0.30) -> None:
        try:
            qtwin = self.v.window._qt_window
            base = self.v.window._dock_widgets.get("Workflow") or self.v.window._dock_widgets.get("Picking") or self.v.window._dock_widgets.get("MDA")
            if base is None:
                return
            target = int(qtwin.size().width() * float(frac))
            try:
                base.setMaximumWidth(target)
            except Exception:
                pass
            try:
                qtwin.resizeDocks([base], [target], Qt.Horizontal)
            except Exception:
                pass
            try:
                QApplication.processEvents()
                qtwin.updateGeometry()
            except Exception:
                pass
        except Exception:
            pass

    def _hide_right_docks(self, keep: str | None = None) -> None:
        for name in self._right_dock_names():
            dw = self.v.window._dock_widgets.get(name)
            if dw is None:
                continue
            if keep and (name == keep or (keep == "MDA" and name == "Crosshairs")):
                continue
            try:
                dw.hide()
            except Exception:
                pass

    def show_right_panel(self, name: str) -> None:
        self._hide_right_docks(keep=name)
        dw = self.v.window._dock_widgets.get(name)
        if dw is not None:
            try:
                dw.show()
                dw.raise_()
            except Exception:
                pass

        if name == "MDA":
            try:
                mda_dw = self.v.window._dock_widgets.get("MDA")
                ch_dw = self.v.window._dock_widgets.get("Crosshairs")
                if ch_dw is not None:
                    ch_dw.show()
                if mda_dw is not None and ch_dw is not None:
                    qtwin = self.v.window._qt_window
                    qtwin.tabifyDockWidget(mda_dw, ch_dw)
            except Exception:
                pass

        QTimer.singleShot(50, lambda: self._apply_right_dock_width(0.30))

    def __init__(self, sim: bool = False):
        _apply_log_filters()

        self.site_cfg = _load_site_cfg()
        self.expt_parent_dir = Path("D:/fishpicker_expts/")
        self.cfg_dir = _repo_root() / "fish_sorter" / "configs"

        self.v = napari.Viewer()
        self.dw, self.main_window = self.v.window.add_plugin_dock_widget("napari-micromanager")
        qtwindow = self.v.window._qt_window
        qtwindow._fishpicker = self
        qtwindow.addDockWidget(Qt.TopDockWidgetArea, self.dw)
        self.dw.show()

        logging.info("Loading mmcore")
        from pymmcore_plus import CMMCorePlus
        self.core = CMMCorePlus.instance()

        if sim:
            if FakeDemoCamera is not None:
                _ = FakeDemoCamera(timing=2)
                try:
                    self.core.setConfig("Channel", "Cy5")
                except Exception:
                    pass
        else:
            mm = self.site_cfg.get("micromanager", {}) if isinstance(self.site_cfg, dict) else {}
            mm_dir = mm.get("mm_install_dir")
            mm_cfg = mm.get("mm_config_path")

            if mm_dir:
                os.environ["MICROMANAGER_PATH"] = str(mm_dir)

            if not mm_cfg:
                raise RuntimeError("micromanager.mm_config_path is missing in fish_sorter.local.toml")

            cfg_path = Path(mm_cfg)
            logging.info(f"Micromanager config: {cfg_path}")
            self.core.loadSystemConfiguration(str(cfg_path))
            _ensure_active_camera(self.core)

            try:
                from pymmcore_widgets.control import PresetsWidget
                from pymmcore_widgets.device_properties import PropertyBrowser
                from qtpy.QtWidgets import QTabWidget

                self.mm_presets_tabs = QTabWidget()
                try:
                    groups = list(self.core.getAvailableConfigGroups())
                except Exception:
                    groups = []

                for g in groups:
                    try:
                        w = PresetsWidget(group=g, mmcore=self.core)
                        self.mm_presets_tabs.addTab(w, g)
                    except Exception as e:
                        logging.warning(f"MM Presets tab failed for group={g!r}: {e!r}")

                self.v.window.add_dock_widget(self.mm_presets_tabs, name="MM Presets", area="right", tabify=True)

                self.mm_props = PropertyBrowser(mmcore=self.core)
                self.v.window.add_dock_widget(self.mm_props, name="MM Properties", area="right", tabify=True)

            except Exception as e:
                logging.warning(f"MM Presets/Properties dock not available: {e!r}")

            try:
                exp = mm.get("default_exposure_ms", None)
                if exp is not None:
                    self.core.setExposure(float(exp))
            except Exception:
                pass

        try:
            self.main_window._mmc = self.core
            if hasattr(self.main_window, "_core_link") and hasattr(self.main_window._core_link, "_mmc"):
                self.main_window._core_link._mmc = self.core
        except Exception:
            pass

        logging.info("Initialize picking hardware controller")
        self.phc = PickingPipette(self.cfg_dir, sim=sim)

        self.image_init()
        self.assign_widgets()

        QTimer.singleShot(200, lambda: self.show_right_panel("Workflow"))

        napari.run()

    def assign_widgets(self):
        self.setup = SetupWidget(self.cfg_dir)
        self.v.window.add_dock_widget(self.setup, name="Setup", area="right", tabify=True)
        self.setup.pick_setup.clicked.connect(self.setup_picker)

        self.pick = Pick(self.phc)
        self.pick_gui = PickGUI(self.pick)
        self.pick_gui.new_expt.new_exp_req.connect(self._new_exp)
        self.pick_gui.calib_pick.save_pick_h.connect(self._save_pick_h)
        self.v.window.add_dock_widget(self.pick_gui, name="Picking", area="right", tabify=True)

        try:
            self.pick_gui.fishpicker = self
            self.workflow = WorkflowPanel(self.pick_gui)
            self.v.window.add_dock_widget(self.workflow, name="Workflow", area="right", tabify=True)

            self.crosshairs = CrosshairsPanel(self)
            self.v.window.add_dock_widget(self.crosshairs, name="Crosshairs", area="right", tabify=True)
            try:
                qtwin = self.v.window._qt_window
                mda_dw = self.v.window._dock_widgets.get("MDA")
                ch_dw  = self.v.window._dock_widgets.get("Crosshairs")
                if mda_dw is not None and ch_dw is not None:
                    qtwin.tabifyDockWidget(mda_dw, ch_dw)
            except Exception:
                pass
        except Exception as e:
            logging.warning(f"Workflow dock failed: {e!r}")

        self._hide_right_docks(keep="Workflow")

    def image_init(self):
        self.mosaic = Mosaic(self.v)
        self.mda = None

        self.img_tools = ImageWidget(self.v)
        self.wrap_widget = QWidget()
        self.ww_layout = QVBoxLayout()
        self.wrap_widget.setLayout(self.ww_layout)
        self.ww_layout.addWidget(self.main_window)
        self.ww_layout.addWidget(self.img_tools)
        self.dw.setWidget(self.wrap_widget)

        self.img_tools.mosaic_btn.clicked.connect(self.run)
        self.img_tools.class_btn.clicked.connect(self.run_class)

        try:
            self.core.events.pixelSizeChanged.connect(self.main_mag)
        except Exception:
            pass

        self.main_mag()
        self.setup_MDA()

    def main_mag(self):
        self.img_tools.get_mag()
        if "crosshairs" in self.v.layers:
            self.img_tools._create_crosshairs()

    def setup_MDA(self):
        self.main_window._show_dock_widget("MDA")

        dw = self.v.window._dock_widgets.get("MDA")
        if dw is None:
            for k, v in self.v.window._dock_widgets.items():
                if isinstance(k, str) and "MDA" in k:
                    dw = v
                    break
        if dw is None:
            raise RuntimeError("Could not locate MDA dock widget in napari window (_dock_widgets).")

        self.mda = dw.widget()

        sequence = self.mosaic.init_pos(self.img_tools.fov_w, self.img_tools.fov_h)

        group, presets = _mm_channel_group_and_presets(self.core, self.site_cfg)

        if group and not presets:
            try:
                presets = list(self.core.getAvailableConfigs(group))
            except Exception:
                presets = []

        seen = set()
        presets = [p for p in presets if not (str(p) in seen or seen.add(str(p)))]

        if group and presets:
            exp = float(self.core.getExposure())
            sequence = sequence.replace(
                channels=tuple(Channel(group=group, config=str(p), exposure=exp) for p in presets)
            )
        else:
            sequence = sequence.replace(channels=())

        self.mda.setValue(sequence)

        seq = self.mda.value()
        new_seq = MDASequence(
            axis_order=seq.axis_order,
            grid_plan=seq.grid_plan,
            channels=seq.channels,
            metadata={
                "pymmcore_widgets": {
                    "save_dir": str(self.expt_parent_dir),
                    "should_save": True,
                },
                "napari_micromanager": {
                    "axis_order": ("g", "c"),
                    "grid_plan": seq.grid_plan,
                },
            },
        )

        self.mda.setValue(new_seq)
        final_seq = self.mda.value()
        logging.info(f"Initial MDA setup sequence prior to TL and BR bounds: {final_seq}")

        try:
            self.v.window._qt_viewer.console.push(
                {"main_window": self.main_window, "mmc": self.core, "sequence": final_seq, "np": np}
            )
        except Exception:
            pass

        self.v.reset_view()

        if not hasattr(self, "_mda_finished_connect"):
            self._cancel = False

            def _mda_cancel(seq):
                logging.info("MDA canceled — user aborted acquisition")
                self._cancel = True

            def _mda_finish(seq):
                if self._cancel:
                    logging.info("Skipping stitching and classification.")
                else:
                    logging.info("MDA sequence finished. Triggering Mosaic stitching and classification")
                    self.run()
                self._cancel = False

            try:
                self.core.mda.events.sequenceCanceled.connect(_mda_cancel)
                self.core.mda.events.sequenceFinished.connect(_mda_finish)
            except Exception:
                pass

            self._mda_finished_connect = True

        self.show_right_panel("Workflow")

    def setup_picker(self):
        sequence = self.mda.value()
        self.main_mag()

        update_fov_gp = sequence.grid_plan.replace(fov_width=self.img_tools.fov_w, fov_height=self.img_tools.fov_h)
        update_fov_seq = sequence.replace(grid_plan=update_fov_gp)
        self.mda.setValue(update_fov_seq)

        self.expt_path = sequence.metadata["pymmcore_widgets"]["save_dir"].strip()
        self.expt_prefix = sequence.metadata["pymmcore_widgets"]["save_name"].removesuffix(".ome.zarr")
        settings_path = Path(self.expt_path) / f"{self.expt_prefix}_settings"
        mda = self.mda.value()
        logging.info(f"Saving MDA sequence: {mda} to {settings_path}")
        self.mda.save(settings_path)

        self.img_array = self.setup.get_img_array()
        self.dp_array = self.setup.get_dp_array()
        self.pick_type, offset, dtime, pick_h = self.setup.get_pick_type()

        logging.info("Picker setup parameters: ")
        logging.info(f"Expt Path: {self.expt_path}")
        logging.info(f"Expt Prefix: {self.expt_prefix}")
        logging.info(f"Image array: {self.img_array}")
        logging.info(f"Dispense array: {self.dp_array}")
        logging.info(f"cfg dir: {self.cfg_dir}")
        logging.info(f"Pick type: {self.pick_type}")
        logging.info(f"Pick offset: {offset}")
        logging.info(f"Pick delay time: {dtime}")
        logging.info(f"Previous pick height: {pick_h}")

        self.setup_iplate()

        logging.info("Enabling full pick functionality")
        self.pick.setup_exp(
            self.cfg_dir,
            self.expt_path,
            self.expt_prefix,
            offset,
            dtime,
            pick_h,
            self.iplate,
            self.dp_array,
            self.img_tools.pixel_size_um,
        )
        self.pick_gui.update_pick_widgets(status=True)
        self._pick_selection_gui()

        self.show_right_panel("Picking")

    def setup_iplate(self):
        array = self.cfg_dir / "arrays" / self.img_array
        logging.info(f"{array}")
        self.iplate = ImagingPlate(self.core, self.mda, array, self.img_tools.pixel_size_um)
        logging.info("Loaded image plate")

    def run_class(self):
        logging.info("Start Classification")
        sequence = self.mda.value()
        _ = self.mosaic.get_mosaic_metadata(sequence)

        self.iplate.set_calib_pts()
        self.iplate.load_wells(grid_list=self.mosaic.grid_list)

        self.classify = Classify(self.cfg_dir, self.pick_type, self.expt_prefix, self.expt_path, self.iplate, self.v)
        self.v.reset_view()

    def run(self):
        sequence = self.mda.value()
        img_arr = self.main_window._core_link._mda_handler._tmp_arrays
        self.stitch = self.mosaic.stitch_mosaic(sequence, img_arr)
        mosaic_metadata = self.mosaic.get_mosaic_metadata(sequence)
        num_chan, chan_names = mosaic_metadata[2], mosaic_metadata[3]

        for chan, chan_name in zip(range(num_chan), chan_names):
            mosaic = self.stitch[chan, :, :]
            if chan_name == "DAPI":
                color = Colormap([[0, 0, 0], [0.16, 0.82, 0.79]], name="DAPI-cyan")
            elif chan_name == "GFP":
                color = Colormap([[0, 0, 0], [0, 1, 0]], name="GFP-green")
            elif chan_name == "TXR":
                color = Colormap([[0, 0, 0], [1, 0.25, 0]], name="tiger-orange")
            elif chan_name == "CIT":
                color = Colormap([[0, 0, 0], [1, 1, 0]], name="CIT-yellow")
            elif chan_name == "CY5":
                color = Colormap([[0, 0, 0], [0.93, 0.13, 0.53]], name="CY5-plasma")
            else:
                color = "grey"
            self.v.add_image(mosaic, colormap=color, blending="additive", name=chan_name)

        remove_layers = []
        save_layers = []
        for layer in self.v.layers:
            if layer.name == "preview" or layer.name == "crosshairs" or "ome.zarr" in layer.name or self.expt_prefix in layer.name:
                remove_layers.append(layer)
            else:
                save_layers.append(layer)

        self._remove_layers(remove_layers)
        QTimer.singleShot(500, lambda: self._save_mosaic(save_layers))

    def _remove_layers(self, layers):
        for layer in layers:
            self.v.layers.remove(layer)

    def _save_mosaic(self, layers):
        logging.info("Saving mosaic layers")
        for layer in layers:
            save_path = Path(self.expt_path) / f"{layer.name}.tif"
            imwrite(save_path, layer.data)

        logging.info("Ready to classify")
        self.run_class()

    def _new_exp(self):
        logging.info("Remove all layers")
        for layer in list(self.v.layers):
            self.v.layers.remove(layer)

        if hasattr(self, "classify") and self.classify is not None:
            try:
                if hasattr(self.classify, "classify_widget"):
                    self.v.window.remove_dock_widget(self.classify.classify_widget)
                if hasattr(self.classify, "save_widget"):
                    self.v.window.remove_dock_widget(self.classify.save_widget)
                if hasattr(self.classify, "fish_widget"):
                    self.v.window.remove_dock_widget(self.classify.fish_widget)
            except Exception:
                pass
        self.classify = None

        if hasattr(self, "selection") and self.selection is not None:
            try:
                self.v.window.remove_dock_widget(self.selection)
            except Exception:
                pass
        self.selection = None

    def _save_pick_h(self):
        logging.info("Saving pick height to the pick type config")
        cfg = self.cfg_dir / "pick/pick_type_config.json"
        with open(cfg, "r") as pc:
            pick_cfg = json.load(pc)
        pick_cfg[self.pick_type]["picker"]["pick_height"] = self.phc.pick_h
        with open(cfg, "w") as pc:
            json.dump(pick_cfg, pc, indent=4, separators=(",", ": "))

    def _pick_selection_gui(self):
        if hasattr(self, "selection") and self.selection is not None:
            if self.selection.isVisible():
                self.selection.raise_()
                self.selection.setFocus()
                return
        self.selection = SelectGUI(self.pick, self.pick_type)
        self.v.window.add_dock_widget(self.selection, name="Pick Selection", area="right", tabify=True)
        self.selection.destroyed.connect(lambda: setattr(self, "selection", None))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="FishSorter")
    parser.add_argument("-s", "--sim", action="store_true")
    args = parser.parse_args()

    FishPicker(sim=args.sim)



