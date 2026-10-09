"""Page layouts. Each page draws for landscape (480x320) or portrait (320x480)."""
import datetime as dt
import math
import time

from core import draw
from core.draw import Canvas
from core.jalali import jalali_string, gregorian_string

PAGE_TITLES = {"overview": "System", "network": "Network", "storage": "Storage", "clock": "Clock"}


# ---------------------------------------------------------------- formatting
def isnum(v):
    return isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))


def fmt_pct(v):
    return f"{v:.0f}" if isnum(v) else "--"


def fmt_temp(v):
    return f"{v:.0f}°" if isnum(v) else "--°"


def fmt_bytes(n, digits=1):
    if not isnum(n):
        return "--", ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            if unit == "B":
                return f"{n:.0f}", unit
            return (f"{n:.{digits}f}" if n < 100 else f"{n:.0f}"), unit
        n /= 1024.0


def fmt_speed(n, bits=False):
    if not isnum(n):
        return "--", ""
    if bits:
        n *= 8
        for unit in ("bps", "Kbps", "Mbps", "Gbps"):
            if n < 1000 or unit == "Gbps":
                return (f"{n:.0f}" if n >= 100 or unit == "bps" else f"{n:.1f}"), unit
            n /= 1000.0
    v, u = fmt_bytes(n)
    return v, (u + "/s")


def fmt_clock_ghz(mhz):
    return f"{mhz / 1000:.2f}" if isnum(mhz) and mhz > 0 else "--"


def fmt_uptime(boot):
    s = int(time.time() - boot)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return (f"{d}d {h:02d}h {m:02d}m" if d else f"{h:02d}h {m:02d}m")


def temp_color(t, v, warn=70, bad=85):
    if not isnum(v):
        return t["dim"]
    return t["ok"] if v < warn else t["warn"] if v < bad else t["bad"]


def load_color(t, v, base):
    if not isnum(v):
        return base
    return base if v < 85 else t["warn"] if v < 95 else t["bad"]


def ms_color(t, ms):
    if ms is None:
        return t["bad"]
    return t["ok"] if ms < 120 else t["warn"] if ms < 300 else t["bad"]


# ---------------------------------------------------------------- shared parts
def header(c: Canvas, title, ctx):
    t = c.t
    W = c.w
    tf = t.get("title_font", "bold")
    size = 14 if tf == "monox" else 15
    c.text(12, 17, title.upper() if tf == "monox" else title, tf, size, t["text"], "lm", glow=True)
    # page dots
    pages, cur = ctx["pages"], ctx["page"]
    if len(pages) > 1:
        n = len(pages)
        x0 = W / 2 - (n - 1) * 6
        for i, p in enumerate(pages):
            on = p == cur
            c.dot(x0 + i * 12, 17, 3 if on else 2.2, t["accent"] if on else t["dim"], glow=on)
    now = ctx["now"]
    hm = now.strftime("%H:%M") if ctx["h24"] else now.strftime("%I:%M").lstrip("0")
    c.text(W - 12, 17, hm, "monob", 17, t["text"], "rm")
    # status icons left of the clock: VPN dot
    vpn = ctx["data"].get("vpn_adapter")
    online = ctx["online"].get("online")
    wclock = c.tlen(hm, "monob", 17)
    x = W - 12 - wclock - 10
    if vpn:
        c.text(x, 17, "VPN", "bold", 9, t["ok"], "rm")
        x -= c.tlen("VPN", "bold", 9) + 8
    if online is False:
        c.text(x, 17, "OFFLINE", "bold", 9, t["bad"], "rm")


def gauge_card(c, x, y, w, h, label, pct, color, sub_left, sub_right, name=None, r=None):
    t = c.t
    c.card(x, y, w, h, accent=color, title=label, title_color=color)
    if name:
        c.text(x + w - 12, y + 12, c.fit(name, "medium", 9.5, w - 60), "medium", 9.5, t["sub"], "rm")
    r = r or min(w, h - 40) * 0.30
    cx, cy = x + w / 2, y + 26 + r + 4
    col = load_color(t, pct, color)
    c.ring(cx, cy, r, max(7, r * 0.2), pct, col, glow=True)
    big = max(20, r * 0.80)
    inner = 2 * (r - max(7, r * 0.2)) - 6
    c.value_unit(cx + 2, cy + big * 0.36, fmt_pct(pct), "%", t["text"], big, anchor="ms", unit_size=big * 0.40,
                 max_w=inner)
    yb = y + h - 14
    if sub_left:
        v, u, col_l = sub_left
        c.value_unit(x + 10, yb, v, u, col_l, 18, anchor="ls", unit_size=9.5, max_w=w / 2 - 12)
    if sub_right:
        v, u, col_r = sub_right
        c.value_unit(x + w - 10, yb, v, u, col_r, 18, anchor="rs", unit_size=9.5, max_w=w / 2 - 12)


def history_card(c, x, y, w, h, title, hist, series, ctx, vmax=100, right=None, legend=None):
    t = c.t
    c.card(x, y, w, h, accent=series[0][1], title=title, title_color=t["sub"], right=right)
    if legend:
        lx = x + 12 + c.tlen(title.upper(), "bold", 10.5) + 16 + len(title) * 1.2
        for name, col in legend:
            c.dot(lx, y + 12, 3, col)
            lx += 7
            lx += c.text(lx, y + 12, name, "medium", 10, t["text"], "lm") + 12
    c.chart(x + 10, y + 26, w - 20, h - 36, [(hist.get(k, []), col, filled) for k, col, filled in series], vmax=vmax)


