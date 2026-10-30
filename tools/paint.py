"""Impasto wallpaper generator.

Paints every wallpaper in the starter pack from code: a height map and a colour map are
built from palette-knife strokes and tube-paint lettering, then lit like a photo of thick
oil paint. Output is lossless PNG at native phone and desktop sizes (no upscaling).

    python3 tools/paint.py            # all wallpapers
    python3 tools/paint.py t01 a02    # some of them
"""
import json, sys, hashlib, os
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parent.parent
FONTS = Path(__file__).resolve().parent / "fonts"
OUT = ROOT / "catalog"
SIZES = {"phone": (1440, 3200), "desktop": (3840, 2160)}


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def smooth_noise(rng, shape, cell):
    """Value noise: random grid of size shape/cell, cubic upscaled."""
    gh, gw = max(2, int(shape[0] / cell) + 3), max(2, int(shape[1] / cell) + 3)
    g = rng.standard_normal((gh, gw)).astype(np.float32)
    z = ndi.zoom(g, (shape[0] / (gh - 3) * 1.0001, shape[1] / (gw - 3) * 1.0001), order=3)
    return z[: shape[0], : shape[1]]


class Canvas:
    def __init__(self, w, h, seed, ground="#efe9dc"):
        self.w, self.h = w, h
        self.s = min(w, h) / 2160  # scale so texture reads the same on phone and desktop
        self.rng = np.random.default_rng(seed)
        self.H = np.zeros((h, w), np.float32)
        self.C = np.empty((h, w, 3), np.float32)
        self.C[:] = hexrgb(ground)

    # ---------- palette knife / brush stroke ----------
    def stroke(self, cx, cy, length, width, angle, color, height=7.0, mix=0.25, ridge=0.35):
        rng, s = self.rng, self.s
        R = int(np.hypot(length, width) / 2) + 4
        x0, x1 = int(max(0, cx - R)), int(min(self.w, cx + R))
        y0, y1 = int(max(0, cy - R)), int(min(self.h, cy + R))
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        dx, dy = xx - cx, yy - cy
        ca, sa = np.cos(angle), np.sin(angle)
        u = (dx * ca + dy * sa) / (length / 2)
        v = (-dx * sa + dy * ca) / (width / 2)
        # ragged edges: the knife never leaves a clean border
        k = np.linspace(-1.3, 1.3, 64)
        edge_v = np.interp(u, k, 1 + 0.12 * np.convolve(rng.standard_normal(64), np.ones(5) / 5, "same"))
        edge_u = np.interp(v, k, 1 + 0.10 * np.convolve(rng.standard_normal(64), np.ones(5) / 5, "same"))
        av, au = np.abs(v) / edge_v, np.abs(u) / edge_u
        m = np.clip((1 - av) / 0.12, 0, 1) * np.clip((1 - au) / 0.10, 0, 1)
        if not m.any():
            return
        # bristle striations run along the stroke
        nb = max(12, int(width / (3 * s)))
        stri = np.interp((v + 1) / 2 * (nb - 1), np.arange(nb), rng.standard_normal(nb)).astype(np.float32)
        stri += 0.35 * np.interp((u + 1) / 2 * 15, np.arange(16), rng.standard_normal(16))
        ridge_h = ridge * np.clip((av - 0.6) / 0.35, 0, 1) ** 2  # paint pushed to the sides
        pile = 0.7 * np.exp(-((u - 0.85) / 0.12) ** 2)           # paint piled where the knife lifts
        h = (0.55 + ridge_h + pile + 0.07 * stri) * height * s
        self.H[y0:y1, x0:x1] = self.H[y0:y1, x0:x1] * (1 - 0.8 * m) + m * h
        col = np.asarray(color, np.float32)
        tint = (0.012 * stri)[..., None]
        old = self.C[y0:y1, x0:x1]
        f = (mix * np.clip(-u, 0, 1))[..., None]  # drags some of the wet paint beneath
        new = col * (1 - f) + old * f + tint
        self.C[y0:y1, x0:x1] = old * (1 - m[..., None]) + new * m[..., None]

    def paint_from(self, target, passes=((0.3, 1.0), (0.16, 1.0), (0.08, 0.5), (0.04, 0.5)), flow=None, height=7.0, jitter=0.025):
        """Painterly render of a target image: coarse knife strokes, then finer ones on detail."""
        rng = self.rng
        self.C[:] = target  # knife drags wet paint from below; start from the picture, not bare canvas
        grad = np.linalg.norm(np.stack(np.gradient(ndi.gaussian_filter(target.mean(2), 3 * self.s))), axis=0)
        for size, cover in passes:
            L = size * min(self.w, self.h)
            step = L * 0.42
            pts = [(x + rng.uniform(-step / 2, step / 2), y + rng.uniform(-step / 2, step / 2))
                   for y in np.arange(-step / 2, self.h + step, step) for x in np.arange(-step / 2, self.w + step, step * 1.4)]
            rng.shuffle(pts)
            for (x, y) in pts:
                xi, yi = int(np.clip(x, 0, self.w - 1)), int(np.clip(y, 0, self.h - 1))
                if cover < 1 and grad[yi, xi] < 0.004 and rng.random() > 0.05:
                    continue
                ang = flow(x, y) if flow else rng.uniform(-0.5, 0.5)
                ang += rng.normal(0, 0.18)
                col = target[yi, xi] * (1 + rng.normal(0, jitter)) + rng.normal(0, jitter * 0.25, 3)
                ln = L * rng.uniform(0.8, 1.4)
                self.stroke(x, y, ln, ln * rng.uniform(0.3, 0.45), ang, col, height=height * (0.7 + size * 2))

    # ---------- tube-paint lettering ----------
    def letters(self, lines, font, size, colors, center=(0.5, 0.5), leading=1.0, thick=34.0, align="center",
                tracking=0.0, warp=1.0):
        """Draw text as squeezed-out paint: rounded tube profile, wobbly outline, one colour per glyph."""
        s, rng = self.s, self.rng
        fnt = ImageFont.truetype(str(FONTS / font), int(size))
        idmap = Image.new("I", (self.w, self.h), 0)
        d = ImageDraw.Draw(idmap)
        asc, desc = fnt.getmetrics()
        lh = (asc + desc) * leading
        widths = [sum(fnt.getlength(ch) + tracking * size for ch in ln) - tracking * size for ln in lines]
        top = self.h * center[1] - lh * len(lines) / 2
        gid = 0
        for li, ln in enumerate(lines):
            x = (self.w * center[0] - widths[li] / 2) if align == "center" else self.w * center[0]
            for ch in ln:
                if ch != " ":
                    gid += 1
                    d.text((x, top + li * lh), ch, font=fnt, fill=gid)
                x += fnt.getlength(ch) + tracking * size
        ids = np.array(idmap, np.int32)
        # hand-painted wobble: displace the glyph map with smooth noise
        amp = 0.045 * size * warp
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        ox = smooth_noise(rng, ids.shape, size * 0.5) * amp
        oy = smooth_noise(rng, ids.shape, size * 0.5) * amp
        ids = ndi.map_coordinates(ids, [yy + oy, xx + ox], order=0, mode="nearest")
        del yy, xx, ox, oy
        mask = ids > 0
        r = thick * s * size / 400
        dist = ndi.distance_transform_edt(mask)
        prof = np.sqrt(np.clip(dist / r, 0, 1))
        # rounded shoulders: blur the profile instead of cutting it at the glyph edge
        lift = ndi.gaussian_filter(np.where(mask, prof, 0).astype(np.float32), r * 0.18)
        lift += (smooth_noise(rng, mask.shape, 60 * s) * 0.08 + smooth_noise(rng, mask.shape, 14 * s) * 0.012) * lift
        a = np.clip(ndi.gaussian_filter(mask.astype(np.float32), 1.2) * 1.6 - 0.3, 0, 1)  # anti-aliased coverage
        self.H = np.maximum(self.H * (1 - a), lift * r * 0.9)
        cols = np.array([hexrgb(c) for c in colors], np.float32)
        near = ndi.grey_dilation(ids, size=5)  # colour reaches the soft edge too
        glyph_col = cols[(np.maximum(ids, near) - 1) % len(cols)]
        shade = smooth_noise(rng, mask.shape, 40 * s)[..., None] * 0.03
        self.C = self.C * (1 - a[..., None]) + (glyph_col + shade) * a[..., None]

    # ---------- a crisp painted object over the background ----------
    def layer(self, rgba, sizes=(0.03, 0.015), height=6.0, lift=3.0):
        """Paint an RGBA picture as its own layer: brush texture inside, a clean silhouette outside."""
        arr = np.asarray(rgba, np.float32) / 255
        target, mask = arr[..., :3], arr[..., 3] > 0.5
        if not mask.any():
            return
        C0, H0 = self.C.copy(), self.H.copy()
        self.C[mask] = target[mask]
        rng = self.rng
        ys, xs = np.nonzero(mask)
        for size in sizes:
            L = size * min(self.w, self.h)
            n = int(mask.sum() / (L * L * 0.18)) + 1
            for i in rng.integers(0, len(xs), n):
                x, y = xs[i], ys[i]
                self.stroke(x, y, L * rng.uniform(0.8, 1.3), L * rng.uniform(0.3, 0.45), rng.uniform(-0.6, 0.6),
                            target[y, x] * (1 + rng.normal(0, 0.03)), height=height, mix=0.1)
        a = np.clip(ndi.gaussian_filter(mask.astype(np.float32), 1.2) * 1.6 - 0.3, 0, 1)
        self.C = C0 * (1 - a[..., None]) + self.C * a[..., None]
        self.H = H0 * (1 - a) + (self.H + lift * self.s) * a

    # ---------- light it like a photograph ----------
    def render(self, light=(-0.55, -0.65, 0.52), spec=0.35, ao=0.5):
        H = ndi.gaussian_filter(self.H, 0.7)
        gy, gx = np.gradient(H)
        n = np.stack([-gx, -gy, np.ones_like(H)], -1)
        n /= np.linalg.norm(n, axis=-1, keepdims=True)
        L = np.array(light, np.float32)
        L /= np.linalg.norm(L)
        L = -L * np.array([1, 1, -1])  # light comes from the top-left, above the canvas
        diff = np.clip((n * L).sum(-1), 0, 1)
        Hh = L + np.array([0, 0, 1.0])
        Hh /= np.linalg.norm(Hh)
        sp = np.clip((n * Hh).sum(-1), 0, 1) ** 60 * spec
        occl = np.clip((ndi.gaussian_filter(H, 12 * self.s) - H) / (10 * self.s), 0, 1) * ao
        base = diff / max(1e-6, float(L[2]))  # flat paint keeps its own colour
        shade = 0.42 + 0.62 * base
        out = self.C * (shade * (1 - occl))[..., None] + sp[..., None]
        # gentle vignette, as if photographed
        yy, xx = np.ogrid[0:self.h, 0:self.w]
        vig = 1 - 0.10 * (((xx - self.w / 2) / (self.w / 2)) ** 2 + ((yy - self.h / 2) / (self.h / 2)) ** 2)
        out *= vig[..., None]
        return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


