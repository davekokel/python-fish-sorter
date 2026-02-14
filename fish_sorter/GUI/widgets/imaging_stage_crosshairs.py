from __future__ import annotations

from typing import Any, Optional


def render_crosshairs(viewer_model: Any, on: bool) -> tuple[bool, Optional[str]]:
    if viewer_model is None:
        return on, "Status: crosshairs unavailable (no viewer_model)"

    preview = None
    try:
        for layer in list(getattr(viewer_model, "layers", [])):
            if getattr(layer, "name", None) == "preview":
                preview = layer
                break
    except Exception:
        preview = None

    if preview is None:
        return on, "Status: crosshairs need preview layer (use camera+TL/Fluor snap/live)"

    if not on:
        try:
            if "crosshairs" in viewer_model.layers:
                del viewer_model.layers["crosshairs"]
        except Exception:
            pass
        return on, "Status: crosshairs OFF"

    try:
        h = int(preview.data.shape[-2])
        w = int(preview.data.shape[-1])
    except Exception:
        return on, "Status: crosshairs failed (unknown preview shape)"

    ymid = float(h) / 2.0
    xmid = float(w) / 2.0

    lines = [
        [[ymid, 0.0], [ymid, float(w)]],
        [[0.0, xmid], [float(h), xmid]],
    ]

    try:
        if "crosshairs" in viewer_model.layers:
            del viewer_model.layers["crosshairs"]
    except Exception:
        pass

    try:
        layer = viewer_model.add_shapes(
            lines,
            shape_type="line",
            edge_color="yellow",
            edge_width=8,
            name="crosshairs",
            blending="translucent",
        )
        try:
            layer.editable = False
            layer.selectable = False
        except Exception:
            pass
        return on, "Status: crosshairs ON"
    except Exception as e:
        return on, f"Status: crosshairs failed: {e!r}"
