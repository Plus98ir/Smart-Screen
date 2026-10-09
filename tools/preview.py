"""Render every page/theme/orientation with sample data into previews/ (no screen needed).
Usage: python tools/preview.py"""
import datetime as dt
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from core.pages import PAGES, render  # noqa: E402
from core.themes import THEMES  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "previews")


def sample():
    random.seed(4)
    n = 90
    hist = {
        "cpu_load": [max(2, 25 + 18 * math.sin(i / 7) + random.uniform(-6, 6)) for i in range(n)],
        "gpu_load": [max(0, 45 + 30 * math.sin(i / 11 + 1) + random.uniform(-5, 5)) for i in range(n)],
        "net_down": [max(0, 3e6 + 2.5e6 * math.sin(i / 5) + random.uniform(-8e5, 8e5)) for i in range(n)],
        "net_up": [max(0, 4e5 + 3e5 * math.sin(i / 4 + 2) + random.uniform(-1e5, 1e5)) for i in range(n)],
    }
    data = {
        "host": "PLUSPC", "cpu_name": "Ryzen 7 5800X", "cpu_load": 34.0, "cpu_temp": 61.0, "cpu_clock": 4475.0,
        "cpu_power": 78.0, "gpu_name": "NVIDIA GeForce RTX 3070", "gpu_short": "RTX 3070", "gpu_load": 72.0,
        "gpu_temp": 66.0, "gpu_clock": 1905.0, "gpu_fan": 1240.0, "gpu_mem_used": 5321.0, "gpu_mem_total": 8192.0,
        "ram_pct": 47.0, "ram_used": 15.1 * 1024 ** 3, "ram_total": 32 * 1024 ** 3,
        "net_down": 4.82 * 1024 ** 2, "net_up": 612 * 1024, "net_total_down": 38.4 * 1024 ** 3,
        "net_total_up": 2.9 * 1024 ** 3, "nic": "Ethernet", "vpn_adapter": "xray_tun",
        "disk_read": 12.5 * 1024 ** 2, "disk_write": 3.1 * 1024 ** 2,
        "disks": [{"label": "C:", "used": 312e9, "total": 500e9, "pct": 62.4},
                  {"label": "D:", "used": 1.62e12, "total": 2e12, "pct": 81.0},
                  {"label": "F:", "used": 455e9, "total": 480e9, "pct": 94.8}],
        "procs": {"cpu": [("chrome", 8.4, 2.1e9), ("FortniteClient-Win64-Shipping", 6.2, 4.3e9),
                          ("v2rayN", 1.9, 1.5e8), ("Discord", 1.1, 6e8), ("explorer", 0.4, 1e8)],
                  "mem": [("FortniteClient-Win64-Shipping", 6.2, 4.3e9)]},
        "boot": time.time() - (2 * 86400 + 5 * 3600 + 17 * 60),
    }
    online = {
        "latency": [{"name": "Google", "ms": 86.0}, {"name": "Cloudflare", "ms": 71.0}],
        "server": {"name": "TR server", "ms": 142.0}, "ip": "185.199.45.12", "country": "TR", "online": True,
        "weather": {"city": "Istanbul", "temp": 18.4, "feels": 17.0, "humidity": 72, "wind": 14, "is_day": True,
                    "text": "Partly cloudy", "icon": "partly", "unit": "°C", "wind_unit": "km/h",
                    "days": [{"date": "2026-10-08", "max": 21, "min": 14, "icon": "partly"},
                             {"date": "2026-10-09", "max": 19, "min": 13, "icon": "rain"},
                             {"date": "2026-10-10", "max": 22, "min": 15, "icon": "sun"}]},
    }
    return data, hist, online


def main():
    from core.draw import set_text_size
    size_name = sys.argv[1] if len(sys.argv) > 1 else "normal"
    set_text_size(size_name)
    os.makedirs(OUT, exist_ok=True)
    data, hist, online = sample()
    pages = list(PAGES)
    now = dt.datetime(2026, 10, 8, 2, 49, 37)
    for theme_key, theme in THEMES.items():
        for orient, size in (("landscape", (480, 320)), ("portrait", (320, 480))):
            imgs = []
            for p in pages:
                ctx = {"data": data, "hist": hist, "online": online, "pages": pages, "page": p, "now": now,
                       "h24": True, "bits": False}
                t0 = time.perf_counter()
                img = render(p, theme, size, ctx)
                ms = (time.perf_counter() - t0) * 1000
                img.save(os.path.join(OUT, f"{theme_key}_{orient}_{p}.png"))
                imgs.append(img)
                print(f"{theme_key:9s} {orient:9s} {p:9s} {ms:6.1f} ms")
            gap = 12
            w, h = size
            sheet = Image.new("RGB", (len(imgs) * (w + gap) + gap, h + 2 * gap), (40, 40, 46))
            for i, im in enumerate(imgs):
                sheet.paste(im, (gap + i * (w + gap), gap))
            suffix = "" if size_name == "normal" else f"_{size_name}"
            sheet.save(os.path.join(OUT, f"sheet_{theme_key}_{orient}{suffix}.png"))


if __name__ == "__main__":
    main()