# ---------------- compositions ----------------

def ground_target(c, base, var=0.04, cell=0.35):
    t = np.empty((c.h, c.w, 3), np.float32)
    t[:] = hexrgb(base)
    t *= 1 + smooth_noise(c.rng, (c.h, c.w), cell * min(c.w, c.h))[..., None] * var
    return t


def knife_ground(c, base, var=0.035, height=6.0):
    c.paint_from(ground_target(c, base, var), passes=((0.34, 1.0), (0.2, 1.0)), height=height)


def is_phone(c):
    return c.h > c.w


def w_soon(c):
    knife_ground(c, "#f2e9d6")
    c.letters(["soon."], "dm-serif-display-latin-400-normal.woff", c.w * (0.36 if is_phone(c) else 0.2),
              ["#1d1b19"], center=(0.5, 0.47), thick=30)


def w_do_it_scared(c):
    knife_ground(c, "#f3ead8")
    lines = ["DO IT", "SCARED."] if is_phone(c) else ["DO IT SCARED."]
    size = c.w * (0.2 if is_phone(c) else 0.115)
    c.letters(lines, "permanent-marker-latin-400-normal.woff", size, ["#c3261d"], center=(0.5, 0.5), leading=1.0, thick=26)


def w_already_working(c):
    knife_ground(c, "#f4eee2")
    cols = ["#e8492f", "#f3a712", "#2a9d5c", "#2f6fdf", "#8e44c9", "#ec5fa3"]
    lines = ["it's", "already", "working"] if is_phone(c) else ["it's already", "working"]
    size = c.w * (0.21 if is_phone(c) else 0.135)
    c.letters(lines, "fredoka-latin-700-normal.woff", size, cols, center=(0.5, 0.5), leading=0.95, thick=60)


