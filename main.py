"""Smart-Screen: system monitor for Turing / UsbMonitor 3.5" USB screens.

Usage:
  pythonw main.py              run with tray icon (normal use)
  python main.py --console     run without tray icon, log to console
  python main.py --preview     no screen: write frames to preview.png (for testing themes)
"""
import argparse
import datetime as dt
import os
import socket
import subprocess
import sys
import threading
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

from library.log import logger  # noqa: E402
from core.config import Config, PAGES, ORIENTATIONS, MIRRORS  # noqa: E402
from core.online import Online  # noqa: E402
from core.pages import render_view, PAGE_TITLES  # noqa: E402
from core.screen import Screen, PreviewScreen, size_for  # noqa: E402
from core.sensors import Stats  # noqa: E402
from core.themes import THEMES, get_theme  # noqa: E402
from core.draw import set_text_size, TEXT_SIZES  # noqa: E402
from PIL import Image  # noqa: E402

LOCK_PORT = 47815
# white-heavy colour cycle used by "Clear ghost image" (helps LCD image retention fade)
WIPE_COLORS = [(255, 255, 255), (255, 0, 0), (255, 255, 255), (0, 255, 0), (255, 255, 255), (0, 0, 255),
               (255, 255, 255), (128, 128, 128)]


def single_instance(retries=10):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for _ in range(retries):
        try:
            s.bind(("127.0.0.1", LOCK_PORT))
            s.listen(1)
            return s
        except OSError:
            time.sleep(0.5)
    return None


def in_window(now: dt.datetime, start: str, end: str) -> bool:
    try:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
    except Exception:
        return False
    cur = now.hour * 60 + now.minute
    a, b = sh * 60 + sm, eh * 60 + em
    return a <= cur < b if a < b else (cur >= a or cur < b)


