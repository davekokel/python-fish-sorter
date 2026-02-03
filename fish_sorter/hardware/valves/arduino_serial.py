from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import serial


class ValveProtocolError(RuntimeError):
    pass


@dataclass
class ArduinoValveConfig:
    port: str
    baudrate: int = 115200
    timeout_s: float = 1.0
    settle_s: float = 2.0


def _drain_startup(ser, timeout_s: float = 2.0) -> None:
    import time
    t0 = time.time()
    try:
        while time.time() - t0 < timeout_s:
            line = ser.readline()
            if not line:
                continue
            s = line.decode('utf-8', errors='ignore').strip()
            if not s:
                continue
            # Arduino resets on open and prints READY
            if s == 'READY':
                continue
            # If something else is printed, keep it but stop draining
            break
    except Exception:
        pass

class ArduinoSerialValves:
    def __init__(self, cfg: ArduinoValveConfig):
        self.cfg = cfg
        self.ser: Optional[serial.Serial] = None

    def connect(self) -> None:
        if self.ser and self.ser.is_open:
            return
        self.ser = serial.Serial(
            self.cfg.port,
            baudrate=int(self.cfg.baudrate),
            timeout=float(self.cfg.timeout_s),
        )
        time.sleep(float(self.cfg.settle_s))
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

    def _write_line(self, line: str) -> None:
        assert self.ser is not None
        b = (line.strip() + "\n").encode("utf-8")
        self.ser.write(b)
        self.ser.flush()

    def _read_line(self) -> str:
        assert self.ser is not None
        b = self.ser.readline()
        if not b:
            raise ValveProtocolError("timeout waiting for response")
        return b.decode("utf-8", errors="replace").strip()

    def cmd(self, line: str, expect_prefix: str | None = None) -> str:
        self.connect()
        assert self.ser is not None

        self._write_line(line)
        resp = self._read_line()
        # Arduino Uno resets on serial open and prints READY. Skip it if encountered.
        tries = 0
        while resp in ("", "READY") and tries < 5:
            resp = self._read_line()
            tries += 1
        if resp.startswith("ERR"):
            raise ValveProtocolError(resp)

        if expect_prefix is not None and not resp.startswith(expect_prefix):
            raise ValveProtocolError(f"unexpected response: {resp!r}")

        return resp

    def ping(self) -> bool:
        try:
            resp = self.cmd("PING", expect_prefix="PONG")
            return resp == "PONG"
        except Exception:
            return False

    def set_valve(self, n: int, on: bool) -> None:
        self.cmd(f"VALVE {int(n)} {'ON' if on else 'OFF'}", expect_prefix="OK")

    def all_off(self) -> None:
        self.cmd("ALL OFF", expect_prefix="OK")

    def status(self) -> str:
        return self.cmd("STATUS", expect_prefix="STATUS")
