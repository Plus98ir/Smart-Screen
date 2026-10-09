"""Drawing helpers. Everything is drawn at 2x and downscaled for clean anti-aliasing."""
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(APP_DIR, "fonts")
S = 2  # supersampling factor

FONTS = {
    "regular": "Roboto-Regular.ttf",
    "medium": "Roboto-Medium.ttf",
    "bold": "Roboto-Bold.ttf",
    "black": "Roboto-Black.ttf",
    "light": "Roboto-Light.ttf",
    "mono": "JetBrainsMono-Medium.ttf",
    "monob": "JetBrainsMono-Bold.ttf",
    "monox": "JetBrainsMono-ExtraBold.ttf",
    "race": "RACESPACEREGULAR-Extended.otf",
}
_font_cache = {}
TEXT_SCALE = 1.0
TEXT_SIZES = {"normal": 1.0, "large": 1.15, "xlarge": 1.3}


def set_text_size(name):
    global TEXT_SCALE
    TEXT_SCALE = TEXT_SIZES.get(name, 1.0) if isinstance(name, str) else float(name)


def font(role: str, size: float) -> ImageFont.FreeTypeFont:
    key = (role, int(round(size * S * TEXT_SCALE)))
    f = _font_cache.get(key)
    if f is None:
        f = ImageFont.truetype(os.path.join(FONT_DIR, FONTS.get(role, role)), key[1])
        _font_cache[key] = f
    return f


def hex2rgb(c):
    if isinstance(c, tuple):
        return c[:3]
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    a, b = hex2rgb(a), hex2rgb(b)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


_bg_cache = {}


