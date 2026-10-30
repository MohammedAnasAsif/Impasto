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


WALLPAPERS = [
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
    cat = dict(name="Impasto Starter Pack", version=1,
               wallpapers=sorted(old.values(), key=lambda w: order.index(w["id"]) if w["id"] in order else 999))
    cat_path.write_text(json.dumps(cat, indent=2))


if __name__ == "__main__":
    main(set(sys.argv[1:]))
