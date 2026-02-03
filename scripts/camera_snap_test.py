from __future__ import annotations

import os
from pathlib import Path

from pymmcore_plus import CMMCorePlus

MM_DIR = r"C:\Program Files\Micro-Manager-2.0"
CFG = r"C:\Program Files\Micro-Manager-2.0\flash4.cfg"

def main() -> None:
    os.environ["MICROMANAGER_PATH"] = MM_DIR

    core = CMMCorePlus()
    core.loadSystemConfiguration(CFG)

    cam = core.getCameraDevice()
    print(f"camera_device: {cam}")

    core.snapImage()
    img = core.getImage()

    try:
        h = core.getImageHeight()
        w = core.getImageWidth()
        print(f"image_shape: {h}x{w}, dtype={img.dtype}, min={img.min()}, max={img.max()}")
    except Exception as e:
        print(f"image info error: {e}")

if __name__ == "__main__":
    main()