def w_build_quietly(c):
    knife_ground(c, "#e7e2d6", var=0.03)
    lines = ["build", "quietly."] if is_phone(c) else ["build quietly."]
    size = c.w * (0.22 if is_phone(c) else 0.115)
    c.letters(lines, "dm-serif-display-latin-400-normal.woff", size, ["#26231f"], center=(0.5, 0.5), thick=22)


def w_stay_delusional(c):
    knife_ground(c, "#141414", var=0.05, height=7)
    lines = ["STAY", "DELU", "SIONAL"] if is_phone(c) else ["STAY", "DELUSIONAL"]
    size = c.w * (0.27 if is_phone(c) else 0.13)
    c.letters(lines, "anton-latin-400-normal.woff", size, ["#f2c230"], center=(0.5, 0.5), leading=0.92, thick=30, warp=0.6)


def w_orange_hour(c):
    t = np.empty((c.h, c.w, 3), np.float32)
    yy, xx = np.mgrid[0:c.h, 0:c.w].astype(np.float32)
    hz = c.h * (0.62 if is_phone(c) else 0.6)
    sky_top, sky_low = hexrgb("#e2502b"), hexrgb("#f6a24a")
    k = np.clip(yy / hz, 0, 1)[..., None]
    t[:] = sky_top * (1 - k) + sky_low * k
    sea = yy > hz
    t[sea] = hexrgb("#24376b")
    sx, sy, sr = c.w * 0.5, hz - 0.02 * c.h, min(c.w, c.h) * (0.2 if is_phone(c) else 0.17)
    t[((xx - sx) ** 2 + (yy - sy) ** 2 < sr ** 2) & ~sea] = hexrgb("#fde3a0")
    refl = sea & (np.abs(xx - sx) < sr * (1 - (yy - hz) / (c.h - hz)) * 0.9) & (np.sin(yy / (14 * c.s)) > 0.1)
    t[refl] = hexrgb("#f5b25b")
    c.paint_from(t, flow=lambda x, y: 0.0, height=8)


def w_low_tide(c):
    t = np.empty((c.h, c.w, 3), np.float32)
    bands = ["#0f2a3f", "#1d4f6e", "#3d8ca3", "#9cc9c4", "#e8e1cf", "#c9b48a"]
    yy = np.arange(c.h)[:, None] * np.ones((1, c.w))
    wav = smooth_noise(c.rng, (c.h, c.w), 0.5 * c.w) * 0.04 * c.h
    idx = np.clip(((yy + wav) / c.h * len(bands)).astype(int), 0, len(bands) - 1)
    t[:] = np.array([hexrgb(b) for b in bands])[idx]
    c.paint_from(t, flow=lambda x, y: 0.0, height=8)


def w_pistachio(c):
    knife_ground(c, "#a9bf7a", var=0.05, height=9)
    # one long cream sweep across the field
    n = 9
    for i in range(n):
        f = i / (n - 1)
        x = c.w * (0.15 + 0.7 * f)
        y = c.h * (0.62 - 0.22 * np.sin(f * np.pi) * (0.6 if is_phone(c) else 1))
        c.stroke(x, y, min(c.w, c.h) * 0.3, min(c.w, c.h) * 0.11, -0.35 + 0.7 * f, hexrgb("#f4eedd"), height=12, mix=0.1)