def net_mini(c, x, y, w, h, d, ctx):
    t = c.t
    bits = ctx["bits"]
    c.card(x, y, w, h, accent=t["down"], title="Network", title_color=t["sub"])
    lat = [l for l in ctx["online"].get("latency") or [] if l.get("ms") is not None]
    ms = min((l["ms"] for l in lat), default=None)
    vpn = d.get("vpn_adapter")
    if w > 220:  # wide and short (portrait): down | up | ping in one row
        yb = y + h - 16
        col_w = (w - 24) / 3
        for i, (key, colr, up) in enumerate((("net_down", t["down"], False), ("net_up", t["up"], True))):
            v, u = fmt_speed(d.get(key), bits)
            xx = x + 12 + i * col_w
            c.arrow(xx + 6, yb - 8, 10, colr, up=up)
            c.value_unit(xx + 16, yb, v, u, t["text"], 24, anchor="ls", unit_size=10, max_w=col_w - 20)
        c.text(x + w - 12, y + 12, "PING", "bold", 9, t["sub"], "rm")
        c.value_unit(x + w - 12, yb, f"{ms:.0f}" if ms is not None else "--", "ms", ms_color(t, ms), 24,
                     anchor="rs", unit_size=10, max_w=col_w - 8)
        c.dot(x + w - 58, y + 12, 3, t["ok"] if vpn else t["dim"], glow=bool(vpn))
        return
    v, u = fmt_speed(d.get("net_down"), bits)
    c.arrow(x + 18, y + 41, 10, t["down"], up=False)
    c.value_unit(x + 30, y + 49, v, u, t["text"], 24, anchor="ls", unit_size=11, max_w=min(w - 40, 150))
    v, u = fmt_speed(d.get("net_up"), bits)
    c.arrow(x + 18, y + 70, 10, t["up"], up=True)
    c.value_unit(x + 30, y + 78, v, u, t["text"], 24, anchor="ls", unit_size=11, max_w=min(w - 40, 150))
    if h > 96:
        yy = y + h - 16
        c.text(x + 12, yy, "PING", "bold", 9, t["sub"], "lm")
        c.value_unit(x + 44, yy + 6, f"{ms:.0f}" if ms is not None else "--", "ms", ms_color(t, ms), 16,
                     anchor="ls", unit_size=9, max_w=w - 100)
        c.dot(x + w - 44, yy, 3.5, t["ok"] if vpn else t["dim"], glow=bool(vpn))
        c.text(x + w - 12, yy, "VPN", "bold", 9, t["ok"] if vpn else t["dim"], "rm")


# ---------------------------------------------------------------- "dash" layout (Pulse theme)
def _icon(c, kind, x, y, s, color):
    """Small line icon in a tinted rounded square, centred on x, y (s = box size)."""
    t = c.t
    col = draw.hex2rgb(color)
    S = draw.S
    c.d.rounded_rectangle(c._r((x - s / 2, y - s / 2, x + s / 2, y + s / 2)), 5 * S,
                          fill=draw.mix(t["card"], color, 0.16), outline=draw.mix(t["card"], color, 0.55), width=S)
    g = s * 0.30  # glyph half size
    lw = max(1, int(1.5 * S))
    X, Y = x * S, y * S
    G = g * S
    if kind == "ram":
        c.d.rectangle((X - G, Y - G * 0.55, X + G, Y + G * 0.35), outline=col, width=lw)
        for i in range(4):
            px = X - G * 0.7 + i * G * 0.47
            c.d.line((px, Y + G * 0.35, px, Y + G * 0.8), fill=col, width=lw)
    elif kind == "vram":
        c.d.rectangle((X - G, Y - G * 0.75, X + G, Y + G * 0.75), outline=col, width=lw)
        c.d.line((X - G * 0.6, Y + G * 0.3, X - G * 0.2, Y - G * 0.2, X + G * 0.15, Y + G * 0.15, X + G * 0.6,
                  Y - G * 0.35), fill=col, width=lw)
    elif kind == "disk":
        c.d.rounded_rectangle((X - G * 0.75, Y - G, X + G * 0.75, Y + G), 2 * S, outline=col, width=lw)
        c.d.line((X - G * 0.4, Y - G * 0.45, X + G * 0.4, Y - G * 0.45), fill=col, width=lw)
        r = G * 0.18
        c.d.ellipse((X - r, Y + G * 0.45 - r, X + r, Y + G * 0.45 + r), fill=col)
    elif kind == "temp":
        c.d.rounded_rectangle((X - G * 0.25, Y - G, X + G * 0.25, Y + G * 0.35), G * 0.25, outline=col, width=lw)
        r = G * 0.45
        c.d.ellipse((X - r, Y + G * 0.55 - r, X + r, Y + G * 0.55 + r), fill=col)
    elif kind == "fan":
        # 4 blades: small ellipses around the hub, each pushed out along its angle
        for a in (20, 110, 200, 290):
            ra = math.radians(a)
            bx, by = X + math.cos(ra) * G * 0.5, Y + math.sin(ra) * G * 0.5
            rb = G * 0.42
            c.d.ellipse((bx - rb, by - rb, bx + rb, by + rb), fill=col)
        r = G * 0.2
        c.d.ellipse((X - r, Y - r, X + r, Y + r), fill=draw.mix(t["card"], color, 0.16))
    elif kind == "ping":
        for i, hh in enumerate((0.4, 0.7, 1.0)):
            px = X - G * 0.7 + i * G * 0.7
            c.d.line((px, Y + G * 0.8, px, Y + G * 0.8 - G * 1.6 * hh), fill=col, width=lw + S)
    elif kind in ("down", "up"):
        top, bot = Y - G, Y + G * 0.45
        tip, tail = (bot, top) if kind == "down" else (top, bot)
        c.d.line((X, tail, X, tip), fill=col, width=lw)
        k = G * 0.55 * (1 if kind == "down" else -1)
        c.d.line((X - G * 0.55, tip - k, X, tip, X + G * 0.55, tip - k), fill=col, width=lw)
        c.d.line((X - G * 0.8, Y + G, X + G * 0.8, Y + G), fill=col, width=lw)