class App:
    def __init__(self, preview=False):
        self.cfg = Config()
        self.preview = preview
        self.stats = Stats(self.cfg)
        self.online = Online(self.cfg)
        self.screen = PreviewScreen(os.path.join(APP_DIR, "preview.png")) if preview \
            else Screen(self.cfg.get("display", "com_port", default="AUTO"))
        self.stop_evt = threading.Event()
        self.status = "Starting…"
        self.page_idx = 0
        self.page_since = time.time()
        self.icon = None
        self.restart_requested = False
        self.wipe_until = 0.0

    # ------------------------------------------------------------ state helpers
    def enabled_pages(self):
        en = self.cfg.get("pages", "enabled", default={}) or {}
        pages = [p for p in PAGES if en.get(p, True)]
        return pages or ["overview"]

    def current_page(self):
        pages = self.enabled_pages()
        if not self.cfg.get("pages", "rotate", default=True):
            cur = self.cfg.get("pages", "current", default="overview")
            return cur if cur in pages else pages[0], pages
        secs = max(3, int(self.cfg.get("pages", "seconds", default=12) or 12))
        if time.time() - self.page_since >= secs:
            self.page_idx += 1
            self.page_since = time.time()
        return pages[self.page_idx % len(pages)], pages

    def view(self):
        """(orientation, flip, mirror). Flip/mirror are done in software so they work on every screen model."""
        o = str(self.cfg.get("display", "orientation", default="landscape"))
        flip = bool(self.cfg.get("display", "flip", default=False))
        if o.startswith("reverse_"):  # old config values
            o, flip = o[len("reverse_"):], not flip
        if o not in ORIENTATIONS:
            o = "landscape"
        mirror = self.cfg.get("display", "mirror", default="none")
        return o, flip, mirror if mirror in MIRRORS else "none"

    def target_brightness(self, now):
        b = self.cfg.get("display", "brightness", default=60)
        if self.cfg.get("display", "night_mode", default=True) and in_window(
                now, self.cfg.get("display", "night_start", default="23:30"),
                self.cfg.get("display", "night_end", default="07:00")):
            b = min(b, self.cfg.get("display", "night_brightness", default=15))
        return b

    def notify(self):
        if self.icon:
            try:
                self.icon.title = f"Smart-Screen — {self.status}"
                self.icon.update_menu()
            except Exception:
                pass

    # ------------------------------------------------------------ main loop
    def loop(self):
        fails = 0
        while not self.stop_evt.is_set():
            # pick up edits made in config.yaml / the Settings window
            if self.cfg.changed_on_disk():
                old_port = self.cfg.get("display", "com_port")
                self.cfg.load()
                logger.info("Settings reloaded")
                self.online.refresh_now()
                if not self.preview and self.cfg.get("display", "com_port") != old_port:
                    self.screen.close()
                    self.screen = Screen(self.cfg.get("display", "com_port", default="AUTO"))
            orientation, flip, mirror = self.view()
            now = dt.datetime.now()
            try:
                if not self.screen.connected:
                    self.status = "Connecting…"
                    self.notify()
                    self.screen.connect(orientation, self.target_brightness(now))
                    fails = 0
                    self.status = "Connected" if not self.preview else "Preview mode"
                    self.notify()
                want_on = bool(self.cfg.get("display", "screen_on", default=True))
                self.screen.power(want_on)
                if not want_on:
                    self.stop_evt.wait(1)
                    continue
                self.screen.set_orientation(orientation)
                if time.time() < self.wipe_until:
                    # panel refresh: slow full-screen colour cycle at full brightness
                    self.screen.set_brightness(100)
                    col = WIPE_COLORS[int(time.time() // 4) % len(WIPE_COLORS)]
                    self.screen.show(Image.new("RGB", size_for(orientation), col))
                    self.stop_evt.wait(1)
                    continue
                self.screen.set_brightness(self.target_brightness(now))
                page, pages = self.current_page()
                data, hist = self.stats.snapshot()
                ctx = {"data": data, "hist": hist, "online": self.online.snapshot(), "pages": pages, "page": page,
                       "now": now, "h24": bool(self.cfg.get("clock_24h", default=True)),
                       "bits": self.cfg.get("network", "speed_unit") == "bits",
                       "date_fmt": self.cfg.get("date_format", default="text")}
                set_text_size(self.cfg.get("display", "text_size", default="normal"))
                img = render_view(page, get_theme(self.cfg.get("theme", default="midnight")), orientation, flip,
                                  mirror, ctx)
                self.screen.full_every = int(self.cfg.get("display", "full_refresh", default=60) or 0)
                self.screen.show(img)
            except Exception as e:
                fails += 1
                self.status = "Screen not found — retrying" if isinstance(e, ConnectionError) else f"Error: {e}"
                logger.warning("Display error (%s): %s", type(e).__name__, e)
                self.notify()
                self.screen.close()
                self.stop_evt.wait(min(30, 3 * fails))
                continue
            # wake up just after the next full second, so the clock ticks evenly
            self.stop_evt.wait(max(0.05, 1.0 - (time.time() % 1.0) + 0.02))

    # ------------------------------------------------------------ tray
    def build_tray(self):
        import pystray
        from pystray import Menu, MenuItem as Item
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((4, 10, 60, 50), 8, fill=(15, 24, 41, 255), outline=(56, 189, 248, 255), width=4)
        d.line((14, 38, 24, 28, 32, 34, 44, 20, 50, 26), fill=(52, 211, 153, 255), width=4)
        d.rectangle((26, 52, 38, 58), fill=(56, 189, 248, 255))

        cfg = self.cfg

        def setter(*keys, value):
            def _a(icon, item):
                cfg.set(*keys, value)
                if keys[0] == "pages" and keys[-1] == "current":
                    cfg.set("pages", "rotate", False)
                self.notify()
            return _a

        def is_(*keys, value):
            return lambda item: cfg.get(*keys) == value

        def toggle(*keys):
            def _a(icon, item):
                cfg.set(*keys, not cfg.get(*keys))
                self.notify()
            return _a

        def next_page(icon, item):
            if cfg.get("pages", "rotate"):
                self.page_idx += 1
                self.page_since = time.time()
            else:
                pages = self.enabled_pages()
                cur = cfg.get("pages", "current")
                i = pages.index(cur) if cur in pages else -1
                cfg.set("pages", "current", pages[(i + 1) % len(pages)])

        theme_menu = Menu(*[Item(t["name"], setter("theme", value=k), checked=is_("theme", value=k), radio=True)
                            for k, t in THEMES.items()])
        page_menu = Menu(
            Item("Auto-rotate", toggle("pages", "rotate"), checked=lambda i: bool(cfg.get("pages", "rotate"))),
            Item("Next page", next_page),
            Menu.SEPARATOR,
            *[Item(PAGE_TITLES[p], setter("pages", "current", value=p),
                   checked=(lambda p: lambda i: not cfg.get("pages", "rotate") and cfg.get("pages", "current") == p)(p),
                   radio=True) for p in PAGES])
        def rotate_next(icon, item):
            o, flip, _ = self.view()
            # 90-degree steps: landscape -> portrait -> landscape+flip -> portrait+flip
            seq = [("landscape", False), ("portrait", False), ("landscape", True), ("portrait", True)]
            i = seq.index((o, flip))
            o2, f2 = seq[(i + 1) % 4]
            cfg.data["display"]["orientation"], cfg.data["display"]["flip"] = o2, f2
            cfg.save()

        orient_menu = Menu(
            *[Item(o.title(), setter("display", "orientation", value=o),
                   checked=(lambda o: lambda i: self.view()[0] == o)(o), radio=True) for o in ORIENTATIONS],
            Menu.SEPARATOR,
            Item("Rotate 90°", rotate_next),
            Item("Flip 180°", toggle("display", "flip"), checked=lambda i: bool(cfg.get("display", "flip"))),
            Menu.SEPARATOR,
            *[Item(f"Mirror: {m.title()}", setter("display", "mirror", value=m),
                   checked=is_("display", "mirror", value=m), radio=True) for m in MIRRORS])
        size_menu = Menu(*[Item(n.replace("xlarge", "Extra large").title(), setter("display", "text_size", value=n),
                                checked=is_("display", "text_size", value=n), radio=True) for n in TEXT_SIZES])
        date_menu = Menu(*[Item(lab, setter("date_format", value=k), checked=is_("date_format", value=k), radio=True)
                           for k, lab in (("text", "Text  (16 Mehr 1405)"), ("numeric", "Numbers  (1405/07/16)"),
                                          ("both", "Both"))])
        bright_menu = Menu(*[Item(f"{b}%", setter("display", "brightness", value=b),
                                  checked=is_("display", "brightness", value=b), radio=True)
                             for b in (5, 10, 25, 40, 60, 80, 100)],
                           Menu.SEPARATOR,
                           Item("Dim at night", toggle("display", "night_mode"),
                                checked=lambda i: bool(cfg.get("display", "night_mode"))))

        def open_settings(icon, item):
            exe = sys.executable
            if exe.lower().endswith("python.exe"):
                exe = exe[:-10] + "pythonw.exe"
            subprocess.Popen([exe, os.path.join(APP_DIR, "settings.py")], cwd=APP_DIR)

        def open_log(icon, item):
            path = os.path.join(APP_DIR, "smartscreen.log")
            if hasattr(os, "startfile"):
                os.startfile(path)

        def restart(icon, item):
            self.restart_requested = True
            self.quit()

        menu = Menu(
            Item(lambda i: f"Smart-Screen — {self.status}", None, enabled=False),
            Menu.SEPARATOR,
            Item("Theme", theme_menu),
            Item("Page", page_menu),
            Item("Rotate / Flip", orient_menu),
            Item("Text size", size_menu),
            Item("Date format", date_menu),
            Item("Brightness", bright_menu),
            Item("Full redraw now", lambda icon, item: setattr(self.screen, "prev", None)),
            Item("Clear ghost image", Menu(
                *[Item(lab, (lambda m: lambda icon, item: self.start_wipe(m))(m),
                       checked=(lambda m: lambda i: self.wipe_minutes == m and time.time() < self.wipe_until)(m),
                       radio=True)
                  for lab, m in (("10 minutes", 10), ("30 minutes", 30), ("1 hour", 60), ("3 hours", 180))],
                Menu.SEPARATOR,
                Item("Stop", lambda icon, item: self.start_wipe(0)))),
            Item("Screen on", toggle("display", "screen_on"),
                 checked=lambda i: bool(cfg.get("display", "screen_on", default=True))),
            Menu.SEPARATOR,
            Item("Settings…", open_settings, default=True),
            Item("Open log", open_log),
            Item("Restart", restart),
            Item("Quit", lambda icon, item: self.quit()),
        )
        self.icon = pystray.Icon("SmartScreen", img, "Smart-Screen", menu)
        return self.icon

    wipe_minutes = 0

    def start_wipe(self, minutes):
        self.wipe_minutes = minutes
        self.wipe_until = time.time() + minutes * 60 if minutes else 0.0
        self.screen.prev = None
        logger.info("Panel refresh %s", f"for {minutes} min" if minutes else "stopped")
        self.notify()

    def quit(self):
        self.stop_evt.set()
        if self.icon:
            self.icon.stop()

    def run(self, tray=True):
        self.stats.start()
        self.online.start()
        t = threading.Thread(target=self.loop, name="display", daemon=True)
        t.start()
        if tray:
            self.build_tray().run()
        else:
            try:
                while t.is_alive():
                    t.join(0.5)
            except KeyboardInterrupt:
                self.stop_evt.set()
        self.stop_evt.set()
        t.join(5)
        self.shutdown()

    def shutdown(self):
        try:
            if self.screen.connected and not self.preview:
                self.screen.power(False)
        except Exception:
            pass
        self.screen.close()
        self.stats.stop()
        self.online.stop()


def main():
    ap = argparse.ArgumentParser(description="Smart-Screen system monitor")
    ap.add_argument("--console", action="store_true", help="no tray icon")
    ap.add_argument("--preview", action="store_true", help="no screen, write preview.png")
    args = ap.parse_args()

    lock = single_instance()
    if lock is None:
        logger.error("Smart-Screen is already running")
        sys.exit(1)
    logger.info("Smart-Screen starting (Python %s)", sys.version.split()[0])
    app = App(preview=args.preview)
    tray = not args.console

    def control():  # stop.bat connects here and sends "quit"
        while not app.stop_evt.is_set():
            try:
                conn, _ = lock.accept()
                with conn:
                    conn.settimeout(2)
                    if conn.recv(16).strip() == b"quit":
                        logger.info("Quit requested by stop.bat")
                        app.quit()
            except OSError:
                return
    threading.Thread(target=control, name="control", daemon=True).start()
    try:
        app.run(tray=tray)
    finally:
        lock.close()
    if app.restart_requested:
        subprocess.Popen([sys.executable] + sys.argv, cwd=APP_DIR)


if __name__ == "__main__":
    main()
