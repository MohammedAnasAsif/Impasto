"""Add a contributed wallpaper (e.g. made with an image AI) to the catalog at full size.

Upscales 4x with tools/upscale.py, blends 35% of a plain Lanczos resize back in so painted texture
survives, then fits each version to its exact size: desktop 3840x2160, phone 1440x3200.
A phone source that isn't 9:20 is either cropped (--phone-fit crop, with --phone-x 0..1 choosing
which part to keep) or extended top and bottom with a mirrored edge (--phone-fit pad).

    python3 tools/add_wallpaper.py --id g01 --title "Vitamin Money" --collection Delusional \\
        --tags type,money --desktop wide.png --phone tall.png --phone-fit pad \\
        --artist "Your Name" --weights realesr-general-x4v3.pth
"""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from PIL import Image
from upscale import session, upscale

ROOT = Path(__file__).resolve().parent.parent
CAT = ROOT / "catalog"
SIZES = {"phone": (1440, 3200), "desktop": (3840, 2160)}
_sess = None


def fit(im, w, h, mode, x_bias):
    sw, sh = im.size
    if abs(sw / sh - w / h) < 0.01:
        return im
    if mode == "pad" and sw / sh > w / h:  # too wide: extend top and bottom with a mirrored edge
        a = np.asarray(im)
        p = int(round((sw * h / w - sh) / 2))
        return Image.fromarray(np.pad(a, ((p, p), (0, 0), (0, 0)), mode="symmetric"))
    if sw / sh > w / h:  # crop the sides
        nw = int(round(sh * w / h))
        x0 = int(round((sw - nw) * x_bias))
        return im.crop((x0, 0, x0 + nw, sh))
    nh = int(round(sw * h / w))  # crop top and bottom
    y0 = (sh - nh) // 2
    return im.crop((0, y0, sw, y0 + nh))


def make(src, size, mode, x_bias, weights):
    global _sess
    _sess = _sess or session(weights)
    im = fit(Image.open(src).convert("RGB"), *size, mode, x_bias)
    ai = upscale(_sess, im).resize(size, Image.LANCZOS)
    return Image.blend(ai, im.resize(size, Image.LANCZOS), 0.35)


def main():
    ap = argparse.ArgumentParser()
    for k in ("id", "title", "collection", "weights"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--tags", default="")
    ap.add_argument("--desktop")
    ap.add_argument("--phone")
    ap.add_argument("--phone-fit", choices=["crop", "pad"], default="crop")
    ap.add_argument("--phone-x", type=float, default=0.5)
    ap.add_argument("--artist", default="Impasto contributors")
    ap.add_argument("--license", default="CC0-1.0")
    ap.add_argument("--format", default="PNG (lossless) · AI-generated, 4× upscaled")
    a = ap.parse_args()
    assert a.desktop or a.phone, "give --desktop and/or --phone"

    d = CAT / "wallpapers" / a.id
    d.mkdir(parents=True, exist_ok=True)
    variants = {}
    for v, src in (("desktop", a.desktop), ("phone", a.phone)):
        if not src:
            continue
        img = make(src, SIZES[v], a.phone_fit if v == "phone" else "crop", a.phone_x if v == "phone" else 0.5, a.weights)
        p = d / f"{v}.png"
        img.save(p, optimize=True)
        prev = img.copy()
        prev.thumbnail((720, 720) if v == "phone" else (1280, 1280), Image.LANCZOS)
        prev.save(d / f"{v}-preview.webp", quality=82, method=6)
        avg = img.resize((1, 1), Image.BOX).getpixel((0, 0))
        variants[v] = dict(file=f"wallpapers/{a.id}/{v}.png", preview=f"wallpapers/{a.id}/{v}-preview.webp",
                           width=SIZES[v][0], height=SIZES[v][1], bytes=p.stat().st_size,
                           sha256=hashlib.sha256(p.read_bytes()).hexdigest(), color="#%02x%02x%02x" % avg)
        print(a.id, v, f"{p.stat().st_size / 1e6:.1f} MB", flush=True)

    cat_path = CAT / "catalog.json"
    cat = json.loads(cat_path.read_text())
    entry = dict(id=a.id, title=a.title, collection=a.collection, tags=[t for t in a.tags.split(",") if t],
                 artist=a.artist, license=a.license, format=a.format, bundle=False, variants=variants)
    # bundle=False: apps ship the preview only and fetch the full file from the catalog source
    cat["wallpapers"] = [w for w in cat["wallpapers"] if w["id"] != a.id] + [entry]
    cat_path.write_text(json.dumps(cat, indent=2))


if __name__ == "__main__":
    main()