def w_ember(c):
    t = np.empty((c.h, c.w, 3), np.float32)
    yy, xx = np.mgrid[0:c.h, 0:c.w].astype(np.float32)
    cx, cy = c.w / 2, c.h / 2
    ang = np.arctan2(yy - cy, xx - cx)
    rad = np.hypot(xx - cx, yy - cy) / (0.5 * min(c.w, c.h))
    sw = np.sin(ang * 3 + rad * 4.5)
    pal = np.array([hexrgb(x) for x in ["#2b0b0a", "#8f1d14", "#d9461c", "#f29b38", "#f8d27a"]])
    i = np.clip(((sw + 1) / 2 * 0.7 + np.clip(1 - rad, 0, 1) * 0.35) * 4.99, 0, 4.99).astype(int)
    t[:] = pal[i]
    c.paint_from(t, flow=lambda x, y: np.arctan2(y - cy, x - cx) + np.pi / 2, height=8)


def w_hills(c):
    t = np.empty((c.h, c.w, 3), np.float32)
    yy, xx = np.mgrid[0:c.h, 0:c.w].astype(np.float32)
    sky = np.clip(yy / (c.h * 0.6), 0, 1)[..., None]
    t[:] = hexrgb("#f3c7a6") * (1 - sky) + hexrgb("#e88e6d") * sky
    sx, sy, sr = c.w * 0.68, c.h * (0.4 if is_phone(c) else 0.33), min(c.w, c.h) * 0.08
    t[(xx - sx) ** 2 + (yy - sy) ** 2 < sr ** 2] = hexrgb("#fff1d6")
    layers = [("#b55a5a", 0.5), ("#7d3f58", 0.62), ("#4a2d4f", 0.74), ("#25193a", 0.86)]
    for i, (col, base) in enumerate(layers):
        f = xx / c.w
        ridge = c.h * (base + 0.05 * np.sin(f * (5 + i) + i * 1.7) + 0.03 * np.sin(f * 13 + i))
        t[yy > ridge] = hexrgb(col)
    c.paint_from(t, flow=lambda x, y: 0.1 * np.sin(x / 300), height=8)


# ---------- Savage: lines with no apology ----------
MARKER, FRED, SERIF, ANTON = ("permanent-marker-latin-400-normal.woff", "fredoka-latin-700-normal.woff",
                              "dm-serif-display-latin-400-normal.woff", "anton-latin-400-normal.woff")


def w_unbothered(c):
    knife_ground(c, "#f07fa8", var=0.05, height=8)
    c.letters(["unbothered."], SERIF, c.w * (0.155 if is_phone(c) else 0.13), ["#141012"], thick=26, warp=0.5)


def w_opinion_budget(c):
    knife_ground(c, "#f3ead8")
    lines = ["YOUR OPINION", "WASN\u2019T IN", "THE BUDGET"] if is_phone(c) else ["YOUR OPINION WASN\u2019T", "IN THE BUDGET"]
    c.letters(lines, MARKER, c.w * (0.12 if is_phone(c) else 0.075), ["#c3261d"], leading=1.05, thick=24)


def w_not_for_everyone(c):
    knife_ground(c, "#8e1414", var=0.06, height=8)
    lines = ["NOT", "FOR", "EVERY", "ONE"] if is_phone(c) else ["NOT FOR", "EVERYONE"]
    c.letters(lines, ANTON, c.w * (0.3 if is_phone(c) else 0.14), ["#f4eee2"], leading=0.92, thick=28, warp=0.6)


def w_low_battery(c):
    knife_ground(c, "#151414", var=0.05, height=7)
    cols = ["#e8492f", "#f3a712", "#2a9d5c", "#2f6fdf", "#8e44c9", "#ec5fa3"]
    lines = ["low", "battery,", "high", "standards"] if is_phone(c) else ["low battery,", "high standards"]
    c.letters(lines, FRED, c.w * (0.19 if is_phone(c) else 0.115), cols, leading=0.95, thick=60)


def w_replace(c):
    knife_ground(c, "#e9e2d2", var=0.03)
    lines = ["I don't", "chase.", "I replace."] if is_phone(c) else ["I don't chase.", "I replace."]
    c.letters(lines, SERIF, c.w * (0.17 if is_phone(c) else 0.1), ["#1d1b19"], leading=1.0, thick=22)


def w_seen(c):
    knife_ground(c, "#f2ebdc")
    lines = ["seen.", "not", "replying."] if is_phone(c) else ["seen.", "not replying."]
    c.letters(lines, MARKER, c.w * (0.18 if is_phone(c) else 0.1), ["#1f4fd1"], leading=1.0, thick=24)


# ---------- Cinema: film-still moods, no faces ----------

def w_night_drive(c):
    t = np.empty((c.h, c.w, 3), np.float32)
    yy, xx = np.mgrid[0:c.h, 0:c.w].astype(np.float32)
    hz = c.h * (0.5 if is_phone(c) else 0.45)
    k = np.clip(yy / hz, 0, 1)[..., None]
    t[:] = hexrgb("#120b2e") * (1 - k) + hexrgb("#c2386b") * k
    # skyline on the horizon with lit windows
    rng = c.rng
    x = 0
    while x < c.w:
        bw = rng.uniform(0.03, 0.08) * c.w
        bh = rng.uniform(0.04, 0.2) * c.h * (0.7 if is_phone(c) else 1)
        m = (xx >= x) & (xx < x + bw) & (yy > hz - bh) & (yy <= hz)
        t[m] = hexrgb("#1b1030")
        win = m & (((xx - x) % (0.012 * c.w)) < 0.005 * c.w) & (((yy - hz) % (0.02 * c.h)) < 0.008 * c.h) & (rng.random() > 0.3)
        t[win & (np.sin(xx * 0.31 + yy * 0.17) > 0.2)] = hexrgb("#ffcf6e")
        x += bw + rng.uniform(0, 0.01) * c.w
    road = yy > hz
    t[road] = hexrgb("#17121f")
    cx = c.w * 0.5
    spread = (yy - hz) / (c.h - hz)
    for side, col in ((-1, "#ff3b2f"), (1, "#fff1c9")):  # tail-lights going, headlights coming
        lane = cx + side * spread * c.w * 0.28
        streak = road & (np.abs(xx - lane) < (2 + spread * 0.018 * c.w)) & (np.sin(yy / (6 * c.s) * (1 + spread)) > -0.4)
        t[streak] = hexrgb(col)
    centre = road & (np.abs(xx - cx) < 1 + spread * 0.004 * c.w) & ((spread * 40) % 1 < 0.5)
    t[centre] = hexrgb("#e9d9a0")
    c.paint_from(t, passes=((0.2, 1.0), (0.1, 1.0), (0.05, 0.5), (0.025, 0.5)), flow=lambda x, y: 0.0, height=7)


