"""Talks to the display. Only changed parts of each frame are sent (the serial link is slow)."""
import time

import numpy as np
from PIL import Image

from library.log import logger

ORIENT = {"portrait": 0, "reverse_portrait": 1, "landscape": 2, "reverse_landscape": 3}

BAND = 16          # rows per band when looking for changes
MIN_GAP = 24       # merge changed column runs closer than this (px)
FULL_RATIO = 0.65  # send the whole frame if more than this share changed


def size_for(orientation: str, native=(320, 480)):
    w, h = native
    return (h, w) if "landscape" in orientation else (w, h)


def to565(img: Image.Image) -> np.ndarray:
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    return ((a[:, :, 0] >> 3) << 11) | ((a[:, :, 1] >> 2) << 5) | (a[:, :, 2] >> 3)


def changed_rects(prev: np.ndarray, cur: np.ndarray):
    """Return [(x0, y0, x1, y1)] (inclusive) covering every changed pixel."""
    diff = prev != cur
    if not diff.any():
        return []
    h, w = diff.shape
    rects = []
    for y0 in range(0, h, BAND):
        band = diff[y0:y0 + BAND]
        cols = np.flatnonzero(band.any(axis=0))
        if cols.size == 0:
            continue
        rows = np.flatnonzero(band.any(axis=1))
        ry0, ry1 = y0 + int(rows[0]), y0 + int(rows[-1])
        # split into runs separated by wide gaps
        start = prev_c = int(cols[0])
        for c in cols[1:]:
            c = int(c)
            if c - prev_c > MIN_GAP:
                rects.append([start, ry0, prev_c, ry1])
                start = c
            prev_c = c
        rects.append([start, ry0, prev_c, ry1])
    # merge vertically touching rects with similar x span
    rects.sort(key=lambda r: (r[0], r[1]))
    merged = []
    for r in rects:
        for m in merged:
            if r[1] <= m[3] + 1 + BAND and abs(r[0] - m[0]) <= MIN_GAP and abs(r[2] - m[2]) <= MIN_GAP:
                m[0], m[1], m[2], m[3] = min(m[0], r[0]), min(m[1], r[1]), max(m[2], r[2]), max(m[3], r[3])
                break
        else:
            merged.append(list(r))
    return [tuple(m) for m in merged]


class Screen:
    """Real Turing / UsbMonitor 3.5" screen (rev A protocol)."""

    def __init__(self, com_port="AUTO"):
        self.com_port = com_port
        self.lcd = None
        self.prev = None
        self.orientation = None
        self.brightness = None
        self.is_on = True
        self.full_every = 60   # seconds; periodic full redraw clears anything a partial update missed
        self.last_full = 0.0

    @property
    def connected(self):
        return self.lcd is not None

    def connect(self, orientation, brightness):
        from library.lcd.lcd_comm_rev_a import LcdCommRevA
        logger.info("Connecting to screen (port %s)...", self.com_port)
        lcd = LcdCommRevA(com_port=self.com_port, display_width=320, display_height=480, update_queue=None)
        lcd.Reset()              # clears a half-sent frame from a previous app; port may change
        lcd.InitializeComm()
        logger.info("Screen sub-revision: %s", getattr(lcd, "sub_revision", "?"))
        lcd.ScreenOn()
        self.lcd = lcd
        self.is_on = True
        self.brightness = None
        self.set_brightness(brightness)
        self.set_orientation(orientation, force=True)

    def close(self):
        if self.lcd:
            try:
                self.lcd.closeSerial()
            except Exception:
                pass
        self.lcd = None
        self.prev = None

    def set_orientation(self, orientation, force=False):
        if orientation == self.orientation and not force:
            return
        self.lcd.SetOrientation(ORIENT.get(orientation, 2))
        self.orientation = orientation
        self.prev = None  # full redraw

    def set_brightness(self, level):
        level = int(max(0, min(100, level)))
        if level != self.brightness:
            self.lcd.SetBrightness(level)
            self.brightness = level

    def power(self, on: bool):
        if on == self.is_on:
            return
        (self.lcd.ScreenOn if on else self.lcd.ScreenOff)()
        self.is_on = on
        if on:
            self.prev = None

    def show(self, img: Image.Image):
        cur = to565(img)
        h, w = cur.shape
        due = self.full_every and time.time() - self.last_full >= self.full_every
        if self.prev is None or self.prev.shape != cur.shape or due:
            self.lcd.DisplayPILImage(img, 0, 0)
            self.prev = cur
            self.last_full = time.time()
            return 1, w * h
        rects = changed_rects(self.prev, cur)
        area = sum((r[2] - r[0] + 1) * (r[3] - r[1] + 1) for r in rects)
        if area > FULL_RATIO * w * h:
            self.lcd.DisplayPILImage(img, 0, 0)
            self.prev = cur
            self.last_full = time.time()
            return 1, w * h
        for x0, y0, x1, y1 in rects:
            self.lcd.DisplayPILImage(img.crop((x0, y0, x1 + 1, y1 + 1)), x0, y0)
        self.prev = cur
        return len(rects), area


class PreviewScreen(Screen):
    """No hardware: writes the latest frame to preview.png (used with --preview)."""

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.img = None

    def connect(self, orientation, brightness):
        self.lcd = True
        self.orientation = orientation
        self.brightness = brightness

    def close(self):
        self.lcd = None

    def set_orientation(self, orientation, force=False):
        self.orientation = orientation
        self.prev = None

    def set_brightness(self, level):
        self.brightness = level

    def power(self, on):
        self.is_on = on

    def show(self, img):
        cur = to565(img)
        rects = [] if self.prev is None or self.prev.shape != cur.shape else changed_rects(self.prev, cur)
        self.prev = cur
        img.save(self.path)
        return len(rects), sum((r[2] - r[0] + 1) * (r[3] - r[1] + 1) for r in rects)
