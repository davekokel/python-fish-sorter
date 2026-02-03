from __future__ import annotations
from zaber_motion.ascii import Connection

with Connection.open_serial_port("COM3") as conn:
    d = conn.detect_devices()[0]
    print("Device type:", type(d))
    print("Has attributes:", [a for a in ("axes", "axis", "get_axis", "get_axes", "get_all_axes") if hasattr(d, a)])
    print("Dir sample:", [x for x in dir(d) if "axis" in x.lower()][:50])

    if hasattr(d, "axes"):
        print("type(d.axes):", type(d.axes))
        try:
            print("len(d.axes):", len(d.axes))
        except Exception as e:
            print("len(d.axes) failed:", e)
        try:
            print("d.axes:", d.axes)
        except Exception as e:
            print("print(d.axes) failed:", e)
