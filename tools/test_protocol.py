"""Offline test: fake serial port that decodes rev A commands and rebuilds the framebuffer,
then checks it matches the frames the app rendered (validates partial updates)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

import library.lcd.lcd_comm as lc  # noqa: E402
import library.lcd.lcd_comm_rev_a as ra  # noqa: E402


class FakeSerial:
    def __init__(self, *a, **k):
        self.buf = bytearray()
        self.fb = None
        self.w, self.h = 320, 480
        self.pending = None
        self.cmds = []
        self.bytes = 0

    def write(self, data):
        self.bytes += len(data)
        self.buf += data
        self._parse()

    def _parse(self):
        while True:
            if self.pending:
                x0, y0, x1, y1 = self.pending
                need = (x1 - x0 + 1) * (y1 - y0 + 1) * 2
                if len(self.buf) < need:
                    return
                px = np.frombuffer(bytes(self.buf[:need]), dtype="<u2").reshape(y1 - y0 + 1, x1 - x0 + 1)
                self.fb[y0:y1 + 1, x0:x1 + 1] = px
                del self.buf[:need]
                self.pending = None
                continue
            if len(self.buf) < 6:
                return
            b = self.buf
            cmd = b[5]
            if b[0] == b[1] == b[2] == b[3] == b[4] == b[5] == 69:  # HELLO
                del self.buf[:6]
                self.cmds.append("HELLO")
                continue
            x = (b[0] << 2) | (b[1] >> 6)
            y = ((b[1] & 63) << 4) | (b[2] >> 4)
            ex = ((b[2] & 15) << 6) | (b[3] >> 2)
            ey = ((b[3] & 3) << 8) | b[4]
            if cmd == 121:
                if len(b) < 16:
                    return
                o = b[6] - 100
                self.w, self.h = (480, 320) if o in (2, 3) else (320, 480)
                self.fb = np.zeros((self.h, self.w), dtype=np.uint16)
                del self.buf[:16]
                self.cmds.append(f"ORIENT {o}")
                continue
            del self.buf[:6]
            if cmd == 197:
                self.pending = (x, y, ex, ey)
                self.cmds.append(f"BITMAP {x},{y}-{ex},{ey}")
            else:
                self.cmds.append(f"CMD {cmd} x={x}")

    def read(self, n):
        return b""

    def reset_input_buffer(self):
        pass

    def close(self):
        pass

    def flush(self):
        pass


fake = FakeSerial()
lc.serial.Serial = lambda *a, **k: fake
ra.LcdCommRevA.auto_detect_com_port = staticmethod(lambda: "FAKE")
ra.time.sleep = lambda s: None

from core.screen import Screen, to565  # noqa: E402
from core.pages import render  # noqa: E402
from core.themes import THEMES  # noqa: E402
from tools.preview import sample  # noqa: E402

scr = Screen("AUTO")
scr.connect("landscape", 50)
print("init:", fake.cmds[:8])
data, hist, online = sample()
ok = True
for i, (page, theme) in enumerate([("overview", "midnight")] * 4 + [("network", "neon")] * 3 + [("clock", "ember")] * 3):
    fake.bytes = 0
    data = dict(data, cpu_load=20 + i * 7, net_down=1e6 * (i + 1))
    for k in hist:
        hist[k] = hist[k][1:] + hist[k][:1]
    ctx = {"data": data, "hist": hist, "online": online, "pages": ["overview", "network", "clock"], "page": page,
           "now": dt.datetime(2026, 10, 8, 3, 4, 10 + i), "h24": True, "bits": False}
    img = render(page, THEMES[theme], (480, 320), ctx)
    n, area = scr.show(img)
    match = np.array_equal(fake.fb, to565(img))
    ok &= match
    print(f"frame {i}: {page:9s} rects={n:3d} px={area:6d} bytes={fake.bytes:7d} match={match}")
# portrait switch
scr.set_orientation("portrait")
img = render("storage", THEMES["frost"], (320, 480), ctx)
scr.show(img)
m = np.array_equal(fake.fb, to565(img))
ok &= m
print("portrait match:", m, fake.cmds[-3:])
print("ALL OK" if ok else "MISMATCH")
