#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sticker-style logo for «الجون» (asked 2026-11-07, replacing the tiger):

    "C:\\Program Files\\Python312\\python.exe" tools/make_logo.py --out DIR

Three 2000x700 PNGs, transparent outside the sticker:

  logo-ar.png   «الجون» (Almarai ExtraBold through fb_cards' shaper); the
                bowl of the و becomes a dart board with a dart stuck in it
  logo-en.png   ELGOON (Almarai Bold); the first O is the board + dart
  logo-mix.png  «الجون» large over elgoon.com small - THE logo (chosen 2026-11-07)
  mark.png      1024x1024: the board + dart alone, for small square places
  logo-en.png   only with --all (a variant the user did not pick)

The style of the "GOALS" sticker: heavy black letters (#111), a round
board of three reds and two whites (outer red ring, white, red, white, red
bull), the dart tilted up-right, the whole shape wrapped in a thick white
die-cut border with rounded corners. Flat - no shadow, no gradient.

Colours from the site's tokens (site_src/style.css):
  dart body    --green   #1f94d3  (the token is called green, it IS the site blue)
  dart flights --green-d #15658f
  board red    --live    #e11d48

The art is drawn at 3x and downsampled (Pillow has no anti-aliased
primitives); the border is the art's alpha blurred and thresholded, which
dilates it by BORDER px with round corners, like a die-cut."""
import argparse
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from fb_cards import ar, font                                     # noqa: E402

W, H = 2000, 700
BORDER = 34                      # the white die-cut rim, final px
MARGIN = 8                       # transparent breathing room outside the rim
INK = (17, 17, 17, 255)          # #111
WHITE = (255, 255, 255, 255)
BLUE = (31, 148, 211, 255)       # --green  #1f94d3
BLUE_D = (21, 101, 143, 255)     # --green-d #15658f
RED = (225, 29, 72, 255)         # --live   #e11d48
S = 3                            # supersampling
ANGLE = 45                       # the dart leans up-right by this much


# ---------------------------------------------------------------- pieces
def board(diam, ow):
    """The dart board: red/white/red/white/red bull inside a black rim, on a
    transparent square of side diam + 2*ow (so the rim is OUTSIDE the glyph
    circle and the letters keep their weight)."""
    side = int(diam + 2 * ow)
    im = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = side / 2
    r = diam / 2
    d.ellipse([c - r - ow, c - r - ow, c + r + ow, c + r + ow], fill=INK)
    for k, col in zip((1.0, 0.78, 0.56, 0.34, 0.14), (RED, WHITE, RED, WHITE, RED)):
        rr = r * k
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=col)
    return im


def dart(diam, ow):
    """A dart, tip at the centre of its square canvas, body to the right,
    then rotated so the body leans up-right. The reference sticker's
    proportions: the whole dart 0.95 of the board's diameter, so the flights
    barely clear the outer ring; shaft 6% of the diameter thick."""
    L = 0.95 * diam
    side = int(2 * L + 4 * ow)
    im = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = cy = side / 2
    D = diam
    ow = max(2, int(D * 0.015))          # a finer line than the board's: the parts are small

    def poly(pts, fill):
        d.polygon([(cx + x, cy + y) for x, y in pts], fill=fill, outline=INK, width=ow)

    # flights (back), then the shaft through them, the barrel and the point
    fl_a, fl_b, fl_h = 0.76 * D, 0.95 * D, 0.13 * D
    poly([(fl_a, -0.01 * D), (fl_b, -fl_h), (fl_b, -0.01 * D)], BLUE_D)
    poly([(fl_a, 0.01 * D), (fl_b, fl_h), (fl_b, 0.01 * D)], BLUE_D)
    sh = 0.03 * D
    poly([(0.36 * D, -sh), (0.95 * D, -sh), (0.95 * D, sh), (0.36 * D, sh)], BLUE)
    bw = 0.06 * D
    d.rounded_rectangle([cx + 0.14 * D, cy - bw, cx + 0.40 * D, cy + bw], radius=bw * 0.6,
                        fill=BLUE, outline=INK, width=ow)
    poly([(0, 0), (0.17 * D, -0.035 * D), (0.17 * D, 0.035 * D)], INK)
    return im.rotate(ANGLE, resample=Image.BICUBIC)      # tip stays at the centre


def text_layer(display, f):
    """Black text on a transparent canvas, with (x0, baseline) and the
    per-glyph x extents in DISPLAY order (BASIC layout: one glyph per char)."""
    pad = f.size
    asc, desc = f.getmetrics()
    w = int(f.getlength(display)) + 2 * pad
    h = asc + desc + 2 * pad
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, base = pad, pad + asc
    d.text((x0, base), display, font=f, fill=INK, anchor="ls")
    spans, x = [], x0
    for i in range(len(display)):
        adv = f.getlength(display[:i + 1]) - f.getlength(display[:i])
        spans.append((x, x + adv))
        x += adv
    return im, (x0, base), spans


def bowl_of_waw(layer, span, base, fsize):
    """The bowl of the final و: the ink inside the glyph's advance above the
    baseline (the tail hangs below). Returns (cx, cy, diameter)."""
    x0, x1 = int(span[0]), int(span[1])
    crop = layer.crop((x0, 0, x1, int(base - 0.04 * fsize)))
    bb = crop.getbbox()
    bx0, by0, bx1, by1 = bb
    h = by1 - by0
    diam = h * 1.10
    return x0 + bx0 + h / 2, by0 + h / 2, diam


def stick(layer, cx, cy, diam):
    """Cut a disc out of the letters, lay the board on it and the dart in it."""
    ow = max(2, int(diam * 0.03))
    d = ImageDraw.Draw(layer)
    r = diam / 2 + ow
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 0))
    b = board(diam, ow)
    layer.alpha_composite(b, (int(cx - b.width / 2), int(cy - b.height / 2)))
    dt = dart(diam, ow)
    layer.alpha_composite(dt, (int(cx - dt.width / 2), int(cy - dt.height / 2)))
    return layer


# ---------------------------------------------------------------- sticker
def sticker(art, w=W, h=H, border=BORDER, margin=MARGIN):
    """Fit the art into w x h minus the rim, then wrap it in the white die-cut."""
    art = art.crop(art.getbbox())
    inner_w, inner_h = w - 2 * (border + margin), h - 2 * (border + margin)
    k = min(inner_w / art.width, inner_h / art.height)
    art = art.resize((int(art.width * k), int(art.height * k)), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.alpha_composite(art, ((w - art.width) // 2, (h - art.height) // 2))
    # the rim: blur the alpha and keep everything above 5% - that is a round
    # dilation of ~1.65 sigma, i.e. `border` px, with rounded corners
    a = canvas.getchannel("A").filter(ImageFilter.GaussianBlur(border / 1.65))
    rim = a.point(lambda v: 255 if v > 13 else 0).filter(ImageFilter.GaussianBlur(1.2))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (w, h), WHITE), (0, 0), rim)
    out.alpha_composite(canvas)
    return out


def save(im, out):
    im.save(out, "PNG", optimize=True)
    print(f"{out}: {im.width}x{im.height}, {os.path.getsize(out) // 1024} KB")


def logo_ar():
    f = font("ExtraBold", 600 * S)
    disp = ar("الجون")
    layer, (x0, base), spans = text_layer(disp, f)
    i = [j for j, ch in enumerate(disp) if ch in ("\ufeee", "\u0648")][0]     # the و
    cx, cy, diam = bowl_of_waw(layer, spans[i], base, f.size)
    return sticker(stick(layer, cx, cy, diam))


def logo_en():
    f = font("Bold", 600 * S)
    txt = "ELGOON"
    layer, (x0, base), spans = text_layer(txt, f)
    i = txt.index("O")
    # a circle the height of the caps, centred on the O's advance
    bb = layer.crop((int(spans[i][0]), 0, int(spans[i][1]), layer.height)).getbbox()
    diam = (bb[3] - bb[1]) * 1.0
    cx = (spans[i][0] + spans[i][1]) / 2
    cy = bb[1] + (bb[3] - bb[1]) / 2
    return sticker(stick(layer, cx, cy, diam))


def logo_mix():
    f = font("ExtraBold", 600 * S)
    disp = ar("الجون")
    layer, (x0, base), spans = text_layer(disp, f)
    i = [j for j, ch in enumerate(disp) if ch in ("\ufeee", "\u0648")][0]
    cx, cy, diam = bowl_of_waw(layer, spans[i], base, f.size)
    layer = stick(layer, cx, cy, diam)
    word = layer.crop(layer.getbbox())
    f2 = font("Bold", 150 * S)
    dom = "elgoon.com"
    dw = int(f2.getlength(dom))
    gap = 10 * S
    h = word.height + gap + f2.size
    w = max(word.width, dw)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    im.alpha_composite(word, ((w - word.width) // 2, 0))
    ImageDraw.Draw(im).text((w / 2, word.height + gap), dom, font=f2, fill=INK, anchor="mt")
    return sticker(im)


def mark(size=1024):
    """The board + dart alone, same rim, on a transparent square."""
    diam = 600 * S
    pad = int(0.6 * diam)
    layer = Image.new("RGBA", (diam + 2 * pad, diam + 2 * pad), (0, 0, 0, 0))
    c = layer.width / 2
    stick(layer, c, c, diam)
    return sticker(layer, size, size, border=int(size * 0.05), margin=int(size * 0.01))


def main():
    ap = argparse.ArgumentParser(description="Elgoon sticker logo")
    ap.add_argument("--out", default=os.path.join(HERE, "assets-src", "logo"))
    ap.add_argument("--all", action="store_true", help="also the ELGOON variant")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    save(logo_mix(), os.path.join(a.out, "logo-mix.png"))
    save(logo_ar(), os.path.join(a.out, "logo-ar.png"))
    save(mark(), os.path.join(a.out, "mark.png"))
    if a.all:
        save(logo_en(), os.path.join(a.out, "logo-en.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