def _label(c, x, y, full, short, role, size, color, max_w, anchor="lm"):
    s = full if c.tlen(full, role, size) <= max_w or not short else short
    return c.text_fit(x, y, s, role, size, color, anchor, max_w=max_w)


def _spark(c, x, y, w, h, vals, color, vmax=None, n=48):
    vals = [v for v in (vals or [])[-n:] if isnum(v)]
    if len(vals) < 2:
        return
    top = vmax or max(max(vals) * 1.15, 1)
    c.chart(x, y, w, h, [(vals, color, True)], vmax=top, grid=False)


def _dash_gauge(c, x, y, w, h, label, name, pct, color, sub, hist_vals):
    t = c.t
    c.text(x + 12, y + 14, label, "bold", 14, t["text"], "lm")
    if name:
        c.text(x + w - 10, y + 14, c.fit(name, "medium", 9, w - 50), "medium", 9, t["sub"], "rm")
    spark_h = h * 0.24
    r = min(w * 0.30, (h - spark_h - 34) / 2 + 2)
    cx, cy = x + w / 2, y + 28 + r
    col = load_color(t, pct, color)
    c.arc_gauge(cx, cy, r, max(6, r * 0.16), pct, col)
    inner = 2 * r * 0.72
    big = r * 0.56
    c.value_unit(cx + 1, cy + big * 0.30, fmt_pct(pct), "%", t["text"], big, anchor="ms", unit_size=big * 0.48,
                 max_w=inner, role="bold")
    if sub:
        c.text_fit(cx, cy + r * 0.5, sub, "medium", 10, t["sub"], "mm", max_w=2 * r * 0.52)
    _spark(c, x + 10, y + h - spark_h - 8, w - 20, spark_h, hist_vals, color, vmax=100)


def _dash_row(c, x, y, w, kind, label, pct, sub, color):
    """Icon, label + small sub line, percent on the right (one row of the RAM / VRAM / disk list)."""
    t = c.t
    _icon(c, kind, x + 13, y, 24, color)
    vw = c.value_unit(x + w, y - 1, fmt_pct(pct), "%", t["text"], 15, anchor="rs", unit_size=10, role="bold",
                      max_w=52)
    c.text(x + 32, y - 7, c.fit(label, "medium", 12, w - 40 - vw), "medium", 12, t["text"], "lm")
    if sub:
        c.text(x + 32, y + 9, c.fit(sub, "regular", 10, w - 36), "regular", 10, t["sub"], "lm")


def _dash_rows(d, t):
    def gb(v):
        return f"{v / 1024 ** 3:.1f}" if v < 100 * 1024 ** 3 else f"{v / 1024 ** 3:.0f}"
    rows = []
    if isnum(d.get("ram_total")):
        rows.append(("ram", "RAM", d.get("ram_pct"), f"{gb(d.get('ram_used', 0))} / {d['ram_total'] / 1024 ** 3:.0f} GB",
                     t["icon"]))
    used, total = d.get("gpu_mem_used"), d.get("gpu_mem_total")
    if isnum(used) and isnum(total) and total:
        rows.append(("vram", "VRAM", used / total * 100, f"{used / 1024:.1f} / {total / 1024:.0f} GB", t["gpu"]))
    for dk in d.get("disks") or []:
        if len(rows) >= 3:
            break
        u, uu = fmt_bytes(dk["used"], 0)
        tot, tu = fmt_bytes(dk["total"], 0)
        rows.append(("disk", f"Disk {dk['label']}", dk["pct"], f"{u} {uu} / {tot} {tu}" if uu != tu else
                     f"{u} / {tot} {tu}", t["disk"]))
    return rows[:3]


def _dash_stats(d, ctx, t):
    """CPU temp, GPU temp, then GPU fan (RPM or %) or the best ping."""
    out = [("temp", "CPU Temp", "CPU", fmt_temp(d.get("cpu_temp")).replace("°", "") , "°C", temp_color(t, d.get("cpu_temp"))),
           ("temp", "GPU Temp", "GPU", fmt_temp(d.get("gpu_temp")).replace("°", ""), "°C",
            temp_color(t, d.get("gpu_temp"), 75, 87))]
    rpm, pct = d.get("gpu_fan"), d.get("gpu_fan_pct")
    if isnum(rpm):
        out.append(("fan", "GPU Fan", "Fan", f"{rpm:.0f}", "RPM", t["text"]))
    elif isnum(pct):
        out.append(("fan", "GPU Fan", "Fan", f"{pct:.0f}", "%", t["text"]))
    else:
        lat = [l["ms"] for l in ctx["online"].get("latency") or [] if l.get("ms") is not None]
        ms = min(lat) if lat else None
        out.append(("ping", "Ping", None, f"{ms:.0f}" if ms is not None else "--", "ms", ms_color(t, ms)))
    return out


def _dash_net(c, x, y, w, h, kind, label, value, hist_vals, color, bits):
    t = c.t
    _icon(c, kind, x + 22, y + 22, 24, color)
    c.text(x + 40, y + 9 + 5 * draw.TEXT_SCALE, label, "medium", 11, t["sub"], "lm")
    v, u = fmt_speed(value, bits)
    vb = y + 17 + 20 * draw.TEXT_SCALE
    c.value_unit(x + 40, vb, v, u, t["text"], 17, anchor="ls", unit_size=10, max_w=w - 48, role="bold")
    sh = y + h - vb - 16
    if sh > 10:
        _spark(c, x + 10, y + h - sh - 8, w - 20, sh, hist_vals, color)


