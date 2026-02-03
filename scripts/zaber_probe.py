from __future__ import annotations

from zaber_motion.ascii import Connection

PORTS = ["COM3", "COM4", "COM5"]

def _safe_identity(d):
    ident = d.identity
    fields = [
        ("serial_number", getattr(ident, "serial_number", None)),
        ("name", getattr(ident, "name", None)),
        ("firmware_version", getattr(ident, "firmware_version", None)),
    ]
    return ", ".join([f"{k}={v}" for k, v in fields if v is not None])

def probe_port(port: str) -> None:
    print(f"\n== {port} ==")
    try:
        with Connection.open_serial_port(port) as conn:
            devices = conn.detect_devices()
            print(f"devices: {len(devices)}")
            for d in devices:
                print(f"  device {d.device_address}: {_safe_identity(d)}")
                try:
                    ax = d.get_axis(1)
                    pos = ax.get_position()
                    print(f"    axis 1 pos={pos}")
                except Exception as e:
                    print(f"    axis 1 pos=? ({e})")
    except Exception as e:
        print(f"ERROR: {e}")

def main() -> None:
    for p in PORTS:
        probe_port(p)

if __name__ == "__main__":
    main()
