from pymmcore_plus import CMMCorePlus
import os

os.environ["MICROMANAGER_PATH"] = r"C:\Program Files\Micro-Manager-2.0"
cfg = r"C:\Program Files\Micro-Manager-2.0\flash4.cfg"

mmc = CMMCorePlus()
mmc.loadSystemConfiguration(cfg)

print("XYStageDevice:", repr(mmc.getXYStageDevice()))
print("ChannelGroup:", repr(mmc.getChannelGroup()))
print("ConfigGroups:", list(mmc.getAvailableConfigGroups()))

for g in mmc.getAvailableConfigGroups():
    presets = list(mmc.getAvailableConfigs(g))
    print(f"{g}: {presets[:20]}")