def w_skyline(c):
    t = np.empty((c.h, c.w, 3), np.float32)
    yy, xx = np.mgrid[0:c.h, 0:c.w].astype(np.float32)
    k = np.clip(yy / c.h, 0, 1)[..., None]
    t[:] = hexrgb("#0b1b3a") * (1 - k) + hexrgb("#2b5c8f") * k
    mx, my, mr = c.w * 0.7, c.h * (0.22 if is_phone(c) else 0.28), min(c.w, c.h) * 0.11
    t[(xx - mx) ** 2 + (yy - my) ** 2 < mr ** 2] = hexrgb("#f6ecd0")
    rng = c.rng
    for layer, (col, base) in enumerate([("#1f3a63", 0.6), ("#0a1428", 0.74)]):
        x = -0.02 * c.w
        while x < c.w:
            bw = rng.uniform(0.04, 0.1) * c.w
            top = c.h * (base - rng.uniform(0.0, 0.22 if layer else 0.15))
            m = (xx >= x) & (xx < x + bw) & (yy > top)
            t[m] = hexrgb(col)
            if layer:
                win = m & (((xx - x) % (0.016 * c.w)) < 0.007 * c.w) & (((yy - top) % (0.024 * c.h)) < 0.01 * c.h)
                t[win & (np.sin(xx * 0.013 + yy * 0.021 + x) * np.sin(yy * 0.0037 + x * 0.7) > 0.45)] = hexrgb("#f7c56a")
            x += bw
    c.paint_from(t, passes=((0.2, 1.0), (0.1, 1.0), (0.05, 0.5), (0.025, 0.5)), flow=lambda x, y: np.pi / 2 if y > c.h * 0.45 else 0.0, height=7)



# ---------- figurative helpers: draw a flat target with Pillow, then paint over it ----------

def pil_target(c, ground):
    im = Image.new("RGB", (c.w, c.h), ground)
    return im, ImageDraw.Draw(im)


def to_arr(im):
    return np.asarray(im, np.float32) / 255


FINE = ((0.2, 1.0), (0.1, 1.0), (0.05, 0.6), (0.025, 0.6), (0.013, 0.6))


def suited_figure(d, cx, feet, H, suit="#1c1f26", hair="#17120f", skin="#c99a7a", shirt="#e9e4da", rim="#4a5a7a"):
    """A man seen from behind, hands in pockets. Proportions in head-heights (H / 7.5)."""
    u = H / 7.5
    top = feet - H
    P = lambda pts: [(cx + x * u, top + y * u) for x, y in pts]
    d.polygon(P([(-0.55, 6.9), (-0.08, 6.9), (-0.12, 7.45), (-0.75, 7.5)]), fill="#0d0d0f")   # shoes
    d.polygon(P([(0.08, 6.9), (0.55, 6.9), (0.75, 7.5), (0.12, 7.45)]), fill="#0d0d0f")
    d.polygon(P([(-0.95, 3.6), (0.95, 3.6), (0.62, 6.95), (0.06, 6.95), (0, 4.5), (-0.06, 6.95), (-0.62, 6.95)]), fill=suit)  # trousers
    d.polygon(P([(-0.5, 1.15), (0.5, 1.15), (1.55, 1.55), (1.45, 3.0), (1.1, 4.1), (-1.1, 4.1), (-1.45, 3.0), (-1.55, 1.55)]), fill=suit)  # jacket
    d.polygon(P([(-1.55, 1.55), (-1.95, 3.1), (-1.25, 3.5), (-1.05, 2.4)]), fill=suit)  # arms bent to pockets
    d.polygon(P([(1.55, 1.55), (1.95, 3.1), (1.25, 3.5), (1.05, 2.4)]), fill=suit)
    d.polygon(P([(0.02, 2.9), (0.06, 4.1), (-0.02, 4.1)]), fill="#0e1015")  # back vent
    d.polygon(P([(-1.55, 1.55), (-1.95, 3.1), (-1.88, 3.15), (-1.5, 1.7)]), fill=rim)  # rim light from the window
    d.rectangle([cx - 0.32 * u, top + 0.85 * u, cx + 0.32 * u, top + 1.25 * u], fill=skin)  # neck
    d.polygon(P([(-0.42, 1.12), (0.42, 1.12), (0.5, 1.3), (-0.5, 1.3)]), fill=shirt)  # collar
    d.ellipse([cx - 0.5 * u, top, cx + 0.5 * u, top + 1.05 * u], fill=hair)  # back of the head
    d.ellipse([cx - 0.58 * u, top + 0.42 * u, cx - 0.42 * u, top + 0.72 * u], fill=skin)  # ears
    d.ellipse([cx + 0.42 * u, top + 0.42 * u, cx + 0.58 * u, top + 0.72 * u], fill=skin)


