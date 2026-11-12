#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Elgoon — the article / news image, second design (2026-11-08).

    python news_image.py --photo <file|url> --kicker "توتنهام" --out media/news-<slug>.jpg --debug [--focus 0.5,0.3]

Why a second design (user, 2026-11-08, on two images that shipped): the hero
of 2026-11-06 (hero_card.py) cut the player out of his photo and set him on
his club's colours with the club crest behind him. Cutting out leaves pieces
of other people (a team-mate's head floating behind Marmoush), the crest is
an official mark we may not use, and a national-team shirt on a club
background reads as the wrong club (Marmoush in Egypt red on Tottenham).
This design never cuts and never borrows a club's identity:

  * the licensed photo is used WHOLE - nothing is cut out, so nothing is left
    floating - and framed around the FACE (OpenCV finds it), so the article
    page's crop never slices a head;
  * the only colours, marks and type are OURS: the site blue, the «الجون»
    wordmark, Almarai. A club appears only as words in the label;
  * one label (kicker) in Arabic: the club, the competition or the story type.

Styles - the user chose C on 2026-11-08 («Style C»); it is the default and
the one every article run uses. a and b stay for comparison only:
  a  full-bleed: the photo fills the image, a soft navy fade at the foot, the
     wordmark bottom-left, the label bottom-right
  b  sticker frame: the photo in a rounded white-bordered frame on our blue,
     the wordmark stuck on the frame's corner like the logo sticker
  c  split: a navy panel with a slanted edge carries the label and the
     wordmark, the photo fills the rest

Output: 1600x900 JPEG. The article page (`.a-img`: width 100%, max-height
400px, object-fit cover, object-position 50% 18%) shows the WHOLE image on a
phone (~360 px wide -> ~200 px high, no crop) and a vertical band on a desktop
(913 px column at 1024 px -> rows ~4-82 %; at the widest ~1540 px column ->
rows ~10-56 %). Columns are never cropped. So the face sits in the upper
middle (ty ~0.36) and nothing that matters is placed below ~60 %.
"""
import argparse
import io
import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import fb_cards as C                    # noqa: E402  fonts + Arabic shaping

W, H = 1600, 900
BLUE = (31, 148, 211)                   # style.css --green: the site blue
BLUE_D = (21, 101, 143)                 # --green-d
NAVY = (9, 27, 46)
WHITE = (255, 255, 255)
MAX_UP = 1.8                            # never blow a photo up more than this
WORDMARK = os.path.join(HERE, "assets-src", "wordmark-1024.png")


# ---------------------------------------------------------------- the photo
def load_photo(src):
    if src.startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "elgoon-news-image/1.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
        im = Image.open(io.BytesIO(data))
    else:
        im = Image.open(src)
    from PIL import ImageOps
    return ImageOps.exif_transpose(im).convert("RGB")


def unpad(photo):
    """Strip a pillarbox: many vetted photos were saved as a narrow photo on
    a blurred, enlarged copy of itself (1600x762). The blurred bands carry no
    fine detail, so the real photo is the central run of columns with edge
    energy. Pillow only (2026-11-08): the deploy-gate runner has no numpy,
    and a numpy-only version silently did nothing there - one implementation
    everywhere. Returns the photo unchanged when there is no such band."""
    from PIL import ImageChops                                     # noqa: PLC0415
    k = min(1.0, 800 / photo.width)
    g = photo.convert("L").resize((max(1, int(photo.width * k)), max(1, int(photo.height * k))))
    w, h = g.size
    if w < 40 or h < 4:
        return photo
    # per column: mean |vertical step| + mean |horizontal step| (exact, not
    # rounded to 8 bits), then a 9-wide zero-padded running mean
    dv = list(ImageChops.difference(g.crop((0, 1, w, h)), g.crop((0, 0, w, h - 1))).getdata())
    dh = list(ImageChops.difference(g.crop((1, 0, w, h)), g.crop((0, 0, w - 1, h))).getdata())
    col = [sum(dv[x::w]) / (h - 1) + sum(dh[x::w - 1]) / h for x in range(w - 1)]
    n = len(col)
    e = [sum(col[max(0, x - 4):x + 5]) / 9 for x in range(n)]
    mid_band = sorted(e[int(n * 0.45):int(n * 0.55)])
    mid = mid_band[len(mid_band) // 2] if mid_band else 0
    if mid <= 0:
        return photo
    sharp = [v > mid * 0.30 for v in e]
    c = n // 2
    if not sharp[c]:
        return photo
    a = c
    while a > 0 and sharp[a - 1]:
        a -= 1
    b = c
    while b < n - 1 and sharp[b + 1]:
        b += 1
    left, right = a, n - 1 - b
    # a pillarbox is CENTRED: two soft bands of about the same width. One soft
    # side is a blurred background (bokeh), not padding - keep the photo.
    if min(left, right) < n * 0.08 or abs(left - right) > n * 0.06:
        return photo
    lo = e[:max(1, a - 5)]
    hi = e[min(n - 1, b + 5):]
    side = max(sum(lo) / len(lo), sum(hi) / len(hi))
    if (b - a + 1) < n * 0.20 or side > mid * 0.30:
        return photo
    pad = 3                                        # stay clear of the soft seam
    x0 = (a + pad) / k
    x1 = (b + 1 - pad) / k
    return photo.crop((int(x0), 0, int(x1), photo.height))


def _person_box(photo):
    """The main person's box (x0, y0, x1, y1) in photo pixels, from the human
    segmentation model rembg already caches on the runner (u2net_human_seg).
    Used only to FIND the person - nothing is cut out. None when rembg or
    its model is not there."""
    try:
        import cv2
        import numpy as np
        from rembg import new_session, remove
    except Exception:
        return None
    k = min(1.0, 640 / max(photo.size))
    small = photo.resize((max(1, int(photo.width * k)), max(1, int(photo.height * k))))
    try:
        m = remove(small, only_mask=True, session=new_session("u2net_human_seg"))
    except Exception:
        return None
    m = (np.asarray(m) > 128).astype("uint8")
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    if n < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < m.size * 0.03:
        return None
    x, y, w, h = (stats[i, j] for j in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
    blob = lab == i
    # the head sits above the CHEST, not at the blob's highest point: a raised
    # arm (a goal, a thumbs-up - Ronaldo, 2026-11-08) is higher than the head.
    # So: the body's centre line from the chest band (30-55 % of the blob),
    # then the highest blob pixels within a window around that line.
    chest = blob[y + int(h * 0.30):y + max(int(h * 0.30) + 1, int(h * 0.55)), :]
    ccols = np.where(chest.any(axis=0))[0]
    if len(ccols):
        wsum = chest.sum(axis=0).astype("float64")
        cx = float((np.arange(len(wsum)) * wsum).sum() / max(1.0, wsum.sum()))
    else:
        cx = x + w / 2
    half = max(6, int(w * 0.14))
    win = blob[:, max(0, int(cx) - half):int(cx) + half + 1]
    rows = np.where(win.any(axis=1))[0]
    htop = int(rows.min()) if len(rows) else y
    band = blob[htop:htop + max(2, int(h * 0.10)), max(0, int(cx) - half):int(cx) + half + 1]
    cols = np.where(band.any(axis=0))[0]
    off = max(0, int(cx) - half)
    hx = off + (cols.min() + cols.max()) / 2 if len(cols) else cx
    hw = (cols.max() - cols.min() + 1) if len(cols) else w * 0.3
    y = htop                                       # the head's top, for the caller
    return (x / k, y / k, (x + w) / k, (y + h) / k), (hx / k, hw / k)


def _haar(photo, region=None):
    try:
        import cv2
        import numpy as np
    except Exception:
        return []
    k = min(1.0, 900 / max(photo.size))
    small = photo.resize((max(1, int(photo.width * k)), max(1, int(photo.height * k))))
    g = cv2.equalizeHist(cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2GRAY))
    found = []
    for share, votes in ((0.06, 6), (0.025, 7)):
        for name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
            cas = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, name))
            mn = max(16, int(min(g.shape) * share))
            for (x, y, w, h) in cas.detectMultiScale(g, scaleFactor=1.08, minNeighbors=votes, minSize=(mn, mn)):
                cx, cy, hh = (x + w / 2) / k, (y + h / 2) / k, h / k
                if region:
                    x0, y0, x1, y1 = region
                    if not (x0 <= cx <= x1 and y0 <= cy <= y0 + (y1 - y0) * 0.45):
                        continue
                elif cy > photo.height * 0.70:
                    continue
                found.append((hh * hh, cx, cy, hh))
        if found:
            return found
    return found


def find_face(photo):
    """The main face as (cx, cy, h) in photo pixels, or None.
    1. find the main PERSON (segmentation - never used to cut), then the
       largest face inside his top part: a face in the crowd or on a shirt
       is outside it, so it cannot win;
    2. no face found there: the head from the top of the person's outline;
    3. no segmentation available: the largest face in the upper part."""
    pb = _person_box(photo)
    if pb:
        box, (hx, hw) = pb
        hh = max(hw, (box[3] - box[1]) * 0.08)          # the head, from the outline
        top = box[1]
        # a face counts only where the outline says the head is: over the head
        # column and near the top - a face in the crowd beside him, or a
        # team-mate's lower down, does not
        faces = [f for f in _haar(photo, box)
                 if abs(f[1] - hx) < hh * 1.1 and f[2] < top + hh * 2.2]
        if faces:
            _, cx, cy, h = max(faces)
            return cx, cy, min(h, hh * 1.4)
        return hx, top + hh * 0.55, hh
    faces = _haar(photo)
    if faces:
        _, cx, cy, h = max(faces)
        return cx, cy, h
    return None


HAIR_ABOVE, HEAD_MARGIN = 1.0, 0.06


def head_cut(photo, face):
    """True when the SOURCE photo itself cuts the top of the head: the hair
    would start above the photo's top edge. No crop can give that head room
    back - pick another photo (graphic-designer review 2026-11-12)."""
    if not face:
        return False
    _, fy, fh = face
    return fy - fh * HAIR_ABOVE < fh * 0.10


def frame(photo, bw, bh, face=None, tx=0.5, ty=0.36, face_share=(0.16, 0.42)):
    """The photo cropped to bw x bh: it covers the box, the face lands at
    (tx, ty) of it, and the face is between face_share[0] and [1] of the box
    height when the photo allows (never more than MAX_UP enlargement)."""
    s = max(bw / photo.width, bh / photo.height)
    if face:
        fx, fy, fh = face
        want = min(max(s, face_share[0] * bh / fh), face_share[1] * bh / fh)
        s = max(s, min(want, MAX_UP))
    else:
        fx, fy = photo.width / 2, photo.height * 0.30
    left = max(0.0, min(fx * s - tx * bw, photo.width * s - bw))
    top = fy * s - ty * bh
    if face:
        # never slice the head: the crop starts above the hair with a margin,
        # even if that puts the face lower than (tx, ty). The hair reaches a
        # full face-height above the face's centre, not 0.85 of it, and the
        # margin is 6 % of the box (graphic-designer review 2026-11-12: the
        # crowns of Salah 1146/1130, Carrick 1144 and Kompany's cap 1128
        # touched the edge)
        top = min(top, (fy - fh * HAIR_ABOVE) * s - bh * HEAD_MARGIN)
    top = max(0.0, min(top, photo.height * s - bh))
    box = (left / s, top / s, (left + bw) / s, (top + bh) / s)
    out = photo.resize((bw, bh), Image.LANCZOS, box=box)
    if s > 1.15:                    # an enlarged photo goes soft: a light unsharp mask
        out = out.filter(ImageFilter.UnsharpMask(radius=1.6, percent=min(90, int(40 * s)), threshold=2))
    return out, s


# ---------------------------------------------------------------- our marks
def wordmark(h, angle=0):
    src = Image.open(WORDMARK).convert("RGBA")
    im = src.resize((round(src.width * h / src.height), h), Image.LANCZOS)
    return im.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else im


def chip(text, size=44, fill=BLUE, ink=WHITE, pad=(26, 14), radius=14):
    """The label: white Arabic on a blue rounded block, as an RGBA image."""
    f = C.font("ExtraBold", size)
    s = C.ar(text)
    tw = int(f.getlength(s))
    asc, desc = f.getmetrics()
    w, h = tw + 2 * pad[0], asc + desc + 2 * pad[1]
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=fill)
    d.text((pad[0], pad[1]), s, font=f, fill=ink)
    return im


def paste(base, im, x, y):
    base.alpha_composite(im, (int(x), int(y)))


def shadow(size, box, radius, blur=28, alpha=150):
    sh = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(box, radius=radius, fill=(0, 0, 0, alpha))
    return sh.filter(ImageFilter.GaussianBlur(blur))


def stripes(im, step=46, width=14, alpha=16):
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for x in range(-im.height, im.width, step):
        d.line([(x, im.height), (x + im.height, 0)], fill=(255, 255, 255, alpha), width=width)
    im.alpha_composite(lay)


def diag_gradient(size, a, b):
    """a in the top-left corner to b in the bottom-right, fast (via a small
    image scaled up)."""
    sw, sh = 64, 36
    g = Image.new("RGB", (sw, sh))
    px = g.load()
    for x in range(sw):
        for y in range(sh):
            t = (x / sw * 0.65 + y / sh * 0.35)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return g.resize(size, Image.BICUBIC).convert("RGBA")


# ---------------------------------------------------------------- styles
def style_a(photo, face, kicker, mood="neutral"):
    pic, _ = frame(photo, W, H, face, tx=0.5, ty=0.34, face_share=(0.12, 0.30))
    pic = grade(pic, mood)
    im = pic.convert("RGBA")
    fade = Image.new("L", (1, H), 0)
    for y in range(H):
        t = max(0.0, (y / H - 0.50) / 0.50)
        fade.putpixel((0, y), int(215 * t ** 1.4))
    lay = Image.new("RGBA", (W, H), NAVY + (0,))
    lay.putalpha(fade.resize((W, H)))
    im.alpha_composite(lay)
    wm = wordmark(92)
    paste(im, wm, 46, H - 46 - wm.height)
    if kicker:
        k = chip(kicker)
        paste(im, k, W - 46 - k.width, H - 46 - wm.height / 2 - k.height / 2)
    return im


def style_b(photo, face, kicker, mood="neutral"):
    im = diag_gradient((W, H), NAVY, BLUE_D)
    stripes(im)
    x0, y0, x1, y1 = 300, 70, 1530, 830
    bd, r = 14, 42
    im.alpha_composite(shadow((W, H), (x0 + 10, y0 + 22, x1 + 10, y1 + 22), r))
    ImageDraw.Draw(im).rounded_rectangle((x0 - bd, y0 - bd, x1 + bd, y1 + bd), radius=r + bd, fill=WHITE)
    pic, _ = frame(photo, x1 - x0, y1 - y0, face, tx=0.5, ty=0.36)
    pic = grade(pic, mood)
    m = Image.new("L", pic.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, pic.width - 1, pic.height - 1), radius=r, fill=255)
    pic = pic.convert("RGBA")
    pic.putalpha(m)
    im.alpha_composite(pic, (x0, y0))
    wm = wordmark(124, angle=6)          # stuck on the frame's left edge, mid-height:
    paste(im, wm, x0 - 150, H * 0.43 - wm.height / 2)   # inside the band every page width shows
    if kicker:
        k = chip(kicker)
        paste(im, k, x1 - 34 - k.width, y0 + 34)
    return im


# ---------------------------------------------------------------- the mood
# User, 2026-11-08: «لو الخبر حزين تخلى الصورة حزينة ولو الخبر حلو تخلى
# الصورة مفرحة». The EXPRESSION comes from choosing the right photo (a smile
# for good news, a serious or dejected face for bad news) - this only grades
# colour and light to match: never an edit of the person, the shirt or the
# face. happy: warmer, brighter, a touch more colour, the bright brand edge.
# sad: most of the colour drained, darker, cooler, a soft vignette, a slate
# panel and a muted steel edge instead of the bright blue.
MOODS = {
    "neutral": {"sat": 1.00, "bright": 1.00, "contrast": 1.00, "tint": (0, 0, 0), "vignette": 0.0,
                "panel": (NAVY, (14, 52, 86)), "edge": BLUE, "bar": BLUE},
    "happy":   {"sat": 1.16, "bright": 1.05, "contrast": 1.04, "tint": (7, 3, -6), "vignette": 0.0,
                "panel": (NAVY, (16, 64, 108)), "edge": BLUE, "bar": BLUE},
    "sad":     {"sat": 0.42, "bright": 0.88, "contrast": 0.96, "tint": (-5, 0, 9), "vignette": 0.38,
                "panel": ((8, 15, 24), (30, 40, 52)), "edge": (112, 128, 146), "bar": (140, 154, 170)},
}


def grade(pic, mood):
    """Colour and light only."""
    from PIL import ImageEnhance                                   # noqa: PLC0415
    m = MOODS[mood]
    if mood == "neutral":
        return pic
    out = ImageEnhance.Color(pic.convert("RGB")).enhance(m["sat"])
    out = ImageEnhance.Brightness(out).enhance(m["bright"])
    out = ImageEnhance.Contrast(out).enhance(m["contrast"])
    if any(m["tint"]):
        r, g, b = out.split()
        r, g, b = (ch.point(lambda v, t=t: max(0, min(255, v + t))) for ch, t in zip((r, g, b), m["tint"]))
        out = Image.merge("RGB", (r, g, b))
    if m["vignette"]:
        w, h = out.size
        small = Image.new("L", (64, 36), 0)
        px = small.load()
        for x in range(64):
            for y in range(36):
                dx, dy = (x - 31.5) / 32, (y - 17.5) / 18
                px[x, y] = int(255 * min(1.0, max(0.0, (dx * dx + dy * dy) ** 0.5 - 0.45)) * m["vignette"])
        dark = Image.new("RGB", out.size, (0, 0, 0))
        out = Image.composite(dark, out, small.resize((w, h), Image.BICUBIC))
    return out


def style_c(photo, face, kicker, mood="neutral"):
    m_ = MOODS[mood]
    edge_top, edge_bot = 660, 540                 # the slanted edge of the panel
    pic, _ = frame(photo, W - edge_bot, H, face, tx=0.56, ty=0.36)
    pic = grade(pic, mood)
    im = Image.new("RGBA", (W, H), m_["panel"][0] + (255,))
    im.alpha_composite(pic.convert("RGBA"), (edge_bot, 0))
    panel = diag_gradient((W, H), *m_["panel"])
    stripes(panel, alpha=10)
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon([(0, 0), (edge_top, 0), (edge_bot, H), (0, H)], fill=255)
    im.paste(panel, (0, 0), m)
    d = ImageDraw.Draw(im)
    d.line([(edge_top, 0), (edge_bot, H)], fill=m_["edge"], width=16)
    # label then wordmark, both in rows ~25-55 %: the band a desktop page shows
    wm = wordmark(112)
    cx = 300
    if kicker:
        f = C.font("ExtraBold", 66)
        s = C.ar(kicker)
        while f.getlength(s) > 470 and f.size > 40:
            f = C.font("ExtraBold", f.size - 4)
        d.text((cx, 270), s, font=f, fill=WHITE, anchor="mm")
        d.rounded_rectangle((cx - 60, 330, cx + 60, 340), radius=5, fill=m_["bar"])
        paste(im, wm, cx - wm.width / 2, 380)
    else:
        paste(im, wm, cx - wm.width / 2, H * 0.42 - wm.height / 2)
    return im


STYLES = {"a": style_a, "b": style_b, "c": style_c}


def build(photo_src, out, kicker="", style="c", focus=None, mood="neutral"):
    photo = unpad(load_photo(photo_src))
    if focus:
        fx, fy = (float(v) for v in focus.split(","))
        face = (fx * photo.width, fy * photo.height, photo.height * 0.12)
    else:
        face = find_face(photo)
    im = STYLES[style](photo, face, kicker, mood).convert("RGB")
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        im.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return im, face


def main():
    ap = argparse.ArgumentParser(description="Elgoon article / news image (no cutout, no club marks)")
    ap.add_argument("--photo", required=True, help="the licensed photo (file or URL)")
    ap.add_argument("--kicker", default="", help="1-3 Arabic words: the club, the competition or the story type")
    ap.add_argument("--style", default="c", choices=sorted(STYLES), help="c = the chosen house style (default)")
    ap.add_argument("--mood", default="neutral", choices=sorted(MOODS),
                    help="the story's mood: happy (a win, a goal, a renewal, a signing, an award, a comeback), "
                         "sad (a loss, an injury, criticism, a sacking, an elimination, a death), neutral otherwise")
    ap.add_argument("--focus", help="x,y of the face as fractions of the photo, when detection misses it")
    ap.add_argument("--out", required=True)
    ap.add_argument("--debug", action="store_true", help="also write <out>-face.jpg: the photo with the face found marked")
    a = ap.parse_args()
    im, face = build(a.photo, a.out, a.kicker, a.style, a.focus, a.mood)
    if a.debug:
        from PIL import ImageDraw as D
        p = unpad(load_photo(a.photo))
        if face:
            cx, cy, h = face
            D.Draw(p).rectangle((cx - h / 2, cy - h / 2, cx + h / 2, cy + h / 2), outline=(0, 255, 0), width=max(4, p.width // 200))
        p.thumbnail((900, 900))
        p.save(os.path.splitext(a.out)[0] + "-face.jpg", quality=85)
    print(f"{a.out}: {W}x{H}, face {'found' if face else 'NOT found - framed on the upper centre; check it, or pass --focus'}")
    if face and head_cut(unpad(load_photo(a.photo)), face):
        print("HEAD CUT: the source photo itself cuts the top of the head - no crop can fix it; pick another photo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
