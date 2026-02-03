from __future__ import annotations
import time
import serial

port = "COM7"
baud = 115200

ser = serial.Serial(port, baudrate=baud, timeout=0.2)
time.sleep(2.0)

t0 = time.time()
buf = b""
while time.time() - t0 < 5.0:
    buf += ser.read(512)
    time.sleep(0.05)

ser.close()
print(buf.decode("utf-8", errors="replace"))
