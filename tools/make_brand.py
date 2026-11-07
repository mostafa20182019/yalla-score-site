#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Every brand file the site and the cards use, from the sticker logo
(2026-11-07: the user replaced the tiger with the target-and-dart sticker,
«استخدم اللوجو الجديد فى كل مكان ... احذف النمر من كل الاماكن»):

    "C:\Program Files\Python312\python.exe" tools/make_brand.py

The art comes from tools/make_logo.py (logo_mix / logo_ar / mark); this
script only places it. Written into assets-src/:

  mark-512.png          the brand corner on every Facebook card
  wordmark-1024.png     «الجون» wordmark (logo-ar), 1024 wide, transparent -
                        the reels' brand at the top (2026-11-07: the plain
                        text + the separate dart were replaced by this)
  brand-logo.png        the header: «الجون» wordmark (logo-ar), 138 px high
                        (46 css px at 3x), width to match
  logo.png        600w  publisher logo (NewsArticle / RSS): the wordmark
  favicon.png     192   <link rel=icon>: the mark alone, transparent
  favicon.ico           16/32/48/64 - /favicon.ico for Google's fetcher
  icon-192.png          home-screen + notification icon, "maskable": the
  icon-512.png          mark at 62% on the site blue, inside Android's 80%
  app-icon-1024.png     the same tile at full size
  badge-96.png          status-bar badge: Android draws ONLY the alpha as a
                        white glyph, so the rings are opaque and the whites
                        (and the sticker rim) are holes
  fb-profile-1024.png   the Facebook page photo (uploaded by hand): the
                        «الجون» wordmark on blue, 80% wide - its corners stay
                        inside the circle Facebook crops (user, 2026-11-07:
                        «اعمل profile picture بيها»)
  fb-cover-1640x924.png the Facebook cover: logo-mix in the 1280x624 safe
                        box both the desktop and the phone crops keep
  og-banner.png   1200x630  every page's default og:image

Flat site blue (style.css --green #1f94d3 = fb_cards.BLUE) under everything
that has a tile; nothing else on them - the sticker is the whole design."""
import os
import sys

from PIL import Image, ImageChops

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.stdout.reconfigure(encoding="utf-8")
from fb_cards import BLUE                                         # noqa: E402
import make_logo as L                                             # noqa: E402

OUT = os.path.join(HERE, "assets-src")
SAFE = (180, 150, 1280, 624)       # the cover's safe box: x, y, w, h


def fit(im, w=None, h=None):
    """The sticker trimmed to its rim, scaled to width w (or height h)."""
    im = im.crop(im.getbbox())
    k = w / im.width if w else h / im.height
    return im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)


def tile(size, art, cx=None, cy=None):
    """art centred on a flat blue canvas (RGB)."""
    im = Image.new("RGBA", size, BLUE + (255,))
    cx = size[0] / 2 if cx is None else cx
    cy = size[1] / 2 if cy is None else cy
    im.alpha_composite(art, (int(cx - art.width / 2), int(cy - art.height / 2)))
    return im.convert("RGB")


def square(art, side):
    """art (trimmed) centred on a transparent side x side canvas."""
    im = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    im.alpha_composite(art, ((side - art.width) // 2, (side - art.height) // 2))
    return im


def badge(mark, size):
    """White-on-alpha glyph: everything in the mark that is not white."""
    m = fit(mark, w=size)
    m = square(m, size)
    r, g, b, a = m.split()
    white = ImageChops.darker(ImageChops.darker(r, g), b).point(lambda v: 255 if v >= 235 else 0)
    alpha = ImageChops.subtract(a, white)
    out = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    out.putalpha(alpha)
    return out


def main():
    logo, word, mark = L.logo_mix(), L.logo_ar(), L.mark()
    files = {}
    files["mark-512.png"] = square(fit(mark, w=int(512 * 0.96)), 512)
    files["wordmark-1024.png"] = fit(word, w=1024)
    files["brand-logo.png"] = fit(word, h=138)
    files["logo.png"] = fit(word, w=600)
    files["favicon.png"] = square(fit(mark, w=int(192 * 0.96)), 192)
    for n, side in (("icon-192.png", 192), ("icon-512.png", 512), ("app-icon-1024.png", 1024)):
        files[n] = tile((side, side), fit(mark, w=int(side * 0.62)))
    files["badge-96.png"] = badge(mark, 96)
    files["fb-profile-1024.png"] = tile((1024, 1024), fit(word, w=int(1024 * 0.80)))
    sx, sy, sw, sh = SAFE
    files["fb-cover-1640x924.png"] = tile((1640, 924), fit(logo, w=int(sw * 0.60)), sx + sw / 2, sy + sh / 2)
    files["og-banner.png"] = tile((1200, 630), fit(logo, w=int(1200 * 0.55)))
    for name, im in files.items():
        L.save(im, os.path.join(OUT, name))
    ico = square(fit(mark, w=int(256 * 0.96)), 256)
    p = os.path.join(OUT, "favicon.ico")
    ico.save(p, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print(f"{p}: {os.path.getsize(p) // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
