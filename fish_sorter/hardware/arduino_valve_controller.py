from __future__ import annotations

import time
import serial


class ArduinoValveController:
    """
    Minimal serial protocol:

      - Send:  PING\n
        Recv:  PONG\n

      - Send:  WR <address> <value>\n
        Recv:  OK\n   (or ERR ...)

    We intentionally keep this "register-like" so we can drop it in where the
    WAGO Modbus controller was used without redesigning the whole call stack.
    """

    def __init__(self, port: str, baudrate: int = 115200, timeout_s: float = 2.0):
        self.port = port
        self.baudrate = int(baudrate)
        self.timeout_s = float(timeout_s)
        self.ser: serial.Serial | None = None

    def connect(self) -> None:
        if self.ser and self.ser.is_open:
            return
        self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout_s, write_timeout=None)
        time.sleep(2.0)
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception:
            pass

    def close(self) -> None:
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def _readline(self) -> str:
        assert self.ser is not None
        b = self.ser.readline()
        return b.decode("utf-8", errors="replace").strip()

    def ping(self) -> bool:
        self.connect()
        assert self.ser is not None
        self.ser.write(b"PING\n")
        self.ser.flush()
        resp = self._readline()
        return resp == "PONG"

    def write_register(self, address: int, value: int) -> None:
        self.connect()
        assert self.ser is not None
        line = f"WR {int(address)} {int(value)}\n".encode("utf-8")
        self.ser.write(line)
        self.ser.flush()
        resp = self._readline()
        if resp != "OK":
            raise RuntimeError(f"Arduino valve write failed: {resp!r}")