def page_dash(c: Canvas, ctx):
    d, hist, t = ctx["data"], ctx["hist"], c.t
    land = c.w > c.h
    bits = ctx["bits"]
    header(c, PAGE_TITLES["overview"], ctx)
    x0, y0, x1, y1 = 8, 34, c.w - 8, c.h - 8
    c.card(x0, y0, x1 - x0, y1 - y0)
    cpu_sub = f"{fmt_clock_ghz(d.get('cpu_clock'))} GHz"
    has_gpu = isnum(d.get("gpu_load"))
    gpu_sub = f"{fmt_temp(d.get('gpu_temp')).rstrip('°')}°C" if has_gpu else "not detected"
    rows = _dash_rows(d, t)
    stats = _dash_stats(d, ctx, t)
    div = t["border"]

    if land:
        cw = 150
        xa, xb, xc = x0, x0 + cw, x0 + 2 * cw
        wc = x1 - xc
        ys = 196  # split between the top (gauges) and bottom (network) halves
        _dash_gauge(c, xa, y0, cw, ys - y0, "CPU", None, d.get("cpu_load"), t["cpu"], cpu_sub, hist.get("cpu_load"))
        _dash_gauge(c, xb, y0, cw, ys - y0, "GPU", None, d.get("gpu_load"), t["gpu"], gpu_sub, hist.get("gpu_load"))
        step = (ys - y0 - 16) / 3
        for i, (kind, label, pct, sub, col) in enumerate(rows):
            _dash_row(c, xc + 10, y0 + 8 + step * (i + 0.5), wc - 22, kind, label, pct, sub, col)
        for xx in (xb, xc):
            c.line(xx, y0 + 12, xx, ys - 6, div)
            c.line(xx, ys + 6, xx, y1 - 12, div)
        c.line(x0 + 12, ys, x1 - 12, ys, div)
        bh = y1 - ys
        _dash_net(c, xa, ys, cw, bh, "down", "Download", d.get("net_down"), hist.get("net_down"), t["down"], bits)
        _dash_net(c, xb, ys, cw, bh, "up", "Upload", d.get("net_up"), hist.get("net_up"), t["up"], bits)
        step = (bh - 12) / 3
        for i, (kind, label, short, v, u, col) in enumerate(stats):
            yy = ys + 6 + step * (i + 0.5)
            _icon(c, kind, xc + 22, yy, 22, t["temp"] if kind == "temp" else t["icon"])
            vw = c.value_unit(x1 - 12, yy + 6, v, u, col, 16, anchor="rs", unit_size=10, role="bold", max_w=70)
            _label(c, xc + 40, yy, label, short, "medium", 11.5, t["text"], wc - 60 - vw)
    else:
        W = x1 - x0
        cw = W / 2
        ya = y0 + 160          # gauges
        yb = ya + 112          # RAM / VRAM / disk rows
        yc = yb + 96           # download / upload
        _dash_gauge(c, x0, y0, cw, ya - y0, "CPU", None, d.get("cpu_load"), t["cpu"], cpu_sub, hist.get("cpu_load"))
        _dash_gauge(c, x0 + cw, y0, cw, ya - y0, "GPU", None, d.get("gpu_load"), t["gpu"], gpu_sub,
                    hist.get("gpu_load"))
        c.line(x0 + cw, y0 + 12, x0 + cw, ya - 6, div)
        c.line(x0 + 12, ya, x1 - 12, ya, div)
        step = (yb - ya - 8) / 3
        for i, (kind, label, pct, sub, col) in enumerate(rows):
            _dash_row(c, x0 + 10, ya + 4 + step * (i + 0.5), W - 22, kind, label, pct, sub, col)
        c.line(x0 + 12, yb, x1 - 12, yb, div)
        _dash_net(c, x0, yb, cw, yc - yb, "down", "Download", d.get("net_down"), hist.get("net_down"), t["down"],
                  bits)
        _dash_net(c, x0 + cw, yb, cw, yc - yb, "up", "Upload", d.get("net_up"), hist.get("net_up"), t["up"], bits)
        c.line(x0 + cw, yb + 6, x0 + cw, yc - 6, div)
        c.line(x0 + 12, yc, x1 - 12, yc, div)
        sw = W / 3
        for i, (kind, label, short, v, u, col) in enumerate(stats):
            xx = x0 + sw * i
            cx = xx + sw / 2
            _icon(c, kind, xx + 20, yc + 22, 22, t["temp"] if kind == "temp" else t["icon"])
            _label(c, xx + 36, yc + 22, label, short, "medium", 10.5, t["sub"], sw - 42)
            c.value_unit(cx, y1 - 14, v, u, col, 20, anchor="ms", unit_size=10, role="bold", max_w=sw - 14)
            if i:
                c.line(xx, yc + 6, xx, y1 - 10, div)


