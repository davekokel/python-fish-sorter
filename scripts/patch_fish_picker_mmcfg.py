from __future__ import annotations
from pathlib import Path
import re

path = Path("fish_sorter/GUI/fish_picker.py")
txt = path.read_text(encoding="utf-8")

# Ensure tomllib + _load_site_cfg exist
if "import tomllib" not in txt:
    txt = txt.replace("import os", "import os\nimport tomllib", 1)

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

# Replace the block that picks the first cfg file with a TOML-first selection.
# We do this by finding the line that defines mm_dir = self.cfg_dir / "micromanager"
# and inserting a TOML override just before it.
if "mm_cfg_path = mm.get('mm_config_path')" not in txt:
    txt = txt.replace(
        "            mm_dir = self.cfg_dir / \"micromanager\"",
        "            site_cfg = _load_site_cfg()\n"
        "            mm = site_cfg.get('micromanager', {}) if isinstance(site_cfg, dict) else {}\n"
        "            mm_cfg_path = mm.get('mm_config_path')\n"
        "            if mm_cfg_path:\n"
        "                mm_cfg_path = Path(mm_cfg_path)\n"
        "                cfg_path = mm_cfg_path\n"
        "            else:\n"
        "                mm_dir = self.cfg_dir / \"micromanager\"",
        1,
    )

path.write_text(txt, encoding="utf-8")
print("patched fish_picker.py for TOML mm_config_path preference")
