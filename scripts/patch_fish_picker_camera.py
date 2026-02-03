from __future__ import annotations
from pathlib import Path
import re

path = Path(r"fish_sorter/GUI/fish_picker.py")
txt = path.read_text(encoding="utf-8")

m = re.search(r"^(\s*self\.core\.loadSystemConfiguration\([^\n]*\)\s*)$", txt, flags=re.M)
if not m:
    raise SystemExit("Couldn't find a line with self.core.loadSystemConfiguration(...)")

if "setCameraDevice(" in txt:
    print("already patched (setCameraDevice found)")
    raise SystemExit(0)

indent = re.match(r"^(\s*)", m.group(1)).group(1)
insert = (
    m.group(1)
    + "\n"
    + indent + "cam = self.core.getCameraDevice()\n"
    + indent + "if not cam:\n"
    + indent + "    try:\n"
    + indent + "        cams = list(self.core.getLoadedDevicesOfType(self.core.DeviceType.CameraDevice))\n"
    + indent + "    except Exception:\n"
    + indent + "        cams = []\n"
    + indent + "    if cams:\n"
    + indent + "        self.core.setCameraDevice(cams[0])\n"
    + indent + "        self.core.initializeDevice(cams[0])\n"
)

txt = txt[: m.start(1)] + insert + txt[m.end(1):]
path.write_text(txt, encoding="utf-8")
print("patched fish_picker.py")
