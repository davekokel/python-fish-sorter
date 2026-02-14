from __future__ import annotations

# Thin shim to keep import paths stable:
#   from fish_sorter.GUI.imaging_stage_panel import ImagingStagePanel
# while implementation lives in GUI/widgets/imaging_stage_panel_impl.py

from fish_sorter.GUI.widgets.imaging_stage_panel_impl import ImagingStagePanel  # noqa: F401