def w_corner_office(c):
    phone = is_phone(c)
    im, d = pil_target(c, "#0b1630")
    rng = c.rng
    hz = c.h * (0.74 if phone else 0.8)
    for i in range(14):  # dusk sky, brightest at the horizon
        k = i / 13
        col = tuple(int(255 * v) for v in hexrgb("#0e1a3a") * (1 - k) + hexrgb("#e07a45") * k)
        d.rectangle([0, hz * i / 14, c.w, hz * (i + 1) / 14 + 2], fill=col)
    x = 0
    while x < c.w:  # towers on the horizon with lit windows
        bw = rng.uniform(0.03, 0.08) * c.w
        top = hz - rng.uniform(0.04, 0.2) * c.h
        d.rectangle([x, top, x + bw, c.h], fill="#121b33")
        sx, sy = 0.012 * c.w, 0.016 * c.h
        for wx in np.arange(x + sx * 0.4, x + bw - sx * 0.5, sx):
            for wy in np.arange(top + sy * 0.6, c.h, sy):
                if rng.random() < 0.35:
                    d.rectangle([wx, wy, wx + sx * 0.45, wy + sy * 0.45], fill="#f2c46b")
        x += bw + rng.uniform(0.002, 0.01) * c.w
    for mx in ([0.04, 0.96] if phone else [0.02, 0.4, 0.98]):  # window mullions
        d.rectangle([mx * c.w - 0.007 * c.w, 0, mx * c.w + 0.007 * c.w, c.h], fill="#06080d")
    d.rectangle([0, c.h * 0.9, c.w, c.h], fill="#0a0c12")  # floor
    c.paint_from(to_arr(im), passes=((0.2, 1.0), (0.1, 1.0), (0.05, 0.6), (0.025, 0.6)), flow=lambda x, y: 0.0, height=6)
    fg = Image.new("RGBA", (c.w, c.h), (0, 0, 0, 0))
    if phone:
        suited_figure(ImageDraw.Draw(fg), c.w * 0.5, c.h * 0.93, c.h * 0.5, rim="#c27a55")
    else:
        suited_figure(ImageDraw.Draw(fg), c.w * 0.7, c.h * 0.95, c.h * 0.74, rim="#c27a55")
    c.layer(fg, sizes=(0.025, 0.012))
    lines = ["Win first.", "Explain later."]
    if phone:
        c.letters(lines, SERIF, c.w * 0.13, ["#f4eee2"], center=(0.5, 0.15), thick=20)
    else:
        c.letters(lines, SERIF, c.w * 0.065, ["#f4eee2"], center=(0.27, 0.28), thick=20)


def w_non_refundable(c):
    knife_ground(c, "#d9d2c3", var=0.04)
    phone = is_phone(c)
    # a long till receipt laid on the paint, flat paper (no impasto under it)
    rw, rh = (c.w * 0.8, c.h * 0.62) if phone else (c.w * 0.62, c.h * 0.62)
    x0, y0 = (c.w - rw) / 2, (c.h - rh) / 2
    paper = Image.new("RGB", (int(rw), int(rh)), "#f7f4ec")
    pd = ImageDraw.Draw(paper)
    mono = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", int(rh * 0.026))
    bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", int(rh * 0.034))
    rows = [("TODAY", "24:00:00"), ("SLEEP", "-07:30:00"), ("WORK", "-09:00:00"), ("COMMUTE", "-01:10:00"),
            ("SCROLLING", "-04:12:00"), ("OVERTHINKING", "-01:28:00"), ("", ""), ("LEFT FOR YOUR DREAM", "00:50:00")]
    y = rh * 0.07
    pd.text((rw / 2, y), "THE DAILY STORE", font=bold, fill="#2b2925", anchor="mt")
    y += rh * 0.05
    pd.text((rw / 2, y), "OPEN 24H  ·  NO EXCHANGES", font=mono, fill="#55514a", anchor="mt")
    y += rh * 0.07
    for a, b in rows:
        pd.text((rw * 0.08, y), a, font=mono, fill="#2b2925")
        pd.text((rw * 0.92, y), b, font=mono, fill="#2b2925", anchor="ra")
        y += rh * 0.045
    pd.line([(rw * 0.08, y), (rw * 0.92, y)], fill="#8a857c", width=max(1, int(rh * 0.002)))
    y += rh * 0.03
    pd.text((rw / 2, y), "ALL SALES FINAL", font=bold, fill="#2b2925", anchor="mt")
    y += rh * 0.08
    bx = rw * 0.18
    while bx < rw * 0.82:  # barcode
        bwid = rng_w = c.rng.choice([1, 1, 2, 3]) * rh * 0.0025
        pd.rectangle([bx, y, bx + bwid, y + rh * 0.08], fill="#2b2925")
        bx += bwid + c.rng.choice([1, 2]) * rh * 0.0025
    arr = to_arr(paper)
    shade = np.linspace(0.97, 1.02, arr.shape[1])[None, :, None]  # a soft curl in the paper
    yi, xi = int(y0), int(x0)
    c.C[yi:yi + arr.shape[0], xi:xi + arr.shape[1]] = arr * shade
    hh = smooth_noise(c.rng, arr.shape[:2], 0.15 * rw) * 1.5 * c.s + 2 * c.s
    c.H[yi:yi + arr.shape[0], xi:xi + arr.shape[1]] = hh
    lines = ["TIME IS", "NON-", "REFUND-", "ABLE"] if phone else ["TIME IS", "NON-REFUNDABLE"]
    c.letters(lines, MARKER, c.w * (0.14 if phone else 0.085), ["#111111"], center=(0.5, 0.5), leading=1.0, thick=22)