# ---------------------------------------------------------------- pages
def page_overview(c: Canvas, ctx):
    d, hist, t = ctx["data"], ctx["hist"], c.t
    if t.get("layout") == "dash":
        return page_dash(c, ctx)
    land = c.w > c.h
    header(c, PAGE_TITLES["overview"], ctx)
    cpu_l = ("%s" % fmt_temp(d.get("cpu_temp")).rstrip("°"), "°C", temp_color(t, d.get("cpu_temp")))
    cpu_r = (fmt_clock_ghz(d.get("cpu_clock")), "GHz", t["text"])
    gpu_l = ("%s" % fmt_temp(d.get("gpu_temp")).rstrip("°"), "°C", temp_color(t, d.get("gpu_temp"), 75, 87))
    if isnum(d.get("gpu_mem_used")) and isnum(d.get("gpu_mem_total")) and d.get("gpu_mem_total"):
        gpu_r = (f"{d['gpu_mem_used'] / 1024:.1f}", f"/{d['gpu_mem_total'] / 1024:.0f}G", t["text"])
    else:
        gpu_r = (fmt_clock_ghz(d.get("gpu_clock")), "GHz", t["text"])
    ram_used = fmt_bytes(d.get("ram_used"))
    ram_tot = d.get("ram_total", 0) / 1024 ** 3 if isnum(d.get("ram_total")) else 0
    ram_l = (ram_used[0], ram_used[1], t["text"])
    ram_r = (f"{ram_tot:.0f}", "GB", t["sub"])
    has_gpu = "gpu_load" in d and isnum(d.get("gpu_load"))

    if land:
        y, h = 34, 140
        w = (c.w - 16 - 16) / 3
        gauge_card(c, 8, y, w, h, "CPU", d.get("cpu_load"), t["cpu"], cpu_l, cpu_r, d.get("cpu_name"), r=36)
        if has_gpu:
            gauge_card(c, 16 + w, y, w, h, "GPU", d.get("gpu_load"), t["gpu"], gpu_l, gpu_r, d.get("gpu_short"),
                       r=36)
        else:
            gauge_card(c, 16 + w, y, w, h, "GPU", None, t["gpu"], None, None, "not detected", r=36)
        gauge_card(c, 24 + 2 * w, y, w, h, "RAM", d.get("ram_pct"), t["ram"], ram_l, ram_r, None, r=36)
        y2 = y + h + 8
        h2 = c.h - y2 - 8
        series = [("cpu_load", t["cpu"], True)] + ([("gpu_load", t["gpu"], False)] if has_gpu else [])
        legend = [("CPU", t["cpu"])] + ([("GPU", t["gpu"])] if has_gpu else [])
        pw = d.get("cpu_power")
        right = f"{pw:.0f} W" if isnum(pw) else None
        history_card(c, 8, y2, 300, h2, "Load", hist, series, ctx, legend=legend, right=right)
        net_mini(c, 316, y2, c.w - 316 - 8, h2, d, ctx)
    else:
        y, h = 34, 150
        w = (c.w - 24) / 2
        gauge_card(c, 8, y, w, h, "CPU", d.get("cpu_load"), t["cpu"], cpu_l, cpu_r, d.get("cpu_name"), r=40)
        if has_gpu:
            gauge_card(c, 16 + w, y, w, h, "GPU", d.get("gpu_load"), t["gpu"], gpu_l, gpu_r, d.get("gpu_short"),
                       r=40)
        else:
            gauge_card(c, 16 + w, y, w, h, "GPU", None, t["gpu"], None, None, "not detected", r=40)
        # RAM bar card
        y2 = y + h + 8
        c.card(8, y2, c.w - 16, 64, accent=t["ram"], title="RAM", title_color=t["ram"])
        c.value_unit(c.w - 20, y2 + 19, fmt_pct(d.get("ram_pct")), "%", t["text"], 20, anchor="rs")
        c.bar(20, y2 + 30, c.w - 40, 8, d.get("ram_pct"), t["ram"], glow=True)
        c.text(20, y2 + 52, f"{ram_used[0]} {ram_used[1]} used", "medium", 10.5, t["sub"], "lm")
        c.text(c.w - 20, y2 + 52, f"{ram_tot:.0f} GB total", "medium", 10.5, t["sub"], "rm")
        y3 = y2 + 72
        series = [("cpu_load", t["cpu"], True)] + ([("gpu_load", t["gpu"], False)] if has_gpu else [])
        legend = [("CPU", t["cpu"])] + ([("GPU", t["gpu"])] if has_gpu else [])
        pw = d.get("cpu_power")
        history_card(c, 8, y3, c.w - 16, 120, "Load", hist, series, ctx, legend=legend,
                     right=f"{pw:.0f} W" if isnum(pw) else None)
        y4 = y3 + 128
        net_mini(c, 8, y4, c.w - 16, c.h - y4 - 8, d, ctx)


