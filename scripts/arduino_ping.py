from __future__ import annotations

import time
import tomllib
from pathlib import Path

import serial


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    cfg = repo / "fish_sorter.local.toml"
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))

    v = data.get("valves", {})
    port = v.get("port")
    baud = int(v.get("baudrate", 115200))

    if not port:
        raise SystemExit("Missing [valves].port in fish_sorter.local.toml")

    ser = serial.Serial(port, baudrate=baud, timeout=0.2)
    time.sleep(4.0)

    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
    except Exception:
        pass

    ser.write(b"PING\n")
    ser.flush()

    deadline = time.time() + 3.0
    buf = b""
    while time.time() < deadline:
        chunk = ser.read(256)
        if chunk:
            buf += chunk
            if b"\n" in buf:
                line = buf.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
                print(f"PING {port} @ {baud}: RECV {line!r}")
                ser.close()
                return
        time.sleep(0.05)

    s = buf.decode("utf-8", errors="replace")
    print(f"PING {port} @ {baud}: TIMEOUT")
    if s:
        print(f"partial: {s!r}")
    ser.close()


if __name__ == "__main__":
    main()
