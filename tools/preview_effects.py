"""Render every page-change effect as an animated GIF in previews/effects/ (no screen needed).
The GIF shows the send order; on the real panel the speed depends on the USB link (~1 s per full frame)."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageEnhance  # noqa: E402

from core.pages import render  # noqa: E402
from core.themes import THEMES  # noqa: E402
from core.transitions import EFFECTS, order  # noqa: E402
from tools.preview import sample  # noqa: E402

FRAMES = 24


def main():
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "previews", "effects")
    os.makedirs(out, exist_ok=True)
    data, hist, online = sample()
    ctx = {"data": data, "hist": hist, "online": online, "pages": ["overview", "clock"], "now": dt.datetime.now(),
           "h24": True, "bits": False, "date_fmt": "text"}
    size = (480, 320)
    a = render("overview", THEMES["midnight"], size, dict(ctx, page="overview")).convert("RGB")
    b = render("clock", THEMES["ember"], size, dict(ctx, page="clock")).convert("RGB")
    for eff in EFFECTS:
        if eff == "random":
            continue
        frames = [a.copy()]
        if eff == "fade":
            for i in range(1, 7):
                frames.append(ImageEnhance.Brightness(a).enhance(1 - i / 6))
            for i in range(1, 7):
                frames.append(ImageEnhance.Brightness(b).enhance(i / 6))
        else:
            rects = order(eff, *size)
            cur = ImageEnhance.Brightness(a).enhance(0.35) if eff == "fade_dissolve" else a.copy()
            if eff == "fade_dissolve":
                frames.append(cur.copy())
            per = max(1, len(rects) // FRAMES)
            for i, (x0, y0, x1, y1) in enumerate(rects, 1):
                src = ImageEnhance.Brightness(b).enhance(0.35) if eff == "fade_dissolve" else b
                cur.paste(src.crop((x0, y0, x1 + 1, y1 + 1)), (x0, y0))
                if i % per == 0 or i == len(rects):
                    frames.append(cur.copy())
            if eff == "fade_dissolve":
                frames.append(b.copy())
        frames += [b] * 8
        frames[0].save(os.path.join(out, f"{eff}.gif"), save_all=True, append_images=frames[1:], duration=60,
                       loop=0)
        print("wrote", eff)


if __name__ == "__main__":
    main()
