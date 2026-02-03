from __future__ import annotations
from pathlib import Path
import re

path = Path("fish_sorter/GUI/fish_picker.py")
txt = path.read_text(encoding="utf-8")

def ensure_import(line: str, after: str) -> None:
    global txt
    if line not in txt:
        txt = txt.replace(after, after + "\n" + line)

# Ensure imports
ensure_import("import tomllib", "import os")
ensure_import("from pymmcore_plus import CMMCorePlus", "import napari")

# Insert _load_site_cfg if missing
if "def _load_site_cfg" not in txt:
    txt = txt.replace(
        "class FishPicker:",
        "def _load_site_cfg() -> dict:\n"
        "    repo = Path(__file__).resolve().parents[2]\n"
        "    cfg = repo / 'fish_sorter.local.toml'\n"
        "    if not cfg.exists():\n"
        "        return {}\n"
        "    return tomllib.loads(cfg.read_text(encoding='utf-8'))\n\n"
        "class FishPicker:",
        1,
    )

# Ensure we read micromanager settings once at init (right after 'Loading mmcore' log)
if "site_cfg = _load_site_cfg()" not in txt:
    txt = re.sub(
        r"(logging\.info\('Loading mmcore'\))",
        r"\1\n"
        r"        site_cfg = _load_site_cfg()\n"
        r"        mm = site_cfg.get('micromanager', {}) if isinstance(site_cfg, dict) else {}\n"
        r"        mm_dir = mm.get('mm_install_dir') or os.environ.get('MICROMANAGER_PATH')\n"
        r"        mm_cfg = mm.get('mm_config_path')\n"
        r"        if mm_dir:\n"
        r"            os.environ['MICROMANAGER_PATH'] = str(mm_dir)\n"
        r"        if mm_cfg:\n"
        r"            cfg_path = Path(mm_cfg)",
        txt,
        count=1,
    )

# After loadSystemConfiguration(...), ensure active camera is set
m = re.search(r"^(\s*self\.core\.loadSystemConfiguration\([^\n]*\)\s*)$", txt, flags=re.M)
if m and "setCameraDevice(" not in txt:
    indent = re.match(r"^(\s*)", m.group(1)).group(1)
    inject = (
        m.group(1) + "\n"
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
    txt = txt[:m.start(1)] + inject + txt[m.end(1):]

path.write_text(txt, encoding="utf-8")
print("patched fish_picker.py")