def page_network(c: Canvas, ctx):
    d, hist, t, on = ctx["data"], ctx["hist"], c.t, ctx["online"]
    land = c.w > c.h
    bits = ctx["bits"]
    header(c, PAGE_TITLES["network"], ctx)
    W = c.w
    # main chart card
    ch = 164 if land else 180
    c.card(8, 34, W - 16, ch, accent=t["down"])
    v, u = fmt_speed(d.get("net_down"), bits)
    c.arrow(22, 54, 10, t["down"], up=False)
    c.label(32, 54, "Download", t["down"])
    vb = 62 + 28 * draw.TEXT_SCALE
    c.value_unit(22, vb, v, u, t["text"], 34, anchor="ls", unit_size=13, glow=True, max_w=W / 2 - 34)
    v, u = fmt_speed(d.get("net_up"), bits)
    xu = W / 2 + (10 if land else 0)
    c.arrow(xu, 54, 10, t["up"], up=True)
    c.label(xu + 10, 54, "Upload", t["up"])
    c.value_unit(xu, vb, v, u, t["text"], 34, anchor="ls", unit_size=13, glow=True, max_w=W - xu - 18)
    downs, ups = hist.get("net_down", []), hist.get("net_up", [])
    peak = max(max(downs or [0]), max(ups or [0]), 1024)
    pv, pu = fmt_speed(peak, bits)
    c.text(W - 20, vb + 14, f"peak {pv} {pu}", "medium", 9, t["dim"], "rm")
    c.chart(18, vb + 20, W - 36, ch - (vb + 20 - 34) - 10, [(downs, t["down"], True), (ups, t["up"], False)], vmax=peak * 1.1)

    y = 34 + ch + 8
    vpn = d.get("vpn_adapter")
    cc, ip = on.get("country"), on.get("ip")
    lat = on.get("latency") or []
    srv = on.get("server")
    if land:
        h = c.h - y - 8
        w1, w2 = 148, 150
        w3 = W - 16 - w1 - w2 - 16
        # VPN card
        col = t["ok"] if vpn else t["dim"]
        c.card(8, y, w1, h, accent=col, title="VPN", title_color=t["sub"])
        c.dot(22, y + 40, 5, col, glow=bool(vpn))
        c.text(34, y + 40, "ON" if vpn else "OFF", "black", 20, col, "lm", glow=bool(vpn))
        c.text(20, y + 62, c.fit(vpn or "no tunnel adapter", "medium", 9.5, w1 - 24), "medium", 9.5, t["sub"], "lm")
        c.text(20, y + h - 16, f"{cc or '--'}", "monob", 15, t["text"], "lm")
        c.text(20 + c.tlen(f"{cc or '--'}", "monob", 15) + 6, y + h - 16, c.fit(ip or "no IP", "mono", 9.5, w1 - 60),
               "mono", 9.5, t["sub"], "lm")
        # latency card
        x2 = 8 + w1 + 8
        c.card(x2, y, w2, h, accent=t["accent"], title="Latency", title_color=t["sub"])
        rows = list(lat) + ([srv] if srv else [])
        for i, r in enumerate(rows[:3]):
            yy = y + 37 + i * 23
            c.dot(x2 + 15, yy, 3.5, ms_color(t, r["ms"]))
            c.text(x2 + 24, yy, c.fit(r["name"], "medium", 11, 58), "medium", 11, t["text"], "lm")
            c.value_unit(x2 + w2 - 10, yy + 6, f"{r['ms']:.0f}" if r["ms"] is not None else "--", "ms",
                         ms_color(t, r["ms"]), 18, anchor="rs", unit_size=9, max_w=w2 - 90)
        if not rows:
            c.text(x2 + 12, y + 40, "no targets", "medium", 10, t["dim"], "lm")
        # totals
        x3 = x2 + w2 + 8
        c.card(x3, y, w3, h, accent=t["up"], title="Since boot", title_color=t["sub"])
        v, u = fmt_bytes(d.get("net_total_down"))
        c.arrow(x3 + 17, y + 39, 9, t["down"], up=False)
        c.value_unit(x3 + 28, y + 46, v, u, t["text"], 20, anchor="ls", unit_size=10, max_w=w3 - 36)
        v, u = fmt_bytes(d.get("net_total_up"))
        c.arrow(x3 + 17, y + 65, 9, t["up"], up=True)
        c.value_unit(x3 + 28, y + 72, v, u, t["text"], 20, anchor="ls", unit_size=10, max_w=w3 - 36)
        c.text(x3 + 12, y + h - 16, c.fit(d.get("nic") or "--", "medium", 9, w3 - 24), "medium", 9, t["sub"], "lm")
    else:
        # VPN + IP row
        col = t["ok"] if vpn else t["dim"]
        c.card(8, y, W - 16, 70, accent=col, title="VPN", title_color=t["sub"])
        c.dot(22, y + 44, 5, col, glow=bool(vpn))
        c.text(34, y + 44, "ON" if vpn else "OFF", "black", 20, col, "lm", glow=bool(vpn))
        c.text(W - 20, y + 12, c.fit(vpn or "no tunnel adapter", "medium", 9.5, 160), "medium", 9.5, t["sub"], "rm")
        c.text(W - 20, y + 36, cc or "--", "monob", 18, t["text"], "rm")
        c.text(W - 20, y + 55, ip or "no IP", "mono", 10, t["sub"], "rm")
        y += 78
        rows = list(lat) + ([srv] if srv else [])
        h = 32 + 23 * max(1, min(3, len(rows)))
        c.card(8, y, W - 16, h, accent=t["accent"], title="Latency", title_color=t["sub"])
        for i, r in enumerate(rows[:3]):
            yy = y + 35 + i * 23
            c.dot(22, yy, 3.5, ms_color(t, r["ms"]))
            c.text(32, yy, c.fit(r["name"], "medium", 12, 150), "medium", 12, t["text"], "lm")
            c.value_unit(W - 20, yy + 6, f"{r['ms']:.0f}" if r["ms"] is not None else "--", "ms",
                         ms_color(t, r["ms"]), 18, anchor="rs", unit_size=9, max_w=110)
        y += h + 8
        hh = c.h - y - 8
        c.card(8, y, W - 16, hh, accent=t["up"], title="Since boot", title_color=t["sub"])
        c.text(W - 20, y + 12, c.fit(d.get("nic") or "--", "medium", 9, 150), "medium", 9, t["sub"], "rm")
        v, u = fmt_bytes(d.get("net_total_down"))
        c.arrow(22, y + hh - 18, 8, t["down"], up=False)
        c.value_unit(32, y + hh - 11, v, u, t["text"], 20, anchor="ls", unit_size=10, max_w=W / 2 - 40)
        v, u = fmt_bytes(d.get("net_total_up"))
        c.arrow(W / 2 + 6, y + hh - 18, 8, t["up"], up=True)
        c.value_unit(W / 2 + 16, y + hh - 11, v, u, t["text"], 20, anchor="ls", unit_size=10, max_w=W / 2 - 36)


