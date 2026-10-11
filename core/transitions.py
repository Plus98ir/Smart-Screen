"""Page-change effects. The panel has no frame buffer tricks, so an effect is just the ORDER in which
parts of the new frame are sent (wipes, iris, dissolve...), or a backlight fade around the redraw."""
import math
import random

EFFECTS = ["none", "fade", "wipe_down", "wipe_up", "wipe_right", "wipe_left", "curtain", "iris", "diagonal",
           "blinds", "checker", "spiral", "dissolve", "fade_dissolve", "random"]
EFFECT_NAMES = {
    "none": "None (plain redraw)", "fade": "Fade (backlight)", "wipe_down": "Wipe down", "wipe_up": "Wipe up",
    "wipe_right": "Wipe right", "wipe_left": "Wipe left", "curtain": "Curtain (from middle)",
    "iris": "Iris (from centre)", "diagonal": "Diagonal", "blinds": "Blinds", "checker": "Checkerboard",
    "spiral": "Spiral", "dissolve": "Dissolve", "fade_dissolve": "Fade + dissolve", "random": "Random",
}
RANDOM_POOL = [e for e in EFFECTS if e not in ("none", "random")]

TILE = 32   # tile size for tile-based effects (480 and 320 are multiples of 32)
STRIP = 16  # strip width/height for wipes
BLIND = 8   # blinds: row height; BLIND_GROUP rows form one slat
BLIND_GROUP = 5


def pick(effect):
    effect = effect if effect in EFFECTS else "none"
    return random.choice(RANDOM_POOL) if effect == "random" else effect


def _grid(w, h, step_x, step_y):
    return [(x, y, min(w, x + step_x) - 1, min(h, y + step_y) - 1)
            for y in range(0, h, step_y) for x in range(0, w, step_x)]


def _spiral(cols, rows):
    """Grid cells (c, r) from the outer ring inwards, clockwise."""
    out, l, t, r, b = [], 0, 0, cols - 1, rows - 1
    while l <= r and t <= b:
        out += [(c, t) for c in range(l, r + 1)]
        out += [(r, y) for y in range(t + 1, b + 1)]
        if t < b:
            out += [(c, b) for c in range(r - 1, l - 1, -1)]
        if l < r:
            out += [(l, y) for y in range(b - 1, t, -1)]
        l, t, r, b = l + 1, t + 1, r - 1, b - 1
    return out


def order(effect, w, h, fx=False, fy=False):
    """Rects (x0, y0, x1, y1 inclusive) of the frame in send order.
    fx / fy: the picture is mirrored on that axis (flip / mirror), so directions are computed as the viewer sees
    them, not in frame coordinates."""
    def vx(x):  # viewer x of a frame x
        return w - 1 - x if fx else x

    def vy(y):
        return h - 1 - y if fy else y

    def centre(r):
        return vx((r[0] + r[2]) / 2), vy((r[1] + r[3]) / 2)

    if effect in ("wipe_down", "wipe_up"):
        rects = _grid(w, h, w, STRIP)
        return sorted(rects, key=lambda r: centre(r)[1], reverse=effect == "wipe_up")
    if effect in ("wipe_right", "wipe_left"):
        rects = _grid(w, h, STRIP, h)
        return sorted(rects, key=lambda r: centre(r)[0], reverse=effect == "wipe_left")
    if effect == "curtain":
        return sorted(_grid(w, h, STRIP, h), key=lambda r: abs(centre(r)[0] - w / 2))
    if effect == "blinds":
        rects = _grid(w, h, w, BLIND)
        return sorted(rects, key=lambda r: (int(centre(r)[1] // BLIND) % BLIND_GROUP, centre(r)[1]))
    tiles = _grid(w, h, TILE, TILE)
    if effect == "iris":
        return sorted(tiles, key=lambda r: math.hypot(centre(r)[0] - w / 2, (centre(r)[1] - h / 2) * 1.2))
    if effect == "diagonal":
        return sorted(tiles, key=lambda r: (centre(r)[0] + centre(r)[1], centre(r)[1]))
    if effect == "checker":
        return sorted(tiles, key=lambda r: ((int(centre(r)[0] // TILE) + int(centre(r)[1] // TILE)) % 2,
                                            centre(r)[1], centre(r)[0]))
    if effect == "spiral":
        by_cell = {(int(centre(r)[0] // TILE), int(centre(r)[1] // TILE)): r for r in tiles}
        cols, rows = math.ceil(w / TILE), math.ceil(h / TILE)
        return [by_cell[c] for c in _spiral(cols, rows) if c in by_cell]
    if effect in ("dissolve", "fade_dissolve"):
        random.shuffle(tiles)
        return tiles
    return _grid(w, h, w, STRIP)
