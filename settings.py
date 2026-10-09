"""Smart-Screen settings window. Saves config.yaml; the running app picks changes up within a second."""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

import psutil  # noqa: E402

import copy  # noqa: E402
import datetime as dt  # noqa: E402

from PIL import ImageEnhance, ImageTk  # noqa: E402

from core import draw  # noqa: E402
from core.config import Config, PAGES, ORIENTATIONS, MIRRORS  # noqa: E402
from core.pages import render_view  # noqa: E402
from core.pages import PAGE_TITLES  # noqa: E402
from core.themes import THEMES  # noqa: E402


def com_ports():
    try:
        from serial.tools.list_ports import comports
        return [f"{p.device}" for p in comports()]
    except Exception:
        return []


class SettingsWindow:
    def __init__(self):
        self.cfg = Config()
        c = self.cfg
        self.root = root = tk.Tk()
        root.title("Smart-Screen — Settings")
        root.resizable(False, False)
        try:
            root.call("tk", "scaling", 1.3)
        except Exception:
            pass
        main = ttk.Frame(root)
        main.pack(fill="both", expand=True, padx=10, pady=10)
        nb = ttk.Notebook(main)
        nb.grid(row=0, column=0, sticky="nsew")
        self.v = {}
        self.applied = copy.deepcopy(c.data)

        # ---------------- Display tab
        f = self._tab(nb, "Display")
        self._combo(f, 0, "Screen port", ("display", "com_port"), ["AUTO"] + com_ports(),
                    "AUTO finds the screen by its USB id. Pick a COM port if it is not found.")
        o = str(c.get("display", "orientation", default="landscape"))
        if o.startswith("reverse_"):  # old config values
            c.data["display"]["orientation"] = o[len("reverse_"):]
            c.data["display"]["flip"] = not c.get("display", "flip", default=False)
        self._combo(f, 1, "Orientation", ("display", "orientation"), ORIENTATIONS, readonly=True)
        self._check(f, 2, "Flip 180° (screen mounted upside down)", ("display", "flip"))
        self._combo(f, 3, "Mirror", ("display", "mirror"), MIRRORS, "for screens seen through glass/reflection",
                    readonly=True)
        self._combo(f, 11, "Text size", ("display", "text_size"), ["normal", "large", "xlarge"], readonly=True)
        self._spin(f, 12, "Full redraw every (s)", ("display", "full_refresh"), 0, 3600)
        theme_names = {k: t["name"] for k, t in THEMES.items()}
        self._combo(f, 4, "Theme", ("theme",), list(theme_names), readonly=True)
        self._scale(f, 5, "Brightness (%)", ("display", "brightness"), 0, 100)
        self._check(f, 6, "Dim at night", ("display", "night_mode"))
        self._scale(f, 7, "Night brightness (%)", ("display", "night_brightness"), 0, 100)
        self._entry(f, 8, "Night from (HH:MM)", ("display", "night_start"), width=8)
        self._entry(f, 9, "Night until (HH:MM)", ("display", "night_end"), width=8)
        self._check(f, 10, "24-hour clock", ("clock_24h",))
        self._combo(f, 13, "Date format", ("date_format",), ["text", "numeric", "both"],
                    "text = 16 Mehr 1405, numeric = 1405/07/16", readonly=True)

        # ---------------- Pages tab
        f = self._tab(nb, "Pages")
        self._check(f, 0, "Rotate pages automatically", ("pages", "rotate"))
        self._spin(f, 1, "Seconds per page", ("pages", "seconds"), 3, 300)
        self._combo(f, 2, "Page when not rotating", ("pages", "current"), PAGES, readonly=True)
        ttk.Label(f, text="Show these pages:").grid(row=3, column=0, sticky="w", pady=(10, 2))
        for i, p in enumerate(PAGES):
            self._check(f, 4 + i, PAGE_TITLES[p], ("pages", "enabled", p))

        # ---------------- Network tab
        f = self._tab(nb, "Network")
        nics = ["auto"] + sorted(psutil.net_if_addrs().keys())
        self._combo(f, 0, "Adapter for speed", ("network", "interface"), nics,
                    "auto = the busiest physical adapter")
        self._combo(f, 1, "Speed unit", ("network", "speed_unit"), ["bytes", "bits"], "bytes = MB/s, bits = Mbps",
                    readonly=True)
        ttk.Label(f, text="Latency targets (one per line:  Name | https://url)").grid(row=2, column=0, columnspan=3,
                                                                                    sticky="w", pady=(10, 2))
        self.targets = tk.Text(f, width=58, height=4)
        self.targets.grid(row=3, column=0, columnspan=3, sticky="we")
        self.targets.insert("1.0", "\n".join(f"{t.get('name', '')} | {t.get('url', '')}"
                                             for t in c.get("network", "latency_targets", default=[]) or []))
        ttk.Label(f, text="Your own server (optional, TCP check):").grid(row=4, column=0, columnspan=3, sticky="w",
                                                                        pady=(10, 2))
        self._entry(f, 5, "Name", ("network", "server", "name"))
        self._entry(f, 6, "Host / IP", ("network", "server", "host"))
        self._spin(f, 7, "Port", ("network", "server", "port"), 1, 65535)
        ttk.Label(f, text="VPN adapter names (comma separated, partial match):").grid(row=8, column=0, columnspan=3,
                                                                                     sticky="w", pady=(10, 2))
        self.vpn = ttk.Entry(f, width=60)
        self.vpn.grid(row=9, column=0, columnspan=3, sticky="we")
        self.vpn.insert(0, ", ".join(c.get("network", "vpn_adapters", default=[]) or []))

        # ---------------- Weather & labels tab
        f = self._tab(nb, "Weather & names")
        self._entry(f, 0, "Weather city", ("weather", "city"), hint="e.g. Istanbul, Tehran, Mashhad")
        self._combo(f, 1, "Units", ("weather", "units"), ["metric", "imperial"], readonly=True)
        self._entry(f, 2, "CPU name on screen", ("sensors", "cpu_label"), hint="empty = automatic")
        self._entry(f, 3, "GPU name on screen", ("sensors", "gpu_label"), hint="empty = automatic")
        self._check(f, 4, "Use LibreHardwareMonitor (temps, GPU, fans)", ("sensors", "use_lhm"))
        ttk.Label(f, text="Changing this needs Restart from the tray menu.", foreground="#666").grid(
            row=5, column=0, columnspan=3, sticky="w")

        # ---------------- live preview (does not touch the screen until Apply)
        pv = ttk.LabelFrame(main, text="Preview", padding=10)
        pv.grid(row=0, column=1, sticky="n", padx=(12, 0))
        self.pv_label = tk.Label(pv, bg="#202020")
        self.pv_label.pack()
        row = ttk.Frame(pv)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Page").pack(side="left")
        self.pv_page = tk.StringVar(value=c.get("pages", "current", default="overview"))
        ttk.Combobox(row, textvariable=self.pv_page, values=PAGES, width=12, state="readonly").pack(side="left",
                                                                                                    padx=6)
        ttk.Label(row, text="example values", foreground="#666").pack(side="right")
        self.pv_page.trace_add("write", lambda *a: self.changed())

        b = ttk.Frame(root)
        b.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(b, text="OK", command=self.ok).pack(side="right")
        ttk.Button(b, text="Apply", command=self.apply).pack(side="right", padx=6)
        ttk.Button(b, text="Cancel", command=root.destroy).pack(side="right")
        self.status = ttk.Label(b, text="", foreground="#666")
        self.status.pack(side="left")

        for _, var in self.v.values():
            var.trace_add("write", lambda *a: self.changed())
        self._after = None
        self.update_preview()
        self.set_status()

    # ------------------------------------------------------------ widgets
    def _tab(self, nb, name):
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text=name)
        return f

    def _row(self, f, r, label, hint=None):
        ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
        if hint:
            ttk.Label(f, text=hint, foreground="#666").grid(row=r, column=2, sticky="w", padx=(8, 0))

    def _combo(self, f, r, label, keys, values, hint=None, readonly=False):
        self._row(f, r, label, hint)
        var = tk.StringVar(value=str(self.cfg.get(*keys, default="")))
        ttk.Combobox(f, textvariable=var, values=values, width=22,
                     state="readonly" if readonly else "normal").grid(row=r, column=1, sticky="w")
        self.v[keys] = ("str", var)

    def _entry(self, f, r, label, keys, width=24, hint=None):
        self._row(f, r, label, hint)
        var = tk.StringVar(value=str(self.cfg.get(*keys, default="") or ""))
        ttk.Entry(f, textvariable=var, width=width).grid(row=r, column=1, sticky="w")
        self.v[keys] = ("str", var)

    def _check(self, f, r, label, keys):
        var = tk.BooleanVar(value=bool(self.cfg.get(*keys, default=True)))
        ttk.Checkbutton(f, text=label, variable=var).grid(row=r, column=0, columnspan=2, sticky="w", pady=2)
        self.v[keys] = ("bool", var)

    def _scale(self, f, r, label, keys, lo, hi):
        self._row(f, r, label)
        var = tk.IntVar(value=int(self.cfg.get(*keys, default=lo) or lo))
        fr = ttk.Frame(f)
        fr.grid(row=r, column=1, columnspan=2, sticky="w")
        ttk.Scale(fr, from_=lo, to=hi, variable=var, length=200,
                  command=lambda v: var.set(int(float(v)))).pack(side="left")
        ttk.Label(fr, textvariable=var, width=4).pack(side="left", padx=6)
        self.v[keys] = ("int", var)

    def _spin(self, f, r, label, keys, lo, hi):
        self._row(f, r, label)
        var = tk.StringVar(value=str(self.cfg.get(*keys, default=lo) or lo))
        ttk.Spinbox(f, from_=lo, to=hi, textvariable=var, width=8).grid(row=r, column=1, sticky="w")
        self.v[keys] = ("int", var)

    # ------------------------------------------------------------ apply / preview
    def collect(self, strict=True):
        """Settings from the widgets as a new dict (config itself is not changed)."""
        data = copy.deepcopy(self.cfg.data)
        for keys, (kind, var) in self.v.items():
            try:
                val = var.get()
                if kind == "int":
                    val = int(val)
                elif kind == "str":
                    val = val.strip()
            except Exception:
                if strict:
                    raise
                continue
            node = data
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = val
        if strict:
            for key in (("display", "night_start"), ("display", "night_end")):
                h, m = data[key[0]][key[1]].split(":")
                assert 0 <= int(h) < 24 and 0 <= int(m) < 60
        targets = []
        for line in self.targets.get("1.0", "end").splitlines():
            if "|" in line:
                name, url = [x.strip() for x in line.split("|", 1)]
                if url.startswith(("http://", "https://")):
                    targets.append({"name": name or url, "url": url})
        data["network"]["latency_targets"] = targets
        data["network"]["vpn_adapters"] = [x.strip() for x in self.vpn.get().split(",") if x.strip()]
        return data

    def changed(self):
        if self._after:
            self.root.after_cancel(self._after)
        self._after = self.root.after(150, lambda: (self.update_preview(), self.set_status()))

    def set_status(self):
        try:
            pending = self.collect(strict=False) != self.applied
        except Exception:
            pending = True
        self.status.config(text="Not applied yet - press Apply to send to the screen" if pending
                           else "Screen is up to date", foreground="#C2410C" if pending else "#15803D")

    def update_preview(self):
        try:
            d = self.collect(strict=False)
            from tools.preview import sample
            data, hist, online = sample()
            draw.set_text_size(d["display"].get("text_size", "normal"))
            en = d["pages"].get("enabled", {})
            pages = [p for p in PAGES if en.get(p, True)] or ["overview"]
            page = self.pv_page.get() or pages[0]
            ctx = {"data": data, "hist": hist, "online": online, "pages": pages, "page": page,
                   "now": dt.datetime.now(), "h24": bool(d.get("clock_24h", True)),
                   "bits": d["network"].get("speed_unit") == "bits", "date_fmt": d.get("date_format", "text")}
            img = render_view(page, THEMES.get(d.get("theme"), THEMES["midnight"]),
                              d["display"].get("orientation", "landscape"), bool(d["display"].get("flip")),
                              d["display"].get("mirror", "none"), ctx)
            b = int(d["display"].get("brightness", 60))
            img = ImageEnhance.Brightness(img).enhance(0.25 + 0.75 * b / 100)  # rough brightness look
            self._photo = ImageTk.PhotoImage(img)
            self.pv_label.config(image=self._photo)
        except Exception as e:
            self.pv_label.config(image="", text=f"Preview error: {e}", fg="white", width=60, height=10)

    def apply(self):
        try:
            data = self.collect(strict=True)
        except Exception:
            messagebox.showerror("Smart-Screen", "Please check the numbers and times (HH:MM).")
            return False
        self.cfg.data = data
        self.cfg.save()
        self.applied = copy.deepcopy(data)
        self.set_status()
        return True

    def ok(self):
        if self.apply():
            self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SettingsWindow().run()