def _drives(c, x, y, w, h, d):
    t = c.t
    c.card(x, y, w, h, accent=t["disk"], title="Drives", title_color=t["sub"])
    disks = d.get("disks") or []
    temps = d.get("disk_temps") or {}
    n = max(1, len(disks))
    avail = h - 34 - 30
    step = min(60, avail / n)
    for i, dk in enumerate(disks):
        yy = y + 34 + i * step
        col = t["disk"] if dk["pct"] < 80 else t["warn"] if dk["pct"] < 90 else t["bad"]
        big = step >= 50
        c.text(x + 12, yy + 6, dk["label"], "monob", 15 if big else 13, t["text"], "lm")
        c.value_unit(x + 14 + c.tlen(dk["label"], "monob", 15 if big else 13) + 6, yy + 10, f"{dk['pct']:.0f}",
                     "%", col, 11, anchor="ls", unit_size=8)
        used, uu = fmt_bytes(dk["used"], 0)
        tot, tu = fmt_bytes(dk["total"], 0)
        c.text(x + w - 12, yy + 6, f"{used} {uu} / {tot} {tu}", "medium", 11, t["sub"], "rm")
        c.bar(x + 12, yy + (19 if big else 16), w - 24, 8 if big else 6, dk["pct"], col)
    # IO line
    yy = y + h - 16
    v, u = fmt_speed(d.get("disk_read"))
    c.text(x + 12, yy, "R", "bold", 10, t["sub"], "lm")
    c.value_unit(x + 24, yy + 6, v, u, t["text"], 16, anchor="ls", unit_size=9, max_w=w / 2 - 34)
    v, u = fmt_speed(d.get("disk_write"))
    c.text(x + w / 2, yy, "W", "bold", 10, t["sub"], "lm")
    c.value_unit(x + w / 2 + 13, yy + 6, v, u, t["text"], 16, anchor="ls", unit_size=9, max_w=w / 2 - 24)


def _procs(c, x, y, w, h, d, n=5):
    t = c.t
    c.card(x, y, w, h, accent=t["cpu"], title="Top apps", title_color=t["sub"], right="CPU")
    procs = (d.get("procs") or {}).get("cpu", [])[:n]
    step = min(22, (h - 34) / max(1, n))
    for i, (name, cpu, mem) in enumerate(procs):
        yy = y + 36 + i * step
        c.text(x + 12, yy, c.fit(name, "medium", 12, w - 84), "medium", 12, t["text"], "lm")
        c.value_unit(x + w - 12, yy + 6, f"{cpu:.1f}", "%", t["cpu"] if cpu < 50 else t["warn"], 16, anchor="rs",
                     unit_size=9, max_w=68)


