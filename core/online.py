"""Background network checks: latency, public IP / exit country, own-server reachability, weather."""
import http.client
import json
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request

from library.log import logger

UA = {"User-Agent": "Smart-Screen/1.0"}

WEATHER_CODES = {
    0: ("Clear", "sun"), 1: ("Mostly clear", "sun"), 2: ("Partly cloudy", "partly"), 3: ("Overcast", "cloud"),
    45: ("Fog", "fog"), 48: ("Fog", "fog"),
    51: ("Light drizzle", "rain"), 53: ("Drizzle", "rain"), 55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "rain"), 57: ("Freezing drizzle", "rain"),
    61: ("Light rain", "rain"), 63: ("Rain", "rain"), 65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "rain"), 67: ("Freezing rain", "rain"),
    71: ("Light snow", "snow"), 73: ("Snow", "snow"), 75: ("Heavy snow", "snow"), 77: ("Snow grains", "snow"),
    80: ("Showers", "rain"), 81: ("Showers", "rain"), 82: ("Heavy showers", "rain"),
    85: ("Snow showers", "snow"), 86: ("Snow showers", "snow"),
    95: ("Thunderstorm", "storm"), 96: ("Thunderstorm", "storm"), 99: ("Thunderstorm", "storm"),
}


def _get_json(url, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_text(url, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def http_rtt(url: str, timeout=5.0) -> float:
    """Round-trip time of one HTTP request on an already-open connection (ms).
    Works through TUN-mode VPNs, where ICMP ping is answered locally and is meaningless."""
    u = urllib.parse.urlparse(url)
    host, port = u.hostname, u.port or (443 if u.scheme == "https" else 80)
    path = u.path or "/"
    if u.scheme == "https":
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ssl.create_default_context())
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        best = None
        for i in range(3):
            t0 = time.perf_counter()
            conn.request("GET", path, headers={**UA, "Connection": "keep-alive"})
            r = conn.getresponse()
            r.read()
            dt = (time.perf_counter() - t0) * 1000
            if i > 0:  # first request includes TCP + TLS setup
                best = dt if best is None else min(best, dt)
        return best
    finally:
        conn.close()


def tcp_rtt(host: str, port: int, timeout=4.0) -> float:
    t0 = time.perf_counter()
    with socket.create_connection((host, int(port)), timeout=timeout):
        return (time.perf_counter() - t0) * 1000


class Online:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.data = {"latency": [], "ip": None, "country": None, "colo": None, "server": None, "weather": None,
                     "online": None}
        self._stop = threading.Event()
        self._geo = None  # (city, lat, lon, label)
        self._wake = threading.Event()

    def _set(self, **kw):
        with self.lock:
            self.data.update(kw)

    def snapshot(self):
        with self.lock:
            return dict(self.data)

    def refresh_now(self):
        self._wake.set()

    # ---------------------------------------------------------------- checks
    def check_latency(self):
        res = []
        for t in self.cfg.get("network", "latency_targets", default=[]) or []:
            try:
                ms = http_rtt(t["url"])
            except Exception:
                ms = None
            res.append({"name": t.get("name", "?"), "ms": ms})
        srv = self.cfg.get("network", "server", default={}) or {}
        server = None
        if srv.get("host"):
            try:
                ms = tcp_rtt(srv["host"], srv.get("port", 443))
            except Exception:
                ms = None
            server = {"name": srv.get("name") or srv["host"], "ms": ms}
        online = any(r["ms"] is not None for r in res) if res else None
        self._set(latency=res, server=server, online=online)

    def check_ip(self):
        try:
            txt = _get_text("https://1.1.1.1/cdn-cgi/trace")
            kv = dict(line.split("=", 1) for line in txt.splitlines() if "=" in line)
            self._set(ip=kv.get("ip"), country=kv.get("loc"), colo=kv.get("colo"))
        except Exception:
            try:
                self._set(ip=_get_text("https://api.ipify.org").strip(), country=None)
            except Exception:
                self._set(ip=None, country=None)

    def check_weather(self):
        city = (self.cfg.get("weather", "city") or "").strip()
        if not city:
            self._set(weather=None)
            return
        if not self._geo or self._geo[0] != city:
            q = urllib.parse.quote(city)
            g = _get_json(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&format=json")
            if not g.get("results"):
                logger.warning("Weather: city '%s' not found", city)
                self._set(weather={"error": f"City not found: {city}"})
                return
            r = g["results"][0]
            self._geo = (city, r["latitude"], r["longitude"], r.get("name", city), r.get("country_code", ""))
        _, lat, lon, label, cc = self._geo
        imperial = self.cfg.get("weather", "units") == "imperial"
        units = "&temperature_unit=fahrenheit&wind_speed_unit=mph" if imperial else ""
        w = _get_json("https://api.open-meteo.com/v1/forecast?"
                      f"latitude={lat}&longitude={lon}"
                      "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,"
                      "wind_speed_10m,is_day"
                      "&daily=temperature_2m_max,temperature_2m_min,weather_code"
                      f"&timezone=auto&forecast_days=3{units}")
        cur = w["current"]
        text, icon = WEATHER_CODES.get(int(cur["weather_code"]), ("—", "cloud"))
        daily = w.get("daily", {})
        days = []
        for i in range(min(3, len(daily.get("time", [])))):
            t2, ic2 = WEATHER_CODES.get(int(daily["weather_code"][i]), ("—", "cloud"))
            days.append({"date": daily["time"][i], "max": daily["temperature_2m_max"][i],
                         "min": daily["temperature_2m_min"][i], "icon": ic2, "text": t2})
        self._set(weather={
            "city": label, "cc": cc, "temp": cur["temperature_2m"], "feels": cur["apparent_temperature"],
            "humidity": cur["relative_humidity_2m"], "wind": cur["wind_speed_10m"],
            "is_day": bool(cur.get("is_day", 1)), "text": text, "icon": icon, "days": days,
            "unit": "°F" if imperial else "°C", "wind_unit": "mph" if imperial else "km/h", "at": time.time()})

    # ---------------------------------------------------------------- loop
    def run(self):
        last = {"lat": 0, "ip": 0, "wx": 0}
        intervals = {"lat": 20, "ip": 120, "wx": 900}
        jobs = {"lat": self.check_latency, "ip": self.check_ip, "wx": self.check_weather}
        while not self._stop.is_set():
            forced = self._wake.is_set()
            self._wake.clear()
            now = time.time()
            for k, fn in jobs.items():
                if forced or now - last[k] >= intervals[k]:
                    try:
                        fn()
                        last[k] = now
                    except Exception as e:
                        logger.info("%s check failed: %s", k, e)
                        last[k] = now - intervals[k] + 30  # retry in 30 s
            self._wake.wait(2)

    def start(self):
        threading.Thread(target=self.run, name="online", daemon=True).start()

    def stop(self):
        self._stop.set()
        self._wake.set()
