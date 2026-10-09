"""Config loading/saving for Smart-Screen (config.yaml next to main.py)."""
import copy
import os
import threading

import yaml

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(APP_DIR, "config.yaml")

PAGES = ["overview", "network", "storage", "clock"]
ORIENTATIONS = ["landscape", "portrait"]
MIRRORS = ["none", "horizontal", "vertical"]

DEFAULTS = {
    "display": {
        "com_port": "AUTO",          # AUTO or e.g. COM5
        "orientation": "landscape",  # landscape | portrait
        "flip": False,               # rotate the picture 180 degrees (screen mounted upside down)
        "mirror": "none",            # none | horizontal | vertical
        "text_size": "normal",       # normal | large | xlarge
        "full_refresh": 60,          # seconds between full-screen redraws (0 = never); clears leftovers
        "brightness": 60,            # 0-100
        "night_mode": True,          # dim the screen at night
        "night_brightness": 15,
        "night_start": "23:30",
        "night_end": "07:00",
        "screen_on": True,
    },
    "theme": "midnight",
    "pages": {
        "rotate": True,              # cycle through enabled pages
        "seconds": 12,               # time per page when rotating
        "current": "overview",       # page shown when rotate is off
        "enabled": {p: True for p in PAGES},
    },
    "network": {
        "interface": "auto",         # auto, or the adapter name shown in Settings
        "speed_unit": "bytes",       # bytes (MB/s) | bits (Mbps)
        "vpn_adapters": ["xray_tun", "wintun", "tun", "wireguard", "wg", "sing-box", "singbox",
                         "v2ray", "openvpn", "tap-windows", "nekoray", "clash", "mihomo", "outline"],
        "latency_targets": [
            {"name": "Google", "url": "https://www.gstatic.com/generate_204"},
            {"name": "Cloudflare", "url": "https://1.1.1.1/cdn-cgi/trace"},
        ],
        "server": {"name": "", "host": "", "port": 443},  # optional: your own VPN server (TCP check)
    },
    "weather": {
        "city": "Istanbul",
        "units": "metric",           # metric | imperial
    },
    "sensors": {
        "use_lhm": True,             # LibreHardwareMonitor for temps / GPU (needs admin)
        "cpu_label": "",             # override the CPU name shown on screen
        "gpu_label": "",             # override the GPU name shown on screen
    },
    "clock_24h": True,
    "date_format": "text",           # text (16 Mehr 1405) | numeric (1405/07/16) | both
}


def _merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.lock = threading.RLock()
        self.data = copy.deepcopy(DEFAULTS)
        self.mtime = 0.0
        self.load()

    def load(self):
        with self.lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        raw = yaml.safe_load(f) or {}
                    self.data = _merge(DEFAULTS, raw)
                except Exception as e:  # keep running with the last good config
                    from library.log import logger
                    logger.error("config.yaml is invalid, keeping previous settings: %s", e)
                self.mtime = os.path.getmtime(self.path)
            else:
                self.save()

    def save(self):
        with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("# Smart-Screen settings. Edit here or from the tray icon -> Settings.\n")
                yaml.safe_dump(self.data, f, sort_keys=False, allow_unicode=True)
            os.replace(tmp, self.path)
            self.mtime = os.path.getmtime(self.path)

    def changed_on_disk(self):
        try:
            return os.path.getmtime(self.path) != self.mtime
        except OSError:
            return False

    def get(self, *keys, default=None):
        with self.lock:
            node = self.data
            for k in keys:
                if not isinstance(node, dict) or k not in node:
                    return default
                node = node[k]
            return node

    def set(self, *keys_and_value):
        *keys, value = keys_and_value
        with self.lock:
            node = self.data
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value
            self.save()