def page_storage(c: Canvas, ctx):
    d, t = ctx["data"], c.t
    land = c.w > c.h
    header(c, PAGE_TITLES["storage"], ctx)
    if land:
        _drives(c, 8, 34, 262, c.h - 42, d)
        x = 278
        w = c.w - x - 8
        _procs(c, x, 34, w, 166, d)
        y = 208
        c.card(x, y, w, c.h - y - 8, accent=t["ram"], title="Uptime", title_color=t["sub"])
        c.text_fit(x + 12, y + 46, fmt_uptime(d.get("boot", time.time())), "monob", 22, t["text"], "lm", max_w=w - 24)
        top_mem = (d.get("procs") or {}).get("mem", [])[:1]
        if top_mem:
            name, _, mem = top_mem[0]
            v, u = fmt_bytes(mem)
            wv = c.value_unit(x + w - 12, y + 85, v, u, t["ram"], 15, anchor="rs", unit_size=9, max_w=64)
            c.text(x + 12, y + 80, c.fit(f"RAM top · {name}", "medium", 10, w - 30 - wv), "medium", 10, t["sub"], "lm")
    else:
        nd = len(d.get("disks") or [])
        hd = 34 + 30 + max(1, nd) * 40 + 4
        _drives(c, 8, 34, c.w - 16, hd, d)
        y = 34 + hd + 8
        hp = c.h - y - 8 - 66 - 8
        _procs(c, 8, y, c.w - 16, hp, d, n=max(2, min(5, int((hp - 34) // 22))))
        y += hp + 8
        c.card(8, y, c.w - 16, 66, accent=t["ram"], title="Uptime", title_color=t["sub"])
        c.text_fit(20, y + 44, fmt_uptime(d.get("boot", time.time())), "monob", 24, t["text"], "lm", max_w=c.w - 40)


def page_clock(c: Canvas, ctx):
    d, t, on = ctx["data"], c.t, ctx["online"]
    now = ctx["now"]
    land = c.w > c.h
    # minimal header: only page dots
    pages, cur = ctx["pages"], ctx["page"]
    if len(pages) > 1:
        x0 = c.w / 2 - (len(pages) - 1) * 6
        for i, p in enumerate(pages):
            on_ = p == cur
            c.dot(x0 + i * 12, 12, 3 if on_ else 2.2, t["accent"] if on_ else t["dim"], glow=on_)
    hm = now.strftime("%H:%M") if ctx["h24"] else now.strftime("%I:%M").lstrip("0")
    ampm = "" if ctx["h24"] else now.strftime("%p")
    sec = now.strftime("%S")
    wx = on.get("weather")

    def weather_block(x, y, w, h):
        c.card(x, y, w, h, accent=t["sun"])
        if not wx or "temp" not in wx:
            msg = (wx or {}).get("error") or "Loading weather…"
            c.text(x + w / 2, y + h / 2, c.fit(msg, "medium", 10, w - 20), "medium", 10, t["sub"], "mm")
            return
        c.label(x + 12, y + 14, c.fit(wx["city"], "bold", 10.5, w - 24), t["sub"])
        c.weather_icon(x + 40, y + 58, 52, wx["icon"], wx.get("is_day", True))
        c.value_unit(x + w - 12, y + 70, f"{wx['temp']:.0f}", wx["unit"], t["text"], 34, anchor="rs",
                     role="bold", unit_size=14, glow=True)
        c.text(x + 12, y + 98, c.fit(wx["text"], "medium", 12, w - 24), "medium", 12, t["text"], "lm")
        c.text(x + 12, y + 116, f"Feels {wx['feels']:.0f}°  ·  {wx['humidity']:.0f}%", "medium", 10, t["sub"], "lm")
        c.text(x + 12, y + 132, f"Wind {wx['wind']:.0f} {wx['wind_unit']}", "medium", 10, t["sub"], "lm")
        days = wx.get("days") or []
        if h > 190 and days:
            yy = y + 152
            c.line(x + 12, yy, x + w - 12, yy, t["border"])
            for i, dd in enumerate(days[:3]):
                ry = yy + 18 + i * 24
                if ry > y + h - 10:
                    break
                name = "Today" if i == 0 else dt.date.fromisoformat(dd["date"]).strftime("%a")
                c.text(x + 12, ry, name, "medium", 10.5, t["text"], "lm")
                c.weather_icon(x + 22 + c.tlen("Today", "medium", 10.5) + 4, ry, 18, dd["icon"], True)
                c.text(x + w - 12, ry, f"{dd['max']:.0f}° / {dd['min']:.0f}°", "mono", 10, t["sub"], "rm")

    def mini_stats(x, y, w):
        items = [("CPU", fmt_pct(d.get("cpu_load")) + "%", t["cpu"]),
                 ("GPU", fmt_pct(d.get("gpu_load")) + "%", t["gpu"]),
                 ("RAM", fmt_pct(d.get("ram_pct")) + "%", t["ram"])]
        v, u = fmt_speed(d.get("net_down"), ctx["bits"])
        items.append(("NET", f"{v}{u.replace('/s', '')}", t["down"]))
        cw = (w - 6 * (len(items) - 1)) / len(items)
        for i, (lab, val, col) in enumerate(items):
            xx = x + i * (cw + 6)
            c.card(xx, y, cw, 44, accent=None)
            c.text(xx + cw / 2, y + 14, lab, "bold", 8.5, col, "mm")
            c.text_fit(xx + cw / 2, y + 30, val, "monob", 16, t["text"], "mm", max_w=cw - 8)

    if land:
        lw = 300
        cx = 8 + lw / 2
        size = 92 / draw.TEXT_SCALE  # the big clock is already as large as it can be
        tw = c.tlen(hm, "monox", size)
        sw = c.tlen(sec, "monob", 22)
        x0 = cx - (tw + 6 + sw) / 2
        c.text(x0, 132, hm, "monox", size, t["clock"], "ls", glow=True)
        c.text(x0 + tw + 6, 132, sec, "monob", 22, t["accent"], "ls", glow=True)
        if ampm:
            c.text(x0 + tw + 6, 132 - 26, ampm, "bold", 12, t["sub"], "ls")
        c.text(cx, 160, now.strftime("%A"), "bold", 17, t["text"], "mm")
        df = ctx.get("date_fmt", "text")
        c.text_fit(cx, 184, gregorian_string(now, df), "medium", 14, t["sub"], "mm", max_w=lw - 16)
        c.text_fit(cx, 208, jalali_string(now, df), "bold", 14, t["accent"], "mm", max_w=lw - 16, glow=True)
        mini_stats(12, c.h - 52, lw - 8)
        weather_block(316, 24, c.w - 324, c.h - 32)
    else:
        size = 84 / draw.TEXT_SCALE
        tw = c.tlen(hm, "monox", size)
        sw = c.tlen(sec, "monob", 20)
        x0 = c.w / 2 - (tw + 5 + sw) / 2
        c.text(x0, 104, hm, "monox", size, t["clock"], "ls", glow=True)
        c.text(x0 + tw + 5, 104, sec, "monob", 20, t["accent"], "ls", glow=True)
        df = ctx.get("date_fmt", "text")
        c.text_fit(c.w / 2, 130, f"{now.strftime('%A')}  ·  {gregorian_string(now, df)}", "medium", 13, t["sub"],
                   "mm", max_w=c.w - 20)
        c.text_fit(c.w / 2, 152, jalali_string(now, df), "bold", 14, t["accent"], "mm", max_w=c.w - 20, glow=True)
        weather_block(8, 170, c.w - 16, 242)
        mini_stats(8, c.h - 52, c.w - 16)


PAGES = {"overview": page_overview, "network": page_network, "storage": page_storage, "clock": page_clock}


def render(page, theme, size, ctx):
    w, h = size
    c = Canvas(w, h, theme)
    PAGES.get(page, page_overview)(c, ctx)
    return c.finish()


def render_view(page, theme, orientation, flip, mirror, ctx):
    """Render a page exactly as it is sent to the screen (orientation, flip 180, mirror)."""
    from PIL import Image
    size = (320, 480) if orientation == "portrait" else (480, 320)
    img = render(page, theme, size, ctx)
    if flip:
        img = img.transpose(Image.ROTATE_180)
    if mirror == "horizontal":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    elif mirror == "vertical":
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    return img