def w_self_made(c):
    knife_ground(c, "#efe6d4", var=0.03)
    phone = is_phone(c)
    c.letters(["Self-made*"], SERIF, c.w * (0.19 if phone else 0.13), ["#191714"], center=(0.5, 0.46), thick=24, warp=0.5)
    c.letters(["*still loading"], SERIF, c.w * (0.06 if phone else 0.032), ["#191714"], center=(0.72 if phone else 0.68, 0.56 if phone else 0.6), thick=16, warp=0.4)


def w_one_day(c):
    phone = is_phone(c)
    knife_ground(c, "#f1eadb")
    im = Image.new("RGBA", (c.w, c.h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    L = c.w * (0.82 if phone else 0.46)
    cx, by = c.w / 2, c.h * (0.6 if phone else 0.66)
    P = lambda pts: [(cx + x * L, by + y * L) for x, y in pts]
    d.ellipse([cx - 0.52 * L, by + 0.01 * L, cx + 0.52 * L, by + 0.07 * L], fill="#5a554c")  # shadow
    d.polygon(P([(-0.5, -0.02), (-0.5, -0.11), (-0.42, -0.14), (-0.14, -0.15), (0.0, -0.24), (0.2, -0.25),
                 (0.36, -0.17), (0.5, -0.13), (0.51, -0.04), (0.47, -0.02)]), fill="#c8261c")  # wedge coupe body
    d.polygon(P([(-0.08, -0.155), (0.02, -0.225), (0.18, -0.232), (0.3, -0.165)]), fill="#1b2530")  # glass
    d.line(P([(0.11, -0.228), (0.12, -0.16)]), fill="#c8261c", width=int(L * 0.012))  # pillar
    d.polygon(P([(-0.5, -0.07), (0.51, -0.07), (0.51, -0.055), (-0.5, -0.055)]), fill="#8e1610")  # side line
    d.rectangle([cx + 0.44 * L, by - 0.12 * L, cx + 0.5 * L, by - 0.1 * L], fill="#ffd27a")  # lamp
    for wx in (-0.3, 0.32):  # wheels
        r = 0.085 * L
        d.ellipse([cx + wx * L - r, by - 0.03 * L - r, cx + wx * L + r, by - 0.03 * L + r], fill="#111111")
        r2 = r * 0.55
        d.ellipse([cx + wx * L - r2, by - 0.03 * L - r2, cx + wx * L + r2, by - 0.03 * L + r2], fill="#b9b9b4")
    c.layer(im, sizes=(0.02, 0.01))
    c.letters(["ONE DAY."], MARKER, c.w * (0.2 if phone else 0.11), ["#151515"], center=(0.5, 0.33 if phone else 0.3), thick=24)


def w_forecast(c):
    phone = is_phone(c)
    im, d = pil_target(c, "#2f6fd6")
    for i in range(10):
        k = i / 9
        col = tuple(int(255 * v) for v in hexrgb("#1d4fb0") * (1 - k) + hexrgb("#6aa6ec") * k)
        d.rectangle([0, c.h * i / 10, c.w, c.h * (i + 1) / 10 + 2], fill=col)
    c.paint_from(to_arr(im), passes=((0.3, 1.0), (0.16, 1.0)), height=8)
    rng = c.rng
    fg = Image.new("RGBA", (c.w, c.h), (0, 0, 0, 0))
    for _ in range(22 if phone else 34):  # falling notes, no real currency design
        bw = min(c.w, c.h) * rng.uniform(0.09, 0.13)
        bill = Image.new("RGBA", (int(bw), int(bw * 0.46)), "#d3dcbc")
        bd = ImageDraw.Draw(bill)
        bd.rectangle([bw * 0.06, bw * 0.05, bw * 0.94, bw * 0.41], outline="#5f7a4f", width=max(2, int(bw * 0.035)))
        bd.ellipse([bw * 0.39, bw * 0.1, bw * 0.61, bw * 0.36], fill="#7f9a68")
        bill = bill.rotate(rng.uniform(0, 360), expand=True, resample=Image.BICUBIC)
        fg.paste(bill, (int(rng.uniform(-0.05, 0.95) * c.w), int(rng.uniform(0.38, 0.95) * c.h)), bill)
    d = ImageDraw.Draw(fg)
    ux, uy, ur = c.w / 2, c.h * (0.7 if phone else 0.66), min(c.w, c.h) * (0.28 if phone else 0.22)
    d.pieslice([ux - ur, uy - ur * 0.75, ux + ur, uy + ur * 0.75], 180, 360, fill="#151515")
    for k in (-0.66, -0.22, 0.22, 0.66):  # canopy ribs catch a little light
        d.line([(ux, uy - ur * 0.75), (ux + k * ur, uy)], fill="#2c2c2c", width=max(2, int(ur * 0.012)))
    d.line([(ux, uy), (ux, uy + ur * 0.95)], fill="#151515", width=int(ur * 0.04))
    d.arc([ux - ur * 0.18, uy + ur * 0.84, ux + ur * 0.02, uy + ur * 1.04], 0, 180, fill="#151515", width=int(ur * 0.04))
    c.layer(fg, sizes=(0.02, 0.01))
    c.letters(["forecast:", "money."], FRED, c.w * (0.16 if phone else 0.085), ["#fff7e6"],
              center=(0.5, 0.22 if phone else 0.24), leading=0.95, thick=50)


WALLPAPERS = [
    dict(id="s01", fn=w_unbothered, title="Unbothered", collection="Savage", tags=["type", "pink", "savage"], seed=31),
    dict(id="s02", fn=w_opinion_budget, title="Not in the Budget", collection="Savage", tags=["type", "red", "savage"], seed=32),
    dict(id="s03", fn=w_not_for_everyone, title="Not for Everyone", collection="Savage", tags=["type", "red", "bold"], seed=33),
    dict(id="s04", fn=w_low_battery, title="High Standards", collection="Savage", tags=["type", "dark", "colorful"], seed=34),
    dict(id="s05", fn=w_replace, title="I Replace", collection="Savage", tags=["type", "serif", "savage"], seed=35),
    dict(id="s06", fn=w_seen, title="Seen.", collection="Savage", tags=["type", "blue", "savage"], seed=36),
    dict(id="s07", fn=w_non_refundable, title="Non-Refundable", collection="Savage", tags=["type", "receipt", "time"], seed=37),
    dict(id="s08", fn=w_self_made, title="Self-Made*", collection="Savage", tags=["type", "serif", "money"], seed=38),
    dict(id="s09", fn=w_one_day, title="One Day", collection="Savage", tags=["car", "red", "money"], seed=39),
    dict(id="s10", fn=w_forecast, title="Forecast: Money", collection="Savage", tags=["money", "blue", "playful"], seed=40),
    dict(id="c03", fn=w_corner_office, title="Corner Office", collection="Cinema", tags=["suit", "city", "night", "boss"], seed=43),
    dict(id="c01", fn=w_night_drive, title="Night Drive", collection="Cinema", tags=["city", "night", "neon"], seed=41),
    dict(id="c02", fn=w_skyline, title="Moon Over the City", collection="Cinema", tags=["city", "night", "blue"], seed=42),
    dict(id="t01", fn=w_do_it_scared, title="Do It Scared", collection="Delusional", tags=["type", "red", "motivation"], seed=11),
    dict(id="t02", fn=w_already_working, title="Already Working", collection="Delusional", tags=["type", "colorful", "playful"], seed=12),
    dict(id="t03", fn=w_stay_delusional, title="Stay Delusional", collection="Delusional", tags=["type", "dark", "gold"], seed=13),
    dict(id="t04", fn=w_build_quietly, title="Build Quietly", collection="Quiet", tags=["type", "serif", "neutral"], seed=14),
    dict(id="t05", fn=w_soon, title="Soon.", collection="Quiet", tags=["type", "serif", "minimal"], seed=15),
    dict(id="a01", fn=w_orange_hour, title="Orange Hour", collection="Painted", tags=["sunset", "sea", "orange"], seed=21),
    dict(id="a02", fn=w_low_tide, title="Low Tide", collection="Painted", tags=["blue", "abstract", "sea"], seed=22),
    dict(id="a03", fn=w_hills, title="Dusk Hills", collection="Painted", tags=["landscape", "purple", "dusk"], seed=23),
    dict(id="a04", fn=w_pistachio, title="Pistachio", collection="Fields", tags=["green", "minimal", "abstract"], seed=24),
    dict(id="a05", fn=w_ember, title="Ember", collection="Fields", tags=["red", "swirl", "abstract"], seed=25),
]


def main(only):
    OUT.mkdir(parents=True, exist_ok=True)
    cat_path = OUT / "catalog.json"
    old = {w["id"]: w for w in json.loads(cat_path.read_text())["wallpapers"]} if cat_path.exists() else {}
    for spec in WALLPAPERS:
        wid = spec["id"]
        if only and wid not in only:
            continue
        d = OUT / "wallpapers" / wid
        d.mkdir(parents=True, exist_ok=True)
        files = {}
        for variant, (w, h) in SIZES.items():
            c = Canvas(w, h, spec["seed"] * 7 + (1 if variant == "phone" else 2))
            spec["fn"](c)
            img = c.render()
            p = d / f"{variant}.png"
            img.save(p, optimize=True, compress_level=9)
            prev = img.copy()
            prev.thumbnail((720, 720) if variant == "phone" else (1280, 1280), Image.LANCZOS)
            prev.save(d / f"{variant}-preview.webp", quality=82, method=6)
            files[variant] = dict(file=f"wallpapers/{wid}/{variant}.png", preview=f"wallpapers/{wid}/{variant}-preview.webp",
                                  width=w, height=h, bytes=p.stat().st_size,
                                  sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            avg = np.asarray(img.resize((1, 1), Image.BOX))[0, 0]
            files[variant]["color"] = "#%02x%02x%02x" % tuple(int(v) for v in avg)
            print(wid, variant, f"{p.stat().st_size / 1e6:.1f} MB", flush=True)
        old[wid] = dict(id=wid, title=spec["title"], collection=spec["collection"], tags=spec["tags"],
                        artist="Impasto", license="CC0-1.0", format="PNG (lossless)", variants=files)
    order = [s["id"] for s in WALLPAPERS]
    cat = {**(json.loads(cat_path.read_text()) if cat_path.exists() else {}), "name": "Impasto", "version": 1}  # keep "featured" etc.
    cat.update(
               wallpapers=sorted(old.values(), key=lambda w: order.index(w["id"]) if w["id"] in order else 999))
    cat_path.write_text(json.dumps(cat, indent=2))


if __name__ == "__main__":
    main(set(sys.argv[1:]))
