from __future__ import annotations
from pathlib import Path
import re

path = Path("fish_sorter/GUI/fish_picker.py")
txt = path.read_text(encoding="utf-8")

# 1) Remove hardcoded MICROMANAGER_PATH lines if present
txt = re.sub(r"(?m)^os\.environ\['MICROMANAGER_PATH'\]\s*=.*\n", "", txt)
txt = re.sub(r"(?m)^micromanager_path\s*=.*\n", "", txt)

# 2) Fix cfg_dir to be repo-relative and stable
# Replace the current cfg_dir assignment line inside __init__
txt = re.sub(
    r"(?m)^\s*self\.cfg_dir\s*=\s*Path\(\)\.absolute\(\)\.parent\s*/\s*\"python-fish-sorter/fish_sorter/configs/\"\s*$",
    "        self.cfg_dir = Path(__file__).resolve().parents[2] / 'fish_sorter' / 'configs'",
    txt,
)

# 3) Ensure we use a known-good MMCore (CMMCorePlus), not the plugin's core
# Replace: self.core = self.main_window._mmc
txt = re.sub(
    r"(?m)^\s*self\.core\s*=\s*self\.main_window\._mmc\s*$",
    "        from pymmcore_plus import CMMCorePlus\n        self.core = CMMCorePlus()",
    txt,
)

# 4) Replace the entire "else:" (non-sim) block with TOML-first config selection
# We'll locate the block that starts with "else:" after the sim check and ends before "logging.info('Initialize picking hardware controller')"
m = re.search(
    r"(?ms)\n\s*else:\n(.*?)\n\s*logging\.info\('Initialize picking hardware controller'\)",
    txt
)
if not m:
    raise SystemExit("Couldn't find the non-sim else-block to replace")

new_else = """
        else:
            site_cfg = _load_site_cfg()
            mm = site_cfg.get('micromanager', {}) if isinstance(site_cfg, dict) else {}

            mm_dir = mm.get('mm_install_dir')
            mm_cfg = mm.get('mm_config_path')

            if mm_dir:
                os.environ['MICROMANAGER_PATH'] = str(mm_dir)

            if not mm_cfg:
                raise RuntimeError("micromanager.mm_config_path is missing in fish_sorter.local.toml")

            cfg_path = Path(mm_cfg)
            logging.info(f"Micromanager config: {cfg_path}")
            self.core.loadSystemConfiguration(str(cfg_path))

            # Ensure an active camera is selected (snap/live UI otherwise inert)
            cam = self.core.getCameraDevice()
            if not cam:
                try:
                    cams = list(self.core.getLoadedDevicesOfType(self.core.DeviceType.CameraDevice))
                except Exception:
                    cams = []
                if cams:
                    self.core.setCameraDevice(cams[0])
                    self.core.initializeDevice(cams[0])

        logging.info('Initialize picking hardware controller')
"""

txt = txt[:m.start(0)] + "\n" + new_else + txt[m.end(0):]

# 5) Ensure PickingPipette gets sim flag
txt = re.sub(
    r"(?m)^\s*self\.phc\s*=\s*PickingPipette\(self\.cfg_dir\)\s*$",
    "        self.phc = PickingPipette(self.cfg_dir, sim=sim)",
    txt,
)

path.write_text(txt, encoding="utf-8")
print("fish_picker.py patched")
