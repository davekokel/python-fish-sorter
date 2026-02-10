from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import tomllib
from pymmcore_plus import CMMCorePlus

from fish_sorter.hardware.valves.arduino_serial import ArduinoSerialValves, ArduinoValveConfig
from fish_sorter.hardware.zaber_controller import ZaberController


def load_site_cfg() -> dict:
    cfg = Path(__file__).resolve().parents[1] / "fish_sorter.local.toml"
    return tomllib.loads(cfg.read_text(encoding="utf-8"))


def snap(core: CMMCorePlus, tag: str) -> tuple[int, int, tuple[int, int]]:
    core.snapImage()
    img = core.getImage()
    h = int(core.getImageHeight())
    w = int(core.getImageWidth())
    arr = np.asarray(img).reshape(h, w)
    return int(arr.min()), int(arr.max()), (h, w)


def main() -> None:
    site = load_site_cfg()

    mm = site.get("micromanager", {}) if isinstance(site, dict) else {}
    mm_dir = mm.get("mm_install_dir")
    mm_cfg = mm.get("mm_config_path")

    if mm_dir:
        os.environ["MICROMANAGER_PATH"] = str(mm_dir)

    core = CMMCorePlus()
    core.loadSystemConfiguration(str(mm_cfg))

    print("MM_LOADED_DEVICES", list(core.getLoadedDevices()))
    print("MM_CAMERA", core.getCameraDevice())
    print("MM_SHUTTER", core.getShutterDevice())

    if "LightPath" in list(core.getLoadedDevices()):
        lp = core.getProperty("LightPath", "State")
        print("LightPath.State", lp)

    if "Objective" in list(core.getLoadedDevices()):
        st = core.getProperty("Objective", "State")
        lab = core.getProperty("Objective", "Label") if "Label" in list(core.getDevicePropertyNames("Objective")) else ""
        print("Objective.State", st, "Objective.Label", lab)

    if core.getShutterDevice():
        print("Shutter.State(before)", core.getProperty(core.getShutterDevice(), "State"))
        core.setProperty(core.getShutterDevice(), "State", "1")
        core.waitForDevice(core.getShutterDevice())
        print("Shutter.State(after_open)", core.getProperty(core.getShutterDevice(), "State"))

    mn, mx, shape = snap(core, "snap0")
    print("SNAP0", "shape", shape, "min", mn, "max", mx)

    if "XYStage" in list(core.getLoadedDevices()):
        x0 = core.getXPosition()
        y0 = core.getYPosition()
        print("XY_START", x0, y0)
        core.setXYPosition(x0 + 500.0, y0)
        core.waitForDevice(core.getXYStageDevice())
        print("XY_AFTER_DX", core.getXPosition(), core.getYPosition())
        core.setXYPosition(x0 + 500.0, y0 + 500.0)
        core.waitForDevice(core.getXYStageDevice())
        print("XY_AFTER_DXDY", core.getXPosition(), core.getYPosition())
        core.setXYPosition(x0, y0)
        core.waitForDevice(core.getXYStageDevice())
        print("XY_END", core.getXPosition(), core.getYPosition())

    zcfg = None
    try:
        zcfg = (Path(__file__).resolve().parents[1] / "fish_sorter" / "configs" / "hardware" / "zaber_config.json").read_text(encoding="utf-8")
    except Exception:
        zcfg = None

    try:
        z = ZaberController({"ports": ["COM3", "COM4", "COM5"]}, env="prod")
        print("ZABER_PORTS", {p: [d.identity.serial_number for d in devs] for p, devs in z.port_devices.items()})
        z.move_arm("x", 0.5, is_relative=True)
        time.sleep(0.2)
        z.move_arm("x", -0.5, is_relative=True)
        time.sleep(0.2)
        print("ZABER_JOG_OK")
        z.disconnect()
    except Exception as e:
        print("ZABER_ERR", repr(e))

    vcfg = site.get("valves", {}) if isinstance(site, dict) else {}
    if (vcfg.get("backend") or "").lower() == "arduino":
        port = str(vcfg.get("port") or "")
        baud = int(vcfg.get("baudrate") or 115200)
        v = ArduinoSerialValves(ArduinoValveConfig(port=port, baudrate=baud))
        v.connect()
        print("VALVES_STATUS", v.status())
        v.set_valve(1, True)
        print("VALVES_STATUS", v.status())
        v.set_valve(1, False)
        v.all_off()
        print("VALVES_STATUS", v.status())
        v.close()
    else:
        print("VALVES_BACKEND", vcfg.get("backend"))

    if core.getShutterDevice():
        core.setProperty(core.getShutterDevice(), "State", "0")
        core.waitForDevice(core.getShutterDevice())
        print("Shutter.State(end)", core.getProperty(core.getShutterDevice(), "State"))

    core.unloadAllDevices()
    print("PASS")


if __name__ == "__main__":
    main()