def _textured_bg(theme, w, h):
    """Static mid-tone backgrounds that hide panel burn-in: soft colour blobs or a carbon weave."""
    key = (theme["name"], w, h)
    if key in _bg_cache:
        return _bg_cache[key].copy()
    W, H = w * S, h * S
    top, bottom = hex2rgb(theme["bg"][0]), hex2rgb(theme["bg"][1])
    grad = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), bottom), Image.new("RGB", (W, H), top), grad)
    deco = theme.get("deco")
    if deco == "aurora":
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for fx, fy, fr, col in theme["blobs"]:
            cx, cy, r = fx * W, fy * H, fr * max(W, H)
            ld.ellipse((cx - r, cy - r, cx + r, cy + r), fill=hex2rgb(col))
        layer = layer.filter(ImageFilter.GaussianBlur(max(W, H) * 0.08))
        img = ImageChops.add(img, layer)
        # fine grain so flat areas never look like a plain dark field
        import random
        rnd = random.Random(7)
        noise = Image.frombytes("L", (W // 2, H // 2), bytes(rnd.randrange(0, 22) for _ in range((W // 2) * (H // 2))))
        noise = noise.resize((W, H), Image.BILINEAR)
        img = ImageChops.add(img, Image.merge("RGB", (noise, noise, noise)))
    elif deco == "carbon":
        cell = 6 * S
        tile = Image.new("RGB", (cell * 2, cell * 2))
        td = ImageDraw.Draw(tile)
        a, b = hex2rgb(theme["weave"][0]), hex2rgb(theme["weave"][1])
        for i, (ox, oy) in enumerate(((0, 0), (cell, cell), (cell, 0), (0, cell))):
            for k in range(cell):
                t = k / cell
                col = mix(a, b, t) if i < 2 else mix(b, a, t)
                if i < 2:
                    td.line((ox, oy + k, ox + cell - 1, oy + k), fill=col)
                else:
                    td.line((ox + k, oy, ox + k, oy + cell - 1), fill=col)
        pat = Image.new("RGB", (W, H))
        for yy in range(0, H, cell * 2):
            for xx in range(0, W, cell * 2):
                pat.paste(tile, (xx, yy))
        img = ImageChops.add(img, pat)
        # diagonal sheen
        sheen = Image.linear_gradient("L").rotate(35, expand=True).resize((W, H)).point(lambda v: int(v * 0.12))
        img = ImageChops.add(img, Image.merge("RGB", (sheen, sheen, sheen)))
    _bg_cache[key] = img
    return img.copy()


class Canvas:
    def __init__(self, w, h, theme):
        self.w, self.h, self.t = w, h, theme
        self.img = Image.new("RGB", (w * S, h * S), hex2rgb(theme["bg"][0]))
        self.d = ImageDraw.Draw(self.img)
        self.glow_img = None
        self.gd = None
        if theme.get("glow"):
            self.glow_img = Image.new("RGB", (w * S, h * S), (0, 0, 0))
            self.gd = ImageDraw.Draw(self.glow_img)
        self._background()

    # ------------------------------------------------------------- base
    def _background(self):
        if self.t.get("deco") in ("aurora", "carbon"):
            self.img.paste(_textured_bg(self.t, self.w, self.h))
            return
        top, bottom = hex2rgb(self.t["bg"][0]), hex2rgb(self.t["bg"][1])
        grad = Image.linear_gradient("L").resize((self.w * S, self.h * S))
        self.img.paste(Image.composite(Image.new("RGB", self.img.size, bottom),
                                       Image.new("RGB", self.img.size, top), grad))
        deco = self.t.get("deco")
        if deco == "grid":
            c = mix(self.t["bg"][0], self.t["grid"], 1.0)
            step = 20 * S
            for x in range(0, self.w * S, step):
                self.d.line([(x, 0), (x, self.h * S)], fill=c, width=1)
            for y in range(0, self.h * S, step):
                self.d.line([(0, y), (self.w * S, y)], fill=c, width=1)

    def finish(self) -> Image.Image:
        img = self.img
        if self.glow_img is not None:
            blur = self.glow_img.filter(ImageFilter.GaussianBlur(7 * S))
            img = ImageChops.screen(img, blur)
            img = ImageChops.screen(img, self.glow_img.filter(ImageFilter.GaussianBlur(2 * S)).point(
                lambda v: int(v * 0.5)))
        return img.resize((self.w, self.h), Image.LANCZOS)

    # ------------------------------------------------------------- primitives
    @staticmethod
    def _r(box):
        return [v * S for v in box]

    def card(self, x, y, w, h, accent=None, title=None, title_color=None, right=None):
        t = self.t
        box = self._r((x, y, x + w, y + h))
        style = t.get("style", "soft")
        if style == "cut":
            c = 10 * S
            x0, y0, x1, y1 = box
            pts = [(x0 + c, y0), (x1, y0), (x1, y1 - c), (x1 - c, y1), (x0, y1), (x0, y0 + c)]
            self.d.polygon(pts, fill=hex2rgb(t["card"]))
            ac = hex2rgb(accent or t["border"])
            self.d.line(pts + [pts[0]], fill=mix(t["border"], ac, 0.55), width=S)
            if accent:
                self.d.line([(x0, y0 + c), (x0 + c, y0), (x0 + c + 28 * S, y0)], fill=ac, width=2 * S)
                if self.gd:
                    self.gd.line([(x0, y0 + c), (x0 + c, y0), (x0 + c + 28 * S, y0)], fill=ac, width=2 * S)
        elif t.get("card_alpha"):
            # frosted glass: card tints the textured background instead of hiding it
            r = t.get("radius", 12) * S
            x0, y0, x1, y1 = [int(v) for v in box]
            region = self.img.crop((x0, y0, x1 + 1, y1 + 1))
            region = region.filter(ImageFilter.GaussianBlur(3 * S))
            mask = Image.new("L", region.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, region.size[0] - 1, region.size[1] - 1), r,
                                                   fill=int(255 * t["card_alpha"]))
            region.paste(Image.new("RGB", region.size, hex2rgb(t["card"])), (0, 0), mask)
            cut = Image.new("L", region.size, 0)
            ImageDraw.Draw(cut).rounded_rectangle((0, 0, region.size[0] - 1, region.size[1] - 1), r, fill=255)
            self.img.paste(region, (x0, y0), cut)
            self.d.rounded_rectangle(box, r, outline=hex2rgb(t["border"]), width=S)
            if accent and t.get("accent_bar", True):
                self.d.rounded_rectangle((x0 + r, y0, x0 + r + 26 * S, y0 + 3 * S), 2 * S, fill=hex2rgb(accent))
        else:
            r = t.get("radius", 12) * S
            self.d.rounded_rectangle(box, r, fill=hex2rgb(t["card"]), outline=hex2rgb(t["border"]), width=S)
            if accent and t.get("accent_bar", True):
                x0, y0, x1, y1 = box
                self.d.rounded_rectangle((x0 + r, y0, x0 + r + 26 * S, y0 + 3 * S), 2 * S, fill=hex2rgb(accent))
        if title:
            self.label(x + 12, y + 12, title, title_color or accent or t["sub"])
        if right:
            self.text(x + w - 12, y + 12, right, "medium", 10, t["sub"], "rm")

    def label(self, x, y, s, color, size=10.5, anchor="lm"):
        s = s.upper() if self.t.get("label_case", "upper") == "upper" else s
        role = self.t.get("label_font", "bold")
        self.text(x, y, s, role, size, color, anchor, spacing=self.t.get("label_spacing", 1.2))

    def text(self, x, y, s, role, size, color, anchor="la", spacing=0.0, glow=False, max_w=None):
        f = font(role, size)
        s = str(s)
        if max_w is not None:
            s = self.fit(s, role, size, max_w)
        col = hex2rgb(color)
        if spacing:
            # manual letter spacing
            total = sum(self.d.textlength(ch, font=f) for ch in s) + spacing * S * (len(s) - 1)
            ax, ay = anchor[0], anchor[1]
            px = x * S - (total if ax == "r" else total / 2 if ax == "m" else 0)
            for ch in s:
                self.d.text((px, y * S), ch, font=f, fill=col, anchor="l" + ay)
                px += self.d.textlength(ch, font=f) + spacing * S
            return total / S
        self.d.text((x * S, y * S), s, font=f, fill=col, anchor=anchor)
        if glow and self.gd:
            self.gd.text((x * S, y * S), s, font=f, fill=col, anchor=anchor)
        return self.d.textlength(s, font=f) / S

    def fit_size(self, s, role, size, max_w):
        while size > 6 and self.tlen(s, role, size) > max_w:
            size *= 0.95
        return size

    def text_fit(self, x, y, s, role, size, color, anchor="la", max_w=None, glow=False):
        """Like text(), but shrinks the font instead of cutting the text."""
        if max_w:
            size = self.fit_size(s, role, size, max_w)
        return self.text(x, y, s, role, size, color, anchor, glow=glow)

    def tlen(self, s, role, size):
        return self.d.textlength(str(s), font=font(role, size)) / S

    def fit(self, s, role, size, max_w):
        s = str(s)
        if self.tlen(s, role, size) <= max_w:
            return s
        while len(s) > 1 and self.tlen(s + "…", role, size) > max_w:
            s = s[:-1]
        return s.rstrip() + "…"

    def value_unit(self, x, y, value, unit, color, size, unit_color=None, anchor="ls", role="monob",
                   unit_size=None, glow=False, max_w=None):
        """Big number with a smaller unit, baseline aligned. anchor: ls / rs / ms.
        max_w: shrink the text until it fits that width."""
        unit_size = unit_size or max(9, size * 0.42)
        while True:
            wv = self.tlen(value, role, size)
            wu = self.tlen(unit, "medium", unit_size) if unit else 0
            gap = 3 if unit else 0
            total = wv + gap + wu
            if not max_w or total <= max_w or size < 8:
                break
            size *= 0.92
            unit_size *= 0.92
        x0 = x - total if anchor[0] == "r" else x - total / 2 if anchor[0] == "m" else x
        self.text(x0, y, value, role, size, color, "ls", glow=glow)
        if unit:
            self.text(x0 + wv + gap, y, unit, "medium", unit_size, unit_color or self.t["sub"], "ls")
        return total

    def ring(self, cx, cy, r, width, pct, color, track=None, glow=False):
        box = self._r((cx - r, cy - r, cx + r, cy + r))
        tr = hex2rgb(track or self.t["track"])
        self.d.ellipse(box, outline=tr, width=int(width * S))
        pct = 0 if pct is None or (isinstance(pct, float) and math.isnan(pct)) else max(0.0, min(100.0, pct))
        if pct > 0:
            start, end = -90, -90 + 360 * pct / 100
            self.d.arc(box, start, end, fill=hex2rgb(color), width=int(width * S))
            # round caps
            for ang in (start, end):
                a = math.radians(ang)
                rr = (r - width / 2) * S
                px, py = cx * S + rr * math.cos(a), cy * S + rr * math.sin(a)
                cr = width * S / 2
                self.d.ellipse((px - cr, py - cr, px + cr, py + cr), fill=hex2rgb(color))
            if glow and self.gd:
                self.gd.arc(box, start, end, fill=hex2rgb(color), width=int(width * S))

    def bar(self, x, y, w, h, pct, color, track=None, glow=False):
        r = h * S / 2 if self.t.get("style") != "cut" else 0
        self.d.rounded_rectangle(self._r((x, y, x + w, y + h)), r, fill=hex2rgb(track or self.t["track"]))
        pct = 0 if pct is None or (isinstance(pct, float) and math.isnan(pct)) else max(0.0, min(100.0, pct))
        if pct > 0:
            fw = max(h, w * pct / 100)
            if self.t.get("style") == "cut":
                # segmented bar
                seg, gap = 6, 2
                n = int(fw // (seg + gap))
                for i in range(n + 1):
                    sx = x + i * (seg + gap)
                    if sx >= x + fw:
                        break
                    self.d.rectangle(self._r((sx, y, min(sx + seg, x + fw), y + h)), fill=hex2rgb(color))
            else:
                self.d.rounded_rectangle(self._r((x, y, x + fw, y + h)), r, fill=hex2rgb(color))
            if glow and self.gd:
                self.gd.rectangle(self._r((x, y, x + fw, y + h)), fill=hex2rgb(color))

    def chart(self, x, y, w, h, series, vmax=None, fill=True, grid=True):
        """series: list of (values, color, filled)."""
        t = self.t
        if grid:
            for i in range(1, 4):
                gy = y + h * i / 4
                self.d.line(self._r((x, gy, x + w, gy)), fill=hex2rgb(t["gridline"]), width=1)
        allv = [v for vals, _, _ in series for v in vals]
        top = vmax or (max(allv) if allv else 1) or 1
        for vals, color, filled in series:
            n = len(vals)
            if n < 2:
                continue
            pts = []
            for i, v in enumerate(vals):
                px = x + w * i / (n - 1)
                py = y + h - h * max(0.0, min(1.0, v / top))
                pts.append((px * S, py * S))
            col = hex2rgb(color)
            if filled and fill:
                layer = Image.new("L", self.img.size, 0)
                ImageDraw.Draw(layer).polygon(pts + [(pts[-1][0], (y + h) * S), (pts[0][0], (y + h) * S)],
                                              fill=int(255 * t.get("fill_alpha", 0.28)))
                grad = Image.linear_gradient("L").resize((1, int(h * S))).transpose(Image.FLIP_TOP_BOTTOM)
                g = Image.new("L", self.img.size, 0)
                g.paste(grad.resize((self.img.size[0], int(h * S))), (0, int(y * S)))
                layer = ImageChops.multiply(layer, g.point(lambda v: 90 + v * 165 // 255))
                self.img.paste(Image.new("RGB", self.img.size, col), (0, 0), layer)
            self.d.line(pts, fill=col, width=int(1.6 * S), joint="curve")
            if self.gd:
                self.gd.line(pts, fill=col, width=int(1.6 * S))

    def dot(self, x, y, r, color, glow=False):
        self.d.ellipse(self._r((x - r, y - r, x + r, y + r)), fill=hex2rgb(color))
        if glow and self.gd:
            self.gd.ellipse(self._r((x - r, y - r, x + r, y + r)), fill=hex2rgb(color))

    def arrow(self, x, y, size, color, up=True):
        s = size
        if up:
            pts = [(x, y - s / 2), (x + s / 2, y + s / 2), (x - s / 2, y + s / 2)]
        else:
            pts = [(x - s / 2, y - s / 2), (x + s / 2, y - s / 2), (x, y + s / 2)]
        self.d.polygon([(px * S, py * S) for px, py in pts], fill=hex2rgb(color))

    def line(self, x0, y0, x1, y1, color, width=1):
        self.d.line(self._r((x0, y0, x1, y1)), fill=hex2rgb(color), width=int(width * S))

    # ------------------------------------------------------------- weather icons
    def weather_icon(self, cx, cy, size, kind, is_day=True):
        t = self.t
        sun_c, cloud_c = hex2rgb(t["sun"]), hex2rgb(t["cloud"])
        rain_c, snow_c = hex2rgb(t["rain"]), (235, 242, 255)
        s = size * S
        X, Y = cx * S, cy * S

        def sun(x, y, r):
            if is_day:
                for i in range(8):
                    a = math.radians(i * 45)
                    self.d.line([(x + math.cos(a) * r * 1.35, y + math.sin(a) * r * 1.35),
                                 (x + math.cos(a) * r * 1.75, y + math.sin(a) * r * 1.75)],
                                fill=sun_c, width=max(2, int(r * 0.22)))
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=sun_c)
            else:
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=(226, 232, 240))
                off = r * 0.55
                self.d.ellipse((x - r + off, y - r - off * 0.4, x + r + off, y + r - off * 0.4),
                               fill=hex2rgb(t["card"]))

        def cloud(x, y, w, color=cloud_c):
            h = w * 0.42
            self.d.rounded_rectangle((x - w / 2, y - h / 2, x + w / 2, y + h / 2), h / 2, fill=color)
            self.d.ellipse((x - w * 0.30, y - h * 1.05, x + w * 0.10, y + h * 0.15), fill=color)
            self.d.ellipse((x - w * 0.05, y - h * 1.35, x + w * 0.38, y + h * 0.1), fill=color)

        if kind == "sun":
            sun(X, Y, s * 0.26)
        elif kind == "partly":
            sun(X - s * 0.14, Y - s * 0.14, s * 0.2)
            cloud(X + s * 0.08, Y + s * 0.12, s * 0.62)
        elif kind == "cloud":
            cloud(X - s * 0.12, Y - s * 0.06, s * 0.5, mix(t["cloud"], t["card"], 0.35))
            cloud(X + s * 0.06, Y + s * 0.1, s * 0.66)
        elif kind == "fog":
            cloud(X, Y - s * 0.1, s * 0.62)
            for i in range(3):
                yy = Y + s * (0.16 + i * 0.1)
                self.d.line([(X - s * 0.3, yy), (X + s * 0.3, yy)], fill=cloud_c, width=max(2, int(s * 0.04)))
        elif kind in ("rain", "storm", "snow"):
            cloud(X, Y - s * 0.12, s * 0.66)
            if kind == "rain":
                for i in range(3):
                    xx = X - s * 0.18 + i * s * 0.18
                    self.d.line([(xx, Y + s * 0.12), (xx - s * 0.06, Y + s * 0.3)], fill=rain_c,
                                width=max(2, int(s * 0.05)))
            elif kind == "snow":
                for i in range(3):
                    xx = X - s * 0.18 + i * s * 0.18
                    r = s * 0.04
                    self.d.ellipse((xx - r, Y + s * 0.2 - r, xx + r, Y + s * 0.2 + r), fill=snow_c)
            else:
                bolt = [(X + s * 0.02, Y + s * 0.02), (X - s * 0.1, Y + s * 0.22), (X, Y + s * 0.22),
                        (X - s * 0.06, Y + s * 0.4), (X + s * 0.12, Y + s * 0.16), (X + s * 0.02, Y + s * 0.16)]
                self.d.polygon(bolt, fill=sun_c)
